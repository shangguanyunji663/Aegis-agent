from __future__ import annotations

from typing import Any


SENSITIVE_PAYLOAD_FIELDS = {
    "api_key",
    "email",
    "message",
    "password",
    "phone",
    "precise_location",
    "session_token",
    "student_id",
    "student_name",
    "token",
}

INTERNAL_RESPONSE_TERMS = ("report_id", "risk-", "内部评分", "confidence")


def redact_payload(payload: dict[str, Any], fields: set[str] | tuple[str, ...] | list[str] | None = None) -> tuple[dict[str, Any], list[str]]:
    selected = set(fields or SENSITIVE_PAYLOAD_FIELDS)
    redacted = {}
    touched = []
    for key, value in (payload or {}).items():
        if key in selected and value:
            redacted[key] = "[redacted]"
            touched.append(key)
        elif isinstance(value, dict):
            nested, nested_fields = redact_payload(value, selected)
            redacted[key] = nested
            touched.extend(f"{key}.{field}" for field in nested_fields)
        else:
            redacted[key] = value
    return redacted, sorted(set(touched))


def redacted_payload(payload: dict[str, Any], fields: set[str] | tuple[str, ...] | list[str] | None = None) -> dict[str, Any]:
    return redact_payload(payload, fields)[0]


def contains_internal_response_leak(text: str) -> bool:
    lowered = (text or "").lower()
    return any(term.lower() in lowered for term in INTERNAL_RESPONSE_TERMS)


def sanitize_user_input(text: str) -> str:
    sanitized = " ".join((text or "").split()).strip()
    replacements = {
        "手机号": "联系方式",
        "电话": "联系方式",
        "身份证": "证件",
    }
    for raw, safe in replacements.items():
        sanitized = sanitized.replace(raw, safe)
    return sanitized
