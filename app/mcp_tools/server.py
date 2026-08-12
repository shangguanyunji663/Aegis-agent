from __future__ import annotations

import argparse
import json
from typing import Any

from app.config import get_settings
from app.database import build_session_factory, create_schema
from app.repository import DatabaseStore

from app.tool_contracts import list_tool_contracts

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None


MCP_RESOURCES = [
    {
        "uri": "aegis://knowledge/search",
        "name": "Knowledge Search",
        "description": "Read-only access to campus psychological support knowledge search.",
    },
    {
        "uri": "aegis://sessions/{session_id}/summary",
        "name": "Session Summary",
        "description": "Read-only memory summary for a specific chat session.",
    },
    {
        "uri": "aegis://reports/{report_id}/summary",
        "name": "Report Summary",
        "description": "Read-only summary of a psychological risk report.",
    },
    {
        "uri": "aegis://cases/{case_id}/summary",
        "name": "Case Summary",
        "description": "Read-only summary and handoff notes for an approved risk case.",
    },
]


def list_mcp_capabilities() -> dict[str, Any]:
    return {
        "server": "aegis-psych-agent-local",
        "mode": "optional",
        "resources": MCP_RESOURCES,
        "tools": list_tool_contracts()
        + [
            {
                "public_name": "aegis_case_create",
                "description": "Create or return an Aegis risk case for one psychological report.",
                "required_role": "admin",
            },
            {
                "public_name": "aegis_case_ack",
                "description": "Mark an Aegis risk case as acknowledged by a counselor or administrator.",
                "required_role": "admin",
            },
            {
                "public_name": "aegis_case_note_add",
                "description": "Append a counselor/admin follow-up note to an Aegis risk case.",
                "required_role": "admin",
            },
        ],
    }


def call_governed_tool(store, kind: str, payload: dict[str, Any], approved: bool = True) -> dict:
    return store.create_tool_job(kind, payload, approved=approved)


def read_resource(store, uri: str, **params: Any) -> dict[str, Any]:
    if uri == "aegis://knowledge/search":
        query = str(params.get("q") or params.get("query") or "").strip()
        if not query:
            return {"uri": uri, "results": []}
        return {
            "uri": uri,
            "query": query,
            "results": store.search_knowledge(
                query,
                int(params.get("top_k") or 3),
                topic=params.get("topic") or None,
                risk_level=params.get("risk_level") or None,
                audience=params.get("audience") or None,
            ),
        }
    if uri == "aegis://sessions/{session_id}/summary":
        session_id = str(params.get("session_id") or "")
        session = store.get_session(session_id)
        return {"uri": uri, "session": None if session is None else {"id": session["id"], "memory_summary": session["memory_summary"]}}
    if uri == "aegis://reports/{report_id}/summary":
        report_id = str(params.get("report_id") or "")
        report = next((item for item in store.list_reports() if item["id"] == report_id), None)
        return {"uri": uri, "report": report}
    if uri == "aegis://cases/{case_id}/summary":
        case_id = str(params.get("case_id") or "")
        case = next((item for item in store.list_cases() if item["id"] == case_id), None)
        return {"uri": uri, "case": case}
    raise ValueError(f"unknown MCP resource: {uri}")


def build_store() -> DatabaseStore:
    settings = get_settings()
    session_factory = build_session_factory(settings)
    create_schema()
    return DatabaseStore(session_factory, settings=settings)


