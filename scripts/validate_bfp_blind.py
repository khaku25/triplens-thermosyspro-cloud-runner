#!/usr/bin/env python3
"""Validate physics continuity and the three-source BFP blind-test contract."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"{path}: contains no data rows")
    return rows


def finite(value: str, label: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} is not numeric: {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--trip-time", type=float, required=True)
    parser.add_argument("--stop-time", type=float, required=True)
    parser.add_argument("--final-rpm", type=float, required=True)
    args = parser.parse_args()

    process_path = args.output_dir / "engineering" / "processbus-bfp.csv"
    process = read_csv(process_path)
    times = [finite(row["time_s"], "time_s") for row in process]
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("BFP ProcessBus time must be strictly increasing")
    if abs(times[0]) > 1e-9 or abs(times[-1] - args.stop_time) > 1e-6:
        raise ValueError("BFP ProcessBus does not span the requested horizon")
    for row_number, row in enumerate(process, start=2):
        for field, raw in row.items():
            if field == "incident_id" or raw == "":
                continue
            finite(raw, f"row {row_number} {field}")

    pre = [row for row in process if finite(row["time_s"], "time_s") < args.trip_time]
    post = [row for row in process if finite(row["time_s"], "time_s") >= args.trip_time + 5]
    if not pre or not post:
        raise ValueError("pre/post incident physics windows are missing")
    initial_rpm = finite(pre[-1]["bfp_hp_speed_rpm"], "pre-trip RPM")
    final_rpm = finite(post[-1]["bfp_hp_speed_rpm"], "final RPM")
    if initial_rpm < 1300 or abs(final_rpm - args.final_rpm) > 1e-3:
        raise ValueError("BFP speed adapter did not reach the declared states")
    exhaust = [finite(row["gt_exhaust_mass_flow_kg_s"], "GT exhaust flow") for row in process]
    if max(exhaust) - min(exhaust) > 1e-6:
        raise ValueError("GT exhaust changed during the isolated BFP incident")
    feedwater = [finite(row["bfp_hp_mass_flow_kg_s"], "HP feedwater flow") for row in process]
    if max(feedwater) - min(feedwater) < max(1.0, abs(feedwater[0]) * 0.05):
        raise ValueError("BFP disturbance did not materially change HP feedwater flow")

    blind = args.output_dir / "blind-input"
    blind_files = sorted(path.name for path in blind.glob("*.csv"))
    if blind_files != ["DCS1.csv", "DCS2.csv", "ECMS.csv"]:
        raise ValueError("blind-input must contain exactly DCS1.csv, DCS2.csv, and ECMS.csv")
    events = {system: read_csv(blind / f"{system}.csv") for system in ("DCS1", "DCS2", "ECMS")}
    required = {
        "DCS1": {"BFP-HP.SPEED_LOW", "HP.FW.FLOW_LOW"},
        "ECMS": {"50BFP-HP.PICKUP", "52BFP-HP.CLOSED", "BFP-HP.MOTOR.CURRENT_A"},
    }
    for system, tags in required.items():
        actual = {row["tag"] for row in events[system]}
        missing = tags.difference(actual)
        if missing:
            raise ValueError(f"{system}.csv is missing: {', '.join(sorted(missing))}")
    if not events["DCS2"]:
        raise ValueError("DCS2.csv contains no downstream physical consequence")

    all_blind_text = "\n".join(path.read_text(encoding="utf-8") for path in blind.glob("*.csv"))
    if "GT.TRIP.CMD" in all_blind_text or "expected_root_cause" in all_blind_text:
        raise ValueError("blind input leaks a scenario answer label")
    answer = json.loads((args.output_dir / "ground-truth" / "answer-key.json").read_text(encoding="utf-8"))
    if answer["expected_root_cause"] != "HP boiler feed pump electrical trip":
        raise ValueError("answer key root cause does not match the physical adapter")
    metadata = json.loads((args.output_dir / "run-metadata.json").read_text(encoding="utf-8"))
    if metadata["blind_upload_directory"] != "blind-input":
        raise ValueError("blind upload contract is missing")
    if metadata["blind_upload_files"] != ["DCS1.csv", "DCS2.csv", "ECMS.csv"]:
        raise ValueError("blind upload file contract is missing")
    print(json.dumps({
        "physics_rows": len(process),
        "last_time_s": times[-1],
        "initial_bfp_rpm": initial_rpm,
        "final_bfp_rpm": final_rpm,
        "feedwater_min_kg_s": min(feedwater),
        "feedwater_max_kg_s": max(feedwater),
        "event_counts": {system: len(rows) for system, rows in events.items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
