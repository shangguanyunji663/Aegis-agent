"""外部与项目候选语料的风险标签映射。"""
from __future__ import annotations

import csv
import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

from aegis_training.data_contract import RiskSample

SELF_HIGH_PATTERN = re.compile(
    r"(想自杀|要自杀|想死|去死|不想活|不想活了|结束生命|结束一切|活着没意义|活着没有意义|"
    r"一起死|相约自杀|割腕|自残|跳楼|跳下去|杀了自己|捅死自己|自杀未遂|遗书|安眠药)"
)
THIRD_PARTY_CONTEXT_PATTERN = re.compile(
    r"(新闻|报道|看到|刷到|朋友|同学|室友|家人|她|他|他们|电视剧|电影|小说|论文|故事).{0,24}"
    r"(自杀|轻生|跳楼|割腕|自残|死亡|去世|想死)"
)


class SourceIngestError(ValueError):
    """外部或项目数据文件结构不符合已知格式。"""


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _bounded_reason(level: str) -> str:
    return {
        "low": "无明确自身自伤意向",
        "medium": "明显痛苦但无自伤意向",
        "high": "存在自身自伤自杀意向",
    }[level]


def _is_third_party_context(text: str) -> bool:
    return bool(THIRD_PARTY_CONTEXT_PATTERN.search(text or ""))


def _distortion_scope_and_risk(text: str) -> tuple[str, str]:
    if SELF_HIGH_PATTERN.search(text or ""):
        if _is_third_party_context(text):
            return "third_party", "low"
        return "self", "high"
    if _is_third_party_context(text):
        return "third_party", "low"
    return "self", "medium"


def _speaker_scope_and_risk_from_suicide(text: str, source_label: str) -> tuple[str, str, str]:
    """合并二分类源标签和主体检查，避免他人事件被当作说话人自身高危。"""
    if _is_third_party_context(text):
        return "third_party", "low", "rule_mapped"
    if source_label == "1":
        return "self", "high", "source_label"
    if SELF_HIGH_PATTERN.search(text or ""):
        return "self", "high", "rule_mapped"
    return "self", "low", "source_label"


def ingest_hongzhi_suicide(source_root: Path, split: str = "train") -> list[RiskSample]:
    """读取 HongzhiQ suicide 的 TSV 实际内容（文件扩展名虽为 csv）。"""
    if split not in {"train", "val"}:
        raise SourceIngestError("split must be train or val")
    path = source_root / "data" / "suicide" / f"suicide_{split}_LLM.csv"
    rows = _read_tsv(path)
    if not rows or set(rows[0]) != {"id", "label", "comment"}:
        raise SourceIngestError(f"unexpected suicide schema in {path}")
    samples: list[RiskSample] = []
    for row in rows:
        source_label = (row.get("label") or "").strip()
        text = (row.get("comment") or "").strip()
        if source_label not in {"0", "1"} or not text:
            continue
        scope, label, label_method = _speaker_scope_and_risk_from_suicide(text, source_label)
        samples.append(
            RiskSample(
                sample_id=f"hongzhi-suicide-{split}-{row['id']}",
                message=text,
                risk_level=label,
                reason=_bounded_reason(label),
                source="hongzhiq-suicide",
                source_version="SupervisedVsLLM-EfficacyEval@78fb4d1",
                label_method=label_method,
                review_status="source_provided" if label_method == "source_label" else "not_reviewed",
                annotator="source-label-mapping-v2",
                speaker_scope=scope,
                adjudication_note=f"source label={source_label}; subject-aware mapping={label_method}",
            )
        )
    return samples


def ingest_socialcd(source_root: Path, split: str = "train") -> list[RiskSample]:
    """读取 SocialCD-3k，作为中文认知困扰的 medium/high 补充来源。"""
    file_map = {"train": "train_data_with_header.tsv", "test": "test_data_with_header.tsv"}
    if split not in file_map:
        raise SourceIngestError("split must be train or test")
    path = source_root / "data" / "SocialCD-3k" / file_map[split]
    rows = _read_tsv(path)
    if not rows or "内容" not in rows[0]:
        raise SourceIngestError(f"unexpected SocialCD schema in {path}")
    samples: list[RiskSample] = []
    for index, row in enumerate(rows, 1):
        text = (row.get("内容") or "").strip()
        if not text:
            continue
        scope, level = _distortion_scope_and_risk(text)
        samples.append(
            RiskSample(
                sample_id=f"socialcd-{split}-{index}",
                message=text,
                risk_level=level,
                reason=_bounded_reason(level),
                source="hongzhiq-socialcd-3k",
                source_version="SupervisedVsLLM-EfficacyEval@78fb4d1",
                label_method="rule_mapped",
                review_status="not_reviewed",
                annotator="weak-risk-mapping-v2",
                speaker_scope=scope,
                adjudication_note="cognitive-distortion data; subject-aware weak risk mapping",
            )
        )
    return samples


