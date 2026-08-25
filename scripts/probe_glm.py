"""GLM 端点探针:验证 OpenAI 兼容 endpoint 与模型名是否可用。

- 默认执行"今天天气挺好的"单次往返,验证端点/模型。退出码 0=可用,1=不可用,2=入参错误。
- 加 --samples 对语料压力层全部隐喻式高危样本做真实风险判定,
  产出 data/eval/glm_probe_25.json(best-effort:429/超时回退 none,如实记录)。

不打印 API key,只报告端点/模型/响应状态。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _ensure_project_root_on_path() -> None:
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))


def load_env(env_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not env_path.exists():
        return out
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def probe(base_url: str, api_key: str, model: str) -> int:
    # SSRF 防护:仅 http(s) 且带主机名;解析后拒绝私网/环回/链路本地 IP(公网 API 放行)
    import ipaddress
    import socket

    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        print(f"[probe] 非法 base_url: {base_url!r}(仅支持 http/https 并带主机名)")
        return 2
    if parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
        print(f"[probe] 拒绝本机地址: {base_url!r}")
        return 2
    try:
        resolved = ipaddress.ip_address(socket.gethostbyname(parsed.hostname))
    except (socket.gaierror, ValueError):
        print(f"[probe] 无法解析主机: {parsed.hostname}")
        return 2
    if resolved.is_private or resolved.is_loopback or resolved.is_link_local:
        print(f"[probe] 拒绝内网目标({resolved}): {base_url!r}")
        return 2
    url = f"{parsed.scheme}://{parsed.netloc}/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": "只输出一个 JSON 对象:{\"risk_level\": \"low|medium|high\", \"reason\": \"20字以内依据\"}"},
            {"role": "user", "content": "今天天气挺好的"},
        ],
        "thinking": {"type": "disabled"},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    print(f"[probe] POST {url}")
    print(f"[probe] model={model}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as exc:
        print(f"[probe] HTTPError {exc.code}: {exc.reason}")
        body = exc.read().decode("utf-8", errors="replace")[:400]
        print(f"[probe] body={body}")
        return 1
    except Exception as exc:
        print(f"[probe] error: {exc!r}")
        return 1
    print(f"[probe] status={status}")
    try:
        data = json.loads(raw)
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        print(f"[probe] content={content!r}")
        print(f"[probe] usage={data.get('usage')}")
    except json.JSONDecodeError:
        print(f"[probe] non-json response (len={len(raw)}): {raw[:200]!r}")
        return 1
    return 0


def probe_samples() -> int:
    """对压力层全部隐喻式高危样本做真实 GLM 风险判定,产出 glm_probe_25.json。

    目的:扩大 sanity check 样本量,验证 MetaphorAwareStubClient 量出的"LLM 通道能力上界"
    是否是真实 GLM 能达到的水平。复用 OpenAICompatibleClient(项目 GLM 配置)。
    """
    _ensure_project_root_on_path()
    from app.config import Settings
    from app.llm import OpenAICompatibleClient

    corpus_path = _ROOT / "eval" / "fixtures" / "representative_corpus.json"
    out_dir = _ROOT / "data" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings()
    if not settings.openai_api_key:
        print("[glm-probe] OPENAI_API_KEY missing; abort")
        return 1

    client = OpenAICompatibleClient(settings)
    print(f"[glm-probe] provider={client.provider} model={client.model} base_url={client.base_url}")

    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = [c for c in corpus if c.get("layer") == "stress" and c.get("expected_risk") == "high"]
    print(f"[glm-probe] {len(cases)} stress+high cases (suicidal_implicit)")
    print(f"[glm-probe] sleep=8s between calls (avoid 429); estimated ~{len(cases)*8}s")

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
        "note": "best-effort probe on stress-layer suicidal_implicit cases; 429/timeout falls back to none",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
    }

    out = {"summary": summary, "results": results}
    out_path = out_dir / "glm_probe_25.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== GLM PROBE SAMPLES SUMMARY ===")
    print(f"matches: {matches}/{len(cases)} = {summary['match_rate']}")
    print(f"  high_correct={high_correct}  none_fallback={none_count}  other={other}")
    print(f"written: {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GLM endpoint probe")
    parser.add_argument("--samples", action="store_true", help="run the extended stress-layer sample probe and write glm_probe_25.json")
    args = parser.parse_args()
    if args.samples:
        return probe_samples()
    env = load_env(_ROOT / ".env")
    base_url = env.get("OPENAI_BASE_URL", "")
    api_key = env.get("OPENAI_API_KEY", "")
    model = env.get("OPENAI_MODEL", "")
    if not (base_url and api_key and model):
        print("[probe] missing OPENAI_BASE_URL/OPENAI_API_KEY/OPENAI_MODEL in .env")
        return 1
    return probe(base_url, api_key, model)


if __name__ == "__main__":
    sys.exit(main())
