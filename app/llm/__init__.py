"""模型后端层:可插拔的 LLM 客户端与提示词模板。

- client.py:LLMClient 协议 + Mock / OpenAI 兼容 / Ollama 三种实现与工厂
- prompts.py:支持回复与查询改写的消息模板
"""
from app.llm.client import (
    LLMClient,
    LLMContext,
    MockLLMClient,
    OllamaClient,
    OpenAICompatibleClient,
    build_llm_client,
    post_json,
)
from app.llm.prompts import build_messages, build_rewrite_messages

__all__ = [
    "LLMClient",
    "LLMContext",
    "MockLLMClient",
    "OllamaClient",
    "OpenAICompatibleClient",
    "build_llm_client",
    "build_messages",
    "build_rewrite_messages",
    "post_json",
]
