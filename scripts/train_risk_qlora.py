"""Deprecated compatibility entry point.

QLoRA training moved to the separate AegisTraining repository. Run
``AegisTraining/training/scripts/train_risk_qlora.py`` from that checkout.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    training_root = os.environ.get("AEGIS_TRAINING_ROOT", "")
    target = Path(training_root) / "training" / "scripts" / "train_risk_qlora.py" if training_root else None
    if target is not None and target.is_file():
        print(f"Use the migrated training entry point: {target}")
    else:
        print(
            "QLoRA training has moved to the separate AegisTraining repository. "
            "Set AEGIS_TRAINING_ROOT and run training/scripts/train_risk_qlora.py there.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
