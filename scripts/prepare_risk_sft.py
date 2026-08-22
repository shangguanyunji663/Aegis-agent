r"""生成 Aegis 风险 QLoRA 的候选池、分层 train/dev JSONL 和数据 manifest。

默认从 D:\AegisTraining\data\external\SupervisedVsLLM-EfficacyEval 读取用户指定的
公开仓库，并可从当前 HEAD 的 representative corpus ``base`` 层取少量项目开发样本。
``stress`` 层是固定最终 holdout，绝不写入 train/dev。输出只写入指定训练数据目录。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING_SRC = ROOT / "training" / "src"
if str(TRAINING_SRC) not in sys.path:
    sys.path.insert(0, str(TRAINING_SRC))

from aegis_training.data_contract import (  # noqa: E402
    DataContractError,
    RiskSample,
    label_distribution,
    write_jsonl,
)
from aegis_training.leakage_guard import (  # noqa: E402
    assert_no_final_holdout_leakage,
    dedupe_against_selected,
)
from aegis_training.source_ingest import (  # noqa: E402
    load_hongzhi_candidate_pool,
    load_project_candidate_pool,
)


def _stable_order(samples: list[RiskSample], seed: int, label: str) -> list[RiskSample]:
    """按样本哈希得到可复现顺序，不把训练 split 随机性误用于安全用途。"""
    return sorted(
        samples,
        key=lambda sample: hashlib.sha256(f"{seed}:{label}:{sample.sample_id}".encode("utf-8")).hexdigest(),
    )


def stratified_split(samples: list[RiskSample], train_size: int, dev_size: int, seed: int) -> tuple[list[RiskSample], list[RiskSample]]:
    required = train_size + dev_size
    if len(samples) < required:
        raise DataContractError(f"candidate pool has {len(samples)} samples, but {required} are required")
    groups: dict[str, list[RiskSample]] = defaultdict(list)
    for sample in samples:
        groups[sample.risk_level].append(sample)
    if set(groups) != {"low", "medium", "high"}:
        raise DataContractError(f"candidate pool must contain low/medium/high, got {sorted(groups)}")

    for level, group in list(groups.items()):
        groups[level] = _stable_order(group, seed, level)

    levels = ["low", "medium", "high"]
    train_quotas = {level: train_size // 3 for level in levels}
    for level in levels[: train_size % 3]:
        train_quotas[level] += 1
    dev_quotas = {level: dev_size // 3 for level in levels}
    for level in levels[: dev_size % 3]:
        dev_quotas[level] += 1

    train: list[RiskSample] = []
    dev: list[RiskSample] = []
    for level in levels:
        needed = train_quotas[level] + dev_quotas[level]
        if len(groups[level]) < needed:
            raise DataContractError(f"{level} pool has {len(groups[level])} samples, need {needed}")
        train.extend(groups[level][: train_quotas[level]])
        dev.extend(groups[level][train_quotas[level]:needed])
    return _stable_order(train, seed, "train"), _stable_order(dev, seed, "dev")


def _source_distribution(samples: list[RiskSample]) -> dict[str, int]:
    return dict(sorted(Counter(sample.source for sample in samples).items()))


def _label_method_distribution(samples: list[RiskSample]) -> dict[str, int]:
    return dict(sorted(Counter(sample.label_method for sample in samples).items()))


def manifest(samples: list[RiskSample], split: str) -> dict:
    return {
        "split": split,
        "count": len(samples),
        "label_distribution": label_distribution(samples),
        "source_distribution": _source_distribution(samples),
        "label_method_distribution": _label_method_distribution(samples),
        "samples": [sample.manifest_row() for sample in samples],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare isolated risk QLoRA SFT data from external and selected project sources")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("D:/AegisTraining/data/external/SupervisedVsLLM-EfficacyEval"),
        help="local clone of the user-approved external source repository",
    )
    parser.add_argument("--project-root", type=Path, default=ROOT, help="Aegis repository; only committed base-layer fixtures are read")
    parser.add_argument("--without-project-base", action="store_true", help="exclude the selected 63 project base-layer samples")
    parser.add_argument("--output-root", type=Path, default=Path("D:/AegisTraining/data/risk_sft_v2"))
    parser.add_argument("--train-size", type=int, default=720)
    parser.add_argument("--dev-size", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--near-duplicate-threshold", type=float, default=0.82)
    args = parser.parse_args()

    try:
        candidates = load_hongzhi_candidate_pool(args.source_root)
        project_samples: list[RiskSample] = []
        if not args.without_project_base:
            project_samples = load_project_candidate_pool(args.project_root)
            candidates.extend(project_samples)
        candidates = dedupe_against_selected(candidates)
        assert_no_final_holdout_leakage(candidates, near_duplicate_threshold=args.near_duplicate_threshold)
        train, dev = stratified_split(candidates, args.train_size, args.dev_size, args.seed)
        args.output_root.mkdir(parents=True, exist_ok=True)
        write_jsonl((sample.to_sft_record() for sample in train), args.output_root / "train.jsonl")
        write_jsonl((sample.to_sft_record() for sample in dev), args.output_root / "dev.jsonl")
        candidate_manifest = manifest(candidates, "candidate_pool")
        candidate_manifest.update(
            {
                "source_root": str(args.source_root),
                "source_revision": "78fb4d1",
                "project_root": str(args.project_root),
                "project_samples_in_candidate_pool": len(project_samples),
                "final_holdout": "eval/fixtures/representative_corpus.json (layer=stress, 87 records)",
                "mapping": {
                    "hongzhi_suicide_source_label_0": "low unless explicit self-risk wording upgrades to high",
                    "hongzhi_suicide_source_label_1": "high unless third-party context downgrades to low",
                    "socialcd_and_cognitive": "subject-aware weak mapping: medium by default, high for self-risk, low for third-party context",
                    "project_base_layer": "uses committed expected_risk labels",
                },
            }
        )
        (args.output_root / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "risk_sft_v2",
                    "seed": args.seed,
                    "candidate_pool": candidate_manifest,
                    "train": manifest(train, "train"),
                    "dev": manifest(dev, "dev"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except (DataContractError, ValueError, OSError) as exc:
        print(f"DATA PREPARATION FAILED: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "output_root": str(args.output_root),
                "candidate_count": len(candidates),
                "project_base_count": len(project_samples),
                "train_count": len(train),
                "dev_count": len(dev),
                "train_labels": label_distribution(train),
                "dev_labels": label_distribution(dev),
                "final_holdout": "representative_corpus:stress",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
