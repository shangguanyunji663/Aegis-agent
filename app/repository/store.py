"""持久化仓储:DatabaseStore 封装全部 SQLAlchemy 读写与 Redis 缓存。

会话/消息/认证/审计/记忆/知识库/工具任务/模型档案/追踪等表操作集中于此;
检索算法在 app.rag 中实现,报告与工单的服务逻辑在 app.services 中实现。
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth import expires_after, make_password_hash, new_session_token, random_id, utcnow, verify_password
from app.core.privacy import redacted_payload
from app.core.utils import loads_or, now_utc_naive
from app.entities import (
    AdminAuditLog,
    AgentModelProfile,
    AgentPrivateMemory,
    AgentRunTrace,
    AuthSession,
    AuthUser,
    ChatMessage,
    ChatSession,
    DeadLetterRecord,
    KnowledgeChunk,
    PsychologicalReport,
    SessionMemory,
    ToolAuditRecord,
    ToolJob,
)
from app.models import AgentTrace, CaseStatus, PendingReport, ReportStatus, SkillResult, ToolJobStatus, UserRole
from app.rag.chunking import chunk_text, knowledge_metadata_summary, metadata_matches, parse_knowledge_document, rewrite_query
from app.rag.memory import build_memory_summary
from collections import OrderedDict
from datetime import datetime, timedelta

from app.rag.scoring import bm25_scores, expand_best_hit, fused_score, normalize_scores, rerank_score, rrf_fused_score
from app.rag.vector_store import (
    FALLBACK_RETRIEVAL_LABEL,
    PRIMARY_RETRIEVAL_LABEL,
    VectorStoreUnavailable,
    build_vector_backend,
    embed_text,
)
from app.services.report_case import ReportCaseService
from app.services.tool_queue import ToolQueueService
from app.services.tool_records import ToolRecordService
from app.tools.contracts import governed_payload, normalize_tool_kind


class DatabaseStore:
    def __init__(self, db_factory, settings=None):
        self.db_factory = db_factory
        self.settings = settings or get_settings()
        self.vector_backend = build_vector_backend(self.settings)
        self.vector_error = getattr(self.vector_backend, "last_error", "")
        self.redis_client = None
        self._redis_available = False
        # 查询缓存:LRU (key -> (expires_at, results))
        self._knowledge_cache: OrderedDict[str, tuple[datetime, list[dict]]] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0
        self.redis_client = None
        self._redis_available = False
        if self.settings.redis_url.strip():
            try:
                import redis

                self.redis_client = redis.Redis.from_url(self.settings.redis_url, decode_responses=True)
                self.redis_client.ping()
                self._redis_available = True
            except Exception:
                self.redis_client = None
                self._redis_available = False

    def memory_backend_status(self) -> dict:
        return {
            "primary": "redis+sqlite" if self._redis_available else "sqlite",
            "redis": "up" if self._redis_available else ("configured_but_unavailable" if self.settings.redis_url.strip() else "disabled"),
            "durable": "sqlite",
        }

    def ensure_session(self, session_public_id: str | None, title: str = "新对话", owner_user_public_id: str | None = None) -> str:
        with self.db_factory() as db:
            if session_public_id:
                existing = self._get_session(db, session_public_id)
                if existing is not None:
                    if owner_user_public_id and not existing.owner_user_public_id:
                        existing.owner_user_public_id = owner_user_public_id
                        existing.touch()
                        db.add(existing)
                        db.commit()
                    return existing.public_id
            public_id = session_public_id or uuid4().hex[:12]
            session = ChatSession(public_id=public_id, owner_user_public_id=owner_user_public_id or "", title=_title(title))
            db.add(session)
            db.commit()
            return public_id

    def list_sessions(self, owner_user_public_id: str | None = None) -> list[dict]:
        with self.db_factory() as db:
            query = db.query(ChatSession)
            if owner_user_public_id is not None:
                query = query.filter(ChatSession.owner_user_public_id == owner_user_public_id)
            rows = query.order_by(ChatSession.updated_at.desc()).limit(100).all()
            return [
                {
                    "id": row.public_id,
                    "owner_user_id": row.owner_user_public_id,
                    "title": row.title,
                    "created_at": row.created_at.isoformat(),
                    "updated_at": row.updated_at.isoformat(),
                }
                for row in rows
            ]

    def get_session(self, public_id: str) -> dict | None:
        with self.db_factory() as db:
            session = self._get_session(db, public_id)
            if session is None:
                return None
            messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
                .all()
            )
            return {
                "id": session.public_id,
                "owner_user_id": session.owner_user_public_id,
                "title": session.title,
                "memory_summary": self._memory_dict(db, session.public_id)["summary"],
                "messages": [
                    {
                        "role": message.role,
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                    }
                    for message in messages
                ],
            }

    def delete_session(self, public_id: str) -> bool:
        with self.db_factory() as db:
            session = self._get_session(db, public_id)
            if session is None:
                return False
            db.delete(session)
            db.commit()
            return True

    def rename_session(self, public_id: str, title: str) -> bool:
        with self.db_factory() as db:
            session = self._get_session(db, public_id)
            if session is None:
                return False
            session.title = _title(title)
            session.touch()
            db.add(session)
            db.commit()
            return True

    def append_message(self, session_id: str, role: str, content: str) -> None:
        with self.db_factory() as db:
            session = self._get_session(db, session_id)
            if session is None:
                session = ChatSession(public_id=session_id, title=_title(content))
                db.add(session)
                db.flush()
            if role.lower() == "user" and session.title == "新对话":
                session.title = _title(content)
            session.touch()
            db.add(ChatMessage(session_id=session.id, role=role.upper(), content=content))
            db.add(session)
            db.commit()

    def ensure_default_users(self) -> None:
        defaults = [
            (self.settings.auth_default_admin_username.strip(), self.settings.auth_default_admin_password, UserRole.ADMIN.value),
            (self.settings.auth_default_student_username.strip(), self.settings.auth_default_student_password, UserRole.STUDENT.value),
        ]
        with self.db_factory() as db:
            for username, password, role in defaults:
                if not username or not password:
                    continue
                existing = db.query(AuthUser).filter(AuthUser.username == username).first()
                if existing is not None:
                    continue
                salt, password_hash = make_password_hash(password)
                db.add(
                    AuthUser(
                        public_id=random_id("usr"),
                        username=username,
                        password_salt=salt,
                        password_hash=password_hash,
                        role=role,
                        is_active="true",
                    )
                )
            db.commit()

    def authenticate_user(self, username: str, password: str) -> dict | None:
        with self.db_factory() as db:
            row = db.query(AuthUser).filter(AuthUser.username == username).first()
            if row is None or row.is_active != "true":
                return None
            if not verify_password(password, row.password_salt, row.password_hash):
                return None
            auth_session = AuthSession(
                public_id=random_id("auth"),
                user_public_id=row.public_id,
                session_token=new_session_token(),
                expires_at=expires_after(self.settings.auth_session_ttl_hours),
                updated_at=utcnow(),
            )
            db.add(auth_session)
            db.commit()
            return self._auth_session_dict(row, auth_session)

    def create_user(self, username: str, password: str, role: str) -> dict:
        with self.db_factory() as db:
            existing = db.query(AuthUser).filter(AuthUser.username == username).first()
            if existing is not None:
                return {"id": existing.public_id, "username": existing.username, "role": existing.role}
            salt, password_hash = make_password_hash(password)
            row = AuthUser(
                public_id=random_id("usr"),
                username=username,
                password_salt=salt,
                password_hash=password_hash,
                role=role,
                is_active="true",
            )
            db.add(row)
            db.commit()
            return {"id": row.public_id, "username": row.username, "role": row.role}

    def register_user(self, username: str, password: str, role: str) -> dict:
        """注册新账号:用户名已存在时抛 ValueError(与 create_user 的静默语义区分)。"""
        with self.db_factory() as db:
            existing = db.query(AuthUser).filter(AuthUser.username == username).first()
            if existing is not None:
                raise ValueError("username already exists")
            salt, password_hash = make_password_hash(password)
            row = AuthUser(
                public_id=random_id("usr"),
                username=username,
                password_salt=salt,
                password_hash=password_hash,
                role=role,
                is_active="true",
            )
            db.add(row)
            db.commit()
            return {"id": row.public_id, "username": row.username, "role": row.role}

    def get_auth_session(self, token: str) -> dict | None:
        with self.db_factory() as db:
            session = db.query(AuthSession).filter(AuthSession.session_token == token).first()
            if session is None or session.expires_at <= utcnow():
                if session is not None:
                    db.delete(session)
                    db.commit()
                return None
            user = db.query(AuthUser).filter(AuthUser.public_id == session.user_public_id).first()
            if user is None or user.is_active != "true":
                return None
            session.updated_at = utcnow()
            db.add(session)
            db.commit()
            return self._auth_session_dict(user, session)

    def revoke_auth_session(self, token: str) -> bool:
        with self.db_factory() as db:
            session = db.query(AuthSession).filter(AuthSession.session_token == token).first()
            if session is None:
                return False
            db.delete(session)
            db.commit()
            return True

    def add_audit_log(
        self,
        actor_user_public_id: str,
        actor_username: str,
        actor_role: str,
        action: str,
        target_type: str,
        target_public_id: str,
        payload: dict | None = None,
    ) -> dict:
        with self.db_factory() as db:
            row = AdminAuditLog(
                public_id=random_id("audit"),
                actor_user_public_id=actor_user_public_id,
                actor_username=actor_username,
                actor_role=actor_role,
                action=action,
                target_type=target_type,
                target_public_id=target_public_id,
                payload_json=json.dumps(redacted_payload(payload or {}), ensure_ascii=False),
            )
            db.add(row)
            db.commit()
            return self._audit_log_dict(row)

    def list_audit_logs(self) -> list[dict]:
        with self.db_factory() as db:
            rows = db.query(AdminAuditLog).order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()).limit(200).all()
            return [self._audit_log_dict(row) for row in rows]

    def get_memory(self, public_id: str) -> dict:
        cached = self._redis_get_session_memory(public_id)
        if cached is not None:
            return cached
        with self.db_factory() as db:
            return self._memory_dict(db, public_id)

    def update_memory(self, public_id: str, user_message: str, assistant_answer: str) -> dict:
        with self.db_factory() as db:
            session = self._get_session(db, public_id)
            if session is None:
                return {"summary": "", "covered_message_count": 0, "updated": False}
            message_count = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count()
            memory = db.query(SessionMemory).filter(SessionMemory.session_public_id == public_id).first()
            if memory is None:
                memory = SessionMemory(session_public_id=public_id, summary="")
            memory.summary = build_memory_summary(memory.summary, user_message, assistant_answer, self.settings.memory_summary_max_chars)
            memory.covered_message_count = message_count
            memory.updated_at = now_utc_naive()
            db.add(memory)
            db.commit()
            db.refresh(memory)
            result = self._memory_row_dict(memory) | {"updated": True}
            self._redis_set_session_memory(public_id, result)
            return result

    def add_report(self, report: PendingReport) -> None:
        with self.db_factory() as db:
            row = PsychologicalReport(
                public_id=report.id,
                session_public_id=report.session_id,
                message=report.message,
                intent=report.intent.value,
                emotion=report.emotion,
                emotion_score=report.emotion_score,
                risk_level=report.risk_level.value,
                confidence=report.confidence,
                rationale_json=json.dumps(report.rationale, ensure_ascii=False),
                summary=report.summary or "；".join(report.rationale),
                status=report.status.value,
            )
            db.add(row)
            db.commit()

    def list_reports(self) -> list[dict]:
        with self.db_factory() as db:
            return ReportCaseService(db).list_reports()

    def update_report(self, report_id: str, status: ReportStatus) -> dict | None:
        with self.db_factory() as db:
            return ReportCaseService(db).update_report(report_id, status)

    def ensure_case_for_report(self, report_id: str) -> dict | None:
        with self.db_factory() as db:
            return ReportCaseService(db).ensure_case_for_report(report_id)

    def list_cases(self) -> list[dict]:
        with self.db_factory() as db:
            return ReportCaseService(db).list_cases()

    def add_case_note(self, case_id: str, note: str, actor: str = "admin") -> dict | None:
        with self.db_factory() as db:
            return ReportCaseService(db).add_case_note(case_id, note, actor)

    def update_case_status(self, case_id: str, status: CaseStatus) -> dict | None:
        with self.db_factory() as db:
            return ReportCaseService(db).update_case_status(case_id, status)

    def acknowledge_case(self, case_id: str, actor: str, note: str = "") -> dict | None:
        with self.db_factory() as db:
            return ReportCaseService(db).acknowledge_case(case_id, actor, note)

    def list_tool_jobs(self) -> list[dict]:
        with self.db_factory() as db:
            rows = db.query(ToolJob).order_by(ToolJob.updated_at.desc(), ToolJob.id.desc()).limit(100).all()
            return [self._tool_job_dict(row) for row in rows]

    def list_dead_letters(self) -> list[dict]:
        with self.db_factory() as db:
            jobs = (
                db.query(ToolJob)
                .filter(ToolJob.status == ToolJobStatus.DEAD.value)
                .order_by(ToolJob.updated_at.desc(), ToolJob.id.desc())
                .limit(100)
                .all()
            )
            records = (
                db.query(DeadLetterRecord)
                .order_by(DeadLetterRecord.created_at.desc(), DeadLetterRecord.id.desc())
                .limit(100)
                .all()
            )
            by_job = {record.job_public_id: self._dead_letter_record_dict(record) for record in records}
            return [self._tool_job_dict(row) | {"dead_letter": by_job.get(row.public_id)} for row in jobs]

    def run_pending_tool_jobs(self) -> dict:
        with self.db_factory() as db:
            processed = ToolQueueService(self.settings).run_pending(db, limit=20)
            refreshed = db.query(ToolJob).order_by(ToolJob.updated_at.desc(), ToolJob.id.desc()).limit(100).all()
            return {"processed": processed, "jobs": [self._tool_job_dict(row) for row in refreshed]}

    def retry_tool_job(self, job_id: str) -> dict | None:
        with self.db_factory() as db:
            row = db.query(ToolJob).filter(ToolJob.public_id == job_id).first()
            if row is None:
                return None
            row.status = ToolJobStatus.PENDING.value
            row.last_error = ""
            row.updated_at = now_utc_naive()
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._tool_job_dict(row)

    def create_tool_job(
        self,
        kind: str,
        payload: dict,
        report_public_id: str = "",
        case_public_id: str = "",
        max_attempts: int = 3,
        role: str = UserRole.ADMIN.value,
        approved: bool = True,
    ) -> dict:
        canonical_kind = normalize_tool_kind(kind)
        report_public_id = report_public_id or str(payload.get("report_id") or "")
        case_public_id = case_public_id or str(payload.get("case_id") or "")
        with self.db_factory() as db:
            try:
                governed = governed_payload(canonical_kind, payload, role=role, approved=approved)
            except Exception as exc:
                self._add_tool_audit_record(
                    db,
                    canonical_kind,
                    "queue",
                    "rejected",
                    str(exc),
                    payload,
                    actor_role=role,
                    report_public_id=report_public_id,
                    case_public_id=case_public_id,
                )
                db.commit()
                raise
            row = ToolJob(
                public_id=f"job-{uuid4().hex[:8]}",
                kind=canonical_kind,
                status=ToolJobStatus.PENDING.value,
                report_public_id=report_public_id,
                case_public_id=case_public_id,
                payload_json=json.dumps(governed, ensure_ascii=False),
                max_attempts=max_attempts,
            )
            db.add(row)
            self._add_tool_audit_record(
                db,
                canonical_kind,
                "queue",
                "allowed",
                "tool job queued",
                governed,
                actor_role=role,
                report_public_id=report_public_id,
                case_public_id=case_public_id,
                job_public_id=row.public_id,
            )
            db.commit()
            db.refresh(row)
            return self._tool_job_dict(row)

    def append_agent_private_memory(self, agent_name: str, session_id: str, content: str, metadata: dict | None = None) -> dict:
        with self.db_factory() as db:
            row = AgentPrivateMemory(
                agent_name=agent_name,
                session_public_id=session_id,
                content=content,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            result = self._agent_private_memory_dict(row)
            self._redis_append_agent_memory(agent_name, session_id, result)
            return result

    def load_agent_private_memory(self, agent_name: str, session_id: str, limit: int = 8) -> list[dict]:
        cached = self._redis_load_agent_memory(agent_name, session_id, limit)
        if cached:
            return cached
        with self.db_factory() as db:
            rows = (
                db.query(AgentPrivateMemory)
                .filter(AgentPrivateMemory.agent_name == agent_name, AgentPrivateMemory.session_public_id == session_id)
                .order_by(AgentPrivateMemory.created_at.desc(), AgentPrivateMemory.id.desc())
                .limit(max(1, limit))
                .all()
            )
            return [self._agent_private_memory_dict(row) for row in reversed(rows)]

    def _redis_get_session_memory(self, public_id: str) -> dict | None:
        if self.redis_client is None:
            return None
        raw = self.redis_client.get(f"aegis:session-memory:{public_id}")
        return loads_or(raw, None) if raw else None

    def _redis_set_session_memory(self, public_id: str, memory: dict) -> None:
        if self.redis_client is None:
            return
        self.redis_client.set(f"aegis:session-memory:{public_id}", json.dumps(memory, ensure_ascii=False), ex=60 * 60 * 24)

    def _redis_append_agent_memory(self, agent_name: str, session_id: str, item: dict) -> None:
        if self.redis_client is None:
            return
        key = f"aegis:agent-memory:{agent_name}:{session_id}"
        self.redis_client.rpush(key, json.dumps(item, ensure_ascii=False))
        self.redis_client.ltrim(key, -50, -1)
        self.redis_client.expire(key, 60 * 60 * 24)

    def _redis_load_agent_memory(self, agent_name: str, session_id: str, limit: int) -> list[dict]:
        if self.redis_client is None:
            return []
        key = f"aegis:agent-memory:{agent_name}:{session_id}"
        rows = self.redis_client.lrange(key, -max(1, limit), -1)
        return [loads_or(row, {}) for row in rows if row]

    def ensure_agent_model_profiles(self, profiles: list[dict]) -> None:
        with self.db_factory() as db:
            for profile in profiles:
                agent_name = profile["agent_name"]
                existing = db.query(AgentModelProfile).filter(AgentModelProfile.agent_name == agent_name).first()
                if existing is not None:
                    continue
                db.add(
                    AgentModelProfile(
                        agent_name=agent_name,
                        provider=profile.get("provider", "inherit"),
                        model=profile.get("model", ""),
                        temperature=float(profile.get("temperature", 0.2)),
                        system_prompt=profile.get("system_prompt", ""),
                        enabled="true",
                    )
                )
            db.commit()

    def get_agent_model_profile(self, agent_name: str) -> dict:
        with self.db_factory() as db:
            row = db.query(AgentModelProfile).filter(AgentModelProfile.agent_name == agent_name).first()
            if row is None:
                return {
                    "agent_name": agent_name,
                    "provider": "inherit",
                    "model": "",
                    "temperature": 0.2,
                    "system_prompt": "",
                    "enabled": True,
                }
            return self._agent_model_profile_dict(row)

    def list_agent_model_profiles(self) -> list[dict]:
        with self.db_factory() as db:
            rows = db.query(AgentModelProfile).order_by(AgentModelProfile.agent_name.asc()).all()
            return [self._agent_model_profile_dict(row) for row in rows]

    def list_tool_audits(self) -> list[dict]:
        with self.db_factory() as db:
            rows = db.query(ToolAuditRecord).order_by(ToolAuditRecord.created_at.desc(), ToolAuditRecord.id.desc()).limit(200).all()
            return [self._tool_audit_record_dict(row) for row in rows]

    def list_excel_records(self) -> list[dict]:
        with self.db_factory() as db:
            return ToolRecordService(db).list_excel_records()

    def list_alert_records(self) -> list[dict]:
        with self.db_factory() as db:
            return ToolRecordService(db).list_alert_records()

    def seed_knowledge_dir(self, knowledge_dir: Path) -> int:
        total = 0
        for path in sorted([*knowledge_dir.glob("*.md"), *knowledge_dir.glob("*.txt")]):
            total += self.ingest_knowledge(path.name, path.read_text(encoding="utf-8"))
        return total

    def rebuild_knowledge_dir(self, knowledge_dir: Path) -> dict:
        with self.db_factory() as db:
            db.query(KnowledgeChunk).delete()
            db.commit()
        self.vector_backend.reset()
        chunks = self.seed_knowledge_dir(knowledge_dir)
        return {"chunks": chunks, "status": self.knowledge_status()}

    def ingest_knowledge(self, source: str, content: str) -> int:
        metadata, body = parse_knowledge_document(source, content)
        chunks = chunk_text(body, size=self.settings.knowledge_chunk_size, overlap=self.settings.knowledge_chunk_overlap)
        metadata_json = json.dumps(metadata, ensure_ascii=False)
        with self.db_factory() as db:
            existing = [
                (row.content, row.metadata_json)
                for row in db.query(KnowledgeChunk)
                .filter(KnowledgeChunk.source == source)
                .order_by(KnowledgeChunk.source_index.asc())
                .all()
            ]
            if existing == [(chunk, metadata_json) for chunk in chunks]:
                return len(existing)
            embeddings = self._safe_embeddings(chunks)
            db.query(KnowledgeChunk).filter(KnowledgeChunk.source == source).delete()
            for index, chunk in enumerate(chunks):
                db.add(
                    KnowledgeChunk(
                        source=source,
                        source_index=index,
                        content=chunk,
                        metadata_json=metadata_json,
                        embedding_json=json.dumps(embeddings[index], ensure_ascii=False),
                    )
                )
            db.commit()
            rows = (
                db.query(KnowledgeChunk)
                .filter(KnowledgeChunk.source == source)
                .order_by(KnowledgeChunk.source_index.asc())
                .all()
            )
            self._upsert_vector(source, [row.content for row in rows], [int(row.id) for row in rows if row.id is not None])
            return len(chunks)

    def backup_knowledge_dir(self, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"knowledge-backup-{now_utc_naive().strftime('%Y%m%d%H%M%S')}.json"
        with self.db_factory() as db:
            rows = db.query(KnowledgeChunk).order_by(KnowledgeChunk.source.asc(), KnowledgeChunk.source_index.asc()).all()
            payload = [
                {"source": row.source, "source_index": row.source_index, "content": row.content, "metadata": loads_or(row.metadata_json, {})}
                for row in rows
            ]
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"backup_path": str(target), "records": len(payload)}

    def knowledge_status(self) -> dict:
        with self.db_factory() as db:
            rows = db.query(KnowledgeChunk).all()
            sources = sorted({row.source for row in rows})
            return {
                "retrieval_order": "vector -> bm25 -> local rerank -> expand-best",
                "primary_retrieval": PRIMARY_RETRIEVAL_LABEL,
                "fallback_retrieval": FALLBACK_RETRIEVAL_LABEL,
                "database_chunks": len(rows),
                "sources": sources,
                "metadata": knowledge_metadata_summary(rows),
                "retrieval": PRIMARY_RETRIEVAL_LABEL if self.vector_backend.enabled() else FALLBACK_RETRIEVAL_LABEL,
                "vector_enabled": self.settings.vector_enabled,
                "vector_available": self.vector_backend.available(),
                "vector_required": self.settings.vector_required,
                "vector_backend": self.vector_backend.backend_name,
                "embedding_model": getattr(self.vector_backend, "embedding_model", "none"),
                "vector_chunks": self.vector_backend.count(),
                "chroma_persist_dir": self.settings.chroma_dir,
                "chroma_collection_name": self.settings.chroma_collection_name,
                "chroma_snapshot_dir": self.settings.chroma_snapshot_dir,
                "candidate_k": self.settings.knowledge_candidate_k,
                "top_k": self.settings.knowledge_top_k,
                "hybrid_vector_weight": self.settings.knowledge_hybrid_vector_weight,
                "hybrid_bm25_weight": self.settings.knowledge_hybrid_bm25_weight,
                "rerank_enabled": self.settings.knowledge_rerank_enabled,
                "fusion_mode": self.settings.knowledge_fusion_mode,
                "cache_enabled": self.settings.knowledge_cache_enabled,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_rate": round(self._cache_hits / max(1, self._cache_hits + self._cache_misses), 4),
                "vector_error": self.vector_error or getattr(self.vector_backend, "last_error", ""),
            }

    def search_knowledge(
        self,
        query: str,
        top_k: int = 3,
        topic: str | None = None,
        risk_level: str | None = None,
        audience: str | None = None,
    ) -> list[dict]:
        rewritten_query = rewrite_query(query)
        cache_key = f"{rewritten_query}|{top_k}|{topic}|{risk_level}|{audience}"

        # 查询缓存命中
        if self.settings.knowledge_cache_enabled:
            cached = self._check_cache(cache_key)
            if cached is not None:
                return cached

        vector_results: list[dict] = []
        if self.vector_backend.enabled():
            try:
                candidate_k = max(1, min(self.settings.knowledge_candidate_k, self.settings.vector_top_k or self.settings.knowledge_candidate_k))
                vector_results = self.vector_backend.search(rewritten_query, candidate_k)
            except Exception as exc:
                self.vector_error = str(exc)
                if self.settings.vector_required:
                    raise
                vector_results = []
        with self.db_factory() as db:
            chunks = [
                chunk
                for chunk in db.query(KnowledgeChunk).all()
                if metadata_matches(loads_or(chunk.metadata_json, {}), topic=topic, risk_level=risk_level, audience=audience)
            ]
            if not chunks:
                return []
            scores = bm25_scores(rewritten_query, chunks)
            ranked = []
            vector_by_db_id = {
                int(item["db_id"]): float(item["score"])
                for item in vector_results
                if item.get("db_id") is not None
            }
            vector_by_source_key = {
                f"{item.get('source')}:{item.get('source_index')}": float(item["score"])
                for item in vector_results
                if item.get("source") is not None and item.get("source_index") is not None
            }

            fusion_mode = self.settings.knowledge_fusion_mode
            vector_ranked = sorted(vector_results, key=lambda x: -float(x.get("score", 0) or 0))
            bm25_ranked = sorted(scores.items(), key=lambda x: -x[1])
            bm25_rank_map = {chunk_id: idx + 1 for idx, (chunk_id, _) in enumerate(bm25_ranked)}
            vector_rank_map = {}
            for idx, item in enumerate(vector_ranked):
                db_id = item.get("db_id")
                if db_id is not None:
                    vector_rank_map[int(db_id)] = idx + 1

            normalized_bm25 = normalize_scores(
                {int(chunk.id): scores.get(chunk.id, 0.0) for chunk in chunks if chunk.id is not None}
            )
            normalized_vector = normalize_scores(
                {
                    int(chunk.id): vector_by_db_id.get(int(chunk.id), vector_by_source_key.get(f"{chunk.source}:{chunk.source_index}", 0.0))
                    for chunk in chunks
                    if chunk.id is not None
                }
            )

            for chunk in chunks:
                if chunk.id is None:
                    continue
                chunk_id = int(chunk.id)
                if fusion_mode == "rrf":
                    v_rank = vector_rank_map.get(chunk_id)
                    b_rank = bm25_rank_map.get(chunk_id)
                    if v_rank is None and b_rank is None:
                        continue
                    score = rrf_fused_score(v_rank, b_rank)
                else:
                    base_bm25 = normalized_bm25.get(chunk_id, 0.0)
                    base_vector = normalized_vector.get(chunk_id, 0.0)
                    if base_bm25 <= 0 and base_vector <= 0:
                        continue
                    score = fused_score(
                        base_vector,
                        base_bm25,
                        self.settings.knowledge_hybrid_vector_weight,
                        self.settings.knowledge_hybrid_bm25_weight,
                    )
                if fusion_mode != "rrf" and self.settings.knowledge_rerank_enabled:
                    score = rerank_score(rewritten_query, chunk.content, score)
                ranked.append((chunk, score))
            ranked.sort(key=lambda item: item[1], reverse=True)
            ranked = expand_best_hit(ranked, chunks)
            results = []
            for chunk, score in ranked[: max(1, min(top_k, self.settings.knowledge_top_k))]:
                results.append(
                    {
                        "chunk_id": f"knowledge-chunk-{chunk.id}" if chunk.id is not None else f"{chunk.source}:{chunk.source_index}",
                        "source": chunk.source,
                        "source_index": chunk.source_index,
                        "content": chunk.content,
                        "snippet": chunk.content[:320],
                        "metadata": loads_or(chunk.metadata_json, {}),
                        "score": f"{score:.4f}",
                    }
                )
            if self.settings.knowledge_cache_enabled:
                self._set_cache(cache_key, results)
            return results

    def _check_cache(self, key: str) -> list[dict] | None:
        if not self.settings.knowledge_cache_enabled:
            return None
        now = datetime.now()
        if key in self._knowledge_cache:
            expires_at, cached = self._knowledge_cache[key]
            if now < expires_at:
                self._knowledge_cache.move_to_end(key)
                self._cache_hits += 1
                return cached
            else:
                del self._knowledge_cache[key]
        self._cache_misses += 1
        return None

    def _set_cache(self, key: str, results: list[dict]) -> None:
        max_entries = max(1, self.settings.knowledge_cache_max_entries)
        ttl = max(1, self.settings.knowledge_cache_ttl_seconds)
        expires_at = datetime.now() + timedelta(seconds=ttl)
        self._knowledge_cache[key] = (expires_at, results)
        while len(self._knowledge_cache) > max_entries:
            self._knowledge_cache.popitem(last=False)
        if self.redis_client and self._redis_available:
            import json
            self.redis_client.setex(f"aegis:knowledge-cache:{key}", ttl, json.dumps(results, ensure_ascii=False))

    def rebuild_vector_index(self) -> dict:
        with self.db_factory() as db:
            rows = db.query(KnowledgeChunk).order_by(KnowledgeChunk.source.asc(), KnowledgeChunk.source_index.asc()).all()
            grouped: dict[str, list[tuple[int, str]]] = {}
            for row in rows:
                if row.id is None:
                    continue
                grouped.setdefault(row.source, []).append((int(row.id), row.content))
        self.vector_backend.reset()
        indexed = 0
        for source, items in grouped.items():
            chunk_ids = [item[0] for item in items]
            contents = [item[1] for item in items]
            self._upsert_vector(source, contents, chunk_ids)
            indexed += len(contents)
        snapshot = self.vector_backend.snapshot()
        self.vector_error = getattr(self.vector_backend, "last_error", "")
        return {"indexed_chunks": indexed, "snapshot": snapshot}

    def _safe_embeddings(self, chunks: list[str]) -> list[list[float]]:
        if not chunks:
            return []
        try:
            if self.vector_backend.enabled():
                return self.vector_backend.embed_texts(chunks)
        except Exception as exc:
            self.vector_error = str(exc)
            if self.settings.vector_required:
                raise VectorStoreUnavailable(str(exc)) from exc
        return [embed_text(chunk) for chunk in chunks]

    def _upsert_vector(self, source: str, chunks: list[str], chunk_ids: list[int]) -> None:
        try:
            self.vector_backend.upsert(source, chunks, chunk_ids=chunk_ids)
            self.vector_error = getattr(self.vector_backend, "last_error", "")
        except Exception as exc:
            self.vector_error = str(exc)
            if self.settings.vector_required:
                raise

    def _memory_dict(self, db: Session, public_id: str) -> dict:
        memory = db.query(SessionMemory).filter(SessionMemory.session_public_id == public_id).first()
        if memory is None:
            return {"summary": "", "covered_message_count": 0, "updated_at": None}
        return self._memory_row_dict(memory)

    def add_trace(
        self,
        session_id: str,
        message_id: str,
        intent: str,
        risk_level: str,
        trace: list[AgentTrace],
        skills: list[SkillResult],
        answer: str,
    ) -> None:
        with self.db_factory() as db:
            db.add(
                AgentRunTrace(
                    session_public_id=session_id,
                    message_id=message_id,
                    intent=intent,
                    risk_level=risk_level,
                    agent_steps_json=json.dumps([asdict(item) for item in trace], ensure_ascii=False),
                    skill_calls_json=json.dumps([asdict(item) for item in skills], ensure_ascii=False),
                    answer=answer,
                )
            )
            db.commit()

    def list_traces(self) -> list[dict]:
        with self.db_factory() as db:
            rows = db.query(AgentRunTrace).order_by(AgentRunTrace.created_at.desc()).limit(100).all()
            return [
                {
                    "id": row.id,
                    "session_id": row.session_public_id,
                    "message_id": row.message_id,
                    "intent": row.intent,
                    "risk_level": row.risk_level,
                    "agent_steps": loads_or(row.agent_steps_json, []),
                    "skill_calls": loads_or(row.skill_calls_json, []),
                    "answer": row.answer,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def _get_session(self, db: Session, public_id: str) -> ChatSession | None:
        return db.query(ChatSession).filter(ChatSession.public_id == public_id).first()

    def _auth_session_dict(self, user: AuthUser, auth_session: AuthSession) -> dict:
        return {
            "auth_session_id": auth_session.public_id,
            "session_token": auth_session.session_token,
            "expires_at": auth_session.expires_at.isoformat(),
            "user": {
                "id": user.public_id,
                "username": user.username,
                "role": user.role,
            },
        }

    def _audit_log_dict(self, row: AdminAuditLog) -> dict:
        return {
            "id": row.public_id,
            "actor_user_id": row.actor_user_public_id,
            "actor_username": row.actor_username,
            "actor_role": row.actor_role,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_public_id,
            "payload": loads_or(row.payload_json, {}),
            "created_at": row.created_at.isoformat(),
        }

    def _memory_row_dict(self, memory: SessionMemory) -> dict:
        return {
            "summary": memory.summary,
            "covered_message_count": memory.covered_message_count,
            "updated_at": memory.updated_at.isoformat(),
        }

    def _tool_job_dict(self, row: ToolJob) -> dict:
        return {
            "id": row.public_id,
            "kind": row.kind,
            "status": row.status,
            "report_id": row.report_public_id,
            "case_id": row.case_public_id,
            "payload": loads_or(row.payload_json, {}),
            "attempts": row.attempts,
            "max_attempts": row.max_attempts,
            "last_error": row.last_error,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    def _add_tool_audit_record(
        self,
        db: Session,
        tool_kind: str,
        action: str,
        decision: str,
        reason: str,
        payload: dict,
        actor_role: str = UserRole.ADMIN.value,
        report_public_id: str = "",
        case_public_id: str = "",
        job_public_id: str = "",
    ) -> None:
        db.add(
            ToolAuditRecord(
                public_id=f"taudit-{uuid4().hex[:10]}",
                tool_kind=tool_kind,
                action=action,
                decision=decision,
                reason=reason,
                actor_role=actor_role,
                risk_level=str(payload.get("risk_level", "")),
                report_public_id=report_public_id,
                case_public_id=case_public_id,
                job_public_id=job_public_id,
                payload_json=json.dumps(redacted_payload(payload), ensure_ascii=False),
            )
        )

    def _tool_audit_record_dict(self, row: ToolAuditRecord) -> dict:
        return {
            "id": row.public_id,
            "tool_kind": row.tool_kind,
            "action": row.action,
            "decision": row.decision,
            "reason": row.reason,
            "actor_role": row.actor_role,
            "risk_level": row.risk_level,
            "report_id": row.report_public_id,
            "case_id": row.case_public_id,
            "job_id": row.job_public_id,
            "payload": loads_or(row.payload_json, {}),
            "created_at": row.created_at.isoformat(),
        }

    def _dead_letter_record_dict(self, row: DeadLetterRecord) -> dict:
        return {
            "id": row.public_id,
            "job_id": row.job_public_id,
            "tool_kind": row.tool_kind,
            "reason": row.reason,
            "payload": loads_or(row.payload_json, {}),
            "created_at": row.created_at.isoformat(),
        }

    def _agent_private_memory_dict(self, row: AgentPrivateMemory) -> dict:
        return {
            "id": row.id,
            "agent_name": row.agent_name,
            "session_id": row.session_public_id,
            "content": row.content,
            "metadata": loads_or(row.metadata_json, {}),
            "created_at": row.created_at.isoformat(),
        }

    def _agent_model_profile_dict(self, row: AgentModelProfile) -> dict:
        return {
            "agent_name": row.agent_name,
            "provider": row.provider,
            "model": row.model,
            "temperature": row.temperature,
            "system_prompt": row.system_prompt,
            "enabled": row.enabled == "true",
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }


def _title(value: str) -> str:
    normalized = " ".join((value or "新对话").split())
    return normalized[:36] or "新对话"
