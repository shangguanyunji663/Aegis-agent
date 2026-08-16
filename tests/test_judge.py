"""LLM-as-Judge 评分测试:解析、聚合与 mock 跳过。"""
from pathlib import Path

from app.evaluation.judge import evaluate_reply_quality, judge_reply
from app.llm import MockLLMClient
from tests.test_orchestrator import build_orchestrator


class JudgeStubClient(MockLLMClient):
    def judge_reply(self, message, reply):
        return {"empathy": 5, "safety": 4, "structure": 3, "comment": "不错"}


def test_judge_parses_and_aggregates():
    client = JudgeStubClient()
    samples = [{"message": "考试压力大", "reply": "先共情再给建议"}]
    result = evaluate_reply_quality(client, samples)

    assert result is not None
    assert result["total"] == 1
    assert result["avg"] == {"empathy": 5.0, "safety": 4.0, "structure": 3.0}


def test_judge_skips_when_mock_or_failure():
    # mock 客户端 judge 返回 None → 整体跳过
    assert evaluate_reply_quality(MockLLMClient(), [{"message": "x", "reply": "y"}]) is None

    class FailingClient(MockLLMClient):
        def judge_reply(self, message, reply):
            raise RuntimeError("boom")

    assert judge_reply(FailingClient(), "x", "y") is None


def test_run_evaluation_includes_judge_key(tmp_path: Path):
    """mock 下 run_evaluation 仍有 judge 键(值为 None),不判失败。"""
    from app.evaluation import run_evaluation

    orchestrator = build_orchestrator(tmp_path)
    fixtures_dir = Path(__file__).resolve().parents[1] / "eval" / "fixtures"
    output_dir = tmp_path / "out"
    results = run_evaluation(orchestrator, orchestrator.store, fixtures_dir, output_dir)

    assert "judge" in results
    assert results["judge"] is None  # mock → 跳过
    assert results["summary"]["judge_avg"] is None
