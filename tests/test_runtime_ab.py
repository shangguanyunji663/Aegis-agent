"""三运行时 A/B 评测测试:结构与一致性。"""
from pathlib import Path

from app.evaluation.runtime_ab import MESSAGES, render_report, run_runtime_ab


def test_runtime_ab_structure_and_consistency(tmp_path: Path):
    result = run_runtime_ab(data_dir=tmp_path)

    assert set(result["runtimes"]) == {"langgraph", "autonomous", "ordered"}
    assert len(result["comparison"]) == 3
    for runtime in result["runtimes"]:
        stats = result["comparison"][runtime]
        assert "avg_latency_ms" in stats
        assert "avg_trace_steps" in stats
        assert "total_llm_calls" in stats
        assert "intent_accuracy" in stats
        assert "risk_accuracy" in stats
        assert len(stats["per_message"]) == len(MESSAGES)

    # mock 下三运行时应判定一致(同一规则库)
    for item in result["consistency"]:
        assert item["intent_consistent"] is True
        assert item["risk_consistent"] is True


def test_runtime_ab_report_renders(tmp_path: Path):
    result = run_runtime_ab(data_dir=tmp_path)
    report = render_report(result)
    assert "# 三运行时 A/B 评测报告" in report
    assert "langgraph" in report and "autonomous" in report and "ordered" in report
    assert "一致性" in report
