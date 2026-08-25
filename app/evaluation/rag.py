from __future__ import annotations

import json
import math
import tempfile
import time
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
    strict_hits = [item for item in results if item["hit_strict"]]
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
        "hitRateStrict": round(len(strict_hits) / total, 4),
        "strictSourceMatches": len(strict_hits),
        "averageFirstRelevantRank": round(sum(item["firstRelevantRank"] for item in hits) / max(1, len(hits)), 4),
        "ablation": run_ablation(store, cases, settings.knowledge_top_k),
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
    first_strict_rank = 0
    relevant_count = 0
    for index, item in enumerate(retrieved, start=1):
        relevant, strict = is_relevant(item.get("source", ""), item.get("content", "") or item.get("snippet", ""), expected_sources, expected_terms)
        if relevant:
            relevant_count += 1
            if first_rank == 0:
                first_rank = index
        if strict and first_strict_rank == 0:
            first_strict_rank = index
        items.append(
            {
                "rank": index,
                "chunkId": item.get("chunk_id"),
                "source": item.get("source"),
                "score": item.get("score"),
                "relevant": relevant,
                "relevant_strict": strict,
                "preview": " ".join(str(item.get("content") or item.get("snippet") or "").split())[:160],
            }
        )
    hit = first_rank > 0
    hit_strict = first_strict_rank > 0
    return {
        "id": case["id"],
        "question": case["question"],
        "expectedSources": case.get("expectedSources", []),
        "expectedTerms": case.get("expectedTerms", []),
        "retrieved": items,
        "hit": hit,
        "hit_strict": hit_strict,
        "firstRelevantRank": first_rank,
        "recallAtK": 1.0 if hit else 0.0,
        "precisionAtK": round(relevant_count / max(1, top_k), 4),
        "reciprocalRank": round(1.0 / first_rank, 4) if hit else 0.0,
        "ndcgAtK": round(ndcg(items), 4),
    }


def is_relevant(source: str, content: str, expected_sources: set[str], expected_terms: list[str]) -> tuple[bool, bool]:
    """返回 (宽松命中, 严格命中)。

    - 宽松命中: 来源文件命中或任意 expected term 出现在内容中(现行口径)
    - 严格命中: 仅来源文件命中
    """
    stripped = source.lower()
    source_hit = stripped in expected_sources
    if source_hit:
        return True, True
    lower = content.lower()
    loose = any(len(term) >= 2 and term in lower for term in expected_terms)
    return loose, False


def run_ablation(store: DatabaseStore, cases: list[dict], top_k: int) -> dict:
    """检索消融实验:同数据集对比不同检索配置的命中率与耗时。

    配置:
    - bm25_only: 关闭向量(仅 BM25 + rerank)
    - hybrid: 开启 local 向量 + BM25 融合
    - hybrid_rerank: hybrid + rerank(生产默认)
    - rrf: RRF 融合
    """
    from app.rag.vector_store import build_vector_backend

    original_backend = store.vector_backend
    original_rerank = store.settings.knowledge_rerank_enabled
    original_fusion = store.settings.knowledge_fusion_mode

    def _swap_vector(enabled: bool) -> None:
        """按模式重建向量后端;开启时重建索引以填充本地向量记录。"""
        cloned = Settings(
            **{
                **store.settings.model_dump(),
                "vector_enabled": enabled,
                "vector_backend": "local",
                "openai_api_key": "",
                "vector_required": False,
            }
        )
        store.settings.vector_enabled = enabled
        store.vector_backend = build_vector_backend(cloned)
        if enabled:
            store.rebuild_vector_index()

    modes = ["bm25_only", "hybrid", "hybrid_rerank", "rrf"]
    ablation = {}
    try:
        for mode in modes:
            if mode == "bm25_only":
                _swap_vector(False)
                store.settings.knowledge_rerank_enabled = True
                store.settings.knowledge_fusion_mode = "weighted"
            elif mode == "hybrid":
                _swap_vector(True)
                store.settings.knowledge_rerank_enabled = False
                store.settings.knowledge_fusion_mode = "weighted"
            elif mode == "hybrid_rerank":
                _swap_vector(True)
                store.settings.knowledge_rerank_enabled = True
                store.settings.knowledge_fusion_mode = "weighted"
            elif mode == "rrf":
                _swap_vector(True)
                store.settings.knowledge_rerank_enabled = False
                store.settings.knowledge_fusion_mode = "rrf"

            hits = 0
            total_latency = 0.0
            for case in cases:
                t0 = time.perf_counter()
                retrieved = store.search_knowledge(case["question"], top_k)
                total_latency += time.perf_counter() - t0
                expected_sources = {source.lower() for source in case.get("expectedSources", [])}
                expected_terms = [term.lower() for term in case.get("expectedTerms", [])]
                if any(
                    is_relevant(item.get("source", ""), item.get("content") or item.get("snippet", ""), expected_sources, expected_terms)[0]
                    for item in retrieved
                ):
                    hits += 1
            ablation[mode] = {
                "hitRate": round(hits / max(1, len(cases)), 4),
                "hitCount": hits,
                "totalCases": len(cases),
                "avgLatencyMs": round(total_latency / max(1, len(cases)) * 1000, 2),
            }
    finally:
        # 还原原配置
        store.vector_backend = original_backend
        store.settings.knowledge_rerank_enabled = original_rerank
        store.settings.knowledge_fusion_mode = original_fusion
    return ablation


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
    for key in ["totalCases", "topK", "recallAtK", "precisionAtK", "mrr", "ndcgAtK", "hitRate", "hitRateStrict", "averageFirstRelevantRank"]:
        print(f"{key}={report[key]}")
    print("\n=== ABLATION (HitRate) ===")
    for mode, metrics in report["ablation"].items():
        print(f"{mode:<15} hitRate={metrics['hitRate']} hitCount={metrics['hitCount']}/{metrics['totalCases']} avgLatencyMs={metrics['avgLatencyMs']}")
