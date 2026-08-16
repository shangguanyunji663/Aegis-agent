"""LLM-as-Judge:用模型为回复打共情性/安全性/结构性分,进入评测报告。

- judge_reply 封装在各 LLMClient 实现(严格 JSON 输出);mock 返回 None。
- 本模块负责对抽样对话运行评分并聚合,失败/mock 时优雅跳过(judge=None)。
"""
from __future__ import annotations

from typing import Any


def judge_reply(llm_client, message: str, reply: str) -> dict | None:
    """单条评分;客户端不支持/失败一律返回 None(调用方跳过)。"""
    try:
        return llm_client.judge_reply(message, reply)
    except Exception:
        return None


def evaluate_reply_quality(llm_client, samples: list[dict[str, str]]) -> dict[str, Any] | None:
    """对抽样 (message, reply) 逐条评分并聚合平均分。无任何可用评分时返回 None。"""
    scored = []
    for sample in samples:
        scores = judge_reply(llm_client, sample["message"], sample["reply"])
        if scores is not None:
            scored.append({"message": sample["message"][:40], "reply": sample["reply"][:60], **scores})
    if not scored:
        return None
    total = len(scored)
    avg = {
        key: round(sum(item[key] for item in scored) / total, 2)
        for key in ("empathy", "safety", "structure")
    }
    return {"total": total, "avg": avg, "cases": scored}
