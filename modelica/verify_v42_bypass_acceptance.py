#!/usr/bin/env python3
"""Validate the fast ThermoSysPro 4.2 HP/LP bypass acceptance result."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path


def load_rows(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            rows.append({key.strip('"'): float(value) for key, value in raw.items()})
    if not rows:
        raise AssertionError("result CSV is empty")
    return rows


def closest(rows: list[dict[str, float]], target: float) -> dict[str, float]:
    return min(rows, key=lambda row: abs(row["time"] - target))


def require_finite_nonnegative(rows: list[dict[str, float]], name: str) -> None:
    values = [row[name] for row in rows]
    if not all(math.isfinite(value) for value in values):
        raise AssertionError(f"{name} contains NaN or infinity")
    if min(values) < -1e-8:
        raise AssertionError(f"{name} contains reverse flow: {min(values)}")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_v42_bypass_acceptance.py RESULT.csv")

    rows = load_rows(Path(sys.argv[1]))
    before_trip = closest(rows, 0.04)
    hp_95 = closest(rows, 0.35)
    lp_95 = closest(rows, 0.45)
    final = rows[-1]

    for name in ("hpBypass.Q", "lpBypass.Q", "hpReference.Q", "lpReference.Q"):
        require_finite_nonnegative(rows, name)

    checks = {
        "pretrip_hp_closed": abs(before_trip["hpBypass.Q"]) <= 1e-6,
        "pretrip_lp_closed": abs(before_trip["lpBypass.Q"]) <= 1e-6,
        "hp_reaches_95_percent_by_0_30_s": hp_95["hpPosition"] >= 0.949,
        "lp_reaches_95_percent_by_0_40_s": lp_95["lpPosition"] >= 0.949,
        "hp_positive_design_flow": final["hpBypass.Q"] >= 140,
        "lp_positive_design_flow": final["lpBypass.Q"] >= 155,
        "hp_matches_tsp42_control_valve": final["hpFlowRelativeError"] <= 1e-6,
        "lp_matches_tsp42_control_valve": final["lpFlowRelativeError"] <= 1e-6,
        "hp_matches_closed_form": abs(final["hpBypass.Q"] - final["hpExpectedFlow"])
        <= 1e-5 * max(1, abs(final["hpExpectedFlow"])),
        "lp_matches_closed_form": abs(final["lpBypass.Q"] - final["lpExpectedFlow"])
        <= 1e-5 * max(1, abs(final["lpExpectedFlow"])),
    }

    evidence = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "trip_time_s": 0.05,
        "pretrip_at_s": before_trip["time"],
        "final_time_s": final["time"],
        "hp": {
            "position_at_0_35_s": hp_95["hpPosition"],
            "final_position": final["hpPosition"],
            "final_mass_flow_kg_s": final["hpBypass.Q"],
            "tsp42_reference_mass_flow_kg_s": final["hpReference.Q"],
            "relative_error": final["hpFlowRelativeError"],
        },
        "lp": {
            "position_at_0_45_s": lp_95["lpPosition"],
            "final_position": final["lpPosition"],
            "final_mass_flow_kg_s": final["lpBypass.Q"],
            "tsp42_reference_mass_flow_kg_s": final["lpReference.Q"],
            "relative_error": final["lpFlowRelativeError"],
        },
        "checks": checks,
    }
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
