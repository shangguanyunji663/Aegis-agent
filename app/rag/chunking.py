"""知识文档处理:YAML frontmatter 解析、元数据过滤、查询规整与滑窗切块。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.utils import loads_or

if TYPE_CHECKING:
    from app.entities import KnowledgeChunk


def parse_knowledge_document(source: str, content: str) -> tuple[dict[str, str], str]:
    """解析知识文档:识别 `---` 包裹的 YAML frontmatter,返回(元数据, 正文)。"""
    default = {
        "topic": Path(source).stem,
        "audience": "student",
        "risk_level": "low",
        "source_type": "local_markdown",
        "last_reviewed": "",
    }
    text = content or ""
    if not text.startswith("---\n"):
        return default, text
    end = text.find("\n---", 4)
    if end == -1:
        return default, text
    raw = text[4:end].strip()
    body = text[end + 4:].lstrip()
    metadata = dict(default)
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().lower()
        if normalized_key in metadata:
            metadata[normalized_key] = value.strip().strip("\"'")
    metadata["source"] = source
    return metadata, body


def metadata_matches(metadata: dict, topic: str | None = None, risk_level: str | None = None, audience: str | None = None) -> bool:
    filters = {
        "topic": topic,
        "risk_level": risk_level,
        "audience": audience,
    }
    for key, expected in filters.items():
        value = (expected or "").strip().lower()
        if not value:
            continue
        actual = str(metadata.get(key, "")).strip().lower()
        if actual != value:
            return False
    return True


def knowledge_metadata_summary(rows: list[KnowledgeChunk]) -> dict[str, list[str]]:
    summary = {"topics": set(), "risk_levels": set(), "audiences": set(), "source_types": set()}
    for row in rows:
        metadata = loads_or(row.metadata_json, {})
        if metadata.get("topic"):
            summary["topics"].add(str(metadata["topic"]))
        if metadata.get("risk_level"):
            summary["risk_levels"].add(str(metadata["risk_level"]))
        if metadata.get("audience"):
            summary["audiences"].add(str(metadata["audience"]))
        if metadata.get("source_type"):
            summary["source_types"].add(str(metadata["source_type"]))
    return {key: sorted(values) for key, values in summary.items()}


def rewrite_query(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= 60:
        return text
    return text[:60]


def chunk_text(content: str, size: int, overlap: int) -> list[str]:
    text = re.sub(r"\s+", " ", content or "").strip()
    if not text:
        return []
    chunks = []
    start = 0
    step = max(1, size - overlap)
    while start < len(text):
        chunks.append(text[start:start + size])
        start += step
    return chunks
