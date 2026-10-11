# -*- coding: utf-8 -*-
"""生产配置复评：用 .env 的真实配置（local-zh + rrf + ce_fusion）跑 77 题。

- 知识库：knowledge/ 目录（173 篇）
- 文本库与向量索引建在临时目录（不污染生产 MySQL / data/chroma）
- 直连 store.search_knowledge（走生产检索路径，含 ce_fusion 精排）
- 输出：data/eval/production-check-report.json
"""
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings, get_settings
from app.database import build_engine, build_session_factory, create_schema
from app.evaluation.rag import _release_vector_backend, is_relevant
from app.repository import DatabaseStore

base = get_settings()
cases = json.loads((ROOT / "eval" / "fixtures" / "rag_queries.json").read_text(encoding="utf-8"))
top_k = base.knowledge_top_k

tmp = Path(tempfile.mkdtemp(prefix="aegis-prodcheck-"))
settings = Settings(
    **{
        **base.model_dump(),
        "database_url": f"sqlite:///{tmp / 'eval.sqlite'}",
        "chroma_dir": str(tmp / "chroma"),
        "chroma_snapshot_dir": str(tmp / "snapshots"),
        "redis_url": "",
    }
)
print(f"[config] embedding={settings.embedding_provider} | fusion={settings.knowledge_fusion_mode} | "
      f"rerank={settings.knowledge_rerank_engine} λ={getattr(settings, 'knowledge_ce_fusion_lambda', '?')} | "
      f"collection={settings.chroma_collection_name} | candidate_k={settings.knowledge_candidate_k} "
      f"head={getattr(settings, 'knowledge_rerank_top_n', 16)}")

schema_engine = build_engine(settings)
session_factory = build_session_factory(settings)
create_schema(schema_engine)
store = DatabaseStore(session_factory, settings=settings)
result = store.rebuild_knowledge_dir(settings.resolve_path(settings.knowledge_dir))
print(f"[index] chunks = {result['chunks']} | vector count = {store.vector_backend.count()}")

loose = 0
strict = 0
latency = 0.0
per_case = {}
for case in cases:
    t0 = time.perf_counter()
    hits = store.search_knowledge(case["question"], top_k)
    latency += time.perf_counter() - t0
    exp_sources = {s.lower() for s in case.get("expectedSources", [])}
    exp_terms = [t.lower() for t in case.get("expectedTerms", [])]
    hit_loose = any(
        item["source"].lower() in exp_sources
        or any(len(t) >= 2 and t in item["content"].lower() for t in exp_terms)
        for item in hits
    )
    hit_strict = any(item["source"].lower() in exp_sources for item in hits)
    per_case[case["id"]] = bool(hit_loose)
    loose += int(hit_loose)
    strict += int(hit_strict)

avg_ms = round(latency / len(cases) * 1000, 1)
report = {
    "createdAt": "2026-10-11",
    "config": {
        "embeddingProvider": settings.embedding_provider,
        "fusionMode": settings.knowledge_fusion_mode,
        "rerankEngine": settings.knowledge_rerank_engine,
        "lambda": getattr(settings, "knowledge_ce_fusion_lambda", None),
        "candidateK": settings.knowledge_candidate_k,
        "rerankTopN": getattr(settings, "knowledge_rerank_top_n", 16),
        "chunks": result["chunks"],
        "documents": len(list(settings.resolve_path(settings.knowledge_dir).glob("*.md"))),
    },
    "totalCases": len(cases),
    "topK": top_k,
    "loose": loose,
    "looseRate": round(loose / len(cases), 4),
    "strict": strict,
    "strictRate": round(strict / len(cases), 4),
    "avgLatencyMs": avg_ms,
    "perCase": per_case,
}

out = ROOT / "data" / "eval" / "production-check-report.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n[result] loose {loose}/{len(cases)} ({loose / len(cases):.4f}) | strict {strict}/{len(cases)} ({strict / len(cases):.4f}) | 平均延迟 {avg_ms} ms")
print(f"[saved] {out}")

schema_engine.dispose()
getattr(store.db_factory, "kw", {}).get("bind").dispose()
_release_vector_backend(store.vector_backend)
shutil.rmtree(tmp, ignore_errors=True)
print("DONE")
