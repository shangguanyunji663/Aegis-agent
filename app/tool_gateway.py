from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
import asyncio

from app.config import Settings
from app.mcp_client import AegisMcpToolClient
from app.mcp_tools.server import read_resource
from app.tool_contracts import normalize_tool_kind


class ToolGateway(Protocol):
    backend: str

    def queue_tool(self, kind: str, payload: dict[str, Any], approved: bool = True) -> dict:
        ...

    def read_resource(self, uri: str, **params: Any) -> dict[str, Any]:
        ...


@dataclass
class InternalToolGateway:
    store: Any
    backend: str = "internal"

    def queue_tool(self, kind: str, payload: dict[str, Any], approved: bool = True) -> dict:
        return self.store.create_tool_job(kind, payload, approved=approved)

    def read_resource(self, uri: str, **params: Any) -> dict[str, Any]:
        return read_resource(self.store, uri, **params)


@dataclass
class McpToolGateway:
    store: Any
    settings: Settings
    backend: str = "mcp"

    def queue_tool(self, kind: str, payload: dict[str, Any], approved: bool = True) -> dict:
        canonical_kind = normalize_tool_kind(kind)
        tool_name = {
            "create_alert": "aegis_create_alert",
            "send_email": "aegis_send_email",
            "write_ledger": "aegis_write_ledger",
            "create_handoff_summary": "aegis_create_handoff_summary",
            "lookup_resource": "aegis_lookup_resource",
        }.get(canonical_kind)
        if tool_name is None:
            return self.store.create_tool_job(canonical_kind, payload, approved=approved)
        arguments = self._arguments(canonical_kind, payload)
        message = asyncio.run(AegisMcpToolClient(self.settings).call_tool(tool_name, arguments))
        job_id = _extract_job_id(message)
        if job_id:
            job = next((item for item in self.store.list_tool_jobs() if item["id"] == job_id), None)
            if job is not None:
                return job
        return {"id": job_id or "", "kind": canonical_kind, "status": "queued_via_mcp", "message": message, "payload": payload}

    def read_resource(self, uri: str, **params: Any) -> dict[str, Any]:
        return read_resource(self.store, uri, **params)

    def _arguments(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if kind == "lookup_resource":
            return {
                "query": payload.get("query") or payload.get("message") or "",
                "topic": payload.get("topic", ""),
                "risk_level": payload.get("risk_level", ""),
                "audience": payload.get("audience", ""),
            }
        return {
            "report_id": payload.get("report_id", ""),
            "case_id": payload.get("case_id", ""),
            "risk_level": payload.get("risk_level", ""),
            "summary": payload.get("summary", ""),
        }


def build_tool_gateway(settings: Settings, store) -> ToolGateway:
    backend = settings.tool_backend.strip().lower()
    if backend == "mcp":
        return McpToolGateway(store, settings)
    return InternalToolGateway(store)


def _extract_job_id(message: str) -> str | None:
    marker = "jobId="
    if marker not in message:
        return None
    tail = message.split(marker, 1)[1]
    return tail.split(",", 1)[0].strip()
