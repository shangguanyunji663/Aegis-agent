"""评测运行器：基于真实代表性数据集的路由/风险/检索/RAG/技能/安全/多轮/规模化指标聚合。

本模块与旧版的关键区别：

1. **数据真实**：规模化基准、路由/风险判定、多轮回归均使用 ``eval/fixtures`` 下的真实标注
   语料（150 条代表性消息 + 8 组多轮场景），不再循环生成伪样本凑满分。
2. **双层拆分**：150 条规模化基准按 ``layer`` 字段拆为两套独立指标，零删改、不凑分：
   - **基础层（贴近真实流量，``layer=base`` / ``source=synthetic-representative``）**：覆盖日常闲聊、
     典型咨询、显式高危等"真实会发生的流量"，证明系统在主流场景上的可靠性（对应"真实"卖点）。
   - **压力层（边界探测，``layer=stress`` / ``source=synthetic-boundary``）**：刻意堆满隐喻式高危、
     无关键词咨询、第三人称干扰等"边界样本"，用于主动暴露规则通道的能力缺口（对应"暴露边界"卖点）。
   ``runner`` 通过 ``evaluate_scaled_benchmark`` 分别输出两套指标（见 ``base`` / ``stress`` 字段），
   两层均基于同一次语料遍历（``_evaluate_corpus``），不做二次推断、也不为满分筛样。
3. **指标完整**：除准确率外，明确输出
   - 意图判定准确率、风险判定准确率
   - 高风险召回率（high-risk recall）、误报率（false-positive rate）
   - RAG：HitRate / Recall@K / Precision@K / MRR / NDCG@K
   并对主指标给出 95% Wilson 置信区间。
4. **如实标注**：每个维度标注样本规模、数据来源、最近验证日期。
5. **去除满分门限**：``summarize`` 不再以"全部 100%"作为通过标准；非 100% 的真实结果
   被如实呈现，并提示其对应的代码/能力边界。
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.evaluation.datasets import (
    load_multi_turn_corpus,
    load_rag_queries,
    load_representative_corpus,
)
from app.evaluation.judge import evaluate_reply_quality
from app.evaluation.report_html import render_html
from app.rag_eval.runner import evaluate as evaluate_rag_eval

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def run_evaluation(orchestrator, store, fixtures_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    corpus = load_representative_corpus()
    multi_turn = load_multi_turn_corpus()

    # RAG 检索评测（基于真实知识库的 50 条自然语言问句）
    rag = evaluate_rag_eval(store, store.settings)
    rag_section = _rag_section(rag)

    results = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": {
            "routing_risk_scaled": str(FIXTURES_DIR / "representative_corpus.json"),
            "rag": rag["dataset"],
            "multi_turn": str(FIXTURES_DIR / "multi_turn_corpus.json"),
        },
        "routing": evaluate_routing(orchestrator, corpus),
        "risk": evaluate_risk(orchestrator, corpus),
        "retrieval": rag_section,
        "rag_eval": rag_section,
        "skills": evaluate_skills(orchestrator, fixtures_dir),
        "safety": evaluate_safety(orchestrator, fixtures_dir),
        "multi_turn": evaluate_multi_turn(orchestrator, multi_turn),
        "scaled_benchmark": evaluate_scaled_benchmark(orchestrator, corpus),
        "judge": evaluate_judge(orchestrator, fixtures_dir),
    }
    results["summary"] = summarize(results)
    (output_dir / "latest.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "latest.html").write_text(render_html(results), encoding="utf-8")
    return results


def latest_evaluation(output_dir: Path) -> dict:
    path = output_dir / "latest.json"
    if not path.exists():
        return {"status": "missing", "summary": {}, "created_at": None}
    return json.loads(path.read_text(encoding="utf-8")) | {"status": "ready"}


# --------------------------------------------------------------------------- #
# 语料级评测（路由 / 风险 / 规模化基准共享同一次遍历，避免重复推断）
# --------------------------------------------------------------------------- #

def _evaluate_corpus(orchestrator, corpus: list[dict]) -> list[dict]:
    rows = []
    for case in corpus:
        response = orchestrator.handle(case["message"])
        intent_ok = response.intent.value == case["expected_intent"]
        risk_ok = response.risk_level.value == case["expected_risk"]
        rows.append(
            {
                "id": case.get("id"),
                "message": case["message"],
                "expected_intent": case["expected_intent"],
                "actual_intent": response.intent.value,
                "intent_ok": intent_ok,
                "expected_risk": case["expected_risk"],
                "actual_risk": response.risk_level.value,
                "risk_ok": risk_ok,
                "category": case.get("category"),
                "difficulty": case.get("difficulty"),
                "layer": case.get("layer"),
                "source": case.get("source"),
                "note": case.get("note"),
                "passed": intent_ok and risk_ok,
            }
        )
    return rows


def evaluate_routing(orchestrator, corpus: list[dict] | None = None) -> dict:
    corpus = corpus if corpus is not None else load_representative_corpus()
    rows = _evaluate_corpus(orchestrator, corpus)
    total = len(rows)
    passed = sum(1 for r in rows if r["intent_ok"])
    accuracy = round(passed / total, 4) if total else 0.0
    # 按期望意图分层
    by_intent = defaultdict(lambda: [0, 0])
    for r in rows:
        by_intent[r["expected_intent"]][1] += 1
        if r["intent_ok"]:
            by_intent[r["expected_intent"]][0] += 1
    breakdown = {
        intent: {"correct": c, "total": t, "accuracy": round(c / t, 4) if t else 0.0}
        for intent, (c, t) in by_intent.items()
    }
    return {
        "sample_size": total,
        "data_source": str(FIXTURES_DIR / "representative_corpus.json"),
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "accuracy": accuracy,
        "ci95": _wilson_ci(passed, total),
        "by_intent": breakdown,
        "cases": rows,
        "passed": passed,
        "total": total,
    }


def evaluate_risk(orchestrator, corpus: list[dict] | None = None) -> dict:
    corpus = corpus if corpus is not None else load_representative_corpus()
    rows = _evaluate_corpus(orchestrator, corpus)
    total = len(rows)
    correct = sum(1 for r in rows if r["risk_ok"])
    accuracy = round(correct / total, 4) if total else 0.0

    high_cases = [r for r in rows if r["expected_risk"] == "high"]
    high_hits = sum(1 for r in high_cases if r["actual_risk"] == "high")
    high_recall = round(high_hits / len(high_cases), 4) if high_cases else 0.0

    non_high = [r for r in rows if r["expected_risk"] != "high"]
    false_positives = sum(1 for r in non_high if r["actual_risk"] == "high")
    false_positive_rate = round(false_positives / len(non_high), 4) if non_high else 0.0

    # 混淆：期望等级 -> 实际等级计数
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        confusion[r["expected_risk"]][r["actual_risk"]] += 1
    confusion_out = {exp: dict(act) for exp, act in confusion.items()}

    # 漏判清单（期望高危但未被判高危）
    missed_high = [{"id": r["id"], "message": r["message"], "actual_risk": r["actual_risk"]} for r in high_cases if r["actual_risk"] != "high"]
    # 误报清单（实际高危但期望非高危）
    fp_list = [{"id": r["id"], "message": r["message"], "expected_risk": r["expected_risk"]} for r in non_high if r["actual_risk"] == "high"]

    return {
        "sample_size": total,
        "data_source": str(FIXTURES_DIR / "representative_corpus.json"),
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "accuracy": accuracy,
        "ci95": _wilson_ci(correct, total),
        "high_recall": high_recall,
        "high_recall_ci95": _wilson_ci(high_hits, len(high_cases)),
        "false_positive_rate": false_positive_rate,
        "confusion": confusion_out,
        "missed_high": missed_high,
        "false_positives": fp_list,
        "cases": rows,
        "passed": correct,
        "total": total,
    }


def _layer_metrics(rows: list[dict], label: str) -> dict:
    """计算单层（基础层/压力层）的完整指标集。

    包含样本量、联合/意图/风险准确率、高风险召回率、误报率及 95% Wilson 置信区间，
    用于 runner 分别输出「基础层（贴近真实流量）」与「压力层（边界探测）」两套指标。
    两层指标均基于同一次语料遍历（``_evaluate_corpus``），不做二次推断，也不为满分筛样。
    """
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    intent_ok = sum(1 for r in rows if r["intent_ok"])
    risk_ok = sum(1 for r in rows if r["risk_ok"])
    high = [r for r in rows if r["expected_risk"] == "high"]
    high_hits = sum(1 for r in high if r["actual_risk"] == "high")
    non_high = [r for r in rows if r["expected_risk"] != "high"]
    fp = sum(1 for r in non_high if r["actual_risk"] == "high")
    return {
        "label": label,
        "sample_size": total,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "ci95": _wilson_ci(passed, total),
        "intent_accuracy": round(intent_ok / total, 4) if total else 0.0,
        "risk_accuracy": round(risk_ok / total, 4) if total else 0.0,
        "high_recall": round(high_hits / len(high), 4) if high else 0.0,
        "high_recall_ci95": _wilson_ci(high_hits, len(high)),
        "false_positive_rate": round(fp / len(non_high), 4) if non_high else 0.0,
        "passed": passed,
        "total": total,
    }


def evaluate_scaled_benchmark(orchestrator, corpus: list[dict] | None = None) -> dict:
    corpus = corpus if corpus is not None else load_representative_corpus()
    rows = _evaluate_corpus(orchestrator, corpus)
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    accuracy = round(passed / total, 4) if total else 0.0
    intent_ok = sum(1 for r in rows if r["intent_ok"])
    risk_ok = sum(1 for r in rows if r["risk_ok"])
    intent_accuracy = round(intent_ok / total, 4) if total else 0.0
    risk_accuracy = round(risk_ok / total, 4) if total else 0.0

    high_cases = [r for r in rows if r["expected_risk"] == "high"]
    high_hits = sum(1 for r in high_cases if r["actual_risk"] == "high")
    high_recall = round(high_hits / len(high_cases), 4) if high_cases else 0.0
    non_high = [r for r in rows if r["expected_risk"] != "high"]
    fp = sum(1 for r in non_high if r["actual_risk"] == "high")
    false_positive_rate = round(fp / len(non_high), 4) if non_high else 0.0

    # 按难度分层
    by_difficulty = defaultdict(lambda: [0, 0])
    for r in rows:
        by_difficulty[r["difficulty"]][1] += 1
        if r["passed"]:
            by_difficulty[r["difficulty"]][0] += 1
    # 按类别分层（取顶层类别，如 suicidal_implicit -> suicidal）
    by_category = defaultdict(lambda: [0, 0])
    for r in rows:
        cat = (r["category"] or "unknown").split("_")[0]
        by_category[cat][1] += 1
        if r["passed"]:
            by_category[cat][0] += 1

    # 按分层（base=贴近真实流量 / stress=边界探测）聚合
    by_layer = defaultdict(lambda: [0, 0])
    for r in rows:
        layer = r.get("layer") or "unknown"
        by_layer[layer][1] += 1
        if r["passed"]:
            by_layer[layer][0] += 1
    base_rows = [r for r in rows if (r.get("layer") or "unknown") == "base"]
    stress_rows = [r for r in rows if (r.get("layer") or "unknown") == "stress"]

    return {
        "sample_size": total,
        "data_source": str(FIXTURES_DIR / "representative_corpus.json"),
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "accuracy": accuracy,
        "ci95": _wilson_ci(passed, total),
        "intent_accuracy": intent_accuracy,
        "risk_accuracy": risk_accuracy,
        "high_recall": high_recall,
        "false_positive_rate": false_positive_rate,
        "by_difficulty": {d: {"correct": c, "total": t, "accuracy": round(c / t, 4) if t else 0.0} for d, (c, t) in by_difficulty.items()},
        "by_category": {c: {"correct": cc, "total": t, "accuracy": round(cc / t, 4) if t else 0.0} for c, (cc, t) in by_category.items()},
        "by_layer": {d: {"correct": c, "total": t, "accuracy": round(c / t, 4) if t else 0.0} for d, (c, t) in by_layer.items()},
        # 双层拆分：同一次语料遍历的结果，分别聚合为两套独立指标（保留全部 150 条，不删改）
        "base": _layer_metrics(base_rows, "基础层（贴近真实流量）"),
        "stress": _layer_metrics(stress_rows, "压力层（边界探测）"),
        "cases": rows,
        "passed": passed,
        "total": total,
    }


# --------------------------------------------------------------------------- #
# RAG 检索 / 技能 / 安全 / 多轮 / LLM-Judge
# --------------------------------------------------------------------------- #

def _rag_section(report: dict) -> dict:
    total = report.get("totalCases", 0)
    hits = round(report.get("hitRate", 0.0) * total)
    per_case = report.get("results", [])
    # Top-1 准确率：首条召回片段是否与期望来源/词命中
    top1_hits = 0
    for case in per_case:
        retrieved = case.get("retrieved") or []
        if retrieved and retrieved[0].get("relevant"):
            top1_hits += 1
    top1 = round(top1_hits / total, 4) if total else 0.0
    return {
        "sample_size": total,
        "data_source": report.get("dataset"),
        "validated_at": report.get("createdAt"),
        "top_k": report.get("topK"),
        "top1_accuracy": top1,
        "hit_rate": report.get("hitRate", 0.0),
        "hit_rate_ci95": _wilson_ci(hits, total),
        "recall_at_k": report.get("recallAtK", 0.0),
        "precision_at_k": report.get("precisionAtK", 0.0),
        "mrr": report.get("mrr", 0.0),
        "ndcg_at_k": report.get("ndcgAtK", 0.0),
        "average_first_relevant_rank": report.get("averageFirstRelevantRank"),
        "cases": per_case,
        "passed": hits,
        "total": total,
        "accuracy": report.get("hitRate", 0.0),
    }


def evaluate_skills(orchestrator, fixtures_dir: Path) -> dict:
    cases = []
    for fixture_name in ["routing.json", "risk.json", "multi-turn.json"]:
        path = fixtures_dir / fixture_name
        if path.exists():
            cases.extend(read_cases(path))
    rows = []
    for case in cases:
        expected = case.get("expected_skills")
        if expected is None:
            continue
        message = case["message"] if "message" in case else case["turns"][-1]
        response = orchestrator.handle(message)
        selected = []
        for item in response.trace:
            if item.agent == "SkillRegistry" and item.action == "select_standard_skills":
                selected = [part for part in item.detail.split(",") if part and part != "none"]
        missing = [name for name in expected if name not in selected]
        rows.append(
            {
                "message": message,
                "expected": expected,
                "actual": selected,
                "missing": missing,
                "passed": not missing,
            }
        )
    if not rows:
        return {
            "sample_size": 0,
            "data_source": str(fixtures_dir),
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "accuracy": None,
            "note": "fixtures 中未定义 expected_skills，技能选择维度暂无以真实数据驱动的评测集（非 0 分失败，属数据缺口）。",
            "cases": [],
            "passed": 0,
            "total": 0,
        }
    passed = sum(1 for r in rows if r["passed"])
    total = len(rows)
    return {
        "sample_size": total,
        "data_source": str(fixtures_dir),
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "accuracy": round(passed / total, 4),
        "cases": rows,
        "passed": passed,
        "total": total,
    }


def evaluate_safety(orchestrator, fixtures_dir: Path) -> dict:
    cases = read_cases(fixtures_dir / "safety.json")
    rows = []
    for case in cases:
        response = orchestrator.handle(case["message"])
        answer = response.answer.lower()
        leaks = [term for term in case["forbidden_terms"] if term.lower() in answer]
        rows.append(
            {
                "message": case["message"],
                "forbidden_terms": case["forbidden_terms"],
                "leaks": leaks,
                "passed": not leaks,
            }
        )
    result = with_accuracy(rows)
    result["sample_size"] = len(rows)
    result["data_source"] = str(fixtures_dir / "safety.json")
    result["validated_at"] = datetime.now(timezone.utc).isoformat()
    result["leak_count"] = sum(len(row["leaks"]) for row in rows)
    return result


def evaluate_multi_turn(orchestrator, scenarios: list[dict] | None = None) -> dict:
    scenarios = scenarios if scenarios is not None else load_multi_turn_corpus()
    rows = []
    for scenario in scenarios:
        session_id = None
        final_answer = ""
        final_intent = None
        final_risk = None
        for turn in scenario["turns"]:
            response = orchestrator.handle(turn, session_id)
            session_id = response.session_id
            final_answer = response.answer
            final_intent = response.intent.value
            final_risk = response.risk_level.value
        expected_intent = scenario.get("expected_intent")
        expected_risk = scenario.get("expected_risk")
        expected_contains = scenario.get("expected_contains")
        failures = []
        if expected_intent and final_intent != expected_intent:
            failures.append(f"expected intent {expected_intent}, got {final_intent}")
        if expected_risk and final_risk != expected_risk:
            failures.append(f"expected risk {expected_risk}, got {final_risk}")
        if expected_contains and expected_contains not in final_answer:
            failures.append(f"expected final answer to contain {expected_contains!r}")
        rows.append(
            {
                "name": scenario.get("name"),
                "turns": scenario["turns"],
                "expected_intent": expected_intent,
                "actual_intent": final_intent,
                "expected_risk": expected_risk,
                "actual_risk": final_risk,
                "expected_contains": expected_contains,
                "passed": not failures,
                "failures": failures,
            }
        )
    result = with_accuracy(rows)
    result["sample_size"] = len(rows)
    result["data_source"] = str(FIXTURES_DIR / "multi_turn_corpus.json")
    result["validated_at"] = datetime.now(timezone.utc).isoformat()
    return result


def evaluate_judge(orchestrator, fixtures_dir: Path) -> dict | None:
    """LLM-as-Judge：对 routing + multi-turn 的回复抽样评分；mock/失败返回 None。"""
    cases = read_cases(fixtures_dir / "routing.json")
    cases += read_cases(fixtures_dir / "multi-turn.json")
    samples = []
    for case in cases[:6]:
        message = case["message"] if "message" in case else case["turns"][-1]
        response = orchestrator.handle(message)
        samples.append({"message": message, "reply": response.answer})
    return evaluate_reply_quality(orchestrator.llm_client, samples)


# --------------------------------------------------------------------------- #
# 聚合 / 工具
# --------------------------------------------------------------------------- #

def with_accuracy(rows: list[dict[str, Any]]) -> dict:
    passed = sum(1 for row in rows if row["passed"])
    total = len(rows)
    return {"passed": passed, "total": total, "accuracy": round(passed / total, 4) if total else 0.0, "cases": rows}


def summarize(results: dict) -> dict:
    risk = results["risk"]
    retrieval = results["retrieval"]
    rag = results["rag_eval"]
    scaled = results["scaled_benchmark"]
    return {
        "validated_at": results["created_at"],
        "data_sources": results["data_sources"],
        "sample_sizes": {
            "routing": results["routing"]["sample_size"],
            "risk": risk["sample_size"],
            "scaled_benchmark": scaled["sample_size"],
            "rag": retrieval["sample_size"],
            "multi_turn": results["multi_turn"]["sample_size"],
            "skills": results["skills"]["sample_size"],
            "safety": results["safety"]["sample_size"],
        },
        "routing_accuracy": results["routing"]["accuracy"],
        "routing_ci95": results["routing"]["ci95"],
        "risk_accuracy": risk["accuracy"],
        "risk_ci95": risk["ci95"],
        "risk_high_recall": risk["high_recall"],
        "risk_high_recall_ci95": risk["high_recall_ci95"],
        "risk_false_positive_rate": risk["false_positive_rate"],
        "retrieval_top1": retrieval["top1_accuracy"],
        "retrieval_hit_rate": retrieval["hit_rate"],
        "retrieval_hit_rate_ci95": retrieval["hit_rate_ci95"],
        "retrieval_recall_at_k": retrieval["recall_at_k"],
        "retrieval_precision_at_k": retrieval["precision_at_k"],
        "retrieval_mrr": retrieval["mrr"],
        "retrieval_ndcg_at_k": retrieval["ndcg_at_k"],
        "rag_eval_total_cases": rag["sample_size"],
        "rag_eval_hit_rate": rag["hit_rate"],
        "rag_eval_mrr": rag["mrr"],
        "rag_eval_ndcg_at_k": rag["ndcg_at_k"],
        "skill_accuracy": results["skills"]["accuracy"],
        "safety_pass_rate": results["safety"]["accuracy"],
        "safety_leak_count": results["safety"].get("leak_count", 0),
        "multi_turn_accuracy": results["multi_turn"]["accuracy"],
        "multi_turn_total": results["multi_turn"]["total"],
        "scaled_benchmark_accuracy": scaled["accuracy"],
        "scaled_benchmark_total": scaled["total"],
        "scaled_high_recall": scaled["high_recall"],
        "scaled_false_positive_rate": scaled["false_positive_rate"],
        "scaled_base_accuracy": scaled["base"]["accuracy"],
        "scaled_stress_accuracy": scaled["stress"]["accuracy"],
        "scaled_base_label": scaled["base"]["label"],
        "scaled_stress_label": scaled["stress"]["label"],
        "scaled_base_high_recall": scaled["base"]["high_recall"],
        "scaled_stress_high_recall": scaled["stress"]["high_recall"],
        "scaled_base_risk_accuracy": scaled["base"]["risk_accuracy"],
        "scaled_stress_risk_accuracy": scaled["stress"]["risk_accuracy"],
        "scaled_base_false_positive_rate": scaled["base"]["false_positive_rate"],
        "scaled_stress_false_positive_rate": scaled["stress"]["false_positive_rate"],
        "judge_avg": (results.get("judge") or {}).get("avg"),
        "evaluation_note": (
            "评测不再以满分(100%)作为通过标准；以上为基于真实代表性数据集的真实通过率。"
            "非 100% 的结果如实保留，并指向对应的代码/能力边界（见各维度 missed_high / false_positives / by_difficulty）。"
        ),
    }


def read_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson 置信区间（比例）。返回 (lower, upper)。"""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    margin = (z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))) / denom
    return (round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4))
