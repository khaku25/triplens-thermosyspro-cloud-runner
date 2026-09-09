#!/usr/bin/env python3
"""Build the authoritative Logic DB from filtered Core inputs.

The legacy builder contains fixed validation counts for the historical broad
catalogue.  Core v1 intentionally prunes that catalogue, so this wrapper keeps
the structural/link/unit checks while making row-count invariants equal the
filtered inputs actually supplied to the build.
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


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


logic_value = argument_value("--logic")
if logic_value is None:
    raise SystemExit("Core build requires explicit --logic <filtered.csv>")
logic_rows = csv_rows(Path(logic_value))
expected_active = sum(as_bool(row.get("enabled_default", "")) for row in logic_rows)

runtime_value = argument_value("--dcs")
expected_runtime = len(csv_rows(Path(runtime_value))) if runtime_value else 32

_original_add_validation = core.add_validation


def core_add_validation(db, check_id, passed, actual, expected, detail):
    if check_id == "active_logic_count":
        return _original_add_validation(
            db,
            check_id,
            int(actual) == expected_active,
            actual,
            expected_active,
            "Enabled first-order rules retained after Core pruning",
        )
    if check_id == "runtime_rule_count":
        return _original_add_validation(
            db,
            check_id,
            int(actual) == expected_runtime,
            actual,
            expected_runtime,
            "Runtime rules retained in first-order Core",
        )
    return _original_add_validation(db, check_id, passed, actual, expected, detail)


core.add_validation = core_add_validation
core.main()
