from __future__ import annotations

import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings, get_settings
from app.database import build_engine, build_session_factory, create_schema
from app.repository import DatabaseStore


def evaluate(store: DatabaseStore | None = None, settings: Settings | None = None, output_path: Path | None = None) -> dict:
    settings = settings or get_settings()
    owned_store = store is None
    if store is None:
        # 独立运行（CLI/__main__）时构造一次性 SQLite 评测库，避免依赖默认 database_url
        # （默认可能为 mysql，进而触发 pymysql；评测检索只需本地知识库索引，无需 MySQL）。
        tmp_db = Path(tempfile.mkdtemp()) / "rag-eval.sqlite"
        eval_settings = Settings(
            database_url=f"sqlite:///{tmp_db}",
            knowledge_dir=settings.knowledge_dir,
            knowledge_top_k=settings.knowledge_top_k,
            vector_enabled=False,
        )
        session_factory = build_session_factory(eval_settings)
        create_schema(build_engine(eval_settings))
        store = DatabaseStore(session_factory, settings=eval_settings)
        store.rebuild_knowledge_dir(eval_settings.resolve_path(eval_settings.knowledge_dir))
        settings = eval_settings
    dataset_path = settings.resolve_path(settings.rag_eval_dataset)
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    results = [evaluate_case(store, case, settings.knowledge_top_k) for case in cases]
    total = max(1, len(results))
    hits = [item for item in results if item["hit"]]
    report = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path),
        "topK": settings.knowledge_top_k,
        "totalCases": len(results),
        "recallAtK": round(sum(item["recallAtK"] for item in results) / total, 4),
        "precisionAtK": round(sum(item["precisionAtK"] for item in results) / total, 4),
        "mrr": round(sum(item["reciprocalRank"] for item in results) / total, 4),
        "ndcgAtK": round(sum(item["ndcgAtK"] for item in results) / total, 4),
        "hitRate": round(len(hits) / total, 4),
        "averageFirstRelevantRank": round(sum(item["firstRelevantRank"] for item in hits) / max(1, len(hits)), 4),
        "results": results,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if owned_store and getattr(store, "redis_client", None) is not None:
        store.redis_client.close()
    return report


def evaluate_case(store: DatabaseStore, case: dict, top_k: int) -> dict:
    retrieved = store.search_knowledge(case["question"], top_k)
    expected_sources = {source.lower() for source in case.get("expectedSources", [])}
    expected_terms = [term.lower() for term in case.get("expectedTerms", [])]
    items = []
    first_rank = 0
    relevant_count = 0
    for index, item in enumerate(retrieved, start=1):
        relevant = is_relevant(item.get("source", ""), item.get("content", "") or item.get("snippet", ""), expected_sources, expected_terms)
        if relevant:
            relevant_count += 1
            if first_rank == 0:
                first_rank = index
        items.append(
            {
                "rank": index,
                "chunkId": item.get("chunk_id"),
                "source": item.get("source"),
                "score": item.get("score"),
                "relevant": relevant,
                "preview": " ".join(str(item.get("content") or item.get("snippet") or "").split())[:160],
            }
        )
    hit = first_rank > 0
    return {
        "id": case["id"],
        "question": case["question"],
        "expectedSources": case.get("expectedSources", []),
        "expectedTerms": case.get("expectedTerms", []),
        "retrieved": items,
        "hit": hit,
        "firstRelevantRank": first_rank,
        "recallAtK": 1.0 if hit else 0.0,
        "precisionAtK": round(relevant_count / max(1, top_k), 4),
        "reciprocalRank": round(1.0 / first_rank, 4) if hit else 0.0,
        "ndcgAtK": round(ndcg(items), 4),
    }


def is_relevant(source: str, content: str, expected_sources: set[str], expected_terms: list[str]) -> bool:
    if source.lower() in expected_sources:
        return True
    lower = content.lower()
    return any(len(term) >= 2 and term in lower for term in expected_terms)


def ndcg(items: list[dict]) -> float:
    dcg = 0.0
    relevant = 0
    for index, item in enumerate(items):
        if item["relevant"]:
            relevant += 1
            dcg += 1.0 / math.log2(index + 2.0)
    if relevant == 0:
        return 0.0
    ideal = sum(1.0 / math.log2(index + 2.0) for index in range(relevant))
    return dcg / ideal


if __name__ == "__main__":
    settings = get_settings()
    output_path = settings.resolve_path(settings.rag_eval_output)
    report = evaluate(output_path=output_path)
    print("Aegis RAG evaluation completed.")
    for key in ["totalCases", "topK", "recallAtK", "precisionAtK", "mrr", "ndcgAtK", "hitRate", "averageFirstRelevantRank"]:
        print(f"{key}={report[key]}")
