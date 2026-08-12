from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from threading import Lock

from app.models import PendingReport, ReportStatus


class JsonStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self.path.exists():
            self.path.write_text(json.dumps({"messages": [], "reports": []}, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            data = self._read()
            data["messages"].append({"session_id": session_id, "role": role, "content": content})
            self._write(data)

    def add_report(self, report: PendingReport) -> None:
        with self._lock:
            data = self._read()
            data["reports"].append(asdict(report))
            self._write(data)

    def list_reports(self) -> list[dict]:
        with self._lock:
            return self._read()["reports"]

    def update_report(self, report_id: str, status: ReportStatus) -> dict | None:
        with self._lock:
            data = self._read()
            for report in data["reports"]:
                if report["id"] == report_id:
                    report["status"] = status.value
                    self._write(data)
                    return report
            return None

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

