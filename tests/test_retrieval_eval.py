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
        embedding_provider="openai",
        chroma_dir=str(tmp_path / "chroma"),
    )
    backend = build_vector_backend(settings)
    assert backend.backend_name == "local"
    assert backend.enabled() is True


def test_chroma_required_without_api_key_raises():
    settings = Settings(vector_enabled=True, vector_backend="chroma", vector_required=True, openai_api_key="", embedding_provider="openai")
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
    
    # 验证 RAG 报告写入临时输出目录，不覆盖项目正式报告
    rag_report = output_dir / "rag-eval-report.json"
    assert rag_report.exists(), "RAG report should be written to output_dir"
    
    formal_report = Path(__file__).resolve().parents[1] / "data" / "eval" / "rag-eval-report.json"
    if formal_report.exists():
        # 如果正式报告存在，确认其 mtime 未被此测试修改
        import json
        formal_data = json.loads(formal_report.read_text(encoding="utf-8"))
        assert formal_data.get("totalCases") != results["rag_eval"].get("totalCases") or \
               formal_data.get("dataset") != results["rag_eval"].get("dataset"), \
               "Test should not overwrite formal RAG report"


def test_scaled_benchmark_supports_layer_split(tmp_path: Path):
    """150 条规模化基准应按 layer(base/stress) 分层，且两层覆盖全部样本。"""
    store, orchestrator = build_store(tmp_path / "eval", vector_enabled=False)
    fixtures_dir = Path(__file__).resolve().parents[1] / "eval" / "fixtures"
    output_dir = tmp_path / "out"

    results = run_evaluation(orchestrator, store, fixtures_dir, output_dir)
    scaled = results["scaled_benchmark"]

    assert "by_layer" in scaled
    assert set(scaled["by_layer"].keys()) >= {"base", "stress"}
    covered = sum(v["total"] for v in scaled["by_layer"].values())
    assert covered == scaled["total"] == 150

    summary = results["summary"]
    assert "scaled_base_accuracy" in summary
    assert "scaled_stress_accuracy" in summary
    assert "scaled_base_high_recall" in summary
    assert "scaled_stress_high_recall" in summary
    # 压力层（隐式/无词样本）准确率应低于基础层，验证分层确实区分了难度
    assert summary["scaled_stress_accuracy"] <= summary["scaled_base_accuracy"]
