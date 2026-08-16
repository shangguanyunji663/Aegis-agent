from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import Settings
from app.entities import DeadLetterRecord, ToolJob
from app.models import ToolJobStatus
from app.services.tool_executor import ToolExecutionService
from app.services.tool_governance import ToolGovernanceService
from app.services.tool_records import ToolRecordService
from app.tools.contracts import normalize_tool_kind
from app.core.utils import loads_dict, now_utc


logger = logging.getLogger("aegis.tool_queue")


class RateLimiter:
    def __init__(self, limit_per_minute: int):
        self.limit = max(0, limit_per_minute)
        self.events: deque[float] = deque()
        self.lock = Lock()

    def allow(self, now_ts: float) -> tuple[bool, float]:
        if self.limit <= 0:
            return True, 0.0
        with self.lock:
            while self.events and now_ts - self.events[0] >= 60.0:
                self.events.popleft()
            if len(self.events) < self.limit:
                self.events.append(now_ts)
                return True, 0.0
            return False, max(1.0, 60.0 - (now_ts - self.events[0]))


class ToolQueueService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.executor = ToolExecutionService(settings)

    def run_pending(self, db: Session, limit: int = 20) -> list[str]:
        now = now_utc()
        rows = (
            db.query(ToolJob)
            .filter(ToolJob.status == ToolJobStatus.PENDING.value)
            .filter((ToolJob.run_after == None) | (ToolJob.run_after <= now))  # noqa: E711
            .order_by(ToolJob.created_at.asc(), ToolJob.id.asc())
            .limit(limit)
            .all()
        )
        rows = sorted(rows, key=_job_priority)
        processed = []
        for row in rows:
            processed.append(row.public_id)
            self.run_job(db, row)
        db.commit()
        return processed

    def run_job(self, db: Session, row: ToolJob, email_limiter: RateLimiter | None = None) -> None:
        payload = loads_dict(row.payload_json)
        governance = ToolGovernanceService(db)
        ready, wait_reason = self._dependency_ready(db, row)
        if not ready:
            row.last_error = wait_reason
            row.run_after = now_utc() + timedelta(seconds=max(0.0, self.settings.tool_queue_retry_delay_seconds))
            row.updated_at = now_utc()
            governance.audit(row, "execute", "deferred", wait_reason, payload)
            db.add(row)
            return
        if normalize_tool_kind(row.kind) == "send_email" and email_limiter is not None:
            allowed, retry_after = email_limiter.allow(time.monotonic())
            if not allowed:
                reason = f"email rate limited, retry after {round(retry_after, 2)} seconds"
                row.last_error = reason
                row.run_after = now_utc() + timedelta(seconds=retry_after)
                row.updated_at = now_utc()
                governance.audit(row, "execute", "deferred", reason, payload)
                db.add(row)
                return
        row.status = ToolJobStatus.RUNNING.value
        row.attempts += 1
        row.updated_at = now_utc()
        db.add(row)
        governance.audit(row, "execute", "started", "tool job execution started", payload)
        try:
            governance.require_allowed(row, payload)
            result = self.executor.execute(row.kind, payload, row.attempts)
            self._record_success(db, row, payload, result)
            row.last_error = ""
            row.payload_json = json.dumps(payload | {"result": result}, ensure_ascii=False)
            row.status = ToolJobStatus.SUCCESS.value
            governance.audit(row, "execute", "allowed", "tool job execution succeeded", payload | {"result": result})
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            self._record_failure(db, row, payload, reason)
            row.last_error = reason
            row.status = ToolJobStatus.DEAD.value if row.attempts >= row.max_attempts else ToolJobStatus.PENDING.value
            if row.status == ToolJobStatus.PENDING.value:
                row.run_after = now_utc() + timedelta(seconds=self.settings.tool_queue_retry_delay_seconds * max(1, row.attempts))
            decision = "rejected" if row.status == ToolJobStatus.DEAD.value else "deferred"
            governance.audit(row, "execute", decision, reason, payload)
            if row.status == ToolJobStatus.DEAD.value:
                self._record_dead_letter(db, row, reason, payload)
        row.updated_at = now_utc()
        db.add(row)

    def _dependency_ready(self, db: Session, row: ToolJob) -> tuple[bool, str]:
        kind = normalize_tool_kind(row.kind)
        if kind != "send_email":
            return True, ""
        payload = loads_dict(row.payload_json)
        if payload.get("risk_level") != "high" or not (row.report_public_id or row.case_public_id):
            return True, ""
        blockers = []
        for dependency_kind in ["write_ledger", "create_alert"]:
            dependency = (
                db.query(ToolJob)
                .filter(ToolJob.report_public_id == row.report_public_id)
                .filter(ToolJob.case_public_id == row.case_public_id)
                .filter(ToolJob.kind == dependency_kind)
                .first()
            )
            if dependency is None or dependency.status != ToolJobStatus.SUCCESS.value:
                blockers.append(dependency_kind)
        if blockers:
            return False, f"waiting for dependencies: {', '.join(blockers)}"
        return True, ""

    def _record_dead_letter(self, db: Session, row: ToolJob, reason: str, payload: dict) -> None:
        existing = db.query(DeadLetterRecord).filter(DeadLetterRecord.job_public_id == row.public_id).first()
        if existing is not None:
            return
        db.add(
            DeadLetterRecord(
                public_id=f"dead-{uuid4().hex[:10]}",
                job_public_id=row.public_id,
                tool_kind=normalize_tool_kind(row.kind),
                reason=reason,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )

    def _record_success(self, db: Session, row: ToolJob, payload: dict, result: dict) -> None:
        records = ToolRecordService(db)
        kind = normalize_tool_kind(row.kind)
        if kind == "write_ledger":
            records.record_excel(payload, result, status="success")
        elif kind == "create_alert":
            records.record_alert(payload, result, status="success", channel="alert")
        elif kind == "send_email":
            records.record_alert(payload, result, status="success", channel="email")

    def _record_failure(self, db: Session, row: ToolJob, payload: dict, reason: str) -> None:
        kind = normalize_tool_kind(row.kind)
        if kind not in {"create_alert", "send_email", "write_ledger"}:
            return
        records = ToolRecordService(db)
        result = {"message": reason, "delivered_to": kind}
        if kind == "write_ledger":
            records.record_excel(payload, result, status="failed", message=reason)
        else:
            channel = "email" if kind == "send_email" else "alert"
            records.record_alert(payload, result, status="failed", channel=channel, message=reason)


class ToolQueueWorker:
    def __init__(self, settings: Settings, db_factory):
        self.settings = settings
        self.db_factory = db_factory
        self.service = ToolQueueService(settings)
        self.email_limiter = RateLimiter(settings.alert_email_rate_limit_per_minute)
        self.stop_event = threading.Event()
        self.dispatcher: threading.Thread | None = None
        self.executor: ThreadPoolExecutor | None = None
        self.dispatch_lock = threading.Lock()

    def start(self) -> None:
        if not self.settings.tool_queue_enabled or self.dispatcher is not None:
            return
        self._recover_running_jobs()
        self.executor = ThreadPoolExecutor(
            max_workers=max(1, self.settings.tool_queue_worker_threads),
            thread_name_prefix="aegis-tool-worker",
        )
        self.dispatcher = threading.Thread(target=self._loop, name="aegis-tool-dispatcher", daemon=True)
        self.dispatcher.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.dispatcher is not None:
            self.dispatcher.join(timeout=5)
            self.dispatcher = None
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.executor = None

    def run_once(self) -> list[str]:
        if self.executor is None:
            with self.db_factory() as db:
                return self.service.run_pending(db, self.settings.tool_queue_batch_size)
        job_ids = self._claim_pending_jobs()
        for job_id in job_ids:
            self.executor.submit(self._run_claimed_job, job_id)
        return job_ids

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("tool queue dispatch failed")
            self.stop_event.wait(self.settings.tool_queue_poll_interval_seconds)

    def _claim_pending_jobs(self) -> list[str]:
        with self.dispatch_lock:
            with self.db_factory() as db:
                now = now_utc()
                rows = (
                    db.query(ToolJob)
                    .filter(ToolJob.status == ToolJobStatus.PENDING.value)
                    .filter((ToolJob.run_after == None) | (ToolJob.run_after <= now))  # noqa: E711
                    .order_by(ToolJob.created_at.asc(), ToolJob.id.asc())
                    .limit(self.settings.tool_queue_batch_size)
                    .all()
                )
                rows = sorted(rows, key=_job_priority)
                job_ids = []
                for row in rows:
                    row.status = ToolJobStatus.RUNNING.value
                    row.updated_at = now_utc()
                    db.add(row)
                    job_ids.append(row.public_id)
                db.commit()
                return job_ids

    def _run_claimed_job(self, job_id: str) -> None:
        with self.db_factory() as db:
            row = db.query(ToolJob).filter(ToolJob.public_id == job_id).first()
            if row is None:
                return
            row.status = ToolJobStatus.PENDING.value
            db.add(row)
            db.flush()
            self.service.run_job(db, row, email_limiter=self.email_limiter)
            db.commit()

    def _recover_running_jobs(self) -> None:
        with self.db_factory() as db:
            rows = db.query(ToolJob).filter(ToolJob.status == ToolJobStatus.RUNNING.value).all()
            for row in rows:
                row.status = ToolJobStatus.PENDING.value
                row.last_error = "service restarted before job completed"
                row.run_after = now_utc()
                row.updated_at = now_utc()
                db.add(row)
            db.commit()


def _job_priority(row: ToolJob) -> tuple[int, datetime, int]:
    priorities = {
        "write_ledger": 10,
        "create_alert": 20,
        "create_handoff_summary": 30,
        "follow_up_suggestion": 40,
        "lookup_resource": 50,
        "send_email": 90,
    }
    return (priorities.get(normalize_tool_kind(row.kind), 80), row.created_at, row.id)
