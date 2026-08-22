r"""以冻结项目 fixture 对原始 Ollama 与 QLoRA 候选进行离线评测。

原始基线固定通过本机 ``ollama`` CLI 执行。候选可使用已验证的本地 Ollama
模型，或从隔离的 safetensors 合并目录经 Transformers 执行。评测报告写入
``D:\AegisTraining\reports``，避免覆盖仓库 data/eval 快照。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
TRAINING_SRC = ROOT / "training" / "src"
for import_root in (ROOT, TRAINING_SRC):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from aegis_training.data_contract import RISK_SYSTEM_PROMPT  # noqa: E402
from aegis_training.metrics import Prediction, risk_eval_report, write_report  # noqa: E402

LEVEL_ORDER = {"low": 1, "medium": 2, "high": 3}
MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


def _load_holdout() -> list[dict]:
    path = ROOT / "eval" / "fixtures" / "representative_corpus.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("representative corpus must be a JSON array")
    holdout = [row for row in rows if isinstance(row, dict) and row.get("layer") == "stress"]
    if len(holdout) != 87:
        raise ValueError(f"expected 87 frozen stress holdout rows, got {len(holdout)}")
    return holdout


def _rules_predict(message: str) -> str:
    from app.assessment import assess_message

    return assess_message(message).risk_level.value


def _validate_model_name(model: str) -> str:
    normalized = model.strip()
    if not MODEL_NAME_RE.fullmatch(normalized):
        raise ValueError("model must be an Ollama model identifier, not a command or path")
    return normalized


def _run_ollama(model: str, message: str, timeout: float) -> tuple[str, float]:
    """执行固定本地 Ollama CLI，不组装 shell 字符串。"""
    executable = shutil.which("ollama")
    if not executable:
        return "__ERROR__:OllamaNotFound", 0.0
    prompt = f"{RISK_SYSTEM_PROMPT}\n\n用户输入：\n{message}"
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [executable, "run", model, prompt, "--format", "json", "--hidethinking", "--think=false"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "__ERROR__:Timeout", (time.perf_counter() - started) * 1000
    elapsed_ms = (time.perf_counter() - started) * 1000
    if completed.returncode != 0:
        return f"__ERROR__:OllamaExit:{completed.stderr.strip()[:240]}", elapsed_ms
    return completed.stdout.strip(), elapsed_ms


def _parse_risk(raw: str) -> tuple[str | None, str, bool]:
    if raw.startswith("__ERROR__"):
        return None, "", False
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, "", False
    if not isinstance(parsed, dict):
        return None, "", False
    level = str(parsed.get("risk_level", "")).lower().strip()
    reason = str(parsed.get("reason", "")).strip()
    return (level if level in LEVEL_ORDER else None), reason, True


def _predict_rows(
    rows: list[dict],
    runner: Callable[[str], tuple[str, float]],
) -> tuple[list[Prediction], list[dict]]:
    predictions: list[Prediction] = []
    raw_rows: list[dict] = []
    for row in rows:
        raw, latency_ms = runner(row["message"])
        level, reason, json_valid = _parse_risk(raw)
        predictions.append(
            Prediction(
                sample_id=row["id"],
                expected=row["expected_risk"],
                predicted=level,
                raw_output=raw,
                json_valid=json_valid,
                reason=reason,
                latency_ms=latency_ms,
                category=row.get("category", ""),
                layer=row.get("layer", ""),
            )
        )
        raw_rows.append({"id": row["id"], "raw": raw, "reason": reason, "latency_ms": latency_ms})
    return predictions, raw_rows


def _predict_ollama(rows: list[dict], model: str, timeout: float) -> tuple[list[Prediction], list[dict]]:
    return _predict_rows(rows, lambda message: _run_ollama(model, message, timeout))


def _build_transformers_runner(model_dir: Path, max_new_tokens: int):
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("local Transformers evaluation requires the isolated QLoRA environment") from exc
    if not torch.cuda.is_available():
        raise RuntimeError("local Transformers evaluation requires CUDA")
    if max_new_tokens <= 0:
        raise ValueError("max_new_tokens must be positive")
    tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_dir,
        dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        device_map={"": 0},
        trust_remote_code=False,
        low_cpu_mem_usage=True,
    )
    model.eval()
    model.generation_config.pad_token_id = tokenizer.pad_token_id
    device = next(model.parameters()).device

    def run(message: str) -> tuple[str, float]:
        prompt_messages = [
            {"role": "system", "content": RISK_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
        started = time.perf_counter()
        try:
            encoded = tokenizer.apply_chat_template(
                prompt_messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            with torch.inference_mode():
                generated = model.generate(
                    **encoded,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    temperature=None,
                    top_p=None,
                )
            prompt_len = encoded["input_ids"].shape[1]
            raw = tokenizer.decode(generated[0, prompt_len:], skip_special_tokens=True).strip()
        except Exception as exc:
            raw = f"__ERROR__:Transformers:{type(exc).__name__}:{exc}"
        return raw, (time.perf_counter() - started) * 1000

    return run


def _predict_transformers(rows: list[dict], model_dir: Path, max_new_tokens: int) -> tuple[list[Prediction], list[dict]]:
    return _predict_rows(rows, _build_transformers_runner(model_dir, max_new_tokens))


def _acceptance_gate(reports: dict) -> dict:
    rules = reports["rules_only"]["overall"]
    rules_implicit = reports["rules_only"]["implicit_high"]
    fused = reports["rules_union_qlora"]["overall"]
    implicit = reports["rules_union_qlora"]["implicit_high"]
    third_person = reports["rules_union_qlora"]["third_person"]
    qlora = reports["qlora_raw"]["overall"]
    checks = {
        "json_valid_rate": qlora.get("json_valid_rate") is not None and qlora["json_valid_rate"] >= 0.98,
        "valid_label_rate": qlora.get("valid_label_rate", 0.0) >= 0.99,
        "reason_over_20_rate": qlora.get("reason_over_20_rate") == 0.0,
        "fused_high_recall_not_below_rules": fused["high_recall"] >= rules["high_recall"],
        "implicit_high_new_hits_at_least_4": (
            implicit["high_recall"] * implicit["count"] - rules_implicit["high_recall"] * rules_implicit["count"] >= 4
        ),
        "third_person_new_high_false_positives_at_most_1": (
            third_person["non_high_to_high_fpr"] * third_person["count"] <= 1
        ),
        "non_high_to_high_fpr_increase_at_most_2pp": (
            fused["non_high_to_high_fpr"] <= rules["non_high_to_high_fpr"] + 0.02
        ),
        "p95_under_8_seconds": (
            qlora.get("latency_ms", {}).get("p95", float("inf")) <= 8000
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def _fuse(rules: list[Prediction], model: list[Prediction]) -> list[Prediction]:
    result = []
    for rule, llm in zip(rules, model, strict=True):
        predicted = rule.predicted
        if llm.predicted is not None and LEVEL_ORDER[llm.predicted] > LEVEL_ORDER[predicted]:
            predicted = llm.predicted
        result.append(
            Prediction(
                sample_id=rule.sample_id,
                expected=rule.expected,
                predicted=predicted,
                raw_output=llm.raw_output,
                json_valid=llm.json_valid,
                reason=llm.reason,
                latency_ms=llm.latency_ms,
                category=rule.category,
                layer=rule.layer,
            )
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate original Ollama and QLoRA risk models on frozen Aegis stress holdout")
    parser.add_argument("--original-model", default="qwen3.5:2b")
    candidate = parser.add_mutually_exclusive_group(required=True)
    candidate.add_argument("--qlora-model", help="validated local Ollama candidate model name")
    candidate.add_argument("--qlora-model-dir", type=Path, help="local merged safetensors candidate for isolated Transformers evaluation")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--output", type=Path, default=Path("D:/AegisTraining/reports/risk-qlora-eval.json"))
    args = parser.parse_args()

    try:
        original_model = _validate_model_name(args.original_model)
        rows = _load_holdout()
        rules = [
            Prediction(
                sample_id=row["id"],
                expected=row["expected_risk"],
                predicted=_rules_predict(row["message"]),
                json_valid=None,
                category=row.get("category", ""),
                layer=row.get("layer", ""),
            )
            for row in rows
        ]
        original, original_raw = _predict_ollama(rows, original_model, args.timeout)
        if args.qlora_model:
            qlora_name = _validate_model_name(args.qlora_model)
            qlora, qlora_raw = _predict_ollama(rows, qlora_name, args.timeout)
            qlora_descriptor = {"backend": "ollama", "model": qlora_name}
        else:
            qlora_dir = args.qlora_model_dir.resolve()
            if not (qlora_dir / "config.json").is_file():
                raise FileNotFoundError(f"missing config.json in QLoRA model directory: {qlora_dir}")
            qlora, qlora_raw = _predict_transformers(rows, qlora_dir, args.max_new_tokens)
            qlora_descriptor = {"backend": "transformers", "model_dir": str(qlora_dir)}
    except Exception as exc:
        print(f"RISK EVALUATION FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    reports = {
        "rules_only": risk_eval_report(rules),
        "original_raw": risk_eval_report(original),
        "rules_union_original": risk_eval_report(_fuse(rules, original)),
        "qlora_raw": risk_eval_report(qlora),
        "rules_union_qlora": risk_eval_report(_fuse(rules, qlora)),
    }
    acceptance = _acceptance_gate(reports)
    payload = {
        "holdout": "eval/fixtures/representative_corpus.json (layer=stress)",
        "count": len(rows),
        "models": {"original": original_model, "qlora": qlora_descriptor},
        "acceptance": acceptance,
        "reports": reports,
        "raw_predictions": {"original": original_raw, "qlora": qlora_raw},
    }
    write_report(payload, args.output)
    print(json.dumps({"acceptance": acceptance, "reports": reports}, ensure_ascii=False, indent=2))
    return 0 if acceptance["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
