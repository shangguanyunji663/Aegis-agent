"""本地官方基座资格检查。

本模块不发起网络请求，也不从 Ollama GGUF 反向推断训练权重。训练前先由人工
从官方来源下载固定 revision 的模型快照；本检查只验证本地快照的结构、权重清单和
转换来源证明记录，避免把推理工件当作可训练 checkpoint。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

OFFICIAL_REPO_ID = "Qwen/Qwen3.5-2B-Base"
OFFICIAL_REVISION = "b1485b2fa6dfa1287294f269f5fb618e03d52d7c"
EXPECTED_MODEL_TYPE = "qwen3_5"
EXPECTED_ARCHITECTURES = frozenset({"Qwen3_5ForConditionalGeneration", "Qwen3_5ForCausalLM"})
EXPECTED_TEXT_LAYERS = 24
EXPECTED_HIDDEN_SIZE = 2048


class BaseModelGateError(RuntimeError):
    """官方基座、转换来源或文本模型结构不符合训练计划。"""


@dataclass(frozen=True)
class GateReport:
    repo_id: str
    revision: str
    model_type: str
    architecture: str
    hidden_size: int | None
    text_layers: int | None
    trainable_safetensors: bool
    family_scale_match: bool
    ollama_conversion_provenance: str
    status: str
    notes: tuple[str, ...]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaseModelGateError(f"cannot read {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise BaseModelGateError(f"{path} must contain a JSON object")
    return result


def _snapshot_config(snapshot_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config_path = snapshot_dir / "config.json"
    index_path = snapshot_dir / "model.safetensors.index.json"
    if not config_path.exists() or not index_path.exists():
        raise BaseModelGateError(
            "snapshot must contain config.json and model.safetensors.index.json; "
            "use the pinned official Qwen/Qwen3.5-2B-Base snapshot, never an Ollama GGUF blob"
        )
    return _read_json(config_path), _read_json(index_path)


def verify_snapshot(snapshot_dir: Path, provenance_path: Path | None, require_exact_ollama_provenance: bool) -> GateReport:
    """验证本地官方 Base 快照与可选 Ollama 转换证明。

    ``require_exact_ollama_provenance`` 是严格模式：证明文件必须声明当前 Ollama
    Q8 工件由同一 official revision 转换。当前 Ollama manifest 不公布该信息，
    因而严格模式会正确拒绝训练，而不是根据模型名称猜测。
    """
    config, index = _snapshot_config(snapshot_dir)
    model_type = str(config.get("model_type", ""))
    architectures = config.get("architectures") or []
    architecture = str(architectures[0]) if architectures else ""
    text_config = config.get("text_config") if isinstance(config.get("text_config"), dict) else config
    hidden_size = text_config.get("hidden_size")
    text_layers = text_config.get("num_hidden_layers")
    weight_map = index.get("weight_map")
    has_weights = isinstance(weight_map, dict) and bool(weight_map)
    family_scale_match = (
        model_type == EXPECTED_MODEL_TYPE
        and architecture in EXPECTED_ARCHITECTURES
        and hidden_size == EXPECTED_HIDDEN_SIZE
        and text_layers == EXPECTED_TEXT_LAYERS
        and has_weights
    )
    if not family_scale_match:
        raise BaseModelGateError(
            "official snapshot does not match expected Qwen3.5-2B Base: "
            f"model_type={model_type!r}, architecture={architecture!r}, "
            f"hidden_size={hidden_size!r}, text_layers={text_layers!r}, has_weights={has_weights}"
        )

    provenance = "unverified: no conversion evidence supplied"
    if provenance_path is not None:
        proof = _read_json(provenance_path)
        repo_ok = proof.get("source_repo") == OFFICIAL_REPO_ID
        revision_ok = proof.get("source_revision") == OFFICIAL_REVISION
        ollama_ok = proof.get("ollama_model") == "qwen3.5:2b"
        if repo_ok and revision_ok and ollama_ok:
            provenance = "verified by supplied conversion record"
        else:
            provenance = "invalid: supplied conversion record does not match pinned source repo/revision/model"

    if require_exact_ollama_provenance and provenance != "verified by supplied conversion record":
        raise BaseModelGateError(
            "strict mode requires a reproducible conversion record proving Ollama qwen3.5:2b "
            f"was built from {OFFICIAL_REPO_ID}@{OFFICIAL_REVISION}; {provenance}"
        )

    status = "pass_exact" if provenance == "verified by supplied conversion record" else "pass_same_family_with_caveat"
    return GateReport(
        repo_id=OFFICIAL_REPO_ID,
        revision=OFFICIAL_REVISION,
        model_type=model_type,
        architecture=architecture,
        hidden_size=hidden_size,
        text_layers=text_layers,
        trainable_safetensors=has_weights,
        family_scale_match=True,
        ollama_conversion_provenance=provenance,
        status=status,
        notes=(
            "The official Base snapshot is trainable safetensors, unlike the local Ollama Q8 GGUF inference artifact.",
            "The snapshot must expose a Qwen3_5ForCausalLM-compatible text path; training rejects vision-module paths.",
            "Exact Ollama conversion provenance is not inferable from model family, parameter count, or license alone.",
        ),
    )


def _print(payload: GateReport) -> None:
    print(json.dumps(asdict(payload), ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a local official Qwen3.5-2B Base snapshot")
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--provenance-path", type=Path)
    parser.add_argument("--require-exact-ollama-provenance", action="store_true")
    args = parser.parse_args()
    try:
        _print(verify_snapshot(args.snapshot_dir, args.provenance_path, args.require_exact_ollama_provenance))
    except BaseModelGateError as exc:
        print(f"BASE MODEL GATE FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
