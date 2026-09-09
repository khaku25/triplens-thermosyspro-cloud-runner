#!/usr/bin/env python3
"""Filter the legacy A-L catalogue to the TripLens first-order Logic Core.

Core policy (2026-09-09):
  Layer 0 = model-backed raw simulation tags.
  Layer 1 = a single raw model signal compared with an absolute threshold to
            create H / HH / L / LL state tags.

Everything that needs a scenario-only sensor, operator event, command, ratio,
rate-of-change, multiple model signals, sequence, interlock, permissive, master
trip, communication state, or protection action is deliberately deferred.

The 899-row legacy CSV remains an archive/traceability source and is never
silently destroyed by this filter.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

FIRST_ORDER_ALARM_TYPES = {"H", "HH", "L", "LL"}
FIRST_ORDER_SOURCE_CLASSES = {"M-V_DIRECT"}

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


def refs(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def exclusion_reason(row: dict[str, str]) -> str:
    source_class = norm(row.get("source_class"))
    data_origin = norm(row.get("data_origin"))
    validation = norm(row.get("validation_status"))
    readiness = norm(row.get("implementation_readiness"))
    conversion = norm(row.get("absolute_conversion_status"))
    alarm_type = norm(row.get("alarm_type"))
    threshold_basis = norm(row.get("threshold_basis"))

    # First remove rows already known to be synthetic/unbound/deferred.
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

    # Core v1 is intentionally only one raw model quantity -> one threshold tag.
    if alarm_type not in FIRST_ORDER_ALARM_TYPES:
        return f"core_scope_alarm_type={alarm_type or 'EMPTY'}"
    if source_class not in FIRST_ORDER_SOURCE_CLASSES:
        return f"core_scope_source_class={source_class or 'EMPTY'}"
    tag_refs = refs(row.get("source_tag_ids"))
    model_refs = refs(row.get("source_model_variables"))
    if len(tag_refs) != 1 or len(model_refs) != 1:
        return f"core_scope_source_count=tag:{len(tag_refs)},model:{len(model_refs)}"
    if not threshold_basis.startswith("ABSOLUTE_") or threshold_basis == "ABSOLUTE_VALUE_PENDING":
        return f"core_scope_threshold_basis={threshold_basis or 'EMPTY'}"

    # A first-order state tag must not itself execute a protection/control action.
    trip_action = norm(row.get("trip_action"))
    if trip_action not in {"", "NONE"}:
        return f"core_scope_action={trip_action}"

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
            copy["core_scope_exclusion_reason"] = reason
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
        report_fields = fieldnames + ["core_scope_exclusion_reason"]
        with args.excluded_report.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=report_fields)
            writer.writeheader()
            writer.writerows(excluded)

    print(
        "FIRST_ORDER_LOGIC_CORE: "
        f"kept={len(kept)} excluded={len(excluded)} total={len(rows)}"
    )


if __name__ == "__main__":
    main()
