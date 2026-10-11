# -*- coding: utf-8 -*-
"""bge-small-zh-v1.5 召回层实测（中文模型替换英文 MiniLM 的验证实验）。

- 隔离环境：一次性 SQLite + 临时 chroma 目录（不碰生产 data/）
- 嵌入：local-zh 生产路径（LocalZhEmbeddingFunction，ONNX CPU）
- 配置矩阵：bm25_only 基线 + hybrid/hybrid_rerank（w0.2/0.35/0.5）+ rrf
- 输出：data/eval/bge-small-zh-recall-report.json（含逐条 perCase，供后续对照）
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from app.config import Settings, get_settings
from app.database import build_engine, build_session_factory, create_schema
from app.evaluation.rag import _release_vector_backend, is_relevant
from app.repository import DatabaseStore
from app.rag.vector_store import build_vector_backend

base = get_settings()
cases = json.loads((ROOT / "eval" / "fixtures" / "rag_queries.json").read_text(encoding="utf-8"))
top_k = base.knowledge_top_k

tmp = Path(tempfile.mkdtemp(prefix="aegis-bge-zh-"))
settings = Settings(
    **{
        **base.model_dump(),
        "database_url": f"sqlite:///{tmp / 'eval.sqlite'}",
        "chroma_dir": str(tmp / "chroma"),
        "chroma_snapshot_dir": str(tmp / "snapshots"),
        "redis_url": "",
        "vector_enabled": True,
        "vector_required": True,
        "embedding_provider": "local-zh",
    }
)
schema_engine = build_engine(settings)
session_factory = build_session_factory(settings)
create_schema(schema_engine)
store = DatabaseStore(session_factory, settings=settings)
store.rebuild_knowledge_dir(settings.resolve_path(settings.knowledge_dir))
enabled_backend = store.vector_backend
print(
    f"[index] backend={enabled_backend.backend_name} chunks={enabled_backend.count()} "
    f"model={getattr(enabled_backend, 'embedding_model', '?')}"
)
assert enabled_backend.backend_name == "chroma" and enabled_backend.count() > 0

results = {}


def run_config(name: str, vector: bool, rerank: bool, weight: float, fusion: str = "weighted") -> dict:
    store.settings.knowledge_hybrid_vector_weight = weight
    store.settings.knowledge_hybrid_bm25_weight = round(1.0 - weight, 4)
    store.settings.knowledge_rerank_enabled = rerank
    store.settings.knowledge_fusion_mode = fusion
    store.settings.vector_enabled = vector
    if vector:
        store.vector_backend = enabled_backend
    else:
        store.vector_backend = build_vector_backend(
            Settings(**{**settings.model_dump(), "vector_enabled": False})
        )
    hits = 0
    latency = 0.0
    per_case = {}
    for case in cases:
        t0 = time.perf_counter()
        got = store.search_knowledge(case["question"], top_k)
        latency += time.perf_counter() - t0
        exp_sources = {s.lower() for s in case.get("expectedSources", [])}
        exp_terms = case.get("expectedTerms", [])
        hit = any(
            is_relevant(i.get("source", ""), i.get("content") or i.get("snippet", ""), exp_sources, exp_terms)[0]
            for i in got
        )
        per_case[case["id"]] = hit
        hits += int(hit)
    avg_ms = round(latency / len(cases) * 1000, 1)
    print(f"[{name:<26}] hit {hits}/{len(cases)} ({hits / len(cases):.4f})  avg {avg_ms} ms")
    return {"hitRate": round(hits / len(cases), 4), "hitCount": hits, "avgLatencyMs": avg_ms, "perCase": per_case}


print("\n== bge-small-zh-v1.5 召回层实测 ==")
results["bm25_only"] = run_config("bm25_only", False, True, 0.0)
for weight in (0.2, 0.35, 0.5):
    results[f"hybrid_w{weight}"] = run_config(f"hybrid w={weight}", True, False, weight)
    results[f"hybrid_rerank_w{weight}"] = run_config(f"hybrid_rerank w={weight}", True, True, weight)
results["rrf_w0.35"] = run_config("rrf w=0.35", True, False, 0.35, fusion="rrf")

reference = {
    "minilm_w0_2": {"note": "MiniLM w0.2 最优（fusion-tuning-report.json）", "hybrid": 73, "hybrid_rerank": 72, "rrf": 64},
    "minilm_w0_65": {"note": "9/29 表（w0.65）", "hybrid": 66, "hybrid_rerank": 67, "rrf": 64},
    "zhipu_w0_35": {"note": "中文强嵌入参照（fusion-tuning-report-openai.json）", "hybrid": 74, "hybrid_rerank": 76, "rrf": 76},
}

report = {
    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "backend": "chroma + bge-small-zh-v1.5 (ONNX int8/fp32, CLS pooling)",
    "totalCases": len(cases),
    "topK": top_k,
    "configs": {k: {kk: vv for kk, vv in v.items() if kk != "perCase"} for k, v in results.items()},
    "perCase": {k: v["perCase"] for k, v in results.items()},
    "reference": reference,
}
out = ROOT / "data" / "eval" / "bge-small-zh-recall-report.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n[saved] {out}")

schema_engine.dispose()
getattr(store.db_factory, "kw", {}).get("bind").dispose()
_release_vector_backend(enabled_backend)
shutil.rmtree(tmp, ignore_errors=True)
print("DONE")
