"""会话记忆摘要:滚动式把每轮对话压缩成一行要点,并按字符预算裁剪旧内容。"""
from __future__ import annotations

import re


def build_memory_summary(previous: str, user_message: str, assistant_answer: str, max_chars: int) -> str:
    user_focus = compact_sentence(user_message, 120)
    answer_focus = compact_sentence(assistant_answer, 160)
    new_line = f"用户提到：{user_focus}；系统回应重点：{answer_focus}"
    lines = [line for line in (previous.splitlines() if previous else []) if line.strip()]
    lines.append(new_line)
    kept: list[str] = []
    current_length = 0
    for line in reversed(lines):
        extra = len(line) + (1 if kept else 0)
        if kept and current_length + extra > max_chars:
            break
        if not kept and len(line) > max_chars:
            kept.append(line[:max_chars])
            break
        kept.append(line)
        current_length += extra
    return "\n".join(reversed(kept)).strip()


def compact_sentence(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:limit] + ("..." if len(text) > limit else "")
