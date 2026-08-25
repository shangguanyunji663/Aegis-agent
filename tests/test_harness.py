from app.evaluation.harness.runner import run_scenario, run_scenarios
from tests.test_orchestrator import build_orchestrator


def test_harness_replays_multi_turn_scenario_with_event_timeline(tmp_path):
    orchestrator = build_orchestrator(tmp_path)

    result = run_scenario(
        orchestrator,
        {
            "name": "exam pressure follow-up",
            "turns": ["我最近考试压力很大，晚上睡不着", "刚才说的考试压力还是一直在"],
            "expected_intent": "counseling",
            "expected_risk": "low",
            "expected_contains": "考试压力",
        },
    )

    assert result["passed"] is True
    assert result["report_status"] is None
    assert len(result["responses"]) == 2
    assert any(event["type"] == "run_started" for event in result["event_timeline"])
    assert any(event["type"] == "run_completed" for event in result["event_timeline"])


def test_harness_reports_failed_expectations(tmp_path):
    orchestrator = build_orchestrator(tmp_path)

    result = run_scenarios(
        orchestrator,
        [
            {
                "message": "今天只是想找人说说话",
                "expected_intent": "risk",
                "forbidden_terms": ["我听到了你的困扰"],
            }
        ],
    )

    assert result["all_passed"] is False
    assert result["passed"] == 0
    assert "expected intent risk" in result["cases"][0]["failures"][0]
