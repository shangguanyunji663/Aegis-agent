# -*- coding: utf-8 -*-
"""路 3 实测：Chroma + 本地 MiniLM 向量召回 vs BM25-only，77 条查询逐条对照。

- 一次性 SQLite + 临时 chroma 目录，不碰 data/chroma 生产索引
- 四种模式：bm25_only / hybrid_minilm / hybrid_rerank_minilm / rrf_minilm
- 输出：data/eval/minilm-eval-report.json + 控制台摘要
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

tmp = Path(tempfile.mkdtemp(prefix="aegis-minilm-eval-"))
tmp_db = tmp / "eval.sqlite"
settings = Settings(
    database_url=f"sqlite:///{tmp_db}",
    vector_enabled=True,
    vector_backend="chroma",
    embedding_provider="local",
    chroma_dir=str(tmp / "chroma"),
    vector_required=False,
)
session_factory = build_session_factory(settings)
create_schema(build_engine(settings))
store = DatabaseStore(session_factory, settings=settings)
store.rebuild_knowledge_dir(settings.resolve_path(settings.knowledge_dir))
n_vec = store.vector_backend.count()
print(f"[index] chroma chunks = {n_vec}, embedding = {store.vector_backend.embedding_model}")

cases = json.loads(Path("eval/fixtures/rag_queries.json").read_text(encoding="utf-8"))
print(f"[dataset] {len(cases)} cases, top_k={settings.knowledge_top_k}")

original = {
    "vector_enabled": store.settings.vector_enabled,
    "rerank": store.settings.knowledge_rerank_enabled,
    "fusion": store.settings.knowledge_fusion_mode,
    "backend": store.vector_backend,
}


def run_mode(name, vector_enabled, rerank, fusion="weighted"):
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
    store.settings.knowledge_fusion_mode = fusion
    store.vector_backend = build_vector_backend(cloned)
    assert store.vector_backend.enabled() == vector_enabled, f"{name}: backend enable mismatch"

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
    print(f"[{name:<22}] hit {hits}/{len(cases)} ({hits/len(cases):.4f})  avg {latency/len(cases)*1000:.2f} ms")
    return {"hits": hits, "per_case": per_case, "avg_ms": round(latency / len(cases) * 1000, 2)}


results = {}
results["bm25_only"] = run_mode("bm25_only", False, True)
results["hybrid_minilm"] = run_mode("hybrid_minilm", True, False)
results["hybrid_rerank_minilm"] = run_mode("hybrid_rerank_minilm", True, True)
results["rrf_minilm"] = run_mode("rrf_minilm", True, False, fusion="rrf")

# 还原
store.settings.vector_enabled = original["vector_enabled"]
store.settings.knowledge_rerank_enabled = original["rerank"]
store.settings.knowledge_fusion_mode = original["fusion"]
store.vector_backend = original["backend"]

# 逐条对照：bm25_only vs hybrid_minilm
base = results["bm25_only"]["per_case"]
hyb = results["hybrid_minilm"]["per_case"]
lost = [cid for cid, h in base.items() if h and not hyb.get(cid)]
gained = [cid for cid, h in base.items() if not h and hyb.get(cid)]
print(f"\n[delta] bm25_only 命中但 hybrid_minilm 漏掉 {len(lost)} 条: {lost}")
print(f"[delta] hybrid_minilm 新增命中 {len(gained)} 条: {gained}")

report = {
    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "backend": "chroma + local-minilm (chromadb 1.5.9 DefaultEmbeddingFunction, 384-dim)",
    "chromaChunks": n_vec,
    "totalCases": len(cases),
    "topK": settings.knowledge_top_k,
    "modes": {k: {"hitRate": round(v["hits"] / len(cases), 4), "hitCount": v["hits"], "avgLatencyMs": v["avg_ms"]} for k, v in results.items()},
    "bm25OnlyLost": lost,
    "hybridGained": gained,
}
out = Path("data/eval/minilm-eval-report.json")
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[saved] {out}")
