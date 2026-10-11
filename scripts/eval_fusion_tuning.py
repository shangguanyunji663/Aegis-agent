# -*- coding: utf-8 -*-
"""融合调优实验:向量权重 sweep + rerank 对照(真实嵌入,隔离环境)。

背景:修复后的主消融(与 9/29 手工实验一致)显示,vector_weight=0.65 下
hybrid 系列(hybrid 0.8571 / hybrid_rerank 0.8701 / rrf 0.8312)均低于
bm25_only(0.9351)。本实验在同一隔离环境内扫描融合权重与 rerank 开关,
用数据回答"向量权重该取多少"——权重应该被测出来,而不是预设。

- 全部副作用隔离在临时目录(独立 SQLite + 临时 chroma,不碰生产索引)
- Stage A: 权重 sweep —— hybrid_rerank × vector_weight ∈ {0.1, 0.2, 0.35, 0.5, 0.65}
- Stage B: 最优权重下 rerank on/off 对照
- 基线:bm25_only(向量关闭)
- 支持 --provider local|openai 切换嵌入(openai = .env 里的 OpenAI 兼容端点,如智谱)
- 输出: data/eval/fusion-tuning-report.json(local) / fusion-tuning-report-openai.json
"""
import argparse
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

from app.config import Settings, get_settings  # noqa: E402
from app.database import build_engine, build_session_factory, create_schema  # noqa: E402
from app.evaluation.rag import _release_vector_backend, is_relevant  # noqa: E402
from app.repository import DatabaseStore  # noqa: E402
from app.rag.vector_store import build_vector_backend  # noqa: E402

parser = argparse.ArgumentParser(description="融合调优实验(权重 sweep)")
parser.add_argument("--provider", default="local", choices=["local", "openai"], help="嵌入提供方(local=MiniLM, openai=.env 配置的兼容端点)")
args = parser.parse_args()

base = get_settings()
tmp = Path(tempfile.mkdtemp(prefix="aegis-fusion-tuning-"))
# 继承真实 .env 的向量配置(chroma + 真实嵌入),仅隔离数据库与 chroma 目录
settings = Settings(
    **{
        **base.model_dump(),
        "database_url": f"sqlite:///{tmp / 'eval.sqlite'}",
        "chroma_dir": str(tmp / "chroma"),
        "chroma_snapshot_dir": str(tmp / "snapshots"),
        "redis_url": "",
        "vector_enabled": True,
        "vector_required": False,
        "embedding_provider": args.provider,
    }
)
session_factory = build_session_factory(settings)
schema_engine = build_engine(settings)
create_schema(schema_engine)
store = DatabaseStore(session_factory, settings=settings)
store.rebuild_knowledge_dir(settings.resolve_path(settings.knowledge_dir))
enabled_backend = store.vector_backend
print(
    f"[index] backend={enabled_backend.backend_name} chunks={enabled_backend.count()} "
    f"embedding={getattr(enabled_backend, 'embedding_model', 'none')}"
)
assert enabled_backend.backend_name == "chroma" and enabled_backend.count() > 0, (
    "期望真实 chroma 向量索引;请检查 .env 的 VECTOR_* 与 EMBEDDING_PROVIDER 配置"
)

cases = json.loads((ROOT / "eval" / "fixtures" / "rag_queries.json").read_text(encoding="utf-8"))
top_k = settings.knowledge_top_k
print(f"[dataset] {len(cases)} cases top_k={top_k}")

results: dict[str, dict] = {}


def set_vector(on: bool) -> None:
    """切换向量路:开=复用已建好的 chroma 后端;关=disabled 后端。"""
    if on:
        store.vector_backend = enabled_backend
    else:
        store.vector_backend = build_vector_backend(
            Settings(**{**settings.model_dump(), "vector_enabled": False})
        )


def run_config(name: str, vector_weight: float, rerank: bool, fusion: str = "weighted") -> dict:
    store.settings.knowledge_hybrid_vector_weight = vector_weight
    store.settings.knowledge_hybrid_bm25_weight = round(1.0 - vector_weight, 4)
    store.settings.knowledge_rerank_enabled = rerank
    store.settings.knowledge_fusion_mode = fusion
    hits = 0
    latency = 0.0
    per_case: dict[str, bool] = {}
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
    print(f"[{name:<28}] hit {hits}/{len(cases)} ({hits / len(cases):.4f})  avg {avg_ms} ms")
    return {"hits": hits, "per_case": per_case, "avg_ms": avg_ms}


# 基线:向量关闭(bm25 + 词法重排)
set_vector(False)
results["bm25_only"] = run_config("bm25_only", 0.0, True)

# Stage A: 权重 sweep(向量开,rerank 开,weighted)
set_vector(True)
weight_grid = [0.1, 0.2, 0.35, 0.5, 0.65]
for w in weight_grid:
    results[f"hybrid_rerank_w{w}"] = run_config(f"hybrid_rerank w={w}", w, True)

# Stage B: 最优权重下 rerank/融合对照
best_w = max(weight_grid, key=lambda w: results[f"hybrid_rerank_w{w}"]["hits"])
results[f"hybrid_norerank_w{best_w}"] = run_config(f"hybrid(no rerank) w={best_w}", best_w, False)
results[f"rrf_w{best_w}"] = run_config(f"rrf w={best_w}", best_w, False, fusion="rrf")

# 逐条对照(vs bm25_only)
base_per_case = results["bm25_only"]["per_case"]
delta = {}
for name, res in results.items():
    if name == "bm25_only":
        continue
    lost = [cid for cid, h in base_per_case.items() if h and not res["per_case"].get(cid)]
    gained = [cid for cid, h in base_per_case.items() if not h and res["per_case"].get(cid)]
    delta[name] = {"lost": lost, "gained": gained}

report = {
    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "backend": enabled_backend.backend_name,
    "embeddingModel": getattr(enabled_backend, "embedding_model", "none"),
    "embeddingProvider": settings.embedding_provider,
    "totalCases": len(cases),
    "topK": top_k,
    "best": {"name": f"hybrid_rerank_w{best_w}", "vectorWeight": best_w},
    "configs": {
        name: {
            "hitRate": round(res["hits"] / len(cases), 4),
            "hitCount": res["hits"],
            "avgLatencyMs": res["avg_ms"],
            "lostVsBm25": delta.get(name, {}).get("lost", []),
            "gainedVsBm25": delta.get(name, {}).get("gained", []),
        }
        for name, res in results.items()
    },
}
out_name = "fusion-tuning-report.json" if args.provider == "local" else f"fusion-tuning-report-{args.provider}.json"
out = ROOT / "data" / "eval" / out_name
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n[saved] {out}")

# 释放句柄并清理隔离目录
schema_engine.dispose()
getattr(session_factory, "kw", {}).get("bind").dispose()
_release_vector_backend(enabled_backend)
shutil.rmtree(tmp, ignore_errors=True)
