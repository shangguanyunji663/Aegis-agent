from __future__ import annotations

import json
import math
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings, get_settings
from app.database import build_engine, build_session_factory, create_schema
from app.repository import DatabaseStore


def _release_vector_backend(backend) -> None:
    """释放向量后端持有的文件句柄(chroma PersistentClient 的 SQLite 文件锁)。

    便于随后清理临时目录——Windows 下被打开的文件无法删除;非 chroma 后端
    (local/disabled 无 client)安全跳过,close() 本身幂等。
    """
    client = getattr(backend, "client", None)
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def evaluate(
    store: DatabaseStore | None = None,
    settings: Settings | None = None,
    output_path: Path | None = None,
    vector_enabled: bool | None = None,
) -> dict:
    """运行 RAG 检索评测。

    vector_enabled 控制向量路口径：
    - None：继承真实配置（生产口径，如 .env 的 chroma + MiniLM）
    - True：强制开启向量
    - False：强制关闭向量（纯词法口径）

    独立运行（store 为 None）时一切副作用均落在临时目录内：
    评测 SQLite、chroma 索引与快照都写入 mkdtemp 目录，不触碰生产
    database_url / data/chroma / data/chroma-snapshots。
    """
    base_settings = settings or get_settings()
    owned_store = store is None
    eval_tmp_root: Path | None = None
    schema_engine = None
    if store is None:
        # 独立运行（CLI/__main__）时构造一次性评测环境：
        # - SQLite 评测库（避免依赖默认 database_url，如 mysql，进而触发 pymysql）
        # - 隔离的临时 chroma 目录（避免重建索引污染生产 data/chroma 与快照）
        # 其余配置（embedding_provider / vector_backend / 融合权重等）继承真实 .env，
        # 使评测结果反映生产口径。
        eval_tmp_root = Path(tempfile.mkdtemp(prefix="aegis-rag-eval-"))
        overrides: dict = {
            "database_url": f"sqlite:///{eval_tmp_root / 'rag-eval.sqlite'}",
            "chroma_dir": str(eval_tmp_root / "chroma"),
            "chroma_snapshot_dir": str(eval_tmp_root / "chroma-snapshots"),
            "redis_url": "",
        }
        if vector_enabled is not None:
            overrides["vector_enabled"] = vector_enabled
        eval_settings = Settings(**{**base_settings.model_dump(), **overrides})
        # schema 建表与会话工厂各需一个 engine;保存引用以便评测结束统一 dispose,
        # 否则连接池句柄会锁定临时 SQLite,导致目录清理残留(Windows)。
        schema_engine = build_engine(eval_settings)
        session_factory = build_session_factory(eval_settings)
        create_schema(schema_engine)
        store = DatabaseStore(session_factory, settings=eval_settings)
        store.rebuild_knowledge_dir(eval_settings.resolve_path(eval_settings.knowledge_dir))
        settings = eval_settings
    dataset_path = settings.resolve_path(settings.rag_eval_dataset)
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    results = [evaluate_case(store, case, settings.knowledge_top_k) for case in cases]
    total = max(1, len(results))
    hits = [item for item in results if item["hit"]]
    strict_hits = [item for item in results if item["hit_strict"]]
    retrieval_config = {
        "vectorEnabled": store.settings.vector_enabled,
        "vectorBackend": store.vector_backend.backend_name,
        "embeddingModel": getattr(store.vector_backend, "embedding_model", "none"),
        "embeddingProvider": store.settings.embedding_provider,
        "fusionMode": store.settings.knowledge_fusion_mode,
        "rerankEnabled": store.settings.knowledge_rerank_enabled,
        "rerankEngine": store.settings.knowledge_rerank_engine,
        "vectorWeight": store.settings.knowledge_hybrid_vector_weight,
        "bm25Weight": store.settings.knowledge_hybrid_bm25_weight,
        "topK": settings.knowledge_top_k,
    }
    report = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path),
        "topK": settings.knowledge_top_k,
        "retrievalConfig": retrieval_config,
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
    if owned_store:
        if getattr(store, "redis_client", None) is not None:
            store.redis_client.close()
        if eval_tmp_root is not None:
            # 释放全部 SQLite 连接池与 chroma 文件句柄(Windows 下被占用文件无法删除),尽力清理
            for engine in (schema_engine, getattr(store.db_factory, "kw", {}).get("bind")):
                dispose = getattr(engine, "dispose", None)
                if callable(dispose):
                    try:
                        dispose()
                    except Exception:
                        pass
            _release_vector_backend(store.vector_backend)
            shutil.rmtree(eval_tmp_root, ignore_errors=True)
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

    配置矩阵(与生产语义对齐,每个模式的生效配置记录在 config 字段):
    - bm25_only: 关闭向量(仅 BM25 + 词法重排)
    - hybrid: 开启向量 + BM25 融合(无重排)
    - hybrid_rerank: hybrid + 词法重排(生产默认)
    - rrf: RRF 排名融合(无重排)

    向量路复用 store 的真实配置(chroma + 真实嵌入模型,MiniLM/OpenAI 兼容 API),
    不再硬编码降级后端;当 store 当前向量后端已有索引数据时直接复用(只读检索,
    不写索引),否则在隔离的临时 chroma 目录内重建,跑完即清理,不触碰生产索引。
    """
    from app.rag.vector_store import build_vector_backend

    original_backend = store.vector_backend
    original_rerank = store.settings.knowledge_rerank_enabled
    original_fusion = store.settings.knowledge_fusion_mode
    original_vector_enabled = store.settings.vector_enabled

    # 复用当前已启用且有数据的 chroma 后端(主评测刚建好的隔离索引 / 生产已有索引),
    # 避免消融对同一知识库重复全量嵌入;否则在临时目录内重建一份。
    reuse_backend = None
    if (
        getattr(original_backend, "backend_name", "") == "chroma"
        and original_backend.enabled()
        and original_backend.count() > 0
    ):
        reuse_backend = original_backend

    tmp_root = Path(tempfile.mkdtemp(prefix="aegis-ablation-"))
    vector_cache: list = []

    def _swap_vector(enabled: bool) -> None:
        """按模式切换向量后端;真实后端的索引只建一次,后续模式复用实例。"""
        if enabled and vector_cache:
            store.settings.vector_enabled = True
            store.vector_backend = vector_cache[0]
            return
        if enabled and reuse_backend is not None:
            store.settings.vector_enabled = True
            store.vector_backend = reuse_backend
            vector_cache.append(reuse_backend)
            return
        overrides: dict = {"vector_enabled": enabled, "vector_required": False}
        if store.settings.vector_backend.strip().lower() in {"chroma", "openai", "openai-chroma"}:
            overrides["chroma_dir"] = str(tmp_root / "chroma")
            overrides["chroma_snapshot_dir"] = str(tmp_root / "snapshots")
        cloned = Settings(**{**store.settings.model_dump(), **overrides})
        store.settings.vector_enabled = enabled
        store.vector_backend = build_vector_backend(cloned)
        if enabled:
            store.rebuild_vector_index()
            vector_cache.append(store.vector_backend)

    mode_configs = {
        "bm25_only": {"vector": False, "rerank": True, "fusion": "weighted"},
        "hybrid": {"vector": True, "rerank": False, "fusion": "weighted"},
        "hybrid_rerank": {"vector": True, "rerank": True, "fusion": "weighted"},
        "rrf": {"vector": True, "rerank": False, "fusion": "rrf"},
    }
    ablation = {}
    try:
        for mode, config in mode_configs.items():
            _swap_vector(config["vector"])
            store.settings.knowledge_rerank_enabled = config["rerank"]
            store.settings.knowledge_fusion_mode = config["fusion"]

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
                "config": {
                    "vectorEnabled": config["vector"],
                    "rerankEnabled": config["rerank"],
                    "fusionMode": config["fusion"],
                    "backend": store.vector_backend.backend_name,
                    "embeddingModel": getattr(store.vector_backend, "embedding_model", "none"),
                },
            }
    finally:
        # 还原全部原始配置(含 vector_enabled,避免评测后状态残留)
        store.vector_backend = original_backend
        store.settings.knowledge_rerank_enabled = original_rerank
        store.settings.knowledge_fusion_mode = original_fusion
        store.settings.vector_enabled = original_vector_enabled
        # 仅释放本函数新建的隔离后端(复用的后端归其所有者管理);临时目录总是清理
        if reuse_backend is None:
            for backend in vector_cache:
                _release_vector_backend(backend)
        shutil.rmtree(tmp_root, ignore_errors=True)
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
    import sys

    args = set(sys.argv[1:])
    vector_choice: bool | None = None
    if "--lexical-only" in args:
        vector_choice = False
    elif "--with-vector" in args:
        vector_choice = True
    settings = get_settings()
    output_path = settings.resolve_path(settings.rag_eval_output)
    report = evaluate(output_path=output_path, vector_enabled=vector_choice)
    print("Aegis RAG evaluation completed.")
    config = report.get("retrievalConfig", {})
    print(
        f"retrieval: enabled={config.get('vectorEnabled')} backend={config.get('vectorBackend')} "
        f"embedding={config.get('embeddingModel')} fusion={config.get('fusionMode')} rerank={config.get('rerankEnabled')}"
    )
    for key in ["totalCases", "topK", "recallAtK", "precisionAtK", "mrr", "ndcgAtK", "hitRate", "hitRateStrict", "averageFirstRelevantRank"]:
        print(f"{key}={report[key]}")
    print("\n=== ABLATION (HitRate) ===")
    for mode, metrics in report["ablation"].items():
        cfg = metrics.get("config", {})
        print(
            f"{mode:<15} hitRate={metrics['hitRate']} hitCount={metrics['hitCount']}/{metrics['totalCases']} "
            f"avgLatencyMs={metrics['avgLatencyMs']} backend={cfg.get('backend')} embedding={cfg.get('embeddingModel')}"
        )
