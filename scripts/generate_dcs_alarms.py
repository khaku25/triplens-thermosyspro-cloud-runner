#!/usr/bin/env python3
"""Generate chronological DCS1/DCS2 alarms from actual ProcessBus crossings."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path


EVENT_FIELDS = [
    "event_sequence", "event_time_ms", "source_time_ms", "time_s",
    "relative_to_trip_s", "phase", "system", "tag", "alarm_state",
    "event_class", "severity", "source_signal", "value", "threshold",
    "unit", "quality", "provenance", "rule_status", "description",
]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    system: str
    signal: str
    tag: str
    description: str
    direction: str
    mode: str
    threshold_value: float
    hysteresis_value: float
    delay_s: float
    severity: str
    unit: str
    status: str


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def load_rules(path: Path) -> list[Rule]:
    required = {
        "rule_id", "system", "source_signal", "alarm_tag", "description_ko",
        "direction", "threshold_mode", "threshold_value", "hysteresis_value",
        "delay_s", "severity", "unit", "status",
    }
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        with sqlite3.connect(path) as database:
            database.row_factory = sqlite3.Row
            result = database.execute(
                """SELECT rule_id, system, source_signal, alarm_tag,
                          description_ko, direction, threshold_mode,
                          threshold_value, hysteresis_value, delay_s,
                          severity, unit, status
                   FROM runtime_alarm_rule ORDER BY rule_id"""
            )
            rows = [dict(row) for row in result]
        fields = list(rows[0]) if rows else []
    else:
        fields, rows = read_csv(path)
    missing = required.difference(fields)
    if missing:
        raise ValueError("DCS rule file is missing: " + ", ".join(sorted(missing)))
    rules: list[Rule] = []
    ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        rule_id = row["rule_id"].strip()
        if not rule_id or rule_id in ids:
            raise ValueError(f"DCS rule row {row_number} has an empty or duplicate rule_id")
        ids.add(rule_id)
        direction = row["direction"].strip().upper()
        mode = row["threshold_mode"].strip().upper()
        system = row["system"].strip().upper()
        if system not in {"DCS1", "DCS2"}:
            raise ValueError(f"{rule_id}: system must be DCS1 or DCS2")
        if direction not in {"LOW", "HIGH"}:
            raise ValueError(f"{rule_id}: direction must be LOW or HIGH")
        if mode not in {"ABSOLUTE", "BOOLEAN"}:
            raise ValueError(f"{rule_id}: unsupported threshold mode")
        rules.append(Rule(
            rule_id=rule_id,
            system=system,
            signal=row["source_signal"].strip(),
            tag=row["alarm_tag"].strip(),
            description=row["description_ko"].strip(),
            direction=direction,
            mode=mode,
            threshold_value=float(row["threshold_value"]),
            hysteresis_value=float(row["hysteresis_value"]),
            delay_s=float(row["delay_s"]),
            severity=row["severity"].strip().upper(),
            unit=row["unit"].strip(),
            status=row["status"].strip(),
        ))
    return rules


def event_phase(time_s: float, trip_time_s: float) -> str:
    if time_s < trip_time_s - 1e-9:
        return "PRE_TRIP"
    if math.isclose(time_s, trip_time_s, abs_tol=1e-9):
        return "AT_TRIP"
    return "POST_TRIP"


def write_events(path: Path, events: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(events)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident-raw", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--trip-time", type=float, required=True)
    parser.add_argument("--dcs1-output", type=Path, required=True)
    parser.add_argument("--dcs2-output", type=Path, required=True)
    args = parser.parse_args()

    fields, rows = read_csv(args.incident_raw)
    if len(rows) < 2 or "time_s" not in fields:
        raise ValueError("incident RAW must contain ordered time_s samples")
    times = [float(row["time_s"]) for row in rows]
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("incident RAW time_s must be strictly increasing")
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    baselines = metadata.get("signal_baselines", {})
    rules = load_rules(args.rules)
    events: list[dict[str, str | int | float]] = []

    for rule_order, rule in enumerate(rules):
        if rule.signal not in fields:
            continue
        if rule.mode == "BOOLEAN":
            baseline = 0.0
            threshold = rule.threshold_value
        else:
            baseline = 0.0
            threshold = rule.threshold_value
        hysteresis = rule.hysteresis_value

        def asserted(value: float) -> bool:
            return value <= threshold if rule.direction == "LOW" else value >= threshold

        def cleared(value: float) -> bool:
            return (
                value > threshold + hysteresis
                if rule.direction == "LOW" else value < threshold - hysteresis
            )

        active = False
        announced = False
        pending_since: float | None = None
        first_valid = True
        for row in rows:
            raw = row.get(rule.signal, "").strip()
            if not raw:
                pending_since = None
                continue
            try:
                value = float(raw)
            except ValueError:
                pending_since = None
                continue
            if not math.isfinite(value):
                pending_since = None
                continue
            time_s = float(row["time_s"])
            condition = asserted(value)
            if first_valid:
                active = condition
                first_valid = False
                continue
            if not active:
                if condition:
                    pending_since = time_s if pending_since is None else pending_since
                    if time_s + 1e-12 >= pending_since + rule.delay_s:
                        active = True
                        announced = True
                        pending_since = None
                        events.append({
                            "_rule_order": rule_order,
                            "event_time_ms": round(time_s * 1000),
                            "source_time_ms": round(time_s * 1000),
                            "time_s": f"{time_s:.9f}",
                            "relative_to_trip_s": f"{time_s - args.trip_time:.9f}",
                            "phase": event_phase(time_s, args.trip_time),
                            "system": rule.system,
                            "tag": rule.tag,
                            "alarm_state": "ACTIVE",
                            "event_class": "ALARM",
                            "severity": rule.severity,
                            "source_signal": rule.signal,
                            "value": f"{value:.12g}",
                            "threshold": f"{threshold:.12g}",
                            "unit": rule.unit,
                            "quality": "GOOD",
                            "provenance": (
                                "SCENARIO_INPUT" if rule.mode == "BOOLEAN"
                                else "PHYSICS_ABSOLUTE_THRESHOLD"
                            ),
                            "rule_status": rule.status,
                            "description": rule.description,
                        })
                else:
                    pending_since = None
            elif cleared(value):
                active = False
                pending_since = None
                if announced:
                    events.append({
                        "_rule_order": rule_order,
                        "event_time_ms": round(time_s * 1000),
                        "source_time_ms": round(time_s * 1000),
                        "time_s": f"{time_s:.9f}",
                        "relative_to_trip_s": f"{time_s - args.trip_time:.9f}",
                        "phase": event_phase(time_s, args.trip_time),
                        "system": rule.system,
                        "tag": rule.tag,
                        "alarm_state": "RETURN",
                        "event_class": "RETURN",
                        "severity": rule.severity,
                        "source_signal": rule.signal,
                        "value": f"{value:.12g}",
                        "threshold": f"{threshold:.12g}",
                        "unit": rule.unit,
                        "quality": "GOOD",
                        "provenance": (
                            "SCENARIO_INPUT" if rule.mode == "BOOLEAN"
                            else "PHYSICS_ABSOLUTE_THRESHOLD"
                        ),
                        "rule_status": rule.status,
                        "description": rule.description,
                    })
                    announced = False

    events.sort(key=lambda row: (int(row["source_time_ms"]), int(row["_rule_order"])))
    clean_events: list[dict[str, str]] = []
    for sequence, row in enumerate(events, start=1):
        output = {key: str(value) for key, value in row.items() if key != "_rule_order"}
        output["event_sequence"] = str(sequence)
        clean_events.append(output)
    dcs1 = [row for row in clean_events if row["system"] == "DCS1"]
    dcs2 = [row for row in clean_events if row["system"] == "DCS2"]
    write_events(args.dcs1_output, dcs1)
    write_events(args.dcs2_output, dcs2)

    metadata["alarm_summary"] = {
        "rules_file": args.rules.name,
        "rule_status": "MODEL_ABSOLUTE_NOT_PLANT_APPROVED",
        "dcs1_event_count": len(dcs1),
        "dcs2_event_count": len(dcs2),
        "pretrip_event_count": sum(row["phase"] == "PRE_TRIP" for row in clean_events),
        "at_trip_event_count": sum(row["phase"] == "AT_TRIP" for row in clean_events),
        "posttrip_event_count": sum(row["phase"] == "POST_TRIP" for row in clean_events),
        "pretrip_alarm_fabricated": False,
    }
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
