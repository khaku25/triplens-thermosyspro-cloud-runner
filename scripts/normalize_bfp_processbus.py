#!/usr/bin/env python3
"""Legacy BFP adapter for the generalized ProcessBus v2 normalizer.

New code should call normalize_processbus.py directly. This wrapper preserves
the historical BFP CLI while delegating all signal discovery and normalization
to the same scenario-agnostic ProcessBus implementation used by GT and future
incidents.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--incident-id", default="BLIND-INCIDENT-001")
    args = parser.parse_args()

    command = [
        sys.executable,
        str(ROOT / "scripts" / "normalize_processbus.py"),
        "--input", str(args.input),
        "--output", str(args.output),
        "--mapping-review", str(args.review),
        "--scenario-id", "",
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        return completed.returncode

    metadata = json.loads(args.review.read_text(encoding="utf-8"))
    metadata["incident_id"] = args.incident_id
    metadata["legacy_adapter"] = "normalize_bfp_processbus.py"
    metadata["generalized_normalizer"] = "normalize_processbus.py"
    args.review.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
