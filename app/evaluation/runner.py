"""评测运行器:路由/风险/检索/RAG/技能/安全/多轮/规模化八套指标聚合。"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.evaluation.datasets import generated_benchmark_cases
from app.evaluation.judge import evaluate_reply_quality
from app.evaluation.report_html import render_html
from app.rag_eval.runner import evaluate as evaluate_rag_eval


def run_evaluation(orchestrator, store, fixtures_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "routing": evaluate_routing(orchestrator, fixtures_dir),
        "risk": evaluate_risk(orchestrator, fixtures_dir),
        "retrieval": evaluate_retrieval(store, fixtures_dir),
        "rag_eval": evaluate_rag_eval(store, store.settings),
        "skills": evaluate_skills(orchestrator, fixtures_dir),
        "safety": evaluate_safety(orchestrator, fixtures_dir),
        "multi_turn": evaluate_multi_turn(orchestrator, fixtures_dir),
        "scaled_benchmark": evaluate_scaled_benchmark(orchestrator),
        "judge": evaluate_judge(orchestrator, fixtures_dir),
    }
    results["rag_eval"]["passed"] = sum(1 for item in results["rag_eval"]["results"] if item["hit"])
    results["rag_eval"]["total"] = results["rag_eval"]["totalCases"]
    results["rag_eval"]["accuracy"] = results["rag_eval"]["hitRate"]
    results["rag_eval"]["cases"] = results["rag_eval"]["results"]
    results["summary"] = summarize(results)
    (output_dir / "latest.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "latest.html").write_text(render_html(results), encoding="utf-8")
    return results


def latest_evaluation(output_dir: Path) -> dict:
    path = output_dir / "latest.json"
    if not path.exists():
        return {"status": "missing", "summary": {}, "created_at": None}
    return json.loads(path.read_text(encoding="utf-8")) | {"status": "ready"}


def evaluate_routing(orchestrator, fixtures_dir: Path) -> dict:
    cases = read_cases(fixtures_dir / "routing.json")
    rows = []
    for case in cases:
        response = orchestrator.handle(case["message"])
        rows.append(
            {
                "message": case["message"],
                "expected": case["expected_intent"],
                "actual": response.intent.value,
                "passed": response.intent.value == case["expected_intent"],
            }
        )
    return with_accuracy(rows)


def evaluate_risk(orchestrator, fixtures_dir: Path) -> dict:
    cases = read_cases(fixtures_dir / "risk.json")
    rows = []
    for case in cases:
        response = orchestrator.handle(case["message"])
        rows.append(
            {
                "message": case["message"],
                "expected": case["expected_risk"],
                "actual": response.risk_level.value,
                "passed": response.risk_level.value == case["expected_risk"],
            }
        )
    result = with_accuracy(rows)
    high_cases = [row for row in rows if row["expected"] == "high"]
    high_hits = sum(1 for row in high_cases if row["actual"] == "high")
    low_medium_cases = [row for row in rows if row["expected"] != "high"]
    false_positives = sum(1 for row in low_medium_cases if row["actual"] == "high")
    result["high_recall"] = round(high_hits / len(high_cases), 4) if high_cases else 0.0
    result["false_positive_rate"] = round(false_positives / len(low_medium_cases), 4) if low_medium_cases else 0.0
    return result


def evaluate_retrieval(store, fixtures_dir: Path) -> dict:
    cases = read_cases(fixtures_dir / "retrieval.json")
    rows = []
    for case in cases:
        results = store.search_knowledge(case["query"], top_k=3)
        actual = results[0]["source"] if results else ""
        expected_source = case["expected_source"]
        reciprocal_rank = 0.0
        relevant_positions = []
        for index, item in enumerate(results, start=1):
            if item["source"] == expected_source:
                relevant_positions.append(index)
                if reciprocal_rank == 0.0:
                    reciprocal_rank = 1.0 / index
        hit = bool(relevant_positions)
        precision_at_k = (1.0 / len(results)) if hit and results else 0.0
        recall_at_k = 1.0 if hit else 0.0
        ndcg_at_k = 1.0 / math.log2(relevant_positions[0] + 1) if hit else 0.0
        rows.append(
            {
                "query": case["query"],
                "expected": expected_source,
                "actual": actual,
                "retrieved": results,
                "hit": hit,
                "first_relevant_rank": relevant_positions[0] if hit else None,
                "recall_at_k": round(recall_at_k, 4),
                "precision_at_k": round(precision_at_k, 4),
                "reciprocal_rank": round(reciprocal_rank, 4),
                "ndcg_at_k": round(ndcg_at_k, 4),
                "passed": actual == case["expected_source"],
            }
        )
    result = with_accuracy(rows)
    total = len(rows) or 1
    result["hit_rate"] = round(sum(1 for row in rows if row["hit"]) / total, 4)
    result["recall_at_k"] = round(sum(row["recall_at_k"] for row in rows) / total, 4)
    result["precision_at_k"] = round(sum(row["precision_at_k"] for row in rows) / total, 4)
    result["mrr"] = round(sum(row["reciprocal_rank"] for row in rows) / total, 4)
    result["ndcg_at_k"] = round(sum(row["ndcg_at_k"] for row in rows) / total, 4)
    avg_rank_values = [row["first_relevant_rank"] for row in rows if row["first_relevant_rank"]]
    result["average_first_relevant_rank"] = round(sum(avg_rank_values) / len(avg_rank_values), 4) if avg_rank_values else None
    return result


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
    return with_accuracy(rows)


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
    result["leak_count"] = sum(len(row["leaks"]) for row in rows)
    return result


def evaluate_multi_turn(orchestrator, fixtures_dir: Path) -> dict:
    cases = read_cases(fixtures_dir / "multi-turn.json")
    rows = []
    for case in cases:
        session_id = None
        final_answer = ""
        for turn in case["turns"]:
            response = orchestrator.handle(turn, session_id)
            session_id = response.session_id
            final_answer = response.answer
        expected = case["expected_contains"]
        rows.append(
            {
                "turns": case["turns"],
                "expected_contains": expected,
                "actual_answer": final_answer,
                "passed": expected in final_answer,
            }
        )
    return with_accuracy(rows)


def evaluate_judge(orchestrator, fixtures_dir: Path) -> dict | None:
    """LLM-as-Judge:对 routing+multi-turn 的回复抽样评分;mock/失败返回 None。"""
    cases = read_cases(fixtures_dir / "routing.json")
    cases += read_cases(fixtures_dir / "multi-turn.json")
    samples = []
    for case in cases[:6]:
        message = case["message"] if "message" in case else case["turns"][-1]
        response = orchestrator.handle(message)
        samples.append({"message": message, "reply": response.answer})
    return evaluate_reply_quality(orchestrator.llm_client, samples)


def with_accuracy(rows: list[dict[str, Any]]) -> dict:
    passed = sum(1 for row in rows if row["passed"])
    total = len(rows)
    return {"passed": passed, "total": total, "accuracy": round(passed / total, 4) if total else 0.0, "cases": rows}


def summarize(results: dict) -> dict:
    return {
        "routing_accuracy": results["routing"]["accuracy"],
        "risk_accuracy": results["risk"]["accuracy"],
        "risk_high_recall": results["risk"].get("high_recall", 0.0),
        "risk_false_positive_rate": results["risk"].get("false_positive_rate", 0.0),
        "retrieval_top1": results["retrieval"]["accuracy"],
        "retrieval_hit_rate": results["retrieval"].get("hit_rate", 0.0),
        "retrieval_mrr": results["retrieval"].get("mrr", 0.0),
        "retrieval_ndcg_at_k": results["retrieval"].get("ndcg_at_k", 0.0),
        "rag_eval_total_cases": results["rag_eval"].get("totalCases", 0),
        "rag_eval_hit_rate": results["rag_eval"].get("hitRate", 0.0),
        "rag_eval_mrr": results["rag_eval"].get("mrr", 0.0),
        "rag_eval_ndcg_at_k": results["rag_eval"].get("ndcgAtK", 0.0),
        "skill_accuracy": results["skills"]["accuracy"],
        "safety_pass_rate": results["safety"]["accuracy"],
        "safety_leak_count": results["safety"].get("leak_count", 0),
        "multi_turn_accuracy": results["multi_turn"]["accuracy"],
        "scaled_benchmark_accuracy": results["scaled_benchmark"]["accuracy"],
        "scaled_benchmark_total": results["scaled_benchmark"]["total"],
        "scaled_high_recall": results["scaled_benchmark"].get("high_recall", 0.0),
        "judge_avg": (results.get("judge") or {}).get("avg"),
        "all_passed": all(
            results[name]["passed"] == results[name]["total"]
            for name in ["routing", "risk", "retrieval", "rag_eval", "skills", "safety", "multi_turn", "scaled_benchmark"]
        ),
    }


def read_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_scaled_benchmark(orchestrator) -> dict:
    rows = []
    for case in generated_benchmark_cases():
        response = orchestrator.handle(case["message"])
        intent_ok = response.intent.value == case["expected_intent"]
        risk_ok = response.risk_level.value == case["expected_risk"]
        rows.append(
            {
                "id": case["id"],
                "message": case["message"],
                "expected_intent": case["expected_intent"],
                "actual_intent": response.intent.value,
                "expected_risk": case["expected_risk"],
                "actual_risk": response.risk_level.value,
                "passed": intent_ok and risk_ok,
            }
        )
    result = with_accuracy(rows)
    high_cases = [row for row in rows if row["expected_risk"] == "high"]
    high_hits = sum(1 for row in high_cases if row["actual_risk"] == "high")
    result["high_recall"] = round(high_hits / len(high_cases), 4) if high_cases else 0.0
    result["intent_accuracy"] = round(sum(1 for row in rows if row["actual_intent"] == row["expected_intent"]) / len(rows), 4)
    result["risk_accuracy"] = round(sum(1 for row in rows if row["actual_risk"] == row["expected_risk"]) / len(rows), 4)
    result["distribution"] = {
        "companion": sum(1 for row in rows if row["expected_intent"] == "companion"),
        "counseling": sum(1 for row in rows if row["expected_intent"] == "counseling"),
        "research": sum(1 for row in rows if row["expected_intent"] == "research"),
        "risk": sum(1 for row in rows if row["expected_intent"] == "risk"),
    }
    return result
