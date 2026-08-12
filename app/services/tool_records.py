from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.entities import AlertRecord, ExcelRecord
from app.privacy import redacted_payload


class ToolRecordService:
    def __init__(self, db: Session):
        self.db = db

    def record_excel(self, payload: dict[str, Any], result: dict[str, Any], status: str = "success", message: str = "") -> ExcelRecord:
        report_id = str(payload.get("report_id") or "")
        case_id = str(payload.get("case_id") or "")
        existing = (
            self.db.query(ExcelRecord)
            .filter(ExcelRecord.report_public_id == report_id)
            .filter(ExcelRecord.case_public_id == case_id)
            .filter(ExcelRecord.status == "success")
            .first()
        )
        if existing is not None and status == "success":
            return existing
        row = ExcelRecord(
            public_id=f"xls-{uuid4().hex[:10]}",
            report_public_id=report_id,
            case_public_id=case_id,
            file_path=str(result.get("path") or ""),
            status=status,
            message=message or str(result.get("message") or "Excel ledger write completed"),
            payload_json=_json({"payload": redacted_payload(payload), "result": result}),
            updated_at=_now(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def record_alert(
        self,
        payload: dict[str, Any],
        result: dict[str, Any],
        status: str = "success",
        channel: str = "",
        message: str = "",
    ) -> AlertRecord:
        row = AlertRecord(
            public_id=f"alert-{uuid4().hex[:10]}",
            report_public_id=str(payload.get("report_id") or ""),
            case_public_id=str(payload.get("case_id") or ""),
            channel=channel or str(result.get("delivered_to") or "alert"),
            recipient=str(result.get("recipient") or payload.get("recipient") or ""),
            status=status,
            message=message or str(result.get("message") or "Alert delivery completed"),
            payload_json=_json({"payload": redacted_payload(payload), "result": result}),
            updated_at=_now(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_excel_records(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.query(ExcelRecord).order_by(ExcelRecord.created_at.desc(), ExcelRecord.id.desc()).limit(limit).all()
        return [excel_record_dict(row) for row in rows]

    def list_alert_records(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.query(AlertRecord).order_by(AlertRecord.created_at.desc(), AlertRecord.id.desc()).limit(limit).all()
        return [alert_record_dict(row) for row in rows]


def excel_record_dict(row: ExcelRecord) -> dict[str, Any]:
    return {
        "id": row.public_id,
        "report_id": row.report_public_id,
        "case_id": row.case_public_id,
        "file_path": row.file_path,
        "status": row.status,
        "message": row.message,
        "payload": _loads(row.payload_json),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def alert_record_dict(row: AlertRecord) -> dict[str, Any]:
    return {
        "id": row.public_id,
        "report_id": row.report_public_id,
        "case_id": row.case_public_id,
        "channel": row.channel,
        "recipient": row.recipient,
        "status": row.status,
        "message": row.message,
        "payload": _loads(row.payload_json),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _now() -> datetime:
    return datetime.now(timezone.utc)
