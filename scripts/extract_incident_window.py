#!/usr/bin/env python3
"""Extract an auditable pre-event/event/post-event window from ProcessBus data.

The extractor is scenario-agnostic. It analyzes every numeric ProcessBus signal
that is present, including dynamically discovered passthrough signals. It does
not require a GT-trip command and never fabricates precursor process values or a
root cause. Legacy GT-trip fields remain supported for compatibility.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


BASE_NON_SIGNAL_FIELDS = {
    "scenario_id",
    "incident_id",
    "time_s",
    "relative_time_s",
    "event_marker",
}


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if "time_s" not in fields:
        raise ValueError("ProcessBus must contain time_s")
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
        ("_kg_s", "kg/s"),
        ("_rpm", "rpm"),
        ("_mw", "MW"),
        ("_w", "W"),
        ("_pa", "Pa"),
        ("_kv", "kV"),
        ("_k", "K"),
        ("_m", "m"),
        ("_pu", "pu"),
        ("_a", "A"),
    )
    return next((unit for suffix, unit in suffixes if field.endswith(suffix)), "")


def phase(time_s: float, event_time_s: float, tolerance_s: float) -> str:
    # Keep legacy labels so existing TripLens/DCS consumers remain compatible.
    if time_s < event_time_s - tolerance_s:
        return "PRE_TRIP"
    if time_s <= event_time_s + tolerance_s:
        return "AT_TRIP"
    return "POST_TRIP"


def command_like(field: str) -> bool:
    lower = field.lower()
    return (
        lower.endswith("_cmd")
        or lower.endswith("_command")
        or lower.startswith("cmd__")
    )


def first_command_transition(
    rows: list[dict[str, str]],
    field: str,
    event_time_s: float,
    search_start_s: float,
    search_end_s: float,
) -> tuple[float, str, str] | None:
    samples: list[tuple[float, str]] = []
    for row in rows:
        time_s = float(row["time_s"])
        if not search_start_s <= time_s <= search_end_s:
            continue
        raw = row.get(field, "").strip()
        if raw == "":
            continue
        samples.append((time_s, raw))
    if len(samples) < 2:
        return None

    candidates: list[tuple[float, str, str]] = []
    _, previous_value = samples[0]
    for time_s, current_value in samples[1:]:
        if current_value != previous_value:
            candidates.append((time_s, previous_value, current_value))
        previous_value = current_value
    if not candidates:
        return None
    after = [item for item in candidates if item[0] >= event_time_s - 1e-12]
    return after[0] if after else candidates[0]


def resolve_event_time(args: argparse.Namespace) -> float:
    if args.event_time is None and args.trip_time is None:
        raise ValueError("one of --event-time or legacy --trip-time is required")
    if args.event_time is not None and args.trip_time is not None:
        if not math.isclose(args.event_time, args.trip_time, abs_tol=1e-12):
            raise ValueError("--event-time and legacy --trip-time disagree")
    event_time = args.event_time if args.event_time is not None else args.trip_time
    assert event_time is not None
    if not math.isfinite(event_time):
        raise ValueError("event time must be finite")
    return event_time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processbus", type=Path, required=True)
    parser.add_argument("--event-time", type=float)
    parser.add_argument("--trip-time", type=float, help="Legacy alias for --event-time")
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

    event_time_s = resolve_event_time(args)
    for name in ("pre_seconds", "post_seconds", "baseline_seconds", "baseline_guard_seconds"):
        if getattr(args, name) < 0:
            parser.error(f"--{name.replace('_', '-')} must be non-negative")
    if args.relative_threshold <= 0 or args.mad_multiplier <= 0:
        parser.error("change thresholds must be positive")
    if args.persistence_samples <= 0:
        parser.error("--persistence-samples must be positive")

    fields, rows = read_rows(args.processbus)
    times = [float(row["time_s"]) for row in rows]
    if not times[0] < event_time_s < times[-1]:
        raise ValueError("event time must have both pre-event and post-event samples")

    nominal_period_s = statistics.median(
        right - left for left, right in zip(times, times[1:])
    )
    tolerance_s = max(nominal_period_s / 2.0, 1e-9)
    requested_start = max(times[0], event_time_s - args.pre_seconds)
    requested_end = min(times[-1], event_time_s + args.post_seconds)

    baseline_end = event_time_s - args.baseline_guard_seconds
    baseline_start = max(times[0], baseline_end - args.baseline_seconds)
    baseline_rows = [
        row for row in rows
        if baseline_start <= float(row["time_s"]) < baseline_end
    ]
    minimum_baseline_rows = max(3, args.persistence_samples)
    if len(baseline_rows) < minimum_baseline_rows:
        pre_event_rows = [row for row in rows if float(row["time_s"]) < event_time_s]
        baseline_rows = pre_event_rows[
            -max(minimum_baseline_rows, min(len(pre_event_rows), 20)):
        ]
        if len(baseline_rows) < 2:
            raise ValueError("not enough pre-event samples to establish a baseline")
        baseline_start = float(baseline_rows[0]["time_s"])
        baseline_end = float(baseline_rows[-1]["time_s"])

    candidate_rows = [
        row for row in rows
        if requested_start <= float(row["time_s"]) <= requested_end
    ]

    command_fields = [field for field in fields if command_like(field)]
    non_signal_fields = BASE_NON_SIGNAL_FIELDS | set(command_fields)

    baselines: dict[str, dict[str, float | str]] = {}
    changes: list[dict[str, str]] = []

    for field in fields:
        if field in non_signal_fields:
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
            "relative_to_trip_s": f"{change_time - event_time_s:.9f}",
            "phase": phase(change_time, event_time_s, tolerance_s),
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

    observed_commands: dict[str, float] = {}
    for field in command_fields:
        transition = first_command_transition(
            rows, field, event_time_s, requested_start, requested_end
        )
        if transition is None:
            continue
        change_time, old_value, new_value = transition
        observed_commands[field] = change_time
        changes.append({
            "change_time_s": f"{change_time:.9f}",
            "relative_to_trip_s": f"{change_time - event_time_s:.9f}",
            "phase": phase(change_time, event_time_s, tolerance_s),
            "change_kind": "COMMAND",
            "signal": field,
            "baseline_value": old_value,
            "observed_value": new_value,
            "delta": "",
            "delta_percent": "",
            "detection_threshold_abs": "",
            "unit": "BOOL" if {old_value.lower(), new_value.lower()} <= {
                "0", "1", "true", "false"
            } else "",
            "provenance": "PROCESSBUS_COMMAND_OBSERVED",
        })

    if not observed_commands and "event_marker" in fields:
        changes.append({
            "change_time_s": f"{event_time_s:.9f}",
            "relative_to_trip_s": "0.000000000",
            "phase": "AT_TRIP",
            "change_kind": "REFERENCE_EVENT",
            "signal": "event_marker",
            "baseline_value": "0",
            "observed_value": "1",
            "delta": "",
            "delta_percent": "",
            "detection_threshold_abs": "",
            "unit": "BOOL",
            "provenance": "PIPELINE_REFERENCE_TIME",
        })

    changes.sort(
        key=lambda row: (
            float(row["change_time_s"]),
            row["change_kind"],
            row["signal"],
        )
    )

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
            output["relative_time_s"] = f"{float(row['time_s']) - event_time_s:.9f}"
            writer.writerow(output)

    change_fields = [
        "change_time_s",
        "relative_to_trip_s",
        "phase",
        "change_kind",
        "signal",
        "baseline_value",
        "observed_value",
        "delta",
        "delta_percent",
        "detection_threshold_abs",
        "unit",
        "provenance",
    ]
    args.changes_output.parent.mkdir(parents=True, exist_ok=True)
    with args.changes_output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=change_fields)
        writer.writeheader()
        writer.writerows(changes)

    process_changes = [row for row in changes if row["change_kind"] == "PROCESS"]
    first_process_change = process_changes[0] if process_changes else None
    metadata: dict[str, object] = {
        "schema_version": "2.0",
        "source_file": args.processbus.name,
        "reference_event_time_s": event_time_s,
        "trip_command_time_s": event_time_s,
        "source_start_s": times[0],
        "source_end_s": times[-1],
        "nominal_physics_output_period_s": nominal_period_s,
        "analysis_window_start_s": float(window_rows[0]["time_s"]),
        "analysis_window_end_s": float(window_rows[-1]["time_s"]),
        "analysis_pre_trip_s": event_time_s - float(window_rows[0]["time_s"]),
        "analysis_post_trip_s": float(window_rows[-1]["time_s"]) - event_time_s,
        "baseline_start_s": baseline_start,
        "baseline_end_s": baseline_end,
        "baseline_sample_count": len(baseline_rows),
        "process_signal_count": len(baselines),
        "command_fields_present": command_fields,
        "observed_command_assertions_s": observed_commands,
        "detection": {
            "method": "persistent absolute deviation from pre-event median",
            "relative_floor": args.relative_threshold,
            "mad_multiplier": args.mad_multiplier,
            "persistence_samples": args.persistence_samples,
            "root_cause_inferred": False,
            "dynamic_processbus_signals_analyzed": True,
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
    if "gt_trip_cmd" in observed_commands:
        metadata["observed_gt_trip_cmd_assertion_s"] = observed_commands["gt_trip_cmd"]

    args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_output.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
