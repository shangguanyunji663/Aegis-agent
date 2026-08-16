import asyncio

from app.tools.mcp_client import AegisMcpToolClient
from app.mcp_tools.server import list_mcp_capabilities
from app.config import Settings
from app.tools.gateway import build_tool_gateway
from tests.test_orchestrator import build_orchestrator


def test_optional_mcp_capability_list_exposes_resources_and_governed_tools():
    capabilities = list_mcp_capabilities()

    assert capabilities["server"] == "aegis-psych-agent-local"
    assert any(item["uri"] == "aegis://knowledge/search" for item in capabilities["resources"])
    assert any(item["public_name"] == "send_email" for item in capabilities["tools"])
    assert any(item["public_name"] == "aegis_case_ack" for item in capabilities["tools"])


def test_mcp_tool_gateway_queues_governed_tool_jobs(tmp_path):
    orchestrator = build_orchestrator(tmp_path)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.sqlite'}", tool_backend="mcp")
    gateway = build_tool_gateway(settings, orchestrator.store)

    job = gateway.queue_tool("lookup_resource", {"risk_level": "low", "message": "学校心理中心"}, approved=True)
    resource = gateway.read_resource("aegis://knowledge/search", q="考试压力", top_k=2)

    assert gateway.backend == "mcp"
    assert job["kind"] == "lookup_resource"
    assert job["payload"]["tool_contract"] == "lookup_resource"
    assert resource["results"]


def test_mcp_case_tools_create_acknowledge_and_note_real_case(tmp_path):
    orchestrator = build_orchestrator(tmp_path)
    response = orchestrator.handle("我不想活了，想结束生命")
    report_id = response.pending_report.id
    settings = orchestrator.store.settings
    client = AegisMcpToolClient(settings)

    created = asyncio.run(client.create_case(report_id))
    case_id = created.split("caseId=", 1)[1].split(",", 1)[0]
    acked = asyncio.run(client.acknowledge_case(case_id, "counselor-a", "已电话联系学生"))
    noted = asyncio.run(client.add_case_note(case_id, "counselor-a", "学生确认身边有同学陪伴"))
    case = next(item for item in orchestrator.store.list_cases() if item["id"] == case_id)

    assert "success" in created
    assert "status=acknowledged" in acked
    assert "success" in noted
    assert case["status"] == "acknowledged"
    assert any(note["note"] == "已电话联系学生" for note in case["notes"])
    assert any(note["note"] == "学生确认身边有同学陪伴" for note in case["notes"])
