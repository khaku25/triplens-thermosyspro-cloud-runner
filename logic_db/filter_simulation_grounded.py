#!/usr/bin/env python3
"""Filter the legacy A-L catalogue down to simulation-grounded logic only.

The legacy CSV is retained as an archive/traceability source.  This filter is
used before building the authoritative Logic DB so scenario-only sensors,
operator-demo events, unbound optional signals and unavailable physical outputs
do not enter the executable/queryable logic set.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

EXCLUDED_SOURCE_CLASSES = {
    "A-L_SCENARIO",
    "A-L_UNLINKED_OPTIONAL",
}
EXCLUDED_DATA_ORIGINS = {
    "DEMO_SCENARIO_ASSUMED",
    "UNLINKED_CANDIDATE",
}
EXCLUDED_VALIDATION_STATUS = {
    "SCENARIO_ONLY_UNVERIFIED",
    "EXCLUDED_MISSING_INPUT",
    "ABSOLUTE_PHYSICAL_VALUE_NOT_AVAILABLE",
}
EXCLUDED_CONVERSION_STATUS = {
    "DEFERRED_SCENARIO_SENSOR",
    "UNLINKED_OPTIONAL_SIGNAL",
    "DEFERRED_PROPERTY_CALCULATION",
    "DEFERRED_LEVEL_OR_MODEL_OUTPUT",
}


def norm(value: str | None) -> str:
    return str(value or "").strip().upper()


def exclusion_reason(row: dict[str, str]) -> str:
    source_class = norm(row.get("source_class"))
    data_origin = norm(row.get("data_origin"))
    validation = norm(row.get("validation_status"))
    readiness = norm(row.get("implementation_readiness"))
    conversion = norm(row.get("absolute_conversion_status"))

    if source_class in EXCLUDED_SOURCE_CLASSES:
        return f"source_class={source_class}"
    if data_origin in EXCLUDED_DATA_ORIGINS:
        return f"data_origin={data_origin}"
    if validation in EXCLUDED_VALIDATION_STATUS:
        return f"validation_status={validation}"
    if readiness.startswith("DISABLED") or readiness.startswith("EXCLUDED"):
        return f"implementation_readiness={readiness}"
    if conversion in EXCLUDED_CONVERSION_STATUS:
        return f"absolute_conversion_status={conversion}"
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--excluded-report", type=Path)
    args = parser.parse_args()

    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    kept: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    for row in rows:
        reason = exclusion_reason(row)
        if reason:
            copy = dict(row)
            copy["simulation_scope_exclusion_reason"] = reason
            excluded.append(copy)
        else:
            kept.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    if args.excluded_report:
        args.excluded_report.parent.mkdir(parents=True, exist_ok=True)
        report_fields = fieldnames + ["simulation_scope_exclusion_reason"]
        with args.excluded_report.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=report_fields)
            writer.writeheader()
            writer.writerows(excluded)

    print(f"SIMULATION_GROUNDED_LOGIC: kept={len(kept)} excluded={len(excluded)} total={len(rows)}")


if __name__ == "__main__":
    main()
