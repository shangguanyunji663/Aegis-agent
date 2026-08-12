from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.models import RiskLevel, UserRole
from app.privacy import redact_payload


@dataclass(frozen=True)
class ToolContract:
    kind: str
    public_name: str
    description: str
    required_role: str
    allowed_risk_levels: tuple[str, ...]
    approval_required: bool
    redacted_payload_fields: tuple[str, ...]
    max_attempts: int = 3

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToolGovernanceError(ValueError):
    pass


TOOL_KIND_ALIASES = {
    "alert_log_mock": "create_alert",
    "email_mock": "send_email",
    "excel_ledger_mock": "write_ledger",
    "handoff_summary_mock": "create_handoff_summary",
    "resource_lookup_mock": "lookup_resource",
}


TOOL_CONTRACTS: dict[str, ToolContract] = {
    "create_alert": ToolContract(
        kind="create_alert",
        public_name="create_alert",
        description="Create an admin-visible alert record for an approved risk case.",
        required_role=UserRole.ADMIN.value,
        allowed_risk_levels=(RiskLevel.MEDIUM.value, RiskLevel.HIGH.value),
        approval_required=True,
        redacted_payload_fields=("message", "student_name", "phone", "email"),
    ),
    "send_email": ToolContract(
        kind="send_email",
        public_name="send_email",
        description="Queue a counselor or administrator notification after human approval.",
        required_role=UserRole.ADMIN.value,
        allowed_risk_levels=(RiskLevel.HIGH.value,),
        approval_required=True,
        redacted_payload_fields=("message", "student_name", "phone", "email"),
    ),
    "write_ledger": ToolContract(
        kind="write_ledger",
        public_name="write_ledger",
        description="Append a redacted case row to the local review ledger.",
        required_role=UserRole.ADMIN.value,
        allowed_risk_levels=(RiskLevel.MEDIUM.value, RiskLevel.HIGH.value),
        approval_required=True,
        redacted_payload_fields=("message", "student_name", "phone", "email"),
    ),
    "create_handoff_summary": ToolContract(
        kind="create_handoff_summary",
        public_name="create_handoff_summary",
        description="Prepare a counselor handoff summary as an admin-reviewed task.",
        required_role=UserRole.ADMIN.value,
        allowed_risk_levels=(RiskLevel.MEDIUM.value, RiskLevel.HIGH.value),
        approval_required=True,
        redacted_payload_fields=("message", "student_name", "phone", "email"),
    ),
    "lookup_resource": ToolContract(
        kind="lookup_resource",
        public_name="lookup_resource",
        description="Look up campus support resources without changing external systems.",
        required_role=UserRole.ADMIN.value,
        allowed_risk_levels=(RiskLevel.LOW.value, RiskLevel.MEDIUM.value, RiskLevel.HIGH.value),
        approval_required=False,
        redacted_payload_fields=("message", "student_name", "phone", "email"),
    ),
    "follow_up_suggestion": ToolContract(
        kind="follow_up_suggestion",
        public_name="create_follow_up_suggestion",
        description="Store a bounded follow-up suggestion for administrator review.",
        required_role=UserRole.ADMIN.value,
        allowed_risk_levels=(RiskLevel.MEDIUM.value, RiskLevel.HIGH.value),
        approval_required=True,
        redacted_payload_fields=("message", "student_name", "phone", "email"),
    ),
}


def list_tool_contracts() -> list[dict[str, Any]]:
    return [contract.as_dict() for contract in sorted(TOOL_CONTRACTS.values(), key=lambda item: item.public_name)]


def normalize_tool_kind(kind: str) -> str:
    return TOOL_KIND_ALIASES.get(kind, kind)


def get_tool_contract(kind: str) -> ToolContract:
    normalized = normalize_tool_kind(kind)
    try:
        return TOOL_CONTRACTS[normalized]
    except KeyError as exc:
        raise ToolGovernanceError(f"unknown governed tool: {kind}") from exc


def governed_payload(kind: str, payload: dict[str, Any], role: str, approved: bool) -> dict[str, Any]:
    contract = get_tool_contract(kind)
    if role != contract.required_role:
        raise ToolGovernanceError(f"{contract.kind} requires role={contract.required_role}")
    risk_level = str(payload.get("risk_level") or "").strip().lower()
    if risk_level and risk_level not in contract.allowed_risk_levels:
        raise ToolGovernanceError(f"{contract.kind} is not allowed for risk_level={risk_level}")
    if contract.approval_required and not approved:
        raise ToolGovernanceError(f"{contract.kind} requires admin approval before queueing")
    redacted, redacted_fields = redact_payload(payload, contract.redacted_payload_fields)
    return {
        **payload,
        "tool_kind": contract.kind,
        "tool_contract": contract.public_name,
        "approval_required": contract.approval_required,
        "redacted_fields": redacted_fields,
        "redacted_payload": redacted,
    }
