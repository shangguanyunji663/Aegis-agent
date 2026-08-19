"""扩展 GLM probe:对压力层全部 25 条隐喻式高危样本做真实 GLM-4.7-flash 风险判定。

目的:扩大 sanity check 样本量,验证 MetaphorAwareStubClient 量出的"LLM 通道能力上界"
(压力层风险 0.94 / 高召回 1.00)是否是真实 GLM 能达到的水平。

- 复用 OpenAICompatibleClient(项目 GLM 配置)+ RISK_ASSESS_SYSTEM_PROMPT
- best-effort:429/超时回退 none,如实记录
- 输出:data/eval/glm_probe_25.json + 控制台摘要
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import Settings
from app.llm import OpenAICompatibleClient

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "eval" / "fixtures" / "representative_corpus.json"
OUT_DIR = ROOT / "data" / "eval"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    if not settings.openai_api_key:
        print("[glm-probe-25] OPENAI_API_KEY missing; abort")
        return 1

    client = OpenAICompatibleClient(settings)
    print(f"[glm-probe-25] provider={client.provider} model={client.model} base_url={client.base_url}")

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    cases = [c for c in corpus if c.get("layer") == "stress" and c.get("expected_risk") == "high"]
    print(f"[glm-probe-25] {len(cases)} stress+high cases (suicidal_implicit)")
    print(f"[glm-probe-25] sleep=8s between calls (avoid 429); estimated ~{len(cases)*8}s")

    results = []
    t0 = time.time()
    for i, case in enumerate(cases, 1):
        msg = case["message"]
        expected = case["expected_risk"]
        cid = case.get("id")
        try:
            llm_out = client.assess_risk(msg)
        except Exception as exc:
            llm_out = {"error": str(exc)}
        if llm_out is None:
            llm_out = {"risk_level": "none", "reason": "429/timeout fallback"}
        actual = llm_out.get("risk_level", "unknown")
        reason = llm_out.get("reason", "")
        if "error" in llm_out:
            reason = f"error:{llm_out['error'][:40]}"
        match = actual == expected
        results.append({
            "id": cid,
            "category": case.get("category"),
            "message": msg,
            "expected_risk": expected,
            "glm_risk_level": actual,
            "glm_reason": reason,
            "match": match,
        })
        elapsed = time.time() - t0
        print(f"  [{i}/{len(cases)}] {cid} exp={expected} glm={actual} match={match} ({elapsed:.0f}s)", flush=True)
        if i < len(cases):
            time.sleep(8)

    matches = sum(1 for r in results if r["match"])
    none_count = sum(1 for r in results if r["glm_risk_level"] == "none")
    high_correct = sum(1 for r in results if r["glm_risk_level"] == "high")
    other = sum(1 for r in results if r["glm_risk_level"] not in ("high", "none"))

    summary = {
        "model": f"{client.provider}/{client.model}",
        "base_url": client.base_url,
        "sample_size": len(cases),
        "matches": matches,
        "match_rate": round(matches / len(cases), 4),
        "high_correct": high_correct,
        "none_fallback": none_count,
        "other_judgment": other,
        "note": "best-effort probe on 25 suicidal_implicit cases; 429/timeout falls back to none",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
    }

    out = {"summary": summary, "results": results}
    out_path = OUT_DIR / "glm_probe_25.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== GLM PROBE 25 SUMMARY ===")
    print(f"matches: {matches}/{len(cases)} = {summary['match_rate']}")
    print(f"  high_correct={high_correct}  none_fallback={none_count}  other={other}")
    print(f"written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
