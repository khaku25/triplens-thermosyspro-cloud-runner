#!/usr/bin/env python3
"""Build the authoritative Logic DB from an already simulation-grounded CSV.

The legacy builder historically asserted exactly 538 active rows.  Once
scenario-only/unbound logic is intentionally pruned, that fixed count is no
longer a valid invariant.  This wrapper preserves every structural/link/unit
validation in build_logic_db.py but changes the active-count invariant to:

    DB active count == enabled rows in the filtered simulation-grounded input.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import build_logic_db as core


def argument_value(name: str) -> str | None:
    try:
        index = sys.argv.index(name)
    except ValueError:
        return None
    if index + 1 >= len(sys.argv):
        raise SystemExit(f"Missing value after {name}")
    return sys.argv[index + 1]


def as_bool(value: str) -> bool:
    return str(value or "").strip().upper() in {"TRUE", "Y", "YES", "1"}


logic_value = argument_value("--logic")
if logic_value is None:
    raise SystemExit("Simulation-grounded build requires explicit --logic <filtered.csv>")
logic_path = Path(logic_value)
with logic_path.open(encoding="utf-8-sig", newline="") as handle:
    expected_active = sum(as_bool(row.get("enabled_default", "")) for row in csv.DictReader(handle))

_original_add_validation = core.add_validation


def simulation_add_validation(db, check_id, passed, actual, expected, detail):
    if check_id == "active_logic_count":
        return _original_add_validation(
            db,
            check_id,
            int(actual) == expected_active,
            actual,
            expected_active,
            "Enabled rules retained after simulation-grounded pruning",
        )
    return _original_add_validation(db, check_id, passed, actual, expected, detail)


core.add_validation = simulation_add_validation
core.main()
