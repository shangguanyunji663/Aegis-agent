from __future__ import annotations

import os
import re
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from app.config import Settings


class AegisMcpToolError(RuntimeError):
    pass


class AegisMcpToolClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        async with self._session() as session:
            result = await session.call_tool(name, arguments=arguments)
            message = self._result_message(result)
            if getattr(result, "isError", False):
                raise AegisMcpToolError(f"{name} failed: {message}")
            return message

    async def queue_case_tools(self, report_id: str, case_id: str, risk_level: str, summary: str = "") -> list[str]:
        calls = [
            ("aegis_write_ledger", {"report_id": report_id, "case_id": case_id, "risk_level": risk_level, "summary": summary}),
            ("aegis_create_handoff_summary", {"report_id": report_id, "case_id": case_id, "risk_level": risk_level, "summary": summary}),
        ]
        if risk_level == "high":
            calls.extend([
                ("aegis_create_alert", {"report_id": report_id, "case_id": case_id, "risk_level": risk_level, "summary": summary}),
                ("aegis_send_email", {"report_id": report_id, "case_id": case_id, "risk_level": risk_level, "summary": summary}),
            ])
        results = []
        async with self._session() as session:
            for name, arguments in calls:
                result = await session.call_tool(name, arguments=arguments)
                message = self._result_message(result)
                if getattr(result, "isError", False):
                    raise AegisMcpToolError(f"{name} failed: {message}")
                results.append(message)
        return results

    async def create_case(self, report_id: str) -> str:
        return await self.call_tool("aegis_case_create", {"report_id": report_id})

    async def acknowledge_case(self, case_id: str, actor: str, note: str = "") -> str:
        return await self.call_tool("aegis_case_ack", {"case_id": case_id, "actor": actor, "note": note})

    async def add_case_note(self, case_id: str, actor: str, note: str) -> str:
        return await self.call_tool("aegis_case_note_add", {"case_id": case_id, "actor": actor, "note": note})

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[Any]:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise AegisMcpToolError("mcp dependency is required for MCP client mode") from exc

        project_root = self.settings.project_root
        env = os.environ.copy()
        python_path = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(project_root) if not python_path else f"{project_root}{os.pathsep}{python_path}"
        env["DATABASE_URL"] = self.settings.database_url
        env["AI_PROVIDER"] = self.settings.ai_provider
        env["KNOWLEDGE_DIR"] = self.settings.knowledge_dir
        env["VECTOR_ENABLED"] = str(self.settings.vector_enabled).lower()
        env["VECTOR_REQUIRED"] = str(self.settings.vector_required).lower()
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp.server"],
            env=env,
            cwd=str(project_root),
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    def _result_message(self, result: Any) -> str:
        parts = []
        for item in getattr(result, "content", []) or []:
            text = getattr(item, "text", None)
            parts.append(text if text is not None else str(item))
        if parts:
            return "\n".join(parts)
        structured = getattr(result, "structuredContent", None)
        return str(structured if structured is not None else result)


def extract_job_id(message: str) -> str | None:
    match = re.search(r"jobId=([^,\\s]+)", message)
    return match.group(1) if match else None
