#!/usr/bin/env python3
"""Create three-source blind incident CSVs from a ThermoSysPro BFP run.

The blind-input directory intentionally contains observations only. Ground
truth and provisional alarm thresholds are written outside that directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean


CLOCK_OFFSET_MS = {"DCS1": 120, "DCS2": -80, "ECMS": 0}


@dataclass(frozen=True)
class Event:
    source_time_ms: int
    system: str
    tag: str
    old_value: str
    new_value: str
    event_class: str
    description: str
    provenance: str


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) < 2:
        raise ValueError("BFP ProcessBus must contain at least two rows")
    return rows


def value(row: dict[str, str], field: str) -> float:
    raw = row.get(field, "")
    if raw == "":
        raise ValueError(f"{field} is unavailable")
    result = float(raw)
    if not math.isfinite(result):
        raise ValueError(f"{field} is not finite")
    return result


def baseline(rows: list[dict[str, str]], field: str, trip_s: float) -> float:
    samples = [value(row, field) for row in rows if trip_s - 10 <= value(row, "time_s") < trip_s]
    if not samples:
        raise ValueError(f"no pre-incident baseline samples for {field}")
    return fmean(samples)


def first_after(
    rows: list[dict[str, str]], field: str, trip_s: float, predicate,
) -> tuple[int, float] | None:
    for row in rows:
        time_s = value(row, "time_s")
        current = value(row, field)
        if time_s >= trip_s and predicate(current):
            return round(time_s * 1000), current
    return None


def add_crossing(
    events: list[Event], rows: list[dict[str, str]], trip_s: float,
    *, system: str, field: str, tag: str, threshold: float,
    predicate, event_class: str, description: str,
) -> None:
    crossing = first_after(rows, field, trip_s, predicate)
    if crossing is None:
        return
    time_ms, current = crossing
    events.append(Event(
        time_ms, system, tag, f"{threshold:.6g}", f"{current:.6g}",
        event_class, description, "E_DERIVED_FROM_THERMOSYSPRO",
    ))


def write_events(path: Path, events: list[Event]) -> None:
    fields = [
        "event_time_ms", "source_time_ms", "system", "tag", "old_value",
        "new_value", "event_class", "quality", "provenance", "description",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for event in sorted(events, key=lambda item: (item.source_time_ms, item.tag)):
            writer.writerow({
                "event_time_ms": event.source_time_ms + CLOCK_OFFSET_MS[event.system],
                "source_time_ms": event.source_time_ms,
                "system": event.system,
                "tag": event.tag,
                "old_value": event.old_value,
                "new_value": event.new_value,
                "event_class": event.event_class,
                "quality": "GOOD",
                "provenance": event.provenance,
                "description": event.description,
            })


def write_trend(path: Path, rows: list[dict[str, str]]) -> None:
    fields = [name for name in rows[0] if name != "incident_id"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processbus", type=Path, required=True)
    parser.add_argument("--trip-time", type=float, required=True)
    parser.add_argument("--stop-time", type=float, required=True)
    parser.add_argument("--final-rpm", type=float, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows = load_rows(args.processbus)
    trip_ms = round(args.trip_time * 1000)
    b_speed = baseline(rows, "bfp_hp_speed_rpm", args.trip_time)
    b_flow = baseline(rows, "bfp_hp_mass_flow_kg_s", args.trip_time)
    b_level = baseline(rows, "hp_drum_level_m", args.trip_time)
    b_pressure = baseline(rows, "hp_drum_pressure_pa", args.trip_time)
    b_steam = baseline(rows, "hp_steam_flow_kg_s", args.trip_time)
    b_power = baseline(rows, "stg_power_w", args.trip_time)
    b_valve = baseline(rows, "hp_feedwater_valve_pu", args.trip_time)

    events: list[Event] = [
        Event(trip_ms + 15, "ECMS", "50BFP-HP.PICKUP", "0", "1", "PICKUP", "HP feedwater-pump motor protection pickup", "E_ELECTRICAL_MODEL"),
        Event(trip_ms + 60, "ECMS", "52BFP-HP.CLOSED", "1", "0", "POSITION", "HP feedwater-pump breaker opened", "E_ELECTRICAL_MODEL"),
        Event(trip_ms + 80, "ECMS", "BFP-HP.MOTOR.CURRENT_A", "RUNNING", "0", "STATE", "HP feedwater-pump motor current lost", "E_ELECTRICAL_MODEL"),
    ]

    speed_low = b_speed * 0.90
    flow_low = abs(b_flow) * 0.80
    flow_low_low = abs(b_flow) * 0.50
    level_low = b_level - 0.03
    level_low_low = b_level - 0.08
    valve_high = min(1.0, b_valve + 0.05)
    pressure_low = b_pressure * 0.98
    steam_low = abs(b_steam) * 0.95
    power_low = abs(b_power) * 0.98

    add_crossing(events, rows, args.trip_time, system="DCS1", field="bfp_hp_speed_rpm", tag="BFP-HP.SPEED_LOW", threshold=speed_low, predicate=lambda x: x < speed_low, event_class="ALARM", description="HP BFP speed below 90% of pre-incident baseline")
    add_crossing(events, rows, args.trip_time, system="DCS1", field="bfp_hp_mass_flow_kg_s", tag="HP.FW.FLOW_LOW", threshold=flow_low, predicate=lambda x: abs(x) < flow_low, event_class="ALARM", description="HP feedwater flow low")
    add_crossing(events, rows, args.trip_time, system="DCS1", field="bfp_hp_mass_flow_kg_s", tag="HP.FW.FLOW_LOW_LOW", threshold=flow_low_low, predicate=lambda x: abs(x) < flow_low_low, event_class="TRIP", description="HP feedwater flow low-low")
    add_crossing(events, rows, args.trip_time, system="DCS1", field="hp_feedwater_valve_pu", tag="HP.FWV.DEMAND_HIGH", threshold=valve_high, predicate=lambda x: x > valve_high, event_class="ALARM", description="HP drum level controller increased feedwater-valve demand")
    add_crossing(events, rows, args.trip_time, system="DCS1", field="hp_drum_level_m", tag="HP.DRUM.LEVEL_LOW", threshold=level_low, predicate=lambda x: x < level_low, event_class="ALARM", description="HP drum level low")
    add_crossing(events, rows, args.trip_time, system="DCS1", field="hp_drum_level_m", tag="HP.DRUM.LEVEL_LOW_LOW", threshold=level_low_low, predicate=lambda x: x < level_low_low, event_class="TRIP", description="HP drum level low-low")
    add_crossing(events, rows, args.trip_time, system="DCS2", field="hp_drum_pressure_pa", tag="HP.DRUM.PRESSURE_LOW", threshold=pressure_low, predicate=lambda x: x < pressure_low, event_class="ALARM", description="HP drum pressure low")
    add_crossing(events, rows, args.trip_time, system="DCS2", field="hp_steam_flow_kg_s", tag="HP.STEAM.FLOW_LOW", threshold=steam_low, predicate=lambda x: abs(x) < steam_low, event_class="ALARM", description="HP steam flow low")
    add_crossing(events, rows, args.trip_time, system="DCS2", field="stg_power_w", tag="STG.ACTIVE_POWER_LOW", threshold=power_low, predicate=lambda x: abs(x) < power_low, event_class="ALARM", description="Steam-turbine generator active power low")

    blind = args.output_dir / "blind-input"
    write_events(blind / "DCS1.csv", [event for event in events if event.system == "DCS1"])
    write_events(blind / "DCS2.csv", [event for event in events if event.system == "DCS2"])
    write_events(blind / "ECMS.csv", [event for event in events if event.system == "ECMS"])
    write_trend(args.output_dir / "engineering" / "trend.csv", rows)

    thresholds = {
        "basis": "PROVISIONAL_RELATIVE_TO_LAST_10S_PRE_INCIDENT",
        "bfp_speed_low_rpm": speed_low,
        "hp_feedwater_flow_low_kg_s": flow_low,
        "hp_feedwater_flow_low_low_kg_s": flow_low_low,
        "hp_drum_level_low_m": level_low,
        "hp_drum_level_low_low_m": level_low_low,
        "hp_feedwater_valve_demand_high_pu": valve_high,
        "hp_drum_pressure_low_pa": pressure_low,
        "hp_steam_flow_low_kg_s": steam_low,
        "stg_power_low_w": power_low,
    }
    truth = args.output_dir / "ground-truth"
    truth.mkdir(parents=True, exist_ok=True)
    (truth / "answer-key.json").write_text(json.dumps({
        "warning": "Do not upload this directory to TripLens during the blind test.",
        "incident_id": "BLIND-INCIDENT-001",
        "expected_root_cause": "HP boiler feed pump electrical trip",
        "physical_adapter": {
            "thermosyspro_component": "PompeAlimHP",
            "normal_speed_rpm": b_speed,
            "hydraulic_residual_speed_rpm": args.final_rpm,
            "note": "Residual RPM is a numerical hydraulic floor; ECMS breaker state is open.",
        },
        "trip_time_s": args.trip_time,
        "stop_time_s": args.stop_time,
        "source_clock_offsets_ms": CLOCK_OFFSET_MS,
        "alarm_thresholds": thresholds,
        "expected_causal_order": [
            event.tag for event in sorted(
                events, key=lambda item: (item.source_time_ms, item.system, item.tag)
            )
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "run-metadata.json").write_text(json.dumps({
        "schema_version": "1.0",
        "incident_id": "BLIND-INCIDENT-001",
        "physics_engine": "ThermoSysPro/OpenModelica",
        "trip_time_s": args.trip_time,
        "stop_time_s": args.stop_time,
        "event_counts": {system: sum(event.system == system for event in events) for system in CLOCK_OFFSET_MS},
        "blind_upload_directory": "blind-input",
        "blind_upload_files": ["DCS1.csv", "DCS2.csv", "ECMS.csv"],
        "answer_key_directory": "ground-truth",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
