# -*- coding: utf-8 -*-
"""Cross-Encoder 精排实测：bm25+CE 与 hybrid(MiniLM)+CE，与基准对照。

前置：data/models/bge-reranker-base-onnx/ 下已有 model_quantized.onnx + tokenizer.json
输出：data/eval/ce-eval-report.json + 控制台摘要
"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.database import build_engine, build_session_factory, create_schema
from app.repository import DatabaseStore
from app.evaluation.rag import is_relevant
from app.rag.vector_store import build_vector_backend

tmp = Path(tempfile.mkdtemp(prefix="aegis-ce-eval-"))
tmp_db = tmp / "eval.sqlite"
settings = Settings(
    database_url=f"sqlite:///{tmp_db}",
    vector_enabled=True,
    vector_backend="chroma",
    embedding_provider="local",
    chroma_dir=str(tmp / "chroma"),
    chroma_snapshot_dir=str(tmp / "snapshots"),
    vector_required=False,
    knowledge_rerank_engine="cross_encoder",
)
session_factory = build_session_factory(settings)
create_schema(build_engine(settings))
store = DatabaseStore(session_factory, settings=settings)
store.rebuild_knowledge_dir(settings.resolve_path(settings.knowledge_dir))
print(f"[index] chroma chunks = {store.vector_backend.count()}")

cases = json.loads(Path("eval/fixtures/rag_queries.json").read_text(encoding="utf-8"))
print(f"[dataset] {len(cases)} cases, top_k={settings.knowledge_top_k}")

original = {
    "vector_enabled": store.settings.vector_enabled,
    "rerank": store.settings.knowledge_rerank_enabled,
    "engine": store.settings.knowledge_rerank_engine,
    "fusion": store.settings.knowledge_fusion_mode,
    "backend": store.vector_backend,
}


def run_mode(name, vector_enabled, engine, rerank=True):
    cloned = Settings(
        **{
            **store.settings.model_dump(),
            "vector_enabled": vector_enabled,
            "vector_backend": "chroma",
            "embedding_provider": "local",
        }
    )
    store.settings.vector_enabled = vector_enabled
    store.settings.knowledge_rerank_enabled = rerank
    store.settings.knowledge_rerank_engine = engine
    store.settings.knowledge_fusion_mode = "weighted"
    store.vector_backend = build_vector_backend(cloned)

    hits = 0
    latency = 0.0
    per_case = {}
    for case in cases:
        t0 = time.perf_counter()
        got = store.search_knowledge(case["question"], settings.knowledge_top_k)
        latency += time.perf_counter() - t0
        exp_sources = {s.lower() for s in case.get("expectedSources", [])}
        exp_terms = case.get("expectedTerms", [])
        hit = any(
            is_relevant(i.get("source", ""), i.get("content") or i.get("snippet", ""), exp_sources, exp_terms)[0]
            for i in got
        )
        per_case[case["id"]] = hit
        hits += int(hit)
    print(f"[{name:<24}] hit {hits}/{len(cases)} ({hits/len(cases):.4f})  avg {latency/len(cases)*1000:.1f} ms")
    return {"hits": hits, "per_case": per_case, "avg_ms": round(latency / len(cases) * 1000, 1)}


results = {}
results["bm25_only"] = run_mode("bm25_only", False, "lexical")
results["bm25_cross_encoder"] = run_mode("bm25_cross_encoder", False, "cross_encoder")
results["hybrid_minilm"] = run_mode("hybrid_minilm", True, "lexical", rerank=False)
results["hybrid_minilm_ce"] = run_mode("hybrid_minilm_ce", True, "cross_encoder")

store.settings.vector_enabled = original["vector_enabled"]
store.settings.knowledge_rerank_enabled = original["rerank"]
store.settings.knowledge_rerank_engine = original["engine"]
store.settings.knowledge_fusion_mode = original["fusion"]
store.vector_backend = original["backend"]

base = results["bm25_only"]["per_case"]
ce = results["bm25_cross_encoder"]["per_case"]
ce_lost = [cid for cid, h in base.items() if h and not ce.get(cid)]
ce_gained = [cid for cid, h in base.items() if not h and ce.get(cid)]
print(f"\n[CE vs BM25] BM25 命中但 CE 漏掉 {len(ce_lost)} 条: {ce_lost}")
print(f"[CE vs BM25] CE 新增命中 {len(ce_gained)} 条: {ce_gained}")

report = {
    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "reranker": "Xenova/bge-reranker-base model_quantized.onnx (int8, onnxruntime CPU)",
    "totalCases": len(cases),
    "topK": settings.knowledge_top_k,
    "modes": {k: {"hitRate": round(v["hits"] / len(cases), 4), "hitCount": v["hits"], "avgLatencyMs": v["avg_ms"]} for k, v in results.items()},
    "ceVsBm25Lost": ce_lost,
    "ceVsBm25Gained": ce_gained,
    "vectorError": store.vector_error or "",
}
out = Path("data/eval/ce-eval-report.json")
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[saved] {out}")
