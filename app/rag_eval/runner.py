from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings, get_settings
from app.database import build_session_factory, create_schema
from app.repository import DatabaseStore


def evaluate(store: DatabaseStore | None = None, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    owned_store = store is None
    if store is None:
        session_factory = build_session_factory(settings)
        create_schema()
        store = DatabaseStore(session_factory, settings=settings)
        store.rebuild_knowledge_dir(settings.resolve_path(settings.knowledge_dir))
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
    output = settings.resolve_path(settings.rag_eval_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
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
    report = evaluate()
    print("Aegis RAG evaluation completed.")
    for key in ["totalCases", "topK", "recallAtK", "precisionAtK", "mrr", "ndcgAtK", "hitRate", "averageFirstRelevantRank"]:
        print(f"{key}={report[key]}")
