"""本地评测 CLI:装配编排器并运行完整评测套件。"""
from __future__ import annotations

from pathlib import Path

from app.evaluation import run_evaluation
from app.harness.factory import build_harness_orchestrator


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    data_dir = ROOT / "data" / "eval"
    orchestrator = build_harness_orchestrator(data_dir=data_dir)
    results = run_evaluation(orchestrator, orchestrator.store, ROOT / "eval" / "fixtures", data_dir)
    print(results["summary"])


if __name__ == "__main__":
    main()