def _messages_user_content(record: object) -> str:
    if not isinstance(record, dict):
        return ""
    messages = record.get("messages")
    if not isinstance(messages, list):
        return ""
    for item in messages:
        if isinstance(item, dict) and item.get("role") == "user" and isinstance(item.get("content"), str):
            return item["content"].strip()
    return ""


def ingest_cognitive_distortion(source_root: Path, split: str = "train") -> list[RiskSample]:
    """读取认知歪曲 JSONL，补齐 medium 类校园心理困扰表达。"""
    if split not in {"train", "val"}:
        raise SourceIngestError("split must be train or val")
    path = source_root / "data" / "cognitive distortion" / f"cognitive_distortion_{split}.jsonl"
    samples: list[RiskSample] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            text = _messages_user_content(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SourceIngestError(f"invalid JSONL in {path}:{index}") from exc
        if not text:
            continue
        scope, level = _distortion_scope_and_risk(text)
        samples.append(
            RiskSample(
                sample_id=f"hongzhi-cognitive-{split}-{index}",
                message=text,
                risk_level=level,
                reason=_bounded_reason(level),
                source="hongzhiq-cognitive-distortion",
                source_version="SupervisedVsLLM-EfficacyEval@78fb4d1",
                label_method="rule_mapped",
                review_status="not_reviewed",
                annotator="weak-risk-mapping-v2",
                speaker_scope=scope,
                adjudication_note="cognitive-distortion source; subject-aware weak risk mapping",
            )
        )
    return samples


def _read_committed_json(project_root: Path, relative_path: str) -> object:
    """只读取 HEAD 中的项目数据，避免工作区改动悄然进入训练集。"""
    try:
        completed = subprocess.run(
            ["git", "-C", str(project_root), "show", f"HEAD:{relative_path}"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise SourceIngestError(f"cannot read committed project dataset HEAD:{relative_path}") from exc


def _project_record(
    sample_id: str,
    message: object,
    level: object,
    source: str,
    note: str,
) -> RiskSample | None:
    if not isinstance(message, str) or not message.strip() or not isinstance(level, str):
        return None
    normalized_level = level.strip().lower()
    if normalized_level not in {"low", "medium", "high"}:
        return None
    scope = "self"
    if normalized_level == "high" and _is_third_party_context(message):
        normalized_level = "low"
        scope = "third_party"
        note = f"{note}; third-party subject override"
    return RiskSample(
        sample_id=sample_id,
        message=message.strip(),
        risk_level=normalized_level,
        reason=_bounded_reason(normalized_level),
        source=source,
        source_version="project-HEAD",
        label_method="project_mapped",
        review_status="project_fixture",
        annotator="project-fixture-mapping-v1",
        speaker_scope=scope,
        adjudication_note=note,
    )


def load_project_candidate_pool(project_root: Path) -> list[RiskSample]:
    """从已提交 corpus 的 ``base`` 层取开发样本，``stress`` 层永久保留为最终 holdout。"""
    corpus_rows = _read_committed_json(project_root, "eval/fixtures/representative_corpus.json")
    samples: list[RiskSample] = []
    if isinstance(corpus_rows, list):
        for row in corpus_rows:
            if not isinstance(row, dict) or row.get("layer") != "base":
                continue
            corpus_id = row.get("id")
            sample = _project_record(
                f"project-corpus-{corpus_id}",
                row.get("message"),
                row.get("expected_risk"),
                "project-representative-base",
                "committed representative corpus base-layer expected_risk mapping",
            )
            if sample:
                samples.append(sample)
    return dedupe_samples(samples)


def dedupe_samples(samples: Iterable[RiskSample]) -> list[RiskSample]:
    """同一文本保留风险更高的第一条，避免跨格式文件重复。"""
    order = {"low": 1, "medium": 2, "high": 3}
    by_text: dict[str, RiskSample] = {}
    for sample in samples:
        current = by_text.get(sample.normalized_message)
        if current is None or order[sample.risk_level] > order[current.risk_level]:
            by_text[sample.normalized_message] = sample
    return list(by_text.values())


def load_hongzhi_candidate_pool(source_root: Path, include_validation: bool = True) -> list[RiskSample]:
    """聚合用户指定公开仓库的可用风险候选池。"""
    samples = [
        *ingest_hongzhi_suicide(source_root, "train"),
        *ingest_socialcd(source_root, "train"),
        *ingest_cognitive_distortion(source_root, "train"),
    ]
    if include_validation:
        samples.extend(
            [
                *ingest_hongzhi_suicide(source_root, "val"),
                *ingest_socialcd(source_root, "test"),
                *ingest_cognitive_distortion(source_root, "val"),
            ]
        )
    return dedupe_samples(samples)
