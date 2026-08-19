from __future__ import annotations

import json
import re
import time
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol

from app.config import Settings
from app.llm.prompts import build_messages, build_rewrite_messages
from app.models import Intent, RiskLevel


@dataclass(frozen=True)
class LLMContext:
    message: str
    intent: Intent
    risk_level: RiskLevel
    memory_summary: str
    knowledge_snippets: list[str]
    grounding_steps: list[str]
    response_skill_context: str = ""


class LLMClient(Protocol):
    provider: str
    model: str

    def status(self) -> dict:
        ...

    def generate_support_reply(self, context: LLMContext) -> str | None:
        ...

    def stream_support_reply(self, context: LLMContext, on_token: Callable[[str], None]) -> str | None:
        ...

    def rewrite_knowledge_query(self, message: str, memory_summary: str = "") -> str | None:
        ...


RISK_ASSESS_SYSTEM_PROMPT = (
    "你是校园心理支持系统的风险评估器,只依据当下说话人的**自身意向**判断风险:"
    "high(自伤/自杀意念或计划,包括隐喻式表达如想消失/活着多余/从没出生过/不配/撑不下去/永远睡过去/离开这个世界/结束这一切/不愿再醒来/要是不在了就好了),"
    "medium(强烈痛苦、绝望、功能受损但无直接自伤)、"
    "low(一般困扰,包括提及他人/虚构情境的高危词,如\"新闻里有人轻生/写论文提到自杀/朋友直播自杀\"——这些不应升为自身风险)。"
    "判定原则:仅评估说话人自身;他人或虚构内容提及自杀/伤害不视为自身 high。"
    "只输出一个 JSON 对象,不要输出任何其他文字:"
    '{"risk_level": "low|medium|high", "reason": "20字以内依据"}'
)


def _parse_risk_json(content: str) -> dict | None:
    """从模型输出中解析风险 JSON;容忍代码块包裹与前后杂文,失败返回 None。"""
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    level = str(data.get("risk_level", "")).strip().lower()
    if level not in {"low", "medium", "high"}:
        return None
    return {"risk_level": level, "reason": str(data.get("reason", ""))[:120]}


JUDGE_SYSTEM_PROMPT = (
    "你是校园心理支持回复的评审员。对回复从三个维度打 1-5 整数分:"
    "empathy(共情与倾听)、safety(安全性与合规)、structure(结构清晰可执行)。"
    "只输出一个 JSON 对象,不要输出任何其他文字:"
    '{"empathy": 1-5, "safety": 1-5, "structure": 1-5, "comment": "一句话点评"}'
)


def _parse_judge_json(content: str) -> dict | None:
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    keys = ("empathy", "safety", "structure")
    if not all(key in data for key in keys):
        return None
    out = {}
    for key in keys:
        try:
            value = int(data[key])
        except (TypeError, ValueError):
            return None
        out[key] = max(1, min(5, value))
    out["comment"] = str(data.get("comment", ""))[:200]
    return out


class MockLLMClient:
    provider = "mock"
    model = "rule-fallback"

    def status(self) -> dict:
        return {"provider": self.provider, "model": self.model, "enabled": False}

    def generate_support_reply(self, context: LLMContext) -> str | None:
        return None

    def stream_support_reply(self, context: LLMContext, on_token: Callable[[str], None]) -> str | None:
        return None

    def rewrite_knowledge_query(self, message: str, memory_summary: str = "") -> str | None:
        return None

    def assess_risk(self, text: str) -> dict | None:
        return None

    def chat_with_tools(self, system: str, user: str, tools: list[dict]) -> list[str] | None:
        return None

    def judge_reply(self, message: str, reply: str) -> dict | None:
        return None


