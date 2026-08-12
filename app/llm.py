from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings
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


def build_messages(context: LLMContext) -> list[dict[str, str]]:
    knowledge = "\n".join(f"- {snippet}" for snippet in context.knowledge_snippets[:3]) or "- 暂无命中的本地知识。"
    grounding = "\n".join(f"- {step}" for step in context.grounding_steps) or "- 当前不需要急性稳定练习。"
    response_skills = context.response_skill_context or "暂无额外标准 Skill。"
    system = (
        "你是校园心理支持产品中的咨询回复生成器。"
        "只能提供支持性倾听、问题澄清、自助练习和求助准备；不能诊断，不能承诺保密，不能替代专业咨询。"
        "高风险安全分流由上游规则处理，你不得输出内部风险分数、报告编号或后台审计细节。"
        "回复要使用简体中文，温和、具体、简洁。"
    )
    user = (
        f"用户消息：{context.message}\n"
        f"历史摘要：{context.memory_summary or '暂无'}\n"
        f"路由意图：{context.intent.value}\n"
        f"风险等级：{context.risk_level.value}\n"
        f"可引用知识：\n{knowledge}\n"
        f"可用稳定练习：\n{grounding}\n\n"
        f"标准回复 Skill：\n{response_skills}\n\n"
        "请生成一段面向用户的回复，先共情，再给 1-3 个可执行下一步，最后用一个开放问题邀请继续表达。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_rewrite_messages(message: str, memory_summary: str = "") -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "你是 Aegis 的 KnowledgeAgent。把学生输入改写成适合检索校园心理知识库的中文查询词，只输出查询词。",
        },
        {
            "role": "user",
            "content": f"记忆摘要：\n{memory_summary or '暂无'}\n\n当前输入：\n{message}",
        },
    ]


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
