"""评测/Harness 共享装配工厂:构造一个使用独立 SQLite 与真实知识库的编排器。

harness.runner 与 eval.run_eval 共用此工厂,避免两处维护
近乎相同的 build_harness_orchestrator / build_local_orchestrator。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.orchestrator import PsychOrchestrator
from app.config import Settings
from app.database import create_schema
from app.llm import MockLLMClient
from app.repository import DatabaseStore
from app.skills import SkillRegistry


ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = ROOT / "knowledge"


def build_harness_orchestrator(data_dir: Path | None = None, knowledge_dir: Path | None = None) -> PsychOrchestrator:
    data_dir = data_dir or ROOT / "data" / "harness"
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{data_dir / 'harness.sqlite'}", connect_args={"check_same_thread": False})
    create_schema(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    hermetic = Settings(
        database_url=f"sqlite:///{data_dir / 'harness.sqlite'}",
        redis_url="",
        vector_enabled=False,
        agent_runtime="autonomous",
    )
    store = DatabaseStore(session_factory, settings=hermetic)
    knowledge_dir = knowledge_dir or KNOWLEDGE_DIR
    store.rebuild_knowledge_dir(knowledge_dir)
    registry = SkillRegistry(knowledge_dir, store.add_report, store.search_knowledge, settings=hermetic)
    return PsychOrchestrator(registry, store, MockLLMClient())
