from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.evaluation import run_evaluation
from app.llm import MockLLMClient
from app.agents.orchestrator import PsychOrchestrator
from app.repository import DatabaseStore
from app.skills import SkillRegistry
from app.rag.vector_store import VectorStoreUnavailable, build_vector_backend


def build_store(tmp_path: Path, vector_enabled: bool, vector_backend: str = "local") -> tuple[DatabaseStore, PsychOrchestrator]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(exist_ok=True)
    (knowledge_dir / "exam.md").write_text("考试压力 睡不着 焦虑 可以先稳定身体反应并拆分任务", encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / ('vector.sqlite' if vector_enabled else 'lexical.sqlite')}",
        knowledge_dir=str(knowledge_dir),
        vector_enabled=vector_enabled,
        vector_backend=vector_backend,
        vector_required=False,
        openai_api_key="",
    )
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    store = DatabaseStore(session_factory, settings=settings)
    store.seed_knowledge_dir(knowledge_dir)
    registry = SkillRegistry(knowledge_dir, store.add_report, store.search_knowledge)
    orchestrator = PsychOrchestrator(registry, store, MockLLMClient())
    return store, orchestrator


def test_knowledge_status_reflects_vector_mode(tmp_path: Path):
    lexical_store, _ = build_store(tmp_path / "lexical", vector_enabled=False)
    vector_store, _ = build_store(tmp_path / "vector", vector_enabled=True, vector_backend="local")

    assert lexical_store.knowledge_status()["vector_enabled"] is False
    assert vector_store.knowledge_status()["vector_enabled"] is True
    assert vector_store.knowledge_status()["candidate_k"] >= 1
    assert vector_store.knowledge_status()["embedding_model"] == "local-hash"
    assert vector_store.search_knowledge("考试压力", top_k=1)[0]["source"] == "exam.md"


def test_chroma_without_api_key_degrades_to_local(tmp_path: Path):
    settings = Settings(
        vector_enabled=True,
        vector_backend="chroma",
        vector_required=False,
        openai_api_key="",
        chroma_dir=str(tmp_path / "chroma"),
    )
    backend = build_vector_backend(settings)
    assert backend.backend_name == "local"
    assert backend.enabled() is True


def test_chroma_required_without_api_key_raises():
    settings = Settings(vector_enabled=True, vector_backend="chroma", vector_required=True, openai_api_key="")
    try:
        build_vector_backend(settings)
        assert False, "expected VectorStoreUnavailable"
    except VectorStoreUnavailable as exc:
        assert "OPENAI_API_KEY" in str(exc)


def test_eval_includes_multi_turn_and_rich_metrics(tmp_path: Path):
    store, orchestrator = build_store(tmp_path / "eval", vector_enabled=False)
    fixtures_dir = Path(__file__).resolve().parents[1] / "eval" / "fixtures"
    output_dir = tmp_path / "out"

    results = run_evaluation(orchestrator, store, fixtures_dir, output_dir)

    assert "multi_turn" in results
    assert "risk_high_recall" in results["summary"]
    assert "safety_leak_count" in results["summary"]
    assert "retrieval_mrr" in results["summary"]
    assert results["multi_turn"]["total"] >= 1
