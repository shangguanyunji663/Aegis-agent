"""冻结最终评测集保护与训练数据去重。"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from aegis_training.data_contract import RiskSample, normalize_message, text_hash

FINAL_HOLDOUT_PATH = Path("eval/fixtures/representative_corpus.json")


@dataclass(frozen=True)
class LeakageMatch:
    sample_id: str
    source_path: str
    kind: str
    score: float
    preview: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _char_ngrams(value: str, width: int = 3) -> set[str]:
    normalized = normalize_message(value)
    if len(normalized) < width:
        return {normalized} if normalized else set()
    return {normalized[index:index + width] for index in range(len(normalized) - width + 1)}


def _similarity(left: str, right: str) -> float:
    left_grams = _char_ngrams(left)
    right_grams = _char_ngrams(right)
    jaccard = len(left_grams & right_grams) / len(left_grams | right_grams) if left_grams and right_grams else 0.0
    sequence = SequenceMatcher(None, normalize_message(left), normalize_message(right)).ratio()
    return max(jaccard, sequence)


def _candidate_indexes(text: str, inverted_ngrams: dict[str, set[int]], minimum_shared: int = 3) -> set[int]:
    counts: Counter[int] = Counter()
    for gram in _char_ngrams(text):
        counts.update(inverted_ngrams.get(gram, ()))
    return {index for index, count in counts.items() if count >= minimum_shared}


def _read_final_holdout(root: Path) -> list[str]:
    path = root / FINAL_HOLDOUT_PATH
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read frozen final holdout: {path}") from exc
    if not isinstance(rows, list):
        raise ValueError(f"frozen final holdout must be a JSON array: {path}")
    return [
        str(row["message"])
        for row in rows
        if isinstance(row, dict)
        and row.get("layer") == "stress"
        and isinstance(row.get("message"), str)
    ]


def scan_final_holdout_leakage(
    samples: Iterable[RiskSample],
    root: Path | None = None,
    near_duplicate_threshold: float = 0.82,
) -> list[LeakageMatch]:
    """拒绝与 stress 最终评测集的精确或近重复样本。

    先用规范化哈希拒绝精确复用，再用共享字符 n-gram 预筛选候选，避免对数千候选
    逐一执行昂贵的 ``SequenceMatcher``。满足 0.82 近重复阈值的文本会共享多个 3-gram，
    因而不会降低该类泄漏的检测覆盖。
    """
    if not 0.0 < near_duplicate_threshold <= 1.0:
        raise ValueError("near_duplicate_threshold must be in (0, 1]")
    root = root or _repo_root()
    source_path = str(FINAL_HOLDOUT_PATH)
    holdout_texts = _read_final_holdout(root)
    holdout_hashes = {text_hash(normalize_message(item)): item for item in holdout_texts}
    ngram_index: dict[str, set[int]] = defaultdict(set)
    for index, text in enumerate(holdout_texts):
        for gram in _char_ngrams(text):
            ngram_index[gram].add(index)

    matches: list[LeakageMatch] = []
    for sample in samples:
        normalized = sample.normalized_message
        exact = holdout_hashes.get(text_hash(normalized))
        if exact is not None:
            matches.append(LeakageMatch(sample.sample_id, source_path, "exact", 1.0, exact[:80]))
            continue
        for index in _candidate_indexes(sample.message, ngram_index):
            holdout_text = holdout_texts[index]
            score = _similarity(sample.message, holdout_text)
            if score >= near_duplicate_threshold:
                matches.append(LeakageMatch(sample.sample_id, source_path, "near_duplicate", round(score, 4), holdout_text[:80]))
                break
    return matches


def dedupe_against_selected(samples: Iterable[RiskSample], near_duplicate_threshold: float = 0.92) -> list[RiskSample]:
    """对候选池内部精确/强近重复去重，保留输入顺序中首个样本。"""
    if not 0.0 < near_duplicate_threshold <= 1.0:
        raise ValueError("near_duplicate_threshold must be in (0, 1]")
    kept: list[RiskSample] = []
    hashes: set[str] = set()
    ngram_index: dict[str, set[int]] = defaultdict(set)
    for sample in samples:
        if sample.message_hash in hashes:
            continue
        is_duplicate = False
        for index in _candidate_indexes(sample.message, ngram_index):
            if _similarity(sample.message, kept[index].message) >= near_duplicate_threshold:
                is_duplicate = True
                break
        if is_duplicate:
            continue
        index = len(kept)
        kept.append(sample)
        hashes.add(sample.message_hash)
        for gram in _char_ngrams(sample.message):
            ngram_index[gram].add(index)
    return kept


def format_matches(matches: Iterable[LeakageMatch]) -> str:
    return "\n".join(
        f"{item.sample_id}: {item.kind} score={item.score} source={item.source_path} text={item.preview!r}"
        for item in matches
    )


def assert_no_final_holdout_leakage(
    samples: Iterable[RiskSample], root: Path | None = None, near_duplicate_threshold: float = 0.82
) -> None:
    matches = scan_final_holdout_leakage(samples, root=root, near_duplicate_threshold=near_duplicate_threshold)
    if matches:
        raise ValueError("final holdout leakage detected:\n" + format_matches(matches))
