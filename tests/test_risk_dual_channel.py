"""风险评估双通道测试:规则 ∪ LLM 取并集,规则兜底。"""
from pathlib import Path

from app.agents.classic import RiskGuardianAgent
from app.llm import MockLLMClient
from app.models import RiskLevel
from app.skills import SkillRegistry
from tests.test_orchestrator import build_orchestrator


class HighRiskStubClient(MockLLMClient):
    """stub:对任何输入都判 high(模拟 LLM 通道捕捉到规则未覆盖的表达)。"""

    def assess_risk(self, text: str) -> dict | None:
        return {"risk_level": "high", "reason": "表达无价值感与被动消极"}


class FailingStubClient(MockLLMClient):
    """stub:LLM 通道异常(网络失败等),应回退纯规则。"""

    def assess_risk(self, text: str) -> dict | None:
        raise RuntimeError("network down")


def build_registry(tmp_path: Path) -> SkillRegistry:
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    (knowledge_dir / "crisis.md").write_text("自杀 轻生 危机干预", encoding="utf-8")
    return SkillRegistry(knowledge_dir, lambda report: None)


def test_llm_channel_escalates_to_high(tmp_path: Path):
    """规则判 LOW/未命中关键词,LLM 通道判 high → 并集取 HIGH 并建报告资格。"""
    registry = build_registry(tmp_path)
    agent = RiskGuardianAgent(registry, llm_client=HighRiskStubClient(), llm_channel_enabled=True)

    result, risk_level, trace = agent.assess("我觉得自己是家人的负担，活着没什么意思")

    assert risk_level is RiskLevel.HIGH  # 规则通道未命中高危词,LLM 通道升级
    assert result.output["risk_channels"] == {"rules": "low", "llm": "high"}
    assert result.output["report_eligible"] is True
    assert any("LLM通道" in item for item in result.output["rationale"])


def test_llm_channel_failure_falls_back_to_rules(tmp_path: Path):
    registry = build_registry(tmp_path)
    agent = RiskGuardianAgent(registry, llm_client=FailingStubClient(), llm_channel_enabled=True)

    result, risk_level, _ = agent.assess("我不想活了，想结束生命")

    assert risk_level is RiskLevel.HIGH  # 规则通道兜底
    assert result.output["risk_channels"]["llm"] == "skipped"


def test_mock_and_disabled_behave_as_before(tmp_path: Path):
    """mock 客户端/开关关闭:行为与纯规则完全一致,通道标记为 skipped。"""
    registry = build_registry(tmp_path)
    agent = RiskGuardianAgent(registry, llm_client=MockLLMClient(), llm_channel_enabled=True)
    result, risk_level, _ = agent.assess("我不想活了")
    assert risk_level is RiskLevel.HIGH
    assert result.output["risk_channels"] == {"rules": "high", "llm": "skipped"}

    agent_off = RiskGuardianAgent(registry, llm_client=HighRiskStubClient(), llm_channel_enabled=False)
    _, risk_off, _ = agent_off.assess("我觉得自己是家人的负担")
    assert risk_off is RiskLevel.LOW  # 开关关闭 → stub 也不生效


def test_dual_channel_in_full_pipeline(tmp_path: Path):
    """端到端:ordered 运行时下 LLM 通道升级触发完整安全闭环(报告创建+安全模板)。"""
    orchestrator = build_orchestrator(tmp_path)
    orchestrator.settings.agent_runtime = "ordered"
    dual_agent = RiskGuardianAgent(
        orchestrator.registry, llm_client=HighRiskStubClient(), llm_channel_enabled=True
    )
    # ordered 路径经 AgentRegistry 调用,需重新注册才能生效
    orchestrator.agent_registry.register("risk_guardian", dual_agent)
    orchestrator.agent_registry.register("safety_planner", dual_agent)
    orchestrator.risk_agent = dual_agent

    response = orchestrator.handle("我觉得自己是家人的负担，活着没什么意思")

    assert response.risk_level is RiskLevel.HIGH
    assert response.pending_report is not None
    assert any(term in response.answer for term in ["可信任的人", "学校心理中心", "紧急服务"])
