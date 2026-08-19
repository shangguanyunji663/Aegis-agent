"""评测数据集加载器。

设计原则（对应"禁止为追求满分而人为凑 100%"的要求）：

- 所有评测指标均基于 **真实代表性数据集**（人工构造但贴近真实校园心理求助语料），
  而非循环生成的伪样本。
- 提供可复现的随机抽样工具 `sample_cases`，便于从大规模语料中抽取固定规模子集，
  保证评测可重复、可审计。
- `generated_benchmark_cases` 保留为向后兼容别名，现直接返回代表性语料。

数据集位置：`eval/fixtures/`
- `representative_corpus.json`：150 条代表性消息（意图/风险双标注，含隐式高危与第三人称干扰项；每条另含 `layer`（base/stress）与 `source`（synthetic-representative/synthetic-boundary）字段，用于双层拆分）
- `rag_queries.json`：50 条自然语言检索问句（基于真实知识库文档，非关键词堆砌）
- `multi_turn_corpus.json`：8 组多轮对话场景（含升级到中/高风险与第三人称转自身）
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "eval" / "fixtures"
REPRESENTATIVE_CORPUS = FIXTURES_DIR / "representative_corpus.json"
RAG_QUERIES = FIXTURES_DIR / "rag_queries.json"
MULTI_TURN_CORPUS = FIXTURES_DIR / "multi_turn_corpus.json"


def load_representative_corpus() -> list[dict]:
    """加载 150 条代表性消息语料（真实标注，非循环生成）。

    每条记录字段：id, message, expected_intent, expected_risk, category, difficulty, note,
    layer（base/stress）, source（synthetic-representative/synthetic-boundary）
    """
    return json.loads(REPRESENTATIVE_CORPUS.read_text(encoding="utf-8"))


def load_rag_queries() -> list[dict]:
    """加载 RAG 检索评测问句（基于真实知识库文档的自然语言问句）。

    每条记录字段：id, question, expectedSources, expectedTerms
    """
    return json.loads(RAG_QUERIES.read_text(encoding="utf-8"))


def load_multi_turn_corpus() -> list[dict]:
    """加载多轮回归场景。

    每条记录字段：name, turns, expected_intent, expected_risk, expected_contains
    """
    return json.loads(MULTI_TURN_CORPUS.read_text(encoding="utf-8"))


def sample_cases(cases: list[dict], n: int, seed: int = 20240819) -> list[dict]:
    """可复现随机抽样：从大规模语料中抽取固定规模子集。

    使用固定种子的 ``random.Random``，保证同一 ``(cases, n, seed)`` 始终得到相同子集，
    使评测结果可复现、可审计。
    """
    if n >= len(cases):
        return list(cases)
    rng = random.Random(seed)
    return rng.sample(cases, n)


def generated_benchmark_cases() -> list[dict]:
    """向后兼容别名：返回代表性语料（150 条真实样本）。

    原实现仅用 5 个模板 × 30 轮循环生成 150 条伪样本（25 句唯一），
    无法反映真实分布。现改为直接加载代表性语料，杜绝人为凑满分。
    """
    return load_representative_corpus()
