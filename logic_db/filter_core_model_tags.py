#!/usr/bin/env python3
"""Keep only model-backed raw ThermoSysPro tags for the TripLens Core.

The source catalogue is broader than the executable Core and contains synthetic
status/event/control aliases.  Core v1 keeps only rows whose value is model
backed and whose model_mapping points to a model quantity.  First-order H/HH/L/LL
state tags are generated separately from the Logic Master.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def norm(value: str | None) -> str:
    return str(value or "").strip().upper()


def exclusion_reason(row: dict[str, str]) -> str:
    tag_class = norm(row.get("tag_class"))
    value_basis = norm(row.get("value_basis"))
    model_mapping = str(row.get("model_mapping") or "").strip()
    mapping_upper = model_mapping.upper()

    if tag_class != "M" or value_basis != "M":
        return f"not_model_backed={tag_class}/{value_basis}"
    if not model_mapping:
        return "missing_model_mapping"
    if mapping_upper.startswith("DERIVED "):
        return "derived_mapping"
    if "ASSUMED" in mapping_upper or mapping_upper.startswith("USER ASSUMPTION"):
        return "assumed_mapping"
    return ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--excluded-report", type=Path)
    a = p.parse_args()

    with a.input.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    kept, excluded = [], []
    for row in rows:
        reason = exclusion_reason(row)
        if reason:
            copy = dict(row)
            copy["core_scope_exclusion_reason"] = reason
            excluded.append(copy)
        else:
            kept.append(row)

    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(kept)

    if a.excluded_report:
        report_fields = fields + ["core_scope_exclusion_reason"]
        with a.excluded_report.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=report_fields)
            writer.writeheader()
            writer.writerows(excluded)

    print(f"MODEL_RAW_TAG_CORE: kept={len(kept)} excluded={len(excluded)} total={len(rows)}")


if __name__ == "__main__":
    main()
