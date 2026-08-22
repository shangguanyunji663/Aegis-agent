"""风险 QLoRA 离线评测指标。"""
from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

LEVELS = ("low", "medium", "high")


@dataclass(frozen=True)
class Prediction:
    sample_id: str
    expected: str
    predicted: str | None
    raw_output: str = ""
    json_valid: bool | None = None
    reason: str = ""
    latency_ms: float | None = None
    category: str = ""
    layer: str = ""


def _safe_div(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _format_metrics(items: list[Prediction]) -> dict:
    json_scored = [item for item in items if item.json_valid is not None]
    parsed = [item for item in json_scored if item.json_valid]
    report = {
        "json_valid_rate": _safe_div(len(parsed), len(json_scored)) if json_scored else None,
        "valid_label_rate": _safe_div(sum(item.predicted in LEVELS for item in items), len(items)),
        "reason_over_20_rate": (
            _safe_div(sum(len(item.reason) > 20 for item in parsed), len(parsed)) if json_scored else None
        ),
    }
    return report


def classification_report(rows: Iterable[Prediction]) -> dict:
    items = list(rows)
    total = len(items)
    report = {
        "count": total,
        **_format_metrics(items),
        "accuracy": _safe_div(sum(item.predicted == item.expected for item in items), total),
        "per_class": {},
    }
    f1_values = []
    for level in LEVELS:
        tp = sum(item.expected == level and item.predicted == level for item in items)
        fp = sum(item.expected != level and item.predicted == level for item in items)
        fn = sum(item.expected == level and item.predicted != level for item in items)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        report["per_class"][level] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(item.expected == level for item in items),
        }
        f1_values.append(f1)
    report["macro_f1"] = sum(f1_values) / len(f1_values)
    report["high_recall"] = report["per_class"]["high"]["recall"]
    report["non_high_to_high_fpr"] = _safe_div(
        sum(item.expected != "high" and item.predicted == "high" for item in items),
        sum(item.expected != "high" for item in items),
    )
    report["medium_to_high_rate"] = _safe_div(
        sum(item.expected == "medium" and item.predicted == "high" for item in items),
        sum(item.expected == "medium" for item in items),
    )
    latency_values = sorted(item.latency_ms for item in items if item.latency_ms is not None)
    if latency_values:
        report["latency_ms"] = {
            "avg": sum(latency_values) / len(latency_values),
            "p95": latency_values[min(len(latency_values) - 1, math.ceil(len(latency_values) * 0.95) - 1)],
        }
    return report


def subset_report(rows: Iterable[Prediction], predicate) -> dict:
    return classification_report([item for item in rows if predicate(item)])


def risk_eval_report(rows: Iterable[Prediction]) -> dict:
    items = list(rows)
    return {
        "overall": classification_report(items),
        "base": subset_report(items, lambda item: item.layer == "base"),
        "stress": subset_report(items, lambda item: item.layer == "stress"),
        "implicit_high": subset_report(items, lambda item: item.category == "suicidal_implicit"),
        "direct_high": subset_report(items, lambda item: item.category == "suicidal_explicit"),
        "third_person": subset_report(items, lambda item: item.category == "third_person"),
    }


def source_distribution(rows: Iterable[Prediction]) -> dict[str, int]:
    return dict(sorted(Counter(item.layer or "unspecified" for item in rows).items()))


def write_report(payload: dict, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
