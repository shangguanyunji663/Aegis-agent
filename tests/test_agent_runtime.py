import pytest

from app.agents.runtime import AgentRegistry, AgentRuntimeRunner
from app.models import RuntimeEventType
from tests.test_orchestrator import build_orchestrator


class DummyAgent:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def step(self, value: str) -> str:
        self.calls.append(value)
        return value.upper()


def test_agent_registry_lookup_and_missing_agent_failure():
    registry = AgentRegistry()
    agent = DummyAgent()

    registry.register("dummy", agent)

    assert registry.get("dummy") is agent
    assert registry.list_ids() == ["dummy"]
    with pytest.raises(KeyError):
        registry.get("missing")


def test_runtime_runner_executes_ordered_plan_and_records_events():
    registry = AgentRegistry()
    agent = DummyAgent()
    registry.register("dummy", agent)
    runner = AgentRuntimeRunner(registry)

    results = runner.run_plan(
        [
            ("dummy", "first", lambda item: item.step("a")),
            ("dummy", "second", lambda item: item.step("b")),
        ]
    )

    assert results == ["A", "B"]
    assert agent.calls == ["a", "b"]
    assert [event.data["action"] for event in runner.event_history] == ["first", "second"]
    assert all(event.type is RuntimeEventType.AGENT_STARTED for event in runner.event_history)


def test_orchestrator_registers_platform_agent_ids(tmp_path):
    orchestrator = build_orchestrator(tmp_path)

    assert orchestrator.agent_registry.list_ids() == [
        "companion",
        "counselor",
        "knowledge",
        "lead",
        "memory",
        "risk_guardian",
        "safety_planner",
    ]


def test_orchestrator_delegates_steps_through_runtime_runner(tmp_path):
    orchestrator = build_orchestrator(tmp_path)

    orchestrator.handle("我最近考试压力很大，晚上睡不着")
    actions = [event.data["action"] for event in orchestrator.runtime_runner.event_history]

    assert "TASK_CREATED" in actions
    assert "TASK_CLAIMED" in actions
    assert "ARTIFACT_PUBLISHED" in actions
    assert "FINAL_ACCEPTED" in actions


def test_autonomous_runtime_publishes_claim_based_collaboration(tmp_path):
    orchestrator = build_orchestrator(tmp_path)

    response = orchestrator.handle("我最近考试压力很大，晚上睡不着")
    board = orchestrator.autonomous_runtime.last_board

    assert board is not None
    assert board.final_artifact_id
    assert any(event.type.value == "TASK_CLAIMED" and event.actor == "KnowledgeAgent" for event in board.events)
    assert any(event.type.value == "TASK_CLAIMED" and event.actor == "CounselorAgent" for event in board.events)
    assert any(item.agent == "SkillRegistry" and "academic_stress_planning" in item.detail for item in response.trace)
