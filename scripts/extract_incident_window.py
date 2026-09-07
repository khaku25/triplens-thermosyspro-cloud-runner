#!/usr/bin/env python3
"""Extract an auditable pre-trip/trip/post-trip window from ProcessBus data.

The extractor never invents precursor values or labels a root cause.  It keeps
the original samples, estimates a stable pre-trip baseline, and records the
first persistent material deviation for each available physical signal.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


NON_SIGNAL_FIELDS = {"scenario_id", "time_s", "relative_time_s", "gt_trip_cmd"}


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if "time_s" not in fields or "gt_trip_cmd" not in fields:
        raise ValueError("ProcessBus must contain time_s and gt_trip_cmd")
    if len(rows) < 2:
        raise ValueError("ProcessBus must contain at least two rows")
    previous: float | None = None
    for row_number, row in enumerate(rows, start=2):
        try:
            value = float(row["time_s"])
        except ValueError as exc:
            raise ValueError(f"row {row_number}: time_s is not numeric") from exc
        if not math.isfinite(value) or (previous is not None and value <= previous):
            raise ValueError("ProcessBus time_s must be finite and strictly increasing")
        previous = value
    return fields, rows


def numeric_values(rows: list[dict[str, str]], field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        raw = row.get(field, "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def unit_for(field: str) -> str:
    suffixes = (
        ("_kg_s", "kg/s"), ("_mw", "MW"), ("_w", "W"),
        ("_pa", "Pa"), ("_k", "K"), ("_m", "m"), ("_pu", "pu"),
    )
    return next((unit for suffix, unit in suffixes if field.endswith(suffix)), "")


def phase(time_s: float, trip_time_s: float, tolerance_s: float) -> str:
    if time_s < trip_time_s - tolerance_s:
        return "PRE_TRIP"
    if time_s <= trip_time_s + tolerance_s:
        return "AT_TRIP"
    return "POST_TRIP"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processbus", type=Path, required=True)
    parser.add_argument("--trip-time", type=float, required=True)
    parser.add_argument("--pre-seconds", type=float, default=60.0)
    parser.add_argument("--post-seconds", type=float, default=400.0)
    parser.add_argument("--baseline-seconds", type=float, default=60.0)
    parser.add_argument("--baseline-guard-seconds", type=float, default=5.0)
    parser.add_argument("--relative-threshold", type=float, default=0.01)
    parser.add_argument("--mad-multiplier", type=float, default=6.0)
    parser.add_argument("--persistence-samples", type=int, default=3)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--changes-output", type=Path, required=True)
    parser.add_argument("--metadata-output", type=Path, required=True)
    args = parser.parse_args()

    for name in ("pre_seconds", "post_seconds", "baseline_seconds", "baseline_guard_seconds"):
        if getattr(args, name) < 0:
            parser.error(f"--{name.replace('_', '-')} must be non-negative")
    if args.relative_threshold <= 0 or args.mad_multiplier <= 0:
        parser.error("change thresholds must be positive")
    if args.persistence_samples <= 0:
        parser.error("--persistence-samples must be positive")

    fields, rows = read_rows(args.processbus)
    times = [float(row["time_s"]) for row in rows]
    if not times[0] < args.trip_time < times[-1]:
        raise ValueError("trip time must have both pre-trip and post-trip samples")

    nominal_period_s = statistics.median(
        right - left for left, right in zip(times, times[1:])
    )
    tolerance_s = max(nominal_period_s / 2.0, 1e-9)
    requested_start = max(times[0], args.trip_time - args.pre_seconds)
    requested_end = min(times[-1], args.trip_time + args.post_seconds)

    baseline_end = args.trip_time - args.baseline_guard_seconds
    baseline_start = max(times[0], baseline_end - args.baseline_seconds)
    baseline_rows = [
        row for row in rows
        if baseline_start <= float(row["time_s"]) < baseline_end
    ]
    minimum_baseline_rows = max(3, args.persistence_samples)
    if len(baseline_rows) < minimum_baseline_rows:
        pretrip_rows = [row for row in rows if float(row["time_s"]) < args.trip_time]
        baseline_rows = pretrip_rows[-max(minimum_baseline_rows, min(len(pretrip_rows), 20)):]
        if len(baseline_rows) < 2:
            raise ValueError("not enough pre-trip samples to establish a baseline")
        baseline_start = float(baseline_rows[0]["time_s"])
        baseline_end = float(baseline_rows[-1]["time_s"])

    candidate_rows = [
        row for row in rows
        if requested_start <= float(row["time_s"]) <= requested_end
    ]
    baselines: dict[str, dict[str, float | str]] = {}
    changes: list[dict[str, str]] = []
    for field in fields:
        if field in NON_SIGNAL_FIELDS:
            continue
        baseline_values = numeric_values(baseline_rows, field)
        if len(baseline_values) < 2:
            continue
        center = statistics.median(baseline_values)
        mad = statistics.median(abs(value - center) for value in baseline_values)
        threshold = max(
            abs(center) * args.relative_threshold,
            1.4826 * mad * args.mad_multiplier,
            1e-12,
        )
        baselines[field] = {
            "median": center,
            "mad": mad,
            "change_threshold_abs": threshold,
            "unit": unit_for(field),
        }

        pending: list[tuple[float, float]] = []
        first_change: tuple[float, float] | None = None
        for row in candidate_rows:
            raw = row.get(field, "").strip()
            if not raw:
                pending.clear()
                continue
            try:
                value = float(raw)
            except ValueError:
                pending.clear()
                continue
            if math.isfinite(value) and abs(value - center) >= threshold:
                pending.append((float(row["time_s"]), value))
                if len(pending) >= args.persistence_samples:
                    first_change = pending[0]
                    break
            else:
                pending.clear()
        if first_change is None:
            continue
        change_time, value = first_change
        delta = value - center
        delta_percent = "" if abs(center) < 1e-12 else f"{delta / abs(center) * 100:.6f}"
        changes.append({
            "change_time_s": f"{change_time:.9f}",
            "relative_to_trip_s": f"{change_time - args.trip_time:.9f}",
            "phase": phase(change_time, args.trip_time, tolerance_s),
            "change_kind": "PROCESS",
            "signal": field,
            "baseline_value": f"{center:.12g}",
            "observed_value": f"{value:.12g}",
            "delta": f"{delta:.12g}",
            "delta_percent": delta_percent,
            "detection_threshold_abs": f"{threshold:.12g}",
            "unit": unit_for(field),
            "provenance": "PROCESSBUS_PERSISTENT_DEVIATION",
        })

    command_row = next(
        (row for row in rows if row["gt_trip_cmd"].strip() in {"1", "true", "TRUE"}),
        None,
    )
    if command_row is None:
        raise ValueError("ProcessBus has no asserted gt_trip_cmd")
    command_time = float(command_row["time_s"])
    changes.append({
        "change_time_s": f"{command_time:.9f}",
        "relative_to_trip_s": f"{command_time - args.trip_time:.9f}",
        "phase": phase(command_time, args.trip_time, tolerance_s),
        "change_kind": "COMMAND",
        "signal": "gt_trip_cmd",
        "baseline_value": "0",
        "observed_value": "1",
        "delta": "1",
        "delta_percent": "",
        "detection_threshold_abs": "1",
        "unit": "BOOL",
        "provenance": "SCENARIO_INPUT",
    })
    changes.sort(key=lambda row: (float(row["change_time_s"]), row["change_kind"], row["signal"]))

    window_rows = [
        row for row in rows
        if requested_start <= float(row["time_s"]) <= requested_end
    ]
    raw_fields = list(fields)
    raw_fields.insert(raw_fields.index("time_s") + 1, "relative_time_s")
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    with args.raw_output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=raw_fields)
        writer.writeheader()
        for row in window_rows:
            output = dict(row)
            output["relative_time_s"] = f"{float(row['time_s']) - args.trip_time:.9f}"
            writer.writerow(output)

    change_fields = [
        "change_time_s", "relative_to_trip_s", "phase", "change_kind", "signal",
        "baseline_value", "observed_value", "delta", "delta_percent",
        "detection_threshold_abs", "unit", "provenance",
    ]
    args.changes_output.parent.mkdir(parents=True, exist_ok=True)
    with args.changes_output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=change_fields)
        writer.writeheader()
        writer.writerows(changes)

    process_changes = [row for row in changes if row["change_kind"] == "PROCESS"]
    first_process_change = process_changes[0] if process_changes else None
    metadata = {
        "schema_version": "1.0",
        "source_file": args.processbus.name,
        "trip_command_time_s": args.trip_time,
        "observed_gt_trip_cmd_assertion_s": command_time,
        "source_start_s": times[0],
        "source_end_s": times[-1],
        "nominal_physics_output_period_s": nominal_period_s,
        "analysis_window_start_s": float(window_rows[0]["time_s"]),
        "analysis_window_end_s": float(window_rows[-1]["time_s"]),
        "analysis_pre_trip_s": args.trip_time - float(window_rows[0]["time_s"]),
        "analysis_post_trip_s": float(window_rows[-1]["time_s"]) - args.trip_time,
        "baseline_start_s": baseline_start,
        "baseline_end_s": baseline_end,
        "baseline_sample_count": len(baseline_rows),
        "detection": {
            "method": "persistent absolute deviation from pre-trip median",
            "relative_floor": args.relative_threshold,
            "mad_multiplier": args.mad_multiplier,
            "persistence_samples": args.persistence_samples,
            "root_cause_inferred": False,
        },
        "first_significant_process_change_s": (
            float(first_process_change["change_time_s"]) if first_process_change else None
        ),
        "first_significant_process_change_signal": (
            first_process_change["signal"] if first_process_change else None
        ),
        "pretrip_process_change_count": sum(
            row["phase"] == "PRE_TRIP" for row in process_changes
        ),
        "posttrip_process_change_count": sum(
            row["phase"] in {"AT_TRIP", "POST_TRIP"} for row in process_changes
        ),
        "signal_baselines": baselines,
    }
    args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_output.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
