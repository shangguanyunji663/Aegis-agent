# -*- coding: utf-8 -*-
"""CE 融合式精排实验：λ 加权 / RRF / 保护式 vs 替换式（三口径，77 条）。

口径 A：BM25 召回（vector off，词法链路 = fused + 词法公式）
口径 B：bge-small-zh 混合召回（weighted w0.35/0.65 + 词法公式）
口径 C：bge-small-zh + RRF 排名融合召回（当前最优召回 75/77；rrf 生产语义下无词法公式）
策略（全部共享同一「词法链路 head top-16」框架）：
- lexical ：纯词法链路（对照）
- replace ：CE 替换式（复刻生产：CE 分覆盖 head 后与 tail 合并做全局重排序）
- fusion_λ：head 内 min-max 归一化后加权（λ ∈ {0.3..0.7}）
- rrf     ：head 内名次倒数融合（k=60）
- protect ：最优 λ 上叠加「短语命中保护」
所有策略：head 重排/替换 → tail 原序拼接 → expand_best_hit → top-4。
输出：data/eval/ce-fusion-report.json + ce-fusion-raw.json（原始分数，供离线复用）
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
    phrase_score,
    rerank_score,
    rrf_fused_score,
)
from app.rag.vector_store import build_vector_backend
from app.repository import DatabaseStore

base = get_settings()
cases = json.loads((ROOT / "eval" / "fixtures" / "rag_queries.json").read_text(encoding="utf-8"))
top_k = base.knowledge_top_k
head_n = max(1, int(getattr(base, "knowledge_rerank_top_n", 16) or 16))
rrf_k = max(1, int(getattr(base, "knowledge_rrf_k", 60) or 60))
model_dir = str(base.resolve_path(base.reranker_model_dir))

W_A_VEC, W_A_BM25 = 0.65, 0.35
W_B_VEC, W_B_BM25 = 0.35, 0.65
LAMBDAS = [0.3, 0.4, 0.5, 0.6, 0.7]

tmp = Path(tempfile.mkdtemp(prefix="aegis-ce-fusion-"))
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
backend = store.vector_backend
print(f"[index] backend={backend.backend_name} chunks={backend.count()} model={getattr(backend, 'embedding_model', '?')}")

with store.db_factory() as db:
    chunks = db.query(KnowledgeChunk).all()
print(f"[chunks] {len(chunks)} | head_n={head_n} | rrf_k={rrf_k} | top_k={top_k}")


def lexical_ranked(rewritten, vector_by_db, vector_by_source, w_vec, w_bm25):
    """复刻 store.search_knowledge 的 weighted+lexical 链路（fused + 词法公式）。"""
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
    """复刻 store.search_knowledge 的 rrf 分支（无词法公式；向量侧仅计 db_id 命中的排名）。"""
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


print("\n[phase 1] 预计算三口径候选与 CE 分数 ...")
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
    """复刻生产替换式：CE 分覆盖 head 后与 tail 合并做全局重排序。"""
    merged = entry[caliber]["ce"] + entry[caliber]["ranked"][head_n:]
    merged.sort(key=lambda item: item[1], reverse=True)
    return merged


def strategy_fusion(entry, caliber, lam):
    head, tail, lex, ce = _split(entry, caliber)
    n_lex = normalize_scores(lex)
    n_ce = normalize_scores(ce)
    merged = [
        (chunk, lam * n_lex.get(int(chunk.id), 0.0) + (1 - lam) * n_ce.get(int(chunk.id), 0.0))
        for chunk, _ in head
    ]
    merged.sort(key=lambda item: item[1], reverse=True)
    return merged + tail


def strategy_rrf(entry, caliber, k=60):
    head, tail, lex, ce = _split(entry, caliber)
    lex_order = [int(c.id) for c, _ in sorted(head, key=lambda item: item[1], reverse=True)]
    ce_order = [int(c.id) for c, _ in sorted(entry[caliber]["ce"], key=lambda item: item[1], reverse=True)]
    lex_rank = {cid: i + 1 for i, cid in enumerate(lex_order)}
    ce_rank = {cid: i + 1 for i, cid in enumerate(ce_order)}
    merged = [
        (chunk, 1.0 / (k + lex_rank[int(chunk.id)]) + 1.0 / (k + ce_rank[int(chunk.id)]))
        for chunk, _ in head
    ]
    merged.sort(key=lambda item: item[1], reverse=True)
    return merged + tail


def strategy_protect(entry, caliber, lam):
    head, tail, lex, ce = _split(entry, caliber)
    n_lex = normalize_scores(lex)
    n_ce = normalize_scores(ce)
    merged = []
    for chunk, _ in head:
        cid = int(chunk.id)
        score = lam * n_lex.get(cid, 0.0) + (1 - lam) * n_ce.get(cid, 0.0)
        if phrase_score(entry["q"], chunk.content) == 1.0:
            score = max(score, n_lex.get(cid, 0.0))
        merged.append((chunk, score))
    merged.sort(key=lambda item: item[1], reverse=True)
    return merged + tail


def evaluate(caliber, strategy_fn):
    hit_count = 0
    per_case = {}
    for case in cases:
        entry = cache[case["id"]]
        ranked = strategy_fn(entry, caliber)
        expanded = expand_best_hit(ranked, chunks)
        top = expanded[:top_k]
        exp_sources = {s.lower() for s in case.get("expectedSources", [])}
        exp_terms = case.get("expectedTerms", [])
        hit = any(is_relevant(chunk.source, chunk.content, exp_sources, exp_terms)[0] for chunk, _ in top)
        per_case[case["id"]] = bool(hit)
        hit_count += int(hit)
    return hit_count, per_case


def delta(base_pc, new_pc):
    lost = [cid for cid, h in base_pc.items() if h and not new_pc.get(cid)]
    gained = [cid for cid, h in base_pc.items() if not h and new_pc.get(cid)]
    return lost, gained


STRATEGY_SPECS = [
    ("lexical", lambda entry, cal: strategy_lexical(entry, cal)),
    ("replace", lambda entry, cal: strategy_replace(entry, cal)),
    ("rrf", lambda entry, cal: strategy_rrf(entry, cal)),
] + [(f"fusion_{lam}", lambda entry, cal, l=lam: strategy_fusion(entry, cal, l)) for lam in LAMBDAS]

report = {
    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "totalCases": len(cases),
    "topK": top_k,
    "ceHeadTopN": head_n,
    "ceComputeSeconds": round(ce_seconds, 1),
    "calibers": {
        "A": {"desc": "BM25 + 词法重排（vector off，统一词法链路口径）", "configs": {}},
        "B": {"desc": f"bge-small-zh hybrid_rerank（w{W_B_VEC}/{W_B_BM25}）", "configs": {}},
        "C": {"desc": "bge-small-zh + rrf 召回（最优召回 75/77）", "configs": {}},
    },
}

for caliber in ("A", "B", "C"):
    print(f"\n== 口径 {caliber}: {report['calibers'][caliber]['desc']} ==")
    configs = report["calibers"][caliber]["configs"]
    per_case_map = {}
    for name, fn in STRATEGY_SPECS:
        hit_count, per_case = evaluate(caliber, fn)
        per_case_map[name] = per_case
        configs[name] = {"hitCount": hit_count, "hitRate": round(hit_count / len(cases), 4)}
        print(f"  [{name:<12}] hit {hit_count}/{len(cases)} ({hit_count / len(cases):.4f})")

    best_lam = max(LAMBDAS, key=lambda lam: configs[f"fusion_{lam}"]["hitCount"])
    hit_count, per_case = evaluate(caliber, lambda entry, cal, l=best_lam: strategy_protect(entry, cal, l))
    per_case_map[f"protect_{best_lam}"] = per_case
    configs[f"protect_{best_lam}"] = {"hitCount": hit_count, "hitRate": round(hit_count / len(cases), 4)}
    print(f"  [protect_{best_lam:<5}] hit {hit_count}/{len(cases)} ({hit_count / len(cases):.4f})  (best λ={best_lam})")

    for name, per_case in per_case_map.items():
        lex_lost, lex_gained = delta(per_case_map["lexical"], per_case)
        rep_lost, rep_gained = delta(per_case_map["replace"], per_case)
        configs[name]["vsLexical"] = {"lost": lex_lost, "gained": lex_gained}
        configs[name]["vsReplace"] = {"lost": rep_lost, "gained": rep_gained}

    report["calibers"][caliber]["perCase"] = per_case_map

raw = {}
for case_id, entry in cache.items():
    raw[case_id] = {}
    for cal in ("A", "B", "C"):
        data = entry[cal]
        raw[case_id][cal] = {
            "head": [
                {"chunkId": int(c.id), "source": c.source, "si": c.source_index, "sLex": round(float(s), 6)}
                for c, s in data["ranked"][:head_n]
            ],
            "tail": [
                {"chunkId": int(c.id), "source": c.source, "si": c.source_index, "sLex": round(float(s), 6)}
                for c, s in data["ranked"][head_n:]
            ],
            "ce": [{"chunkId": int(c.id), "sCe": round(float(s), 6)} for c, s in data["ce"]],
        }
raw_path = ROOT / "data" / "eval" / "ce-fusion-raw.json"
raw_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
print(f"[saved] {raw_path}")

out = ROOT / "data" / "eval" / "ce-fusion-report.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[saved] {out}")

schema_engine.dispose()
getattr(store.db_factory, "kw", {}).get("bind").dispose()
_release_vector_backend(backend)
shutil.rmtree(tmp, ignore_errors=True)
print("DONE")