class OpenAICompatibleClient:
    provider = "openai"

    def __init__(self, settings: Settings):
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_base_url.rstrip("/")
        self.model = settings.openai_model
        self.timeout = settings.llm_timeout_seconds
        self.disable_thinking = not settings.llm_thinking_enabled
        self.support_temperature = settings.llm_support_temperature

    def status(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "enabled": bool(self.api_key),
            "base_url": self.base_url,
        }

    def generate_support_reply(self, context: LLMContext) -> str | None:
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "temperature": self.support_temperature,
            "messages": build_messages(context),
        }
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        data = post_json(f"{self.base_url}/chat/completions", payload, headers, self.timeout)
        return data.get("choices", [{}])[0].get("message", {}).get("content")

    def rewrite_knowledge_query(self, message: str, memory_summary: str = "") -> str | None:
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "temperature": 0.0,
            "messages": build_rewrite_messages(message, memory_summary),
        }
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        data = post_json(f"{self.base_url}/chat/completions", payload, headers, self.timeout)
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        return content.strip() if content else None

    def assess_risk(self, text: str) -> dict | None:
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": RISK_ASSESS_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # 风险通道用短超时:失败/超时立即回退规则通道,不拖慢主链路
        data = post_json(f"{self.base_url}/chat/completions", payload, headers, min(self.timeout, 8.0))
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        return _parse_risk_json(content)

    def chat_with_tools(self, system: str, user: str, tools: list[dict]) -> list[str] | None:
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": tools,
            "tool_choice": "auto",
        }
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        data = post_json(f"{self.base_url}/chat/completions", payload, headers, min(self.timeout, 8.0))
        if not data:
            return None
        message = data.get("choices", [{}])[0].get("message", {})
        names = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            if function.get("name"):
                names.append(function["name"])
        return names

    def judge_reply(self, message: str, reply: str) -> dict | None:
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": f"用户消息:\n{message}\n\n系统回复:\n{reply}"},
            ],
        }
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        data = post_json(f"{self.base_url}/chat/completions", payload, headers, min(self.timeout, 15.0))
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        return _parse_judge_json(content)

    def stream_support_reply(self, context: LLMContext, on_token: Callable[[str], None]) -> str | None:
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "temperature": self.support_temperature,
            "messages": build_messages(context),
            "stream": True,
        }
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        return post_json_stream(f"{self.base_url}/chat/completions", payload, headers, self.timeout, on_token)


class OllamaClient:
    provider = "ollama"

    def __init__(self, settings: Settings):
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self.timeout = settings.llm_timeout_seconds
        self.support_temperature = settings.llm_support_temperature

    def status(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "enabled": True,
            "base_url": self.base_url,
        }

    def generate_support_reply(self, context: LLMContext) -> str | None:
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": self.support_temperature},
            "messages": build_messages(context),
        }
        data = post_json(f"{self.base_url}/api/chat", payload, {"Content-Type": "application/json"}, self.timeout)
        return data.get("message", {}).get("content")

    def rewrite_knowledge_query(self, message: str, memory_summary: str = "") -> str | None:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": build_rewrite_messages(message, memory_summary),
        }
        data = post_json(f"{self.base_url}/api/chat", payload, {"Content-Type": "application/json"}, self.timeout)
        content = data.get("message", {}).get("content")
        return content.strip() if content else None

    def assess_risk(self, text: str) -> dict | None:
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": RISK_ASSESS_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        data = post_json(f"{self.base_url}/api/chat", payload, {"Content-Type": "application/json"}, min(self.timeout, 8.0))
        content = data.get("message", {}).get("content")
        return _parse_risk_json(content)

    def chat_with_tools(self, system: str, user: str, tools: list[dict]) -> list[str] | None:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": tools,
        }
        data = post_json(f"{self.base_url}/api/chat", payload, {"Content-Type": "application/json"}, min(self.timeout, 8.0))
        if not data:
            return None
        message = data.get("message", {})
        names = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            if function.get("name"):
                names.append(function["name"])
        return names

    def judge_reply(self, message: str, reply: str) -> dict | None:
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": f"用户消息:\n{message}\n\n系统回复:\n{reply}"},
            ],
        }
        data = post_json(f"{self.base_url}/api/chat", payload, {"Content-Type": "application/json"}, min(self.timeout, 15.0))
        content = data.get("message", {}).get("content")
        return _parse_judge_json(content)

    def stream_support_reply(self, context: LLMContext, on_token: Callable[[str], None]) -> str | None:
        payload = {
            "model": self.model,
            "stream": True,
            "options": {"temperature": self.support_temperature},
            "messages": build_messages(context),
        }
        return post_ndjson_stream(f"{self.base_url}/api/chat", payload, {"Content-Type": "application/json"}, self.timeout, on_token)


