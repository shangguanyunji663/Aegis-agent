"""文本基础件:面向中英文混合内容的分词、计数与余弦相似度。

分词策略:英文/数字按词,中文先逐字再补二元组(bigram),
使 BM25 与词法打分对中文短查询也具备区分度。
"""
from __future__ import annotations

import math
import re
from typing import Hashable


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", text.lower())
    grams = words[:]
    compact = "".join(ch for ch in text.lower() if "\u4e00" <= ch <= "\u9fff")
    grams.extend(compact[i:i + 2] for i in range(max(0, len(compact) - 1)))
    return [item for item in grams if item.strip()]


def counts(values: list[Hashable]) -> dict[Hashable, int]:
    result: dict[Hashable, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def token_cosine(left: str, right: str) -> float:
    left_counts = counts(tokenize(left))
    right_counts = counts(tokenize(right))
    if not left_counts or not right_counts:
        return 0.0
    dot = sum(value * right_counts.get(key, 0) for key, value in left_counts.items())
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    return 0.0 if left_norm == 0 or right_norm == 0 else dot / (left_norm * right_norm)
