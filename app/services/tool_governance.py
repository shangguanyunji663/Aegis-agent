from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy.orm import Session

from app.entities import ToolAuditRecord, ToolJob
from app.models import UserRole
from app.privacy import redacted_payload
from app.tool_contracts import get_tool_contract, normalize_tool_kind


class ToolGovernanceService:
    def __init__(self, db: Session):
        self.db = db

    def authorize_execution(self, job: ToolJob, payload: dict) -> tuple[bool, str]:
        try:
            contract = get_tool_contract(job.kind)
        except Exception as exc:
            return False, str(exc)
        risk_level = str(payload.get("risk_level") or "").strip().lower()
        if risk_level and risk_level not in contract.allowed_risk_levels:
            return False, f"{contract.kind} is not allowed for risk_level={risk_level}"
        return True, "allowed"

    def require_allowed(self, job: ToolJob, payload: dict) -> None:
        allowed, reason = self.authorize_execution(job, payload)
        if not allowed:
            raise RuntimeError(reason)

    def audit(
        self,
        job: ToolJob,
        action: str,
        decision: str,
        reason: str,
        payload: dict,
        actor_role: str = UserRole.ADMIN.value,
    ) -> None:
        self.db.add(
            ToolAuditRecord(
                public_id=f"taudit-{uuid4().hex[:10]}",
                tool_kind=normalize_tool_kind(job.kind),
                action=action,
                decision=decision,
                reason=reason,
                actor_role=actor_role,
                risk_level=str(payload.get("risk_level", "")),
                report_public_id=job.report_public_id,
                case_public_id=job.case_public_id,
                job_public_id=job.public_id,
                payload_json=json.dumps(redacted_payload(payload), ensure_ascii=False),
            )
        )
