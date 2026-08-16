from __future__ import annotations

import json
import re
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
    "你是校园心理支持系统的风险评估器。只依据用户消息判断心理危机风险等级:"
    "high(自伤/自杀/伤人意图或计划)、medium(强烈痛苦、绝望、功能受损)、low(一般困扰)。"
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


class OpenAICompatibleClient:
    provider = "openai"

    def __init__(self, settings: Settings):
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_base_url.rstrip("/")
        self.model = settings.openai_model
        self.timeout = settings.llm_timeout_seconds
        self.disable_thinking = not settings.llm_thinking_enabled

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
            "temperature": 0.2,
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

    def stream_support_reply(self, context: LLMContext, on_token: Callable[[str], None]) -> str | None:
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "temperature": 0.2,
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

    def stream_support_reply(self, context: LLMContext, on_token: Callable[[str], None]) -> str | None:
        payload = {
            "model": self.model,
            "stream": True,
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


def post_json(url: str, payload: dict, headers: dict[str, str], timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return {}


def post_json_stream(url: str, payload: dict, headers: dict[str, str], timeout: float, on_token: Callable[[str], None]) -> str | None:
    """OpenAI 兼容 SSE 流式请求:逐 delta 回调 on_token,返回累积全文(失败返回 None)。

    中途异常时返回已积累的部分(这些内容用户已经看到),一个字都没拿到才返回 None。
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    parts: list[str] = []
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
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return "".join(parts) or None
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
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return "".join(parts) or None
    return "".join(parts) or None
