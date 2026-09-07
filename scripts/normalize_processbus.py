#!/usr/bin/env python3
"""Normalize an OpenModelica result CSV into the TripLens ProcessBus contract."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def canonical_header(value: str) -> str:
    return value.lstrip("\ufeff").strip().strip('"')


def resolve_column(headers: list[str], aliases: list[str]) -> str | None:
    canonical = {canonical_header(h): h for h in headers}
    for alias in aliases:
        if alias in canonical:
            return canonical[alias]
    for alias in aliases:
        matches = [raw for name, raw in canonical.items() if name.endswith("." + alias)]
        if len(matches) == 1:
            return matches[0]
    return None


def parse_float(value: str, field: str, row_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"row {row_number}: {field} is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"row {row_number}: {field} is not finite")
    return number


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, default=PROJECT_ROOT / "config/signal_map.json")
    parser.add_argument("--mapping-review", type=Path)
    parser.add_argument("--trip-time", type=float, required=True)
    parser.add_argument("--scenario-id", default="GT_TRIP_TAC")
    args = parser.parse_args()

    specification = json.loads(args.mapping.read_text(encoding="utf-8"))
    with args.input.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("input CSV has no header")
        source_rows = list(reader)
        headers = list(reader.fieldnames)
    if len(source_rows) < 2:
        raise ValueError("input CSV must contain at least two data rows")

    resolved: dict[str, str | None] = {}
    missing_required: list[str] = []
    for target, definition in specification["signals"].items():
        source = resolve_column(headers, definition["aliases"])
        resolved[target] = source
        if definition.get("required") and source is None:
            missing_required.append(target)
    if missing_required:
        raise ValueError("required ThermoSysPro signals were not found: " + ", ".join(missing_required))

    output_fields = [
        "scenario_id",
        "time_s",
        "gt_trip_cmd",
        *[name for name in specification["signals"] if name != "time_s"],
    ]
    normalized: list[dict[str, str | int | float]] = []
    previous_time: float | None = None
    duplicate_time_rows_collapsed = 0
    for row_index, source_row in enumerate(source_rows, start=2):
        time_source = resolved["time_s"]
        assert time_source is not None
        time_s = parse_float(source_row[time_source], "time_s", row_index)
        if previous_time is not None and time_s < previous_time:
            raise ValueError(f"row {row_index}: time_s must be strictly increasing")
        target_row: dict[str, str | int | float] = {
            "scenario_id": args.scenario_id,
            "time_s": f"{time_s:.9f}",
            "gt_trip_cmd": int(time_s >= args.trip_time),
        }
        for target in specification["signals"]:
            if target == "time_s":
                continue
            source = resolved[target]
            target_row[target] = "" if source is None else f"{parse_float(source_row[source], target, row_index):.12g}"
        if previous_time is not None and time_s == previous_time:
            # OpenModelica may emit pre-event and post-event values at one
            # timestamp. ProcessBus retains the final post-event state.
            normalized[-1] = target_row
            duplicate_time_rows_collapsed += 1
        else:
            normalized.append(target_row)
        previous_time = time_s

    if not (float(normalized[0]["time_s"]) <= args.trip_time <= float(normalized[-1]["time_s"])):
        raise ValueError("trip time is outside the simulation time range")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(normalized)

    review_path = args.mapping_review or args.output.with_name("signal-mapping-review.json")
    review = {
        "schema_version": specification["schema_version"],
        "input_file": args.input.name,
        "scenario_id": args.scenario_id,
        "trip_time_s": args.trip_time,
        "duplicate_time_rows_collapsed": duplicate_time_rows_collapsed,
        "duplicate_time_policy": "keep_last_event_state",
        "resolved": resolved,
        "missing_optional": [name for name, source in resolved.items() if source is None],
    }
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
