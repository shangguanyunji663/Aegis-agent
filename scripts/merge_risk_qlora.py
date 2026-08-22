"""将已验收的 PEFT adapter 与官方 Qwen3.5 Base 合并为 Ollama 可导入的 safetensors 快照。"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING_SRC = ROOT / "training" / "src"
if str(TRAINING_SRC) not in sys.path:
    sys.path.insert(0, str(TRAINING_SRC))


def _assert_empty_or_export_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"output directory already contains files: {path}; use a new explicit versioned directory")


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge a validated risk QLoRA adapter into the official Qwen3.5 Base snapshot")
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--adapter-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-shard-size", default="2GB")
    parser.add_argument(
        "--preserve-multimodal-architecture",
        action="store_true",
        help="merge into the official conditional-generation architecture so Ollama can import its Qwen3.5 config",
    )
    args = parser.parse_args()

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoModelForImageTextToText, AutoTokenizer

        from aegis_training.base_model_gate import verify_snapshot
    except ImportError as exc:
        print(f"EXPORT ENVIRONMENT FAILED: {exc}", file=sys.stderr)
        return 2

    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required to merge the 2B BF16 base safely on this machine")
        if not (args.adapter_dir / "adapter_config.json").exists():
            raise FileNotFoundError(f"adapter_config.json is missing from {args.adapter_dir}")
        if not (args.adapter_dir / "adapter_model.safetensors").exists():
            raise FileNotFoundError(f"adapter_model.safetensors is missing from {args.adapter_dir}")
        _assert_empty_or_export_dir(args.output_dir)
        gate = verify_snapshot(args.snapshot_dir, provenance_path=None, require_exact_ollama_provenance=False)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        tokenizer = AutoTokenizer.from_pretrained(args.snapshot_dir, trust_remote_code=False)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model_loader = AutoModelForImageTextToText if args.preserve_multimodal_architecture else AutoModelForCausalLM
        base_model = model_loader.from_pretrained(
            args.snapshot_dir,
            torch_dtype=torch.bfloat16,
            device_map={"": 0},
            trust_remote_code=False,
            low_cpu_mem_usage=True,
        )
        model = PeftModel.from_pretrained(base_model, args.adapter_dir)
        merged = model.merge_and_unload(safe_merge=True)
        if args.preserve_multimodal_architecture:
            merged.config.architectures = ["Qwen3_5ForConditionalGeneration"]
        else:
            merged.config.architectures = [type(merged).__name__]
        merged.generation_config.do_sample = False
        merged.generation_config.temperature = None
        merged.save_pretrained(args.output_dir, safe_serialization=True, max_shard_size=args.max_shard_size)
        tokenizer.save_pretrained(args.output_dir)
        provenance = {
            "kind": "merged-risk-qlora-export",
            "official_base": gate.__dict__,
            "adapter_dir": str(args.adapter_dir),
            "output_dir": str(args.output_dir),
            "dtype": "bfloat16",
            "merged_model_class": type(merged).__name__,
            "max_shard_size": args.max_shard_size,
            "peak_cuda_memory_bytes": torch.cuda.max_memory_allocated(0),
        }
        (args.output_dir / "aegis-export-manifest.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(provenance, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"MERGE EXPORT FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        try:
            del merged
        except UnboundLocalError:
            pass
        try:
            del model
        except UnboundLocalError:
            pass
        try:
            del base_model
        except UnboundLocalError:
            pass
        if "torch" in locals() and torch.cuda.is_available():
            torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
