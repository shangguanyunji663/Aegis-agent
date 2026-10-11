# -*- coding: utf-8 -*-
"""嵌入模型对照:MiniLM(chromadb 内置) vs 智谱 embedding-3(OpenAI 兼容 API)。

背景:当前 .env 生产配置为 chromadb + 本地 MiniLM(384 维,英文模型)。线上消融
显示 hybrid 系列输给 bm25_only。本实验检验"换成中文强语义嵌入"(智谱 embedding-3,
2048 维,API 已配通)能否改变结论。

- 两套嵌入各用独立临时 chroma 目录(嵌入空间不同,索引不可共用),不碰生产 data/
- 权重取 fusion-tuning-report.json 的最优解(缺省 0.35),两套嵌入公平对照
- 每套跑 hybrid / hybrid_rerank / rrf;bm25_only 只跑一次(与嵌入无关)作公共基线
- 输出: data/eval/embedding-compare-report.json

用法: python scripts/eval_embedding_compare.py
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

from app.config import Settings, get_settings  # noqa: E402
from app.database import build_engine, build_session_factory, create_schema  # noqa: E402
from app.evaluation.rag import _release_vector_backend, is_relevant  # noqa: E402
from app.repository import DatabaseStore  # noqa: E402
from app.rag.vector_store import build_vector_backend  # noqa: E402

base = get_settings()
cases = json.loads((ROOT / "eval" / "fixtures" / "rag_queries.json").read_text(encoding="utf-8"))
top_k = base.knowledge_top_k

fusion_path = ROOT / "data" / "eval" / "fusion-tuning-report.json"
best_w = 0.35
if fusion_path.exists():
    best_w = json.loads(fusion_path.read_text(encoding="utf-8")).get("best", {}).get("vectorWeight", best_w)
print(f"[config] vector_weight={best_w} bm25_weight={round(1 - best_w, 4)}")


def run_modes(store: DatabaseStore, enabled_backend, modes: list[tuple[str, bool, bool, str]]) -> dict:
    """在给定 store 上跑一组模式,返回 {name: {hitRate,hitCount,avgLatencyMs,perCase}}。"""
    disabled_backend = build_vector_backend(
        Settings(**{**store.settings.model_dump(), "vector_enabled": False})
    )
    out = {}
    for name, vector, rerank, fusion in modes:
        store.vector_backend = enabled_backend if vector else disabled_backend
        store.settings.knowledge_hybrid_vector_weight = best_w if vector else 0.0
        store.settings.knowledge_hybrid_bm25_weight = round(1 - best_w, 4) if vector else 1.0
        store.settings.knowledge_rerank_enabled = rerank
        store.settings.knowledge_fusion_mode = fusion
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
        print(f"  [{name:<26}] hit {hits}/{len(cases)} ({hits / len(cases):.4f})  avg {avg_ms} ms")
        out[name] = {"hitRate": round(hits / len(cases), 4), "hitCount": hits, "avgLatencyMs": avg_ms, "perCase": per_case}
    return out


def run_provider(label: str, provider: str) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"aegis-embed-{provider}-"))
    s = Settings(
        **{
            **base.model_dump(),
            "database_url": f"sqlite:///{tmp / 'eval.sqlite'}",
            "chroma_dir": str(tmp / "chroma"),
            "chroma_snapshot_dir": str(tmp / "snapshots"),
            "redis_url": "",
            "vector_enabled": True,
            "vector_required": False,
            "embedding_provider": provider,
        }
    )
    schema_engine = build_engine(s)
    sf = build_session_factory(s)
    create_schema(schema_engine)
    store = DatabaseStore(sf, settings=s)
    store.rebuild_knowledge_dir(s.resolve_path(s.knowledge_dir))
    backend = store.vector_backend
    model = getattr(backend, "embedding_model", "none")
    print(f"[{label}] backend={backend.backend_name} chunks={backend.count()} embedding={model}")
    assert backend.backend_name == "chroma" and backend.count() > 0, f"{label}: 期望真实 chroma 索引"

    modes = [
        ("hybrid", True, False, "weighted"),
        ("hybrid_rerank", True, True, "weighted"),
        ("rrf", True, False, "rrf"),
    ]
    result = run_modes(store, backend, modes)
    result["embeddingModel"] = model

    session_factory_bind = getattr(store.db_factory, "kw", {}).get("bind")
    for engine in (schema_engine, session_factory_bind):
        dispose = getattr(engine, "dispose", None)
        if callable(dispose):
            try:
                dispose()
            except Exception:
                pass
    _release_vector_backend(backend)
    shutil.rmtree(tmp, ignore_errors=True)
    return result


print("\n=== bm25_only 公共基线 ===")
baseline_tmp = Path(tempfile.mkdtemp(prefix="aegis-embed-baseline-"))
baseline_settings = Settings(
    **{
        **base.model_dump(),
        "database_url": f"sqlite:///{baseline_tmp / 'eval.sqlite'}",
        "chroma_dir": str(baseline_tmp / "chroma"),
        "chroma_snapshot_dir": str(baseline_tmp / "snapshots"),
        "redis_url": "",
        "vector_enabled": False,
    }
)
baseline_engine = build_engine(baseline_settings)
baseline_sf = build_session_factory(baseline_settings)
create_schema(baseline_engine)
baseline_store = DatabaseStore(baseline_sf, settings=baseline_settings)
baseline_store.rebuild_knowledge_dir(baseline_settings.resolve_path(baseline_settings.knowledge_dir))
bm25 = run_modes(baseline_store, None, [("bm25_only", False, True, "weighted")])
baseline_engine.dispose()
getattr(baseline_sf, "kw", {}).get("bind").dispose()
shutil.rmtree(baseline_tmp, ignore_errors=True)

print("\n=== 嵌入模型对照 ===")
providers = {
    "minilm_local": run_provider("minilm_local", "local"),
    "zhipu_embedding3": run_provider("zhipu_embedding3", "openai"),
}

# 逐条对照(vs bm25_only)
bm25_per_case = bm25["bm25_only"]["perCase"]
for name, res in providers.items():
    for mode, m in res.items():
        if not isinstance(m, dict) or "perCase" not in m:
            continue
        lost = [cid for cid, h in bm25_per_case.items() if h and not m["perCase"].get(cid)]
        gained = [cid for cid, h in bm25_per_case.items() if not h and m["perCase"].get(cid)]
        m["lostVsBm25"] = lost
        m["gainedVsBm25"] = gained
        m.pop("perCase", None)

report = {
    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "vectorWeight": best_w,
    "bm25Weight": round(1 - best_w, 4),
    "totalCases": len(cases),
    "topK": top_k,
    "bm25_only": bm25["bm25_only"],
    "providers": providers,
}
out = ROOT / "data" / "eval" / "embedding-compare-report.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n[saved] {out}")
