"""LangGraph checkpoint 持久化测试:跨实例读取终态(断点可恢复)。"""
from pathlib import Path

from app.agents.langgraph_runtime import LangGraphRuntime
from app.config import Settings
from tests.test_orchestrator import build_orchestrator


def test_checkpoint_persists_across_instances(tmp_path: Path):
    orchestrator = build_orchestrator(tmp_path)
    orchestrator.settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite'}",
        redis_url="", vector_enabled=False, agent_runtime="langgraph",
        langgraph_checkpoint_enabled=True,
        langgraph_checkpoint_path=str(tmp_path / "ckpt.sqlite"),
    )
    runtime = LangGraphRuntime(
        orchestrator.registry, orchestrator.store, orchestrator.llm_client,
        orchestrator.settings, orchestrator.model_registry,
    )

    session_id = "sess-abc"
    outcome = runtime.run(session_id, "我最近考试压力很大，晚上睡不着")
    assert outcome.answer

    # 第二个实例:同一 sqlite 文件,应能读到同一会话的最近检查点终态
    runtime2 = LangGraphRuntime(
        orchestrator.registry, orchestrator.store, orchestrator.llm_client,
        orchestrator.settings, orchestrator.model_registry,
    )
    state = runtime2.get_state(session_id)
    assert state is not None
    assert state.get("answer") == outcome.answer
    assert state.get("session_id") == session_id


def test_checkpoint_disabled_returns_none(tmp_path: Path):
    orchestrator = build_orchestrator(tmp_path)
    orchestrator.settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite'}",
        redis_url="", vector_enabled=False, agent_runtime="langgraph",
        langgraph_checkpoint_enabled=False,
    )
    runtime = LangGraphRuntime(
        orchestrator.registry, orchestrator.store, orchestrator.llm_client,
        orchestrator.settings, orchestrator.model_registry,
    )
    assert runtime.checkpointer is None
    assert runtime.get_state("any") is None
