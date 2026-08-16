from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

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

    def rewrite_knowledge_query(self, message: str, memory_summary: str = "") -> str | None:
        ...


class MockLLMClient:
    provider = "mock"
    model = "rule-fallback"

    def status(self) -> dict:
        return {"provider": self.provider, "model": self.model, "enabled": False}

    def generate_support_reply(self, context: LLMContext) -> str | None:
        return None

    def rewrite_knowledge_query(self, message: str, memory_summary: str = "") -> str | None:
        return None


class OpenAICompatibleClient:
    provider = "openai"

    def __init__(self, settings: Settings):
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_base_url.rstrip("/")
        self.model = settings.openai_model
        self.timeout = settings.llm_timeout_seconds

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
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        data = post_json(f"{self.base_url}/chat/completions", payload, headers, self.timeout)
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        return content.strip() if content else None


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
