"""Deprecated compatibility entry point.

Training code moved to the separate AegisTraining repository. Use
``AegisTraining/training/scripts/prepare_risk_sft.py`` instead.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    training_root = os.environ.get("AEGIS_TRAINING_ROOT", "")
    target = Path(training_root) / "training" / "scripts" / "prepare_risk_sft.py" if training_root else None
    message = (
        "Training has moved to the separate AegisTraining repository. "
        "Set AEGIS_TRAINING_ROOT to its checkout and run "
        "training/scripts/prepare_risk_sft.py there."
    )
    if target is not None and target.is_file():
        print(f"Use the migrated training entry point: {target}")
    else:
        print(message, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
