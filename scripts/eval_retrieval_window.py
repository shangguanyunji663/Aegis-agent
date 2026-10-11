# -*- coding: utf-8 -*-
"""检索窗口对照实验：RRF 候选窗口大小对命中率的影响（570 块生产库）。

背景（ROUND-21 §6）：RRF 的向量侧排名项 1/(k+v_rank) 只覆盖"被向量召回进候选窗口"的条目；
窗口过小（生产历史值 16）会让向量排名靠后的期望源拿不到 v 项，RRF 排名塌陷出 head-16，
CE 精排无法触达。

本脚本以同一次向量全库排名为基准，模拟任意候选窗口 K
（K 口径 = 只保留全库排名 <= K 的条目的 v 项），走完整链路评测：
RRF → head16 → Cross-Encoder → λ 融合（0.4）→ 邻块扩展 → Top-4。

用法：
    .conda/python.exe scripts/eval_retrieval_window.py                # 默认窗口 [16, 128, 全库]
    .conda/python.exe scripts/eval_retrieval_window.py --windows 16,32,64,128,0   # 0=全库

输出：data/eval/retrieval-window-report.json（含各窗口 loose/strict 与逐题结果）
"""
import argparse
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
    normalize_scores,
    rrf_fused_score,
)
from app.repository import DatabaseStore

LAMBDA = 0.4
TOPN = 16  # head 精排窗口（KNOWLEDGE_RERANK_TOP_N），与候选窗口 K 无关


def main() -> None:
    parser = argparse.ArgumentParser(description="RRF 候选窗口对照实验")
    parser.add_argument("--windows", default="16,128,0", help="候选窗口列表,逗号分隔,0=全库")
    parser.add_argument("--library", default="", help="知识库目录(默认取 .env knowledge_dir)")
    args = parser.parse_args()
    windows = [int(x) for x in args.windows.split(",") if x.strip() != ""]

    base = get_settings()
    cases = json.loads((ROOT / "eval" / "fixtures" / "rag_queries.json").read_text(encoding="utf-8"))

    tmp = Path(tempfile.mkdtemp(prefix="aegis-window-"))
    settings = Settings(
        **{
            **base.model_dump(),
            "database_url": f"sqlite:///{tmp / 'e.sqlite'}",
            "chroma_dir": str(tmp / "chroma"),
            "chroma_snapshot_dir": str(tmp / "snap"),
            "redis_url": "",
        }
    )
    if args.library:
        settings.knowledge_dir = args.library
    schema_engine = build_engine(settings)
    sf = build_session_factory(settings)
    create_schema(schema_engine)
    store = DatabaseStore(sf, settings=settings)
    store.rebuild_knowledge_dir(settings.resolve_path(settings.knowledge_dir))
    backend = store.vector_backend
    model_dir = str(settings.resolve_path(settings.reranker_model_dir))

    with store.db_factory() as db:
        chunks = db.query(KnowledgeChunk).all()
    n = len(chunks)
    cid2 = {int(c.id): f"{c.source}#{c.source_index}" for c in chunks if c.id is not None}
    chunk_by_id = {int(c.id): c for c in chunks if c.id is not None}
    k_rrf = int(settings.knowledge_rrf_k)
    print(f"[index] chunks={n} k_rrf={k_rrf} lambda={LAMBDA} head={TOPN} windows={windows}", flush=True)

    per_case = {str(w): {} for w in windows}
    strict_case = {str(w): {} for w in windows}
    for ci, case in enumerate(cases, 1):
        q = rewrite_query(case["question"])
        exp_sources = {s.lower() for s in case.get("expectedSources", [])}
        exp_terms = [t.lower() for t in case.get("expectedTerms", [])]

        vres_all = backend.search(q, n)
        v_rank_all = {int(i["db_id"]): k + 1 for k, i in enumerate(vres_all) if i.get("db_id") is not None}
        scores = bm25_scores(q, chunks)
        bm25_ranked = sorted(scores.items(), key=lambda x: -x[1])
        b_rank = {cid: i + 1 for i, (cid, _) in enumerate(bm25_ranked)}

        for w in windows:
            v_rank_use = {cid: r for cid, r in v_rank_all.items() if w == 0 or r <= w}
            items = []
            for cid in cid2:
                v = v_rank_use.get(cid)
                b = b_rank.get(cid)
                if v is None and b is None:
                    continue
                items.append((cid, rrf_fused_score(v, b, k=k_rrf)))
            items.sort(key=lambda x: -x[1])
            head, tail = items[:TOPN], items[TOPN:]

            ce = cross_encoder_rerank(q, [(chunk_by_id[cid], s) for cid, s in head], model_dir)
            ce_map = {int(c.id): s for c, s in ce}
            n_lex = normalize_scores({cid: s for cid, s in head})
            n_ce = normalize_scores({cid: ce_map.get(cid, 0.0) for cid, _ in head})
            fused = sorted(
                [(cid, LAMBDA * n_lex.get(cid, 0.0) + (1 - LAMBDA) * n_ce.get(cid, 0.0)) for cid, _ in head],
                key=lambda x: -x[1],
            )
            final = expand_best_hit([(chunk_by_id[cid], s) for cid, s in fused + tail], chunks)
            top4 = final[:4]

            hit_loose = any(
                c.source.lower() in exp_sources or any(len(t) >= 2 and t in c.content.lower() for t in exp_terms)
                for c, _ in top4
            )
            hit_strict = any(c.source.lower() in exp_sources for c, _ in top4)
            per_case[str(w)][case["id"]] = bool(hit_loose)
            strict_case[str(w)][case["id"]] = bool(hit_strict)

        if ci % 20 == 0:
            print(f"  ... {ci}/{len(cases)}", flush=True)

    report = {
        "createdAt": "2026-10-11",
        "library": f"{settings.resolve_path(settings.knowledge_dir)} ({n} chunks)",
        "note": "窗口口径 = 只保留全库向量排名<=K 的条目的 v 项; K=0 表示全库; 完整链路含 CE 融合 λ0.4",
        "kRrf": k_rrf,
        "head": TOPN,
        "lambda": LAMBDA,
        "windows": {},
        "perCase": per_case,
        "strictPerCase": strict_case,
    }
    print("\n==== 窗口对照结果 ====")
    for w in windows:
        loose = sum(per_case[str(w)].values())
        strict = sum(strict_case[str(w)].values())
        tag = "（全库）" if w == 0 else ""
        report["windows"][str(w)] = {
            "loose": loose, "looseRate": round(loose / len(cases), 4),
            "strict": strict, "strictRate": round(strict / len(cases), 4),
        }
        print(f"  K={str(w):6s}{tag}: loose {loose}/{len(cases)} ({loose/len(cases):.4f}) | strict {strict}/{len(cases)} ({strict/len(cases):.4f})")

    out = ROOT / "data" / "eval" / "retrieval-window-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {out}")

    schema_engine.dispose()
    getattr(store.db_factory, "kw", {}).get("bind").dispose()
    client = getattr(backend, "client", None)
    if client is not None and callable(getattr(client, "close", None)):
        client.close()
    shutil.rmtree(tmp, ignore_errors=True)
    print("DONE")


if __name__ == "__main__":
    main()
