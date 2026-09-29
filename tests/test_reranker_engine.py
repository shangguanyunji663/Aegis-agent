"""Cross-Encoder 重排引擎单元测试:纯逻辑路径,不加载真实 ONNX 模型。"""
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.repository import DatabaseStore
from app.rag import reranker
from app.rag.reranker import _sigmoid, cross_encoder_rerank, reset_cache


def build_store(tmp_path: Path, **overrides) -> DatabaseStore:
    tmp_path.mkdir(parents=True, exist_ok=True)
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(exist_ok=True)
    (knowledge_dir / "exam.md").write_text("考试压力 睡不着 焦虑 可以先稳定身体反应并拆分任务", encoding="utf-8")
    (knowledge_dir / "sleep.md").write_text("失眠 入睡困难 保持规律作息 避免睡前使用手机", encoding="utf-8")
    params = {
        "database_url": f"sqlite:///{tmp_path / 't.sqlite'}",
        "knowledge_dir": str(knowledge_dir),
        "vector_enabled": False,
        "vector_required": False,
        "openai_api_key": "",
    }
    params.update(overrides)
    settings = Settings(**params)
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    store = DatabaseStore(session_factory, settings=settings)
    store.seed_knowledge_dir(knowledge_dir)
    return store


def test_sigmoid_bounded():
    assert _sigmoid(0.0) == 0.5
    assert 0.0 <= _sigmoid(-50.0) < 0.01
    assert 0.99 < _sigmoid(50.0) <= 1.0


def test_model_missing_raises(tmp_path):
    reset_cache()
    empty = tmp_path / "no-model"
    empty.mkdir()
    from app.entities import KnowledgeChunk

    ranked = [(KnowledgeChunk(source="a.md", source_index=0, content="内容"), 0.5)]
    with pytest.raises(RuntimeError):
        cross_encoder_rerank("q", ranked, str(empty))
    reset_cache()


def test_default_engine_is_lexical(tmp_path):
    store = build_store(tmp_path / "lexical")
    assert store.settings.knowledge_rerank_engine == "lexical"
    rows = store.search_knowledge("考试压力睡不着", top_k=2)
    assert rows and rows[0]["source"] == "exam.md"


def test_cross_engine_two_stage(monkeypatch, tmp_path):
    store = build_store(tmp_path / "ce", knowledge_rerank_engine="cross_encoder")
    seen = {}

    def fake_rerank(query, ranked, model_dir):
        seen["query"] = query
        seen["n"] = len(ranked)
        seen["model_dir"] = model_dir
        return [(chunk, 0.42) for chunk, _ in ranked]

    monkeypatch.setattr(reranker, "cross_encoder_rerank", fake_rerank)
    rows = store.search_knowledge("考试压力睡不着", top_k=2)
    assert rows
    assert seen["n"] >= 1
    assert seen["query"]
    assert "bge-reranker-base-onnx" in seen["model_dir"]
    assert float(rows[0]["score"]) == pytest.approx(0.42)


def test_cross_engine_fallback_to_lexical(monkeypatch, tmp_path):
    store = build_store(tmp_path / "fallback", knowledge_rerank_engine="cross_encoder")

    def boom(query, ranked, model_dir):
        raise RuntimeError("model missing")

    monkeypatch.setattr(reranker, "cross_encoder_rerank", boom)
    rows = store.search_knowledge("考试压力睡不着", top_k=2)
    assert rows
    assert "fallback to lexical" in (store.vector_error or "")

    lexical_store = build_store(tmp_path / "plain")
    rows_lexical = lexical_store.search_knowledge("考试压力睡不着", top_k=2)
    assert [r["source"] for r in rows] == [r["source"] for r in rows_lexical]
