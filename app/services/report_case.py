from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.entities import CaseNote, PsychologicalReport, RiskCase, ToolJob
from app.models import CaseStatus, ReportStatus, RiskLevel, ToolJobStatus, UserRole
from app.tool_contracts import governed_payload, normalize_tool_kind


class ReportCaseService:
    def __init__(self, db: Session):
        self.db = db

    def list_reports(self) -> list[dict]:
        rows = self.db.query(PsychologicalReport).order_by(PsychologicalReport.created_at.desc()).limit(100).all()
        return [report_dict(row) for row in rows]

    def update_report(self, report_id: str, status: ReportStatus) -> dict | None:
        row = self.db.query(PsychologicalReport).filter(PsychologicalReport.public_id == report_id).first()
        if row is None:
            return None
        row.status = status.value
        row.updated_at = _now()
        self.db.add(row)
        if status is ReportStatus.APPROVED and row.risk_level in {RiskLevel.MEDIUM.value, RiskLevel.HIGH.value}:
            self.ensure_case(row)
        self.db.commit()
        self.db.refresh(row)
        return report_dict(row)

    def ensure_case_for_report(self, report_id: str) -> dict | None:
        report = self.db.query(PsychologicalReport).filter(PsychologicalReport.public_id == report_id).first()
        if report is None:
            return None
        case = self.ensure_case(report)
        self.db.commit()
        self.db.refresh(case)
        return case_dict(self.db, case)

    def list_cases(self) -> list[dict]:
        cases = self.db.query(RiskCase).order_by(RiskCase.updated_at.desc()).limit(100).all()
        return [case_dict(self.db, case) for case in cases]

    def add_case_note(self, case_id: str, note: str, actor: str = "admin") -> dict | None:
        case = self.db.query(RiskCase).filter(RiskCase.public_id == case_id).first()
        if case is None:
            return None
        self.db.add(CaseNote(case_public_id=case.public_id, actor=actor, note=note))
        case.updated_at = _now()
        self.db.add(case)
        self.db.commit()
        self.db.refresh(case)
        return case_dict(self.db, case)

    def update_case_status(self, case_id: str, status: CaseStatus) -> dict | None:
        case = self.db.query(RiskCase).filter(RiskCase.public_id == case_id).first()
        if case is None:
            return None
        case.status = status.value
        case.updated_at = _now()
        self.db.add(case)
        self.db.commit()
        self.db.refresh(case)
        return case_dict(self.db, case)

    def acknowledge_case(self, case_id: str, actor: str, note: str = "") -> dict | None:
        case = self.db.query(RiskCase).filter(RiskCase.public_id == case_id).first()
        if case is None:
            return None
        case.status = CaseStatus.ACKNOWLEDGED.value
        case.owner = actor.strip() or case.owner or "admin"
        case.updated_at = _now()
        self.db.add(case)
        self.db.add(CaseNote(case_public_id=case.public_id, actor=actor.strip() or "admin", note=note.strip() or "已确认接手该个案"))
        self.db.commit()
        self.db.refresh(case)
        return case_dict(self.db, case)

    def ensure_case(self, report: PsychologicalReport) -> RiskCase:
        existing = self.db.query(RiskCase).filter(RiskCase.report_public_id == report.public_id).first()
        if existing is not None:
            self.ensure_case_tool_jobs(report, existing)
            return existing
        case = RiskCase(
            public_id=f"case-{uuid4().hex[:8]}",
            report_public_id=report.public_id,
            session_public_id=report.session_public_id,
            risk_level=report.risk_level,
            status=CaseStatus.OPEN.value,
            summary=report.summary,
            handoff_summary=handoff_summary(report),
        )
        self.db.add(case)
        self.db.flush()
        self.ensure_case_tool_jobs(report, case)
        return case

    def ensure_case_tool_jobs(self, report: PsychologicalReport, case: RiskCase) -> None:
        existing = self.db.query(ToolJob).filter(ToolJob.case_public_id == case.public_id).first()
        if existing is not None:
            return
        payload = {
            "report_id": report.public_id,
            "case_id": case.public_id,
            "session_id": report.session_public_id,
            "risk_level": report.risk_level,
            "summary": report.summary,
        }
        kinds = ["create_alert", "send_email", "write_ledger", "create_handoff_summary", "follow_up_suggestion"]
        for kind in kinds:
            job_payload = governed_payload(
                kind,
                payload | {"kind": kind, "suggestion": follow_up_suggestion(report, case, kind)},
                role=UserRole.ADMIN.value,
                approved=True,
            )
            self.db.add(
                ToolJob(
                    public_id=f"job-{uuid4().hex[:8]}",
                    kind=kind,
                    status=ToolJobStatus.PENDING.value,
                    report_public_id=report.public_id,
                    case_public_id=case.public_id,
                    payload_json=json.dumps(job_payload, ensure_ascii=False),
                    run_after=_now(),
                )
            )


def report_dict(row: PsychologicalReport) -> dict:
    return {
        "id": row.public_id,
        "session_id": row.session_public_id,
        "message": row.message,
        "intent": row.intent,
        "emotion": row.emotion,
        "emotion_score": row.emotion_score,
        "risk_level": row.risk_level,
        "confidence": row.confidence,
        "rationale": _loads(row.rationale_json, []),
        "summary": row.summary,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }


def case_dict(db: Session, case: RiskCase) -> dict:
    notes = (
        db.query(CaseNote)
        .filter(CaseNote.case_public_id == case.public_id)
        .order_by(CaseNote.created_at.asc(), CaseNote.id.asc())
        .all()
    )
    return {
        "id": case.public_id,
        "report_id": case.report_public_id,
        "session_id": case.session_public_id,
        "risk_level": case.risk_level,
        "status": case.status,
        "owner": case.owner,
        "summary": case.summary,
        "handoff_summary": case.handoff_summary,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
        "notes": [
            {
                "id": note.id,
                "actor": note.actor,
                "note": note.note,
                "created_at": note.created_at.isoformat(),
            }
            for note in notes
        ],
    }


def handoff_summary(report: PsychologicalReport) -> str:
    return (
        f"报告 {report.public_id}，风险等级 {report.risk_level}。"
        f"摘要：{report.summary or '暂无摘要'}。"
        "建议确认学生当前位置、身边支持者、当前安全状态，并记录后续跟进安排。"
    )


def follow_up_suggestion(report: PsychologicalReport, case: RiskCase, kind: str) -> str:
    if kind == "follow_up_suggestion":
        return (
            "建议管理员优先复核该高风险报告，确认学生当前安全状态、可联系支持者、"
            "以及是否需要辅导员介入。该建议仅供后台审核，不直接触达学生。"
        )
    if normalize_tool_kind(kind) == "create_handoff_summary":
        return case.handoff_summary
    return "等待管理员确认后执行对应后置任务。"


def _loads(raw: str, default):
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
