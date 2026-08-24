"""Deprecated compatibility entry point.

Model merging moved to the separate AegisTraining repository. Run
``AegisTraining/training/scripts/merge_risk_qlora.py`` there.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = os.environ.get("AEGIS_TRAINING_ROOT", "")
    target = Path(root) / "training" / "scripts" / "merge_risk_qlora.py" if root else None
    if target is not None and target.is_file():
        print(f"Use the migrated training entry point: {target}")
    else:
        print(
            "Model merging has moved to AegisTraining. Set AEGIS_TRAINING_ROOT "
            "and run training/scripts/merge_risk_qlora.py there.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
