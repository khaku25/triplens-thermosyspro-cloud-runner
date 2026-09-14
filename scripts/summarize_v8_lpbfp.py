#!/usr/bin/env python3
"""Build a compact, independently checkable verdict from V8 LP-BFP artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


EVENT_COLUMNS = (
    "event_id", "event_sequence", "session_id", "incident_id", "model_time_s",
    "wall_time_utc", "priority", "event_class", "equipment", "tag", "state",
    "value", "unit", "message", "source", "acknowledged",
)
FORBIDDEN_EVENT_TAGS = {
    "TRIP_CMD", "VCB_TRIP_CMD", "BREAKER_COMMAND", "OPEN_CMD", "CLOSE_CMD",
    "LP_BFP_TRIP_CMD", "LP_BFP_TRIP_LATCH", "VCB_A02_TRIP_CMD",
    "VCB_A02_OPEN_CMD", "VCB_A02_CLOSE_CMD",
}
REQUIRED_EVENT_TAGS = {
    "LP_BFP_TRIP_PB", "BREAKER_OPEN", "MOTOR_DEENERGIZED", "RUNNING_LOST",
    "SPEED_PROVEN_LOST", "FLOW_LOW", "CHECK_VALVE_CLOSED",
}
CHAIN = (
    ("vppLPFWPTripCommandNative", "rise"),
    ("vppLPFWPTripLatchNative", "rise"),
    ("vppVCBA02TripCommandNative", "rise"),
    ("vppECMSVCBA02Closed", "fall"),
)


def read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def number(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite value: {value}")
    return result


def edge_time(rows: list[dict[str, str]], field: str, direction: str) -> float | None:
    previous = None
    for row in rows:
        current = number(row[field])
        if previous is not None:
            crossed = previous < 0.5 <= current if direction == "rise" else previous >= 0.5 > current
            if crossed:
                return number(row["model_time_s"])
        previous = current
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    event_fields, events = read(args.event)
    raw_fields, raw = read(args.raw)
    analysis = json.loads(args.analysis.read_text(encoding="utf-8-sig"))
    problems: list[str] = []
    if tuple(event_fields) != EVENT_COLUMNS:
        problems.append("EVENT schema mismatch")
    if not events:
        problems.append("EVENT has no rows")
    if len(raw) < 2:
        problems.append("RAW has fewer than two rows")

    tags = {row.get("tag", "") for row in events}
    missing_events = sorted(REQUIRED_EVENT_TAGS - tags)
    leaked = sorted(tags & FORBIDDEN_EVENT_TAGS)
    if missing_events:
        problems.append("missing EVENT tags: " + ",".join(missing_events))
    if leaked:
        problems.append("command leakage in EVENT: " + ",".join(leaked))

    chain_times: dict[str, float | None] = {}
    for field, direction in CHAIN:
        if field not in raw_fields:
            problems.append(f"RAW missing chain field: {field}")
            chain_times[field] = None
        else:
            chain_times[field] = edge_time(raw, field, direction)
            if chain_times[field] is None:
                problems.append(f"RAW missing {direction} edge: {field}")

    physical = {}
    for field in ("vppLPFWPSpeedRPM", "vppLPFWPMassFlowTH"):
        if field not in raw_fields or len(raw) < 2:
            problems.append(f"RAW missing physical series: {field}")
            continue
        before = number(raw[0][field])
        after = number(raw[-1][field])
        physical[field] = {"before": before, "after": after, "delta": after - before}
        if not after < before:
            problems.append(f"physical response did not decrease: {field}")

    if analysis.get("status") != "PASS":
        problems.append(f"dual analysis status={analysis.get('status')}")
    result = {
        "status": "PASS" if not problems else "FAIL",
        "event_rows": len(events),
        "raw_rows": len(raw),
        "event_tags": sorted(tags),
        "command_leakage_count": len(leaked),
        "chain_edge_model_time_s": chain_times,
        "physical_response": physical,
        "analysis_status": analysis.get("status"),
        "problems": problems,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
