"""Function Calling 技能自主选择测试:白名单兜底,模型在白名单内挑选。"""
from pathlib import Path

from app.agents.skill_selection import select_response_skills
from app.llm import MockLLMClient
from app.models import Intent, RiskLevel
from tests.test_orchestrator import build_orchestrator


class FCStubClient(MockLLMClient):
    """stub:chat_with_tools 返回预设选择。

    继承 MockLLMClient(provider=mock);无需覆盖 provider——守卫改为能力探测:
    chat_with_tools 返回非 None 即视为可信客户端,stub 自然放行。
    """

    def __init__(self, chosen):
        super().__init__()
        self.chosen = chosen

    def chat_with_tools(self, system, user, tools):
        return self.chosen


def test_fc_picks_subset_within_whitelist(tmp_path: Path):
    orchestrator = build_orchestrator(tmp_path)
    whitelist_case = "我最近考试压力很大，晚上睡不着"  # 规则白名单≈[baseline, sleep, academic]
    full, mode = select_response_skills(MockLLMClient(), orchestrator.registry, Intent.COUNSELING, RiskLevel.LOW, whitelist_case)
    assert mode == "rules" and "sleep_routine_support" in full

    chosen, mode = select_response_skills(FCStubClient(["sleep_routine_support"]), orchestrator.registry, Intent.COUNSELING, RiskLevel.LOW, whitelist_case)
    assert mode == "fc"
    assert chosen == ["sleep_routine_support"]  # 只保留模型选择的白名单子集


def test_fc_explicit_none_yields_empty(tmp_path: Path):
    orchestrator = build_orchestrator(tmp_path)
    chosen, mode = select_response_skills(FCStubClient([]), orchestrator.registry, Intent.COUNSELING, RiskLevel.LOW, "考试压力睡不着")
    assert mode == "fc" and chosen == []


def test_fc_hallucination_falls_back_to_whitelist(tmp_path: Path):
    orchestrator = build_orchestrator(tmp_path)
    chosen, mode = select_response_skills(FCStubClient(["nonexistent_skill"]), orchestrator.registry, Intent.COUNSELING, RiskLevel.LOW, "考试压力睡不着")
    assert mode == "rules" and chosen  # 幻觉名不在白名单 → 兜底全白名单


def test_fc_disabled_or_mock_uses_rules(tmp_path: Path):
    orchestrator = build_orchestrator(tmp_path)
    chosen, mode = select_response_skills(FCStubClient(["sleep_routine_support"]), orchestrator.registry, Intent.COUNSELING, RiskLevel.LOW, "考试压力睡不着", enabled=False)
    assert mode == "rules" and "sleep_routine_support" in chosen


def test_fc_in_full_pipeline_trace(tmp_path: Path):
    """端到端:ordered 运行时下 FC 生效并留下 skill_selection_mode trace。"""
    orchestrator = build_orchestrator(tmp_path)
    orchestrator.settings.agent_runtime = "ordered"
    orchestrator.settings.function_calling_enabled = True
    orchestrator.llm_client = FCStubClient(["sleep_routine_support"])
    # CounselorAgent 持有旧客户端,FC 只影响技能选择;生成回复仍走 mock → 模板,行为确定
    response = orchestrator.handle("我最近考试压力很大，晚上睡不着")
    modes = [item for item in response.trace if item.action == "skill_selection_mode"]
    assert modes and "function-calling" in modes[-1].detail
    selected = [item for item in response.trace if item.action == "select_standard_skills"]
    assert selected and selected[-1].detail == "sleep_routine_support"