def create_fastmcp_server():
    if FastMCP is None:
        raise RuntimeError("mcp dependency is required for FastMCP server mode")
    mcp = FastMCP("aegis-psych-agent-tools")

    @mcp.tool()
    def aegis_case_create(report_id: str) -> str:
        """Create or return the active Aegis risk case for one psychological report."""
        store = build_store()
        case = store.ensure_case_for_report(report_id)
        if case is None:
            return f"report {report_id} not found"
        return f"success: caseId={case['id']}, reportId={case['report_id']}, status={case['status']}"

    @mcp.tool()
    def aegis_case_ack(case_id: str, actor: str, note: str = "") -> str:
        """Mark an Aegis risk case as acknowledged by a counselor or administrator."""
        store = build_store()
        case = store.acknowledge_case(case_id, actor, note)
        if case is None:
            return f"case {case_id} not found"
        return f"success: caseId={case['id']}, status={case['status']}, owner={case['owner']}"

    @mcp.tool()
    def aegis_case_note_add(case_id: str, actor: str, note: str) -> str:
        """Append a follow-up note to an Aegis risk case."""
        store = build_store()
        if not note.strip():
            return "case note cannot be empty"
        case = store.add_case_note(case_id, note, actor)
        if case is None:
            return f"case {case_id} not found"
        return f"success: caseId={case['id']}, notes={len(case['notes'])}"

    @mcp.tool()
    def aegis_create_alert(report_id: str, case_id: str, risk_level: str, summary: str = "") -> str:
        """Queue a governed alert creation task for an approved Aegis risk case."""
        store = build_store()
        job = store.create_tool_job(
            "create_alert",
            {"report_id": report_id, "case_id": case_id, "risk_level": risk_level, "summary": summary},
            report_public_id=report_id,
            case_public_id=case_id,
            approved=True,
        )
        return f"success: jobId={job['id']}, kind={job['kind']}, status={job['status']}"

    @mcp.tool()
    def aegis_write_ledger(report_id: str, case_id: str, risk_level: str, summary: str = "") -> str:
        """Queue a governed ledger-write task for an approved Aegis risk case."""
        store = build_store()
        job = store.create_tool_job(
            "write_ledger",
            {"report_id": report_id, "case_id": case_id, "risk_level": risk_level, "summary": summary},
            report_public_id=report_id,
            case_public_id=case_id,
            approved=True,
        )
        return f"success: jobId={job['id']}, kind={job['kind']}, status={job['status']}"

    @mcp.tool()
    def aegis_send_email(report_id: str, case_id: str, risk_level: str, summary: str = "") -> str:
        """Queue a governed email notification task for an approved high-risk Aegis case."""
        store = build_store()
        job = store.create_tool_job(
            "send_email",
            {"report_id": report_id, "case_id": case_id, "risk_level": risk_level, "summary": summary},
            report_public_id=report_id,
            case_public_id=case_id,
            approved=True,
        )
        return f"success: jobId={job['id']}, kind={job['kind']}, status={job['status']}"

    @mcp.tool()
    def aegis_create_handoff_summary(report_id: str, case_id: str, risk_level: str, summary: str = "") -> str:
        """Queue a governed counselor handoff summary task for an approved Aegis risk case."""
        store = build_store()
        job = store.create_tool_job(
            "create_handoff_summary",
            {"report_id": report_id, "case_id": case_id, "risk_level": risk_level, "summary": summary},
            report_public_id=report_id,
            case_public_id=case_id,
            approved=True,
        )
        return f"success: jobId={job['id']}, kind={job['kind']}, status={job['status']}"

    @mcp.tool()
    def aegis_lookup_resource(query: str, topic: str = "", risk_level: str = "", audience: str = "") -> str:
        """Search Aegis knowledge resources with optional metadata filters."""
        store = build_store()
        job = store.create_tool_job(
            "lookup_resource",
            {
                "query": query,
                "risk_level": risk_level or "low",
                "topic": topic,
                "audience": audience,
                "message": query,
            },
            approved=True,
        )
        result = read_resource(
            store,
            "aegis://knowledge/search",
            q=query,
            topic=topic,
            risk_level=risk_level,
            audience=audience,
        )
        return f"success: jobId={job['id']}, kind={job['kind']}, status={job['status']}; result={json.dumps(result, ensure_ascii=False)}"

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="List optional Aegis MCP capabilities.")
    parser.add_argument("--list", action="store_true", help="Print tool and resource capabilities as JSON.")
    args = parser.parse_args()
    if args.list:
        print(json.dumps(list_mcp_capabilities(), ensure_ascii=False, indent=2))
        return
    create_fastmcp_server().run()


if __name__ == "__main__":
    main()
