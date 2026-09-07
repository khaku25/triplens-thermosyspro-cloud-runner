#!/usr/bin/env python3
"""Normalize the BFP physics run without inserting a GT-trip command."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


SIGNALS: dict[str, tuple[bool, tuple[str, ...]]] = {
    "time_s": (True, ("time", "Time")),
    "bfp_hp_speed_rpm": (True, ("PompeAlimHP.Vr", "arretPomesHP.y.signal")),
    "bfp_hp_mass_flow_kg_s": (True, ("CapteurDebitEauHP.Q", "PompeAlimHP.Q")),
    "bfp_hp_mechanical_power_w": (False, ("PompeAlimHP.Wm",)),
    "hp_drum_level_m": (True, ("BallonHP.yLevel.signal", "BallonHP.zl")),
    "ip_drum_level_m": (False, ("BallonMP.yLevel.signal", "BallonMP.zl")),
    "lp_drum_level_m": (False, ("BallonBP.yLevel.signal", "BallonBP.zl")),
    "hp_drum_pressure_pa": (True, ("BallonHP.P",)),
    "ip_drum_pressure_pa": (False, ("BallonMP.P",)),
    "lp_drum_pressure_pa": (False, ("BallonBP.P",)),
    "hp_steam_flow_kg_s": (True, ("TurbineHP.Q",)),
    "ip_steam_flow_kg_s": (False, ("TurbineMP.Q",)),
    "lp_steam_flow_kg_s": (False, ("TurbineBP.Q",)),
    "hp_feedwater_valve_pu": (True, ("vanne_alimentationHP.Ouv.signal",)),
    "ip_feedwater_valve_pu": (False, ("vanne_alimentationMP.Ouv.signal",)),
    "stg_power_w": (True, ("Alternateur.Welec",)),
    "gt_exhaust_mass_flow_kg_s": (True, ("Debit.y.signal",)),
    "gt_exhaust_temperature_k": (True, ("Temperature.y.signal",)),
}


def canonical(value: str) -> str:
    return value.lstrip("\ufeff").strip().strip('"')


def resolve(headers: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {canonical(header): header for header in headers}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    for alias in aliases:
        matches = [raw for name, raw in normalized.items() if name.endswith("." + alias)]
        if len(matches) == 1:
            return matches[0]
    return None


def number(value: str, field: str, row_number: int) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"row {row_number}: {field} is not numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"row {row_number}: {field} is not finite")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--incident-id", default="BLIND-INCIDENT-001")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = list(reader.fieldnames or [])
        source_rows = list(reader)
    if len(source_rows) < 2:
        raise ValueError("raw result must contain at least two rows")

    resolved = {name: resolve(headers, aliases) for name, (_, aliases) in SIGNALS.items()}
    missing = [name for name, (required, _) in SIGNALS.items() if required and resolved[name] is None]
    if missing:
        raise ValueError("required BFP signals were not found: " + ", ".join(missing))

    fields = ["incident_id", *SIGNALS]
    rows: list[dict[str, str]] = []
    previous_time: float | None = None
    duplicates = 0
    for row_number, source in enumerate(source_rows, start=2):
        time_column = resolved["time_s"]
        assert time_column is not None
        time_s = number(source[time_column], "time_s", row_number)
        if previous_time is not None and time_s < previous_time:
            raise ValueError(f"row {row_number}: time decreases")
        target = {"incident_id": args.incident_id, "time_s": f"{time_s:.9f}"}
        for name in SIGNALS:
            if name == "time_s":
                continue
            column = resolved[name]
            target[name] = "" if column is None else f"{number(source[column], name, row_number):.12g}"
        if previous_time is not None and time_s == previous_time:
            rows[-1] = target
            duplicates += 1
        else:
            rows.append(target)
        previous_time = time_s

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    args.review.parent.mkdir(parents=True, exist_ok=True)
    args.review.write_text(json.dumps({
        "schema_version": "1.0",
        "incident_id": args.incident_id,
        "source_file": args.input.name,
        "resolved": resolved,
        "missing_optional": [name for name, source in resolved.items() if source is None],
        "duplicate_time_rows_collapsed": duplicates,
        "duplicate_time_policy": "keep_last_event_state",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