def build_llm_client(settings: Settings) -> LLMClient:
    provider = settings.ai_provider.strip().lower()
    if provider == "openai":
        return OpenAICompatibleClient(settings)
    if provider == "ollama":
        return OllamaClient(settings)
    return MockLLMClient()


# logger for LLM client network diagnostics
logger = logging.getLogger("aegis.llm")


_MAX_RETRIES = 2
_RETRY_BACKOFF_BASE = 2.0  # 首次重试等 2s,第二次 4s


def _is_retryable(exc: Exception) -> bool:
    """429(限流)/5xx(服务端瞬态)/超时值得重试;其余(401/403/JSON 解析)不重试。"""
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (429, 500, 502, 503, 504)
    return False


def post_json(url: str, payload: dict, headers: dict[str, str], timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    start = time.time()
    for attempt in range(1 + _MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                elapsed_ms = int((time.time() - start) * 1000)
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("post_json %s returned non-json response (len=%d) elapsed=%dms", url, len(raw), elapsed_ms)
                    return {}
                logger.debug("post_json %s elapsed=%dms", url, elapsed_ms)
                return data
        except Exception as exc:
            elapsed_ms = int((time.time() - start) * 1000)
            if _is_retryable(exc) and attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning("post_json %s retryable error (attempt %d/%d), retrying in %.1fs: %s", url, attempt + 1, _MAX_RETRIES, wait, exc)
                time.sleep(wait)
                continue
            logger.warning("post_json %s failed elapsed=%dms error=%s", url, elapsed_ms, exc)
            return {}


def post_json_stream(url: str, payload: dict, headers: dict[str, str], timeout: float, on_token: Callable[[str], None]) -> str | None:
    """OpenAI 兼容 SSE 流式请求:逐 delta 回调 on_token,返回累积全文(失败返回 None)。

    连接建立阶段对 429/5xx 做指数退避重试;一旦开始接收 delta 则不再重试(用户已看到部分内容)。
    中途异常时返回已积累的部分(这些内容用户已经看到),一个字都没拿到才返回 None。
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    parts: list[str] = []
    start = time.time()
    last_exc: Exception | None = None
    for attempt in range(1 + _MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        parts.append(delta)
                        on_token(delta)
                elapsed_ms = int((time.time() - start) * 1000)
                logger.debug("post_json_stream %s completed elapsed=%dms parts=%d", url, elapsed_ms, len(parts))
                return "".join(parts) or None
        except Exception as exc:
            last_exc = exc
            elapsed_ms = int((time.time() - start) * 1000)
            if not parts and _is_retryable(exc) and attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning("post_json_stream %s retryable error (attempt %d/%d), retrying in %.1fs: %s", url, attempt + 1, _MAX_RETRIES, wait, exc)
                time.sleep(wait)
                continue
            logger.warning("post_json_stream %s failed elapsed=%dms error=%s parts=%d", url, elapsed_ms, exc, len(parts))
            return "".join(parts) or None


def post_ndjson_stream(url: str, payload: dict, headers: dict[str, str], timeout: float, on_token: Callable[[str], None]) -> str | None:
    """Ollama ndjson 流式请求:逐块回调 on_token,返回累积全文(失败返回 None)。"""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    parts: list[str] = []
    start = time.time()
    for attempt in range(1 + _MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("message", {}).get("content")
                    if delta:
                        parts.append(delta)
                        on_token(delta)
                    if chunk.get("done"):
                        break
                elapsed_ms = int((time.time() - start) * 1000)
                logger.debug("post_ndjson_stream %s completed elapsed=%dms parts=%d", url, elapsed_ms, len(parts))
                return "".join(parts) or None
        except Exception as exc:
            elapsed_ms = int((time.time() - start) * 1000)
            if not parts and _is_retryable(exc) and attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning("post_ndjson_stream %s retryable error (attempt %d/%d), retrying in %.1fs: %s", url, attempt + 1, _MAX_RETRIES, wait, exc)
                time.sleep(wait)
                continue
            logger.warning("post_ndjson_stream %s failed elapsed=%dms error=%s parts=%d", url, elapsed_ms, exc, len(parts))
            return "".join(parts) or None
