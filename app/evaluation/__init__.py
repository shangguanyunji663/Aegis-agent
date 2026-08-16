"""评测包:运行器 + 基准数据集 + HTML 报告渲染。"""
from app.evaluation.datasets import generated_benchmark_cases
from app.evaluation.report_html import escape, render_html, render_section
from app.evaluation.runner import (
    latest_evaluation,
    run_evaluation,
    evaluate_multi_turn,
    evaluate_risk,
    evaluate_routing,
    evaluate_safety,
    evaluate_scaled_benchmark,
    evaluate_skills,
    read_cases,
    summarize,
    with_accuracy,
)

__all__ = [
    "generated_benchmark_cases",
    "escape",
    "render_html",
    "render_section",
    "latest_evaluation",
    "run_evaluation",
    "evaluate_multi_turn",
    "evaluate_risk",
    "evaluate_routing",
    "evaluate_safety",
    "evaluate_scaled_benchmark",
    "evaluate_skills",
    "read_cases",
    "summarize",
    "with_accuracy",
]
