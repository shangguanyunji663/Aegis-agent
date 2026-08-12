from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import create_schema
from app.evaluation import run_evaluation
from app.llm import MockLLMClient
from app.orchestrator import PsychOrchestrator
from app.repository import DatabaseStore
from app.skills import SkillRegistry


ROOT = Path(__file__).resolve().parents[1]


def build_local_orchestrator() -> PsychOrchestrator:
    data_dir = ROOT / "data" / "eval"
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{data_dir / 'eval.sqlite'}", connect_args={"check_same_thread": False})
    create_schema(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    store = DatabaseStore(session_factory)
    knowledge_dir = ROOT / "app" / "knowledge"
    store.rebuild_knowledge_dir(knowledge_dir)
    registry = SkillRegistry(knowledge_dir, store.add_report, store.search_knowledge)
    return PsychOrchestrator(registry, store, MockLLMClient())


def main() -> None:
    orchestrator = build_local_orchestrator()
    results = run_evaluation(orchestrator, orchestrator.store, ROOT / "eval" / "fixtures", ROOT / "data" / "eval")
    print(results["summary"])


if __name__ == "__main__":
    main()
