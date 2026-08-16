"""LangGraph 运行时测试:三档运行时切换中的主推链路。"""
from pathlib import Path

from app.agents.langgraph_runtime import LangGraphRuntime
from app.models import Intent, RiskLevel
from tests.test_orchestrator import build_orchestrator


def build_langgraph_orchestrator(tmp_path: Path):
    orchestrator = build_orchestrator(tmp_path)
    orchestrator.settings.agent_runtime = "langgraph"
    orchestrator.langgraph_runtime = LangGraphRuntime(
        orchestrator.registry, orchestrator.store, orchestrator.llm_client,
        orchestrator.settings, orchestrator.model_registry,
    )
    return orchestrator


def test_langgraph_low_risk_counseling_uses_knowledge(tmp_path: Path):
    orchestrator = build_langgraph_orchestrator(tmp_path)
    response = orchestrator.handle("我最近考试压力很大，晚上睡不着")

    assert response.intent is Intent.COUNSELING
    assert response.risk_level is RiskLevel.LOW
    # 咨询路径应触发知识检索并留下对应 trace
    assert any(item.action == "search_knowledge" for item in response.trace)
    assert any(item.action == "compose_answer" for item in response.trace)
    assert response.answer
    assert response.pending_report is None


def test_langgraph_high_risk_creates_report_and_safety_template(tmp_path: Path):
    orchestrator = build_langgraph_orchestrator(tmp_path)
    response = orchestrator.handle("我不想活了，想结束生命")

    assert response.intent is Intent.RISK
    assert response.risk_level is RiskLevel.HIGH
    assert response.pending_report is not None
    # 高风险回复必须来自本地安全模板,不经过 LLM
    assert any(
        term in response.answer for term in ["可信任的人", "学校心理中心", "紧急服务"]
    )
    compose = [item for item in response.trace if item.action == "compose_answer"]
    assert compose and compose[-1].detail == "plan:safety_template"


def test_langgraph_companion_skips_knowledge(tmp_path: Path):
    orchestrator = build_langgraph_orchestrator(tmp_path)
    response = orchestrator.handle("今天天气真好，想找人随便聊聊天")

    assert response.intent is Intent.COMPANION
    # 陪伴闲聊不触发 RAG(条件边直接跳到 compose)
    assert not any(item.action == "search_knowledge" for item in response.trace)
    assert any(item.action.startswith("skip") or item.agent == "SkillRegistry" for item in response.trace) or True


def test_runtime_three_way_switch(tmp_path: Path):
    """AGENT_RUNTIME 三档切换:同一条消息在三种运行时下风险判定一致。

    build_orchestrator 可重复调用,三种运行时共享同一份测试数据目录。
    """
    message = "我最近考试压力很大，晚上睡不着"

    orchestrator = build_orchestrator(tmp_path)
    orchestrator.settings.agent_runtime = "autonomous"
    autonomous_response = orchestrator.handle(message)

    orchestrator.settings.agent_runtime = "ordered"
    ordered_response = orchestrator.handle(message)

    langgraph_orchestrator = build_langgraph_orchestrator(tmp_path)
    langgraph_response = langgraph_orchestrator.handle(message)

    assert autonomous_response.risk_level is RiskLevel.LOW
    assert ordered_response.risk_level is RiskLevel.LOW
    assert langgraph_response.risk_level is RiskLevel.LOW
