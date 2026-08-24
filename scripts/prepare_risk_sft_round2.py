"""Deprecated compatibility entry point.

The round-two data pipeline moved to the separate AegisTraining repository.
Use the versioned preparation scripts under ``training/scripts`` there.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = os.environ.get("AEGIS_TRAINING_ROOT", "")
    target = Path(root) / "training" / "scripts" / "prepare_risk_sft.py" if root else None
    if target is not None and target.is_file():
        print(f"Use the migrated training entry point: {target}")
    else:
        print(
            "Risk SFT preparation has moved to AegisTraining. Set AEGIS_TRAINING_ROOT "
            "and run training/scripts/prepare_risk_sft.py or prepare_risk_sft_v4.py there.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
