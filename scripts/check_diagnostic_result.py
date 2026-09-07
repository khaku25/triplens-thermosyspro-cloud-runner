#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--expected-stop-time", type=float, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--omc-status", type=int, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    times: list[float] = []
    finite_rows = 0
    invalid_rows = 0
    if args.csv.is_file():
        with args.csv.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    values = [float(value) for value in row.values()]
                    time_s = float(row["time"])
                except (TypeError, ValueError, KeyError):
                    invalid_rows += 1
                    continue
                if all(math.isfinite(value) for value in values):
                    finite_rows += 1
                    times.append(time_s)
                else:
                    invalid_rows += 1

    last_finite_time = max(times) if times else None
    completed = (
        args.omc_status == 0
        and last_finite_time is not None
        and last_finite_time >= args.expected_stop_time - 1e-6
        and invalid_rows == 0
    )
    summary = {
        "variant": args.variant,
        "omc_status": args.omc_status,
        "result_exists": args.csv.is_file(),
        "finite_rows": finite_rows,
        "invalid_rows": invalid_rows,
        "last_finite_time_s": last_finite_time,
        "expected_stop_time_s": args.expected_stop_time,
        "completed": completed,
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())

