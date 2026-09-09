#!/usr/bin/env python3
"""Keep only first-order H/HH/L/LL runtime alarm rules.

Command inputs and TRIP actions are intentionally outside Core v1.  A kept rule
must be an absolute threshold on a physical/canonical signal and its alarm tag
must end in H, HH, L, or LL.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ALLOWED_SUFFIXES = {"H", "HH", "L", "LL"}


def exclusion_reason(row: dict[str, str]) -> str:
    alarm_tag = str(row.get("alarm_tag") or "").strip()
    suffix = alarm_tag.rsplit(".", 1)[-1].upper() if alarm_tag else ""
    threshold_mode = str(row.get("threshold_mode") or "").strip().upper()
    source_signal = str(row.get("source_signal") or "").strip().lower()

    if suffix not in ALLOWED_SUFFIXES:
        return f"alarm_suffix={suffix or 'EMPTY'}"
    if threshold_mode != "ABSOLUTE":
        return f"threshold_mode={threshold_mode or 'EMPTY'}"
    if source_signal.endswith("_cmd"):
        return "command_source"
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

    print(f"FIRST_ORDER_RUNTIME_CORE: kept={len(kept)} excluded={len(excluded)} total={len(rows)}")


if __name__ == "__main__":
    main()
