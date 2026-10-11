# -*- coding: utf-8 -*-
"""v2 库（590 块，真实扩库）完整评测：A vs C 配置对比。

- 库：data/scale-test/knowledge-v2（原 24 + univs 65 + 百科词条 84 + AI 10）
- 口径：A（BM25+词法）/ B（weighted fused+词法）/ C（rrf 召回）
- 策略：lexical（词法链路）/ replace（CE 替换式）/ fusion（CE 融合式 λ=0.4）
- 评测：77 条原题，宽松 + 严格双口径
- 优化：BM25 与向量检索每条 query 只算一次，三口径由它们派生（省约一半时间）
- 输出：data/eval/v2-full-report.json
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings, get_settings
from app.database import build_engine, build_session_factory, create_schema
from app.entities import KnowledgeChunk
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
from app.repository import DatabaseStore

LAMBDA = 0.4
W_B_VEC, W_B_BM25 = 0.35, 0.65
W_A_VEC, W_A_BM25 = 0.65, 0.35

base = get_settings()
cases = json.loads((ROOT / "eval" / "fixtures" / "rag_queries.json").read_text(encoding="utf-8"))
ORIG = {p.name for p in (ROOT / "knowledge").glob("*.md")}
BIG = 10**9

tmp = Path(tempfile.mkdtemp(prefix="aegis-v2full-"))
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
        "knowledge_dir": str(ROOT / "data" / "scale-test" / "knowledge-v2"),
    }
)
schema_engine = build_engine(settings)
session_factory = build_session_factory(settings)
create_schema(schema_engine)
store = DatabaseStore(session_factory, settings=settings)
store.rebuild_knowledge_dir(settings.resolve_path(settings.knowledge_dir))
backend = store.vector_backend
with store.db_factory() as db:
    chunks = db.query(KnowledgeChunk).all()
n = len(chunks)
print(f"[index] chunks={n}", flush=True)
chunk_source = {int(c.id): c.source for c in chunks if c.id is not None}
chunk_by_id = {int(c.id): c for c in chunks if c.id is not None}


def build_per_query(query: str) -> tuple[dict, dict]:
    """返回 (normalized_bm25, normalized_vector) 全库字典（每条 query 一次）。"""
    scores = bm25_scores(query, chunks)
    norm_bm25 = normalize_scores({int(c.id): scores.get(c.id, 0.0) for c in chunks if c.id is not None})
    vres = backend.search(query, n)
    vec_score = {int(i["db_id"]): float(i["score"]) for i in vres if i.get("db_id") is not None}
    norm_vec = normalize_scores({int(c.id): vec_score.get(int(c.id), 0.0) for c in chunks if c.id is not None})
    return norm_bm25, norm_vec


def rank_rrf(norm_bm25: dict, norm_vec: dict) -> list[tuple[int, float]]:
    bm25_ranked = sorted(norm_bm25.items(), key=lambda x: -x[1])
    vec_ranked = sorted(norm_vec.items(), key=lambda x: -x[1])
    b_rank = {cid: i + 1 for i, (cid, _) in enumerate(bm25_ranked)}
    v_rank = {cid: i + 1 for i, (cid, _) in enumerate(vec_ranked)}
    items = []
    for cid in norm_bm25:
        if norm_bm25.get(cid, 0.0) <= 0 and norm_vec.get(cid, 0.0) <= 0:
            continue
        items.append((cid, rrf_fused_score(v_rank.get(cid), b_rank.get(cid), k=60)))
    items.sort(key=lambda x: -x[1])
    return items


def rank_by_base(norm_bm25: dict, norm_vec: dict, w_vec: float, w_bm25: float) -> list[tuple[int, float]]:
    items = []
    for cid in norm_bm25:
        base_bm25 = norm_bm25.get(cid, 0.0)
        base_vec = norm_vec.get(cid, 0.0)
        if base_bm25 <= 0 and base_vec <= 0:
            continue
        base = fused_score(base_vec, base_bm25, w_vec, w_bm25)
        items.append((cid, base))
    items.sort(key=lambda x: -x[1])
    return items


print("[phase 1] 计算 BM25 / 向量 / 三口径候选 + CE 分数 ...")
cache = {}
for index, case in enumerate(cases, 1):
    q = rewrite_query(case["question"])
    norm_bm25, norm_vec = build_per_query(q)

    # A: BM25 only（无向量），走词法公式
    a_ranked = []
    for cid, base_bm25 in norm_bm25.items():
        if base_bm25 <= 0:
            continue
        a_base = fused_score(0.0, base_bm25, W_A_VEC, W_A_BM25)
        content = chunk_by_id[cid].content
        a_ranked.append((cid, rerank_score(q, content, a_base)))
    a_ranked.sort(key=lambda x: -x[1])

    # C: rrf（无词法公式）
    c_ranked = rank_rrf(norm_bm25, norm_vec)

    entry = {"q": q, "A": [], "C": []}
    for caliber, ranked in (("A", a_ranked), ("C", c_ranked)):
        head = [(chunk_by_id[cid], score) for cid, score in ranked[:16]]
        tail = [(cid, score) for cid, score in ranked[16:]]
        ce = cross_encoder_rerank(q, head, str(base.resolve_path(base.reranker_model_dir)))
        entry[caliber] = {"ranked": ranked, "ce": ce, "tail": tail}
    cache[case["id"]] = entry
    if index % 10 == 0:
        print(f"  ... {index}/{len(cases)}", flush=True)

print("[phase 1] done", flush=True)


def strategy(caliber: str, mode: str, entry: dict):
    ranked = entry[caliber]["ranked"]
    ce_map = {int(chunk.id): score for chunk, score in entry[caliber]["ce"]}
    head = ranked[:16]
    tail = ranked[16:]
    if mode == "lexical":
        return ranked
    if mode == "replace":
        merged = [(cid, ce_map.get(cid, 0.0)) for cid, _ in head] + [(cid, score) for cid, score in tail]
        merged.sort(key=lambda x: -x[1])
        return merged
    n_lex = normalize_scores({cid: score for cid, score in head})
    n_ce = normalize_scores({cid: ce_map.get(cid, 0.0) for cid, _ in head})
    fused_head = sorted(
        [(cid, LAMBDA * n_lex[cid] + (1 - LAMBDA) * n_ce[cid]) for cid, _ in head], key=lambda x: -x[1]
    )
    return fused_head + [(cid, score) for cid, score in tail]


def evaluate(caliber: str, mode: str) -> tuple[int, int, dict]:
    loose = 0
    strict = 0
    per_case = {}
    for case in cases:
        entry = cache[case["id"]]
        ranked = strategy(caliber, mode, entry)
        # 统一转为 (chunk, score) 列表供 expand
        pairs = []
        for item in ranked:
            cid, score = item
            chunk = chunk_by_id[cid]
            pairs.append((chunk, score))
        expanded = expand_best_hit(pairs, chunks)
        top = expanded[: base.knowledge_top_k]
        exp_sources = {s.lower() for s in case.get("expectedSources", [])}
        exp_terms = [t.lower() for t in case.get("expectedTerms", [])]
        hit_loose = any(
            chunk.source.lower() in exp_sources or any(len(t) >= 2 and t in chunk.content.lower() for t in exp_terms)
            for chunk, _ in top
        )
        hit_strict = any(chunk.source.lower() in exp_sources for chunk, _ in top)
        per_case[case["id"]] = bool(hit_loose)
        loose += int(hit_loose)
        strict += int(hit_strict)
    return loose, strict, per_case


CONFIGS = [
    ("A_lexical", "A", "lexical"),
    ("A_replace", "A", "replace"),
    ("A_fusion", "A", "fusion"),
    ("C_lexical", "C", "lexical"),
    ("C_replace", "C", "replace"),
    ("C_fusion", "C", "fusion"),
]
report = {
    "createdAt": "2026-10-10",
    "library": f"knowledge-v2 ({n} chunks, 真实扩库：原24 + univs65 + 词条84 + AI10)",
    "totalCases": len(cases),
    "topK": base.knowledge_top_k,
    "lambda": LAMBDA,
    "configs": {},
    "perCase": {},
}
print("\n[phase 2] 评估 ...")
for name, caliber, mode in CONFIGS:
    loose, strict, per_case = evaluate(caliber, mode)
    report["configs"][name] = {"loose": loose, "looseRate": round(loose / len(cases), 4), "strict": strict, "strictRate": round(strict / len(cases), 4)}
    report["perCase"][name] = per_case
    print(f"  [{name:<11}] loose {loose}/{len(cases)} ({loose / len(cases):.4f}) | strict {strict}/{len(cases)} ({strict / len(cases):.4f})", flush=True)

out = ROOT / "data" / "eval" / "v2-full-report.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n[saved] {out}")

schema_engine.dispose()
getattr(store.db_factory, "kw", {}).get("bind").dispose()
client = getattr(backend, "client", None)
if client is not None and callable(getattr(client, "close", None)):
    client.close()
shutil.rmtree(tmp, ignore_errors=True)
print("DONE")
