"""GLM 端点探针:验证 OpenAI 兼容 endpoint 与模型名是否可用。

不打印 API key,只报告端点/模型/响应状态。退出码 0=可用,1=不可用。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


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


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    env = load_env(root / ".env")
    base_url = env.get("OPENAI_BASE_URL", "")
    api_key = env.get("OPENAI_API_KEY", "")
    model = env.get("OPENAI_MODEL", "")
    if not (base_url and api_key and model):
        print("[probe] missing OPENAI_BASE_URL/OPENAI_API_KEY/OPENAI_MODEL in .env")
        return 1
    return probe(base_url, api_key, model)


if __name__ == "__main__":
    sys.exit(main())
