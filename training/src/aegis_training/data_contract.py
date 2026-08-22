"""风险 QLoRA 数据契约、SFT 转换和训练标签校验。"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

RISK_LEVELS = frozenset({"low", "medium", "high"})
REQUIRED_FIELDS = frozenset({"sample_id", "message", "risk_level", "reason", "source"})
LABEL_METHODS = frozenset({"source_label", "rule_mapped", "project_mapped", "manual_reviewed", "synthetic"})

RISK_SYSTEM_PROMPT = (
    "你是校园心理支持系统的风险评估器,只依据当下说话人的**自身意向**判断风险:"
    "high(自伤/自杀意念或计划,包括隐喻式表达如想消失/活着多余/从没出生过/不配/撑不下去/永远睡过去/离开这个世界/结束这一切/不愿再醒来/要是不在了就好了),"
    "medium(强烈痛苦、绝望、功能受损但无直接自伤)、"
    "low(一般困扰,包括提及他人/虚构情境的高危词,如\"新闻里有人轻生/写论文提到自杀/朋友直播自杀\"——这些不应升为自身风险)。"
    "判定原则:仅评估说话人自身;他人或虚构内容提及自杀/伤害不视为自身 high。"
    "只输出一个 JSON 对象,不要输出任何其他文字:"
    '{"risk_level": "low|medium|high", "reason": "20字以内依据"}'
)


class DataContractError(ValueError):
    """训练样本不满足文本、标签或来源记录约束时抛出。"""


@dataclass(frozen=True)
class RiskSample:
    sample_id: str
    message: str
    risk_level: str
    reason: str
    source: str
    source_version: str = "unspecified"
    label_method: str = "rule_mapped"
    review_status: str = "not_reviewed"
    annotator: str = "automated-mapping"
    speaker_scope: str = "self"
    adjudication_note: str = ""

    @property
    def normalized_message(self) -> str:
        return normalize_message(self.message)

    @property
    def message_hash(self) -> str:
        return text_hash(self.normalized_message)

    def to_sft_record(self) -> dict[str, list[dict[str, str]]]:
        answer = json.dumps(
            {"risk_level": self.risk_level, "reason": self.reason},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return {
            "messages": [
                {"role": "system", "content": RISK_SYSTEM_PROMPT},
                {"role": "user", "content": self.message},
                {"role": "assistant", "content": answer},
            ]
        }

    def manifest_row(self) -> dict[str, Any]:
        row = asdict(self)
        row.pop("message")
        row["message_sha256"] = self.message_hash
        return row


def normalize_message(value: str) -> str:
    """用于泄漏检测的稳定文本规范化，不改变训练原文。"""
    text = unicodedata.normalize("NFKC", value or "").lower().strip()
    return re.sub(r"\s+", "", text)


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _required_text(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DataContractError(f"{record.get('sample_id', '<unknown>')}: {key} must be a non-empty string")
    return value.strip()


def _optional_text(record: dict[str, Any], key: str, default: str) -> str:
    value = record.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise DataContractError(f"{record.get('sample_id', '<unknown>')}: {key} must be a string")
    return value.strip() or default


def parse_sample(record: dict[str, Any]) -> RiskSample:
    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        raise DataContractError(f"{record.get('sample_id', '<unknown>')}: missing fields {sorted(missing)}")

    sample = RiskSample(
        sample_id=_required_text(record, "sample_id"),
        message=_required_text(record, "message"),
        risk_level=_required_text(record, "risk_level").lower(),
        reason=_required_text(record, "reason"),
        source=_required_text(record, "source"),
        source_version=_optional_text(record, "source_version", "unspecified"),
        label_method=_optional_text(record, "label_method", "rule_mapped").lower(),
        review_status=_optional_text(record, "review_status", "not_reviewed").lower(),
        annotator=_optional_text(record, "annotator", "automated-mapping"),
        speaker_scope=_optional_text(record, "speaker_scope", "self").lower(),
        adjudication_note=_optional_text(record, "adjudication_note", ""),
    )
    validate_sample(sample)
    return sample


def validate_sample(sample: RiskSample) -> None:
    if sample.risk_level not in RISK_LEVELS:
        raise DataContractError(f"{sample.sample_id}: risk_level must be one of {sorted(RISK_LEVELS)}")
    if sample.label_method not in LABEL_METHODS:
        raise DataContractError(f"{sample.sample_id}: unsupported label_method={sample.label_method!r}")
    if len(sample.reason) > 20:
        raise DataContractError(f"{sample.sample_id}: reason exceeds 20 characters")
    if len(sample.message) > 1500:
        raise DataContractError(f"{sample.sample_id}: message exceeds 1500 characters; split or curate it")
    if sample.speaker_scope not in {"self", "third_party", "fictional"}:
        raise DataContractError(f"{sample.sample_id}: unsupported speaker_scope={sample.speaker_scope!r}")
    if sample.risk_level == "high" and sample.speaker_scope != "self":
        raise DataContractError(f"{sample.sample_id}: high samples must describe the speaker's own risk")


def load_raw_jsonl(path: Path) -> list[RiskSample]:
    samples: list[RiskSample] = []
    sample_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DataContractError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise DataContractError(f"{path}:{line_number}: JSONL record must be an object")
            sample = parse_sample(record)
            if sample.sample_id in sample_ids:
                raise DataContractError(f"{path}:{line_number}: duplicate sample_id={sample.sample_id}")
            sample_ids.add(sample.sample_id)
            samples.append(sample)
    if not samples:
        raise DataContractError(f"{path}: no valid samples")
    return samples


def write_jsonl(records: Iterable[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def label_distribution(samples: Iterable[RiskSample]) -> dict[str, int]:
    counts = {level: 0 for level in sorted(RISK_LEVELS)}
    for sample in samples:
        counts[sample.risk_level] += 1
    return counts
