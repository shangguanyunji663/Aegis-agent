# -*- coding: utf-8 -*-
"""规模化对比实验：在 298 块实验库上复跑三口径 × 三策略（对照 24 块库结果）。

- 实验库：data/scale-test/knowledge-200（原库 24 块 + 合成 274 块；全隔离，不碰生产）
- 口径：A（BM25+词法链路）/ B（bge hybrid w0.35）/ C（bge rrf）
- 策略：lexical（词法链路）/ replace（CE 替换式）/ fusion（CE 融合式 λ=0.4）
- 评测：77 条原题，宽松 + 严格双口径
- 输出：data/eval/scale200-report.json
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
from app.entities import KnowledgeChunk
from app.evaluation.rag import _release_vector_backend, is_relevant
from app.rag.chunking import rewrite_query
from app.rag.reranker import cross_encoder_rerank
from app.rag.scoring import (
    bm25_scores,
    expand_best_hit,
    fused_score,
    normalize_scores,
    rerank_score,
    rrf_fused_score,
)
from app.rag.vector_store import build_vector_backend
from app.repository import DatabaseStore

SCALE_DIR = ROOT / "data" / "scale-test" / "knowledge-200"
LAMBDA = 0.4

base = get_settings()
cases = json.loads((ROOT / "eval" / "fixtures" / "rag_queries.json").read_text(encoding="utf-8"))
top_k = base.knowledge_top_k
head_n = max(1, int(getattr(base, "knowledge_rerank_top_n", 16) or 16))
rrf_k = max(1, int(getattr(base, "knowledge_rrf_k", 60) or 60))
model_dir = str(base.resolve_path(base.reranker_model_dir))

W_A_VEC, W_A_BM25 = 0.65, 0.35
W_B_VEC, W_B_BM25 = 0.35, 0.65

tmp = Path(tempfile.mkdtemp(prefix="aegis-scale200-"))
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
        "knowledge_dir": str(SCALE_DIR),
    }
)
schema_engine = build_engine(settings)
session_factory = build_session_factory(settings)
create_schema(schema_engine)
store = DatabaseStore(session_factory, settings=settings)
store.rebuild_knowledge_dir(settings.resolve_path(settings.knowledge_dir))
backend = store.vector_backend
print(f"[index] backend={backend.backend_name} chunks={backend.count()} model={getattr(backend, 'embedding_model', '?')}")

with store.db_factory() as db:
    chunks = db.query(KnowledgeChunk).all()
print(f"[chunks] {len(chunks)} | head_n={head_n} | rrf_k={rrf_k} | top_k={top_k} | lambda={LAMBDA}")


def lexical_ranked(rewritten, vector_by_db, vector_by_source, w_vec, w_bm25):
    scores = bm25_scores(rewritten, chunks)
    normalized_bm25 = normalize_scores({int(c.id): scores.get(c.id, 0.0) for c in chunks if c.id is not None})
    normalized_vector = normalize_scores(
        {
            int(c.id): vector_by_db.get(int(c.id), vector_by_source.get(f"{c.source}:{c.source_index}", 0.0))
            for c in chunks
            if c.id is not None
        }
    )
    ranked = []
    for chunk in chunks:
        if chunk.id is None:
            continue
        chunk_id = int(chunk.id)
        base_bm25 = normalized_bm25.get(chunk_id, 0.0)
        base_vector = normalized_vector.get(chunk_id, 0.0)
        if base_bm25 <= 0 and base_vector <= 0:
            continue
        base_score = fused_score(base_vector, base_bm25, w_vec, w_bm25)
        score = rerank_score(rewritten, chunk.content, base_score)
        ranked.append((chunk, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def rrf_ranked(rewritten, vector_by_db):
    scores = bm25_scores(rewritten, chunks)
    bm25_ranked = sorted(scores.items(), key=lambda item: -item[1])
    bm25_rank_map = {chunk_id: idx + 1 for idx, (chunk_id, _) in enumerate(bm25_ranked)}
    vector_rank_map = {
        chunk_id: idx + 1
        for idx, (chunk_id, _) in enumerate(sorted(vector_by_db.items(), key=lambda item: -item[1]))
    }
    ranked = []
    for chunk in chunks:
        if chunk.id is None:
            continue
        chunk_id = int(chunk.id)
        v_rank = vector_rank_map.get(chunk_id)
        b_rank = bm25_rank_map.get(chunk_id)
        if v_rank is None and b_rank is None:
            continue
        score = rrf_fused_score(v_rank, b_rank, k=rrf_k)
        ranked.append((chunk, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


print("\n[phase 1] 预计算三口径候选与 CE 分数（298 块库）...")
cache = {}
ce_seconds = 0.0
for index, case in enumerate(cases, 1):
    rewritten = rewrite_query(case["question"])
    entry = {"q": rewritten}

    ranked_a = lexical_ranked(rewritten, {}, {}, W_A_VEC, W_A_BM25)
    t0 = time.perf_counter()
    ce_a = cross_encoder_rerank(rewritten, ranked_a[:head_n], model_dir)
    ce_seconds += time.perf_counter() - t0
    entry["A"] = {"ranked": ranked_a, "ce": ce_a}

    candidate_k = max(1, min(settings.knowledge_candidate_k, settings.vector_top_k or settings.knowledge_candidate_k))
    vector_results = backend.search(rewritten, candidate_k)
    by_db = {int(i["db_id"]): float(i["score"]) for i in vector_results if i.get("db_id") is not None}
    by_src = {
        f"{i.get('source')}:{i.get('source_index')}": float(i["score"])
        for i in vector_results
        if i.get("source") is not None and i.get("source_index") is not None
    }

    ranked_b = lexical_ranked(rewritten, by_db, by_src, W_B_VEC, W_B_BM25)
    t0 = time.perf_counter()
    ce_b = cross_encoder_rerank(rewritten, ranked_b[:head_n], model_dir)
    ce_seconds += time.perf_counter() - t0
    entry["B"] = {"ranked": ranked_b, "ce": ce_b}

    ranked_c = rrf_ranked(rewritten, by_db)
    t0 = time.perf_counter()
    ce_c = cross_encoder_rerank(rewritten, ranked_c[:head_n], model_dir)
    ce_seconds += time.perf_counter() - t0
    entry["C"] = {"ranked": ranked_c, "ce": ce_c}

    cache[case["id"]] = entry
    if index % 20 == 0:
        print(f"  ... {index}/{len(cases)} cases")

print(f"[phase 1] done. CE total {ce_seconds:.1f}s")


def _split(entry, caliber):
    ranked = entry[caliber]["ranked"]
    tail = ranked[head_n:]
    head = ranked[:head_n]
    lex_scores = {int(c.id): s for c, s in head}
    ce_scores = {int(c.id): s for c, s in entry[caliber]["ce"]}
    return head, tail, lex_scores, ce_scores


def strategy_lexical(entry, caliber):
    return entry[caliber]["ranked"]


def strategy_replace(entry, caliber):
    merged = entry[caliber]["ce"] + entry[caliber]["ranked"][head_n:]
    merged.sort(key=lambda item: item[1], reverse=True)
    return merged


def strategy_fusion(entry, caliber, lam=LAMBDA):
    head, tail, lex, ce = _split(entry, caliber)
    n_lex = normalize_scores(lex)
    n_ce = normalize_scores(ce)
    merged = [
        (chunk, lam * n_lex.get(int(chunk.id), 0.0) + (1 - lam) * n_ce.get(int(chunk.id), 0.0))
        for chunk, _ in head
    ]
    merged.sort(key=lambda item: item[1], reverse=True)
    return merged + tail


def evaluate(caliber, strategy_fn):
    loose_count = 0
    strict_count = 0
    per_loose = {}
    per_strict = {}
    latency = 0.0
    for case in cases:
        entry = cache[case["id"]]
        t0 = time.perf_counter()
        ranked = strategy_fn(entry, caliber)
        expanded = expand_best_hit(ranked, chunks)
        latency += time.perf_counter() - t0
        top = expanded[:top_k]
        exp_sources = {s.lower() for s in case.get("expectedSources", [])}
        exp_terms = [case_term.lower() for case_term in case.get("expectedTerms", [])]
        hit_loose = any(is_relevant(chunk.source, chunk.content, exp_sources, exp_terms)[0] for chunk, _ in top)
        hit_strict = any(is_relevant(chunk.source, chunk.content, exp_sources, exp_terms)[1] for chunk, _ in top)
        per_loose[case["id"]] = bool(hit_loose)
        per_strict[case["id"]] = bool(hit_strict)
        loose_count += int(hit_loose)
        strict_count += int(hit_strict)
    return loose_count, strict_count, per_loose, per_strict


CONFIGS = [
    ("A_lexical", lambda e, c: strategy_lexical(e, c)),
    ("A_replace", lambda e, c: strategy_replace(e, c)),
    ("A_fusion", lambda e, c: strategy_fusion(e, c)),
    ("B_lexical", lambda e, c: strategy_lexical(e, c)),
    ("B_replace", lambda e, c: strategy_replace(e, c)),
    ("B_fusion", lambda e, c: strategy_fusion(e, c)),
    ("C_lexical", lambda e, c: strategy_lexical(e, c)),
    ("C_replace", lambda e, c: strategy_replace(e, c)),
    ("C_fusion", lambda e, c: strategy_fusion(e, c)),
]

report = {
    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "library": f"scale-test/knowledge-200 ({len(chunks)} chunks)",
    "totalCases": len(cases),
    "topK": top_k,
    "ceHeadTopN": head_n,
    "lambda": LAMBDA,
    "ceComputeSeconds": round(ce_seconds, 1),
    "configs": {},
    "perCase": {},
}
REFERENCE_24 = {
    "note": "24 块库对照（data/eval/ce-fusion-report.json）",
    "A_lexical": 72, "A_replace": 76, "A_fusion": 77,
    "B_lexical": 73, "B_replace": 74, "B_fusion": 75,
    "C_lexical": 75, "C_replace": 75, "C_fusion": 76,
}
report["reference24"] = REFERENCE_24

for name, fn in CONFIGS:
    caliber = name.split("_")[0]
    loose, strict, per_loose, per_strict = evaluate(caliber, fn)
    report["configs"][name] = {
        "loose": loose,
        "looseRate": round(loose / len(cases), 4),
        "strict": strict,
        "strictRate": round(strict / len(cases), 4),
        "reference24Loose": REFERENCE_24.get(name),
        "deltaVs24": (loose - REFERENCE_24[name]) if name in REFERENCE_24 else None,
    }
    report["perCase"][name] = per_loose
    print(
        f"  [{name:<11}] loose {loose}/{len(cases)} ({loose / len(cases):.4f}) | "
        f"strict {strict}/{len(cases)} ({strict / len(cases):.4f}) | "
        f"Δ24块库 {loose - REFERENCE_24.get(name, loose):+d}"
    )

out = ROOT / "data" / "eval" / "scale200-report.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n[saved] {out}")

schema_engine.dispose()
getattr(store.db_factory, "kw", {}).get("bind").dispose()
_release_vector_backend(backend)
shutil.rmtree(tmp, ignore_errors=True)
print("DONE")
