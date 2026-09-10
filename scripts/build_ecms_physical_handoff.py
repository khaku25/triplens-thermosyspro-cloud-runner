#!/usr/bin/env python3
"""Publish simulator-observed physical values to the ECMS intake boundary.

This is a transport step, not a second simulator.  Values are copied from the
normalized ProcessBus without interpolation, thresholding, fallback values or
ECMS-side dynamics.  The manifest retains the originating OpenModelica column
for every published signal so the handoff can be audited end to end.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


SIGNALS: tuple[tuple[str, str, str], ...] = (
    ("gt_trip_cmd", "BOOL", "DCS1"),
    ("gt_trip_latch", "BOOL", "DCS1"),
    ("st_trip_latch", "BOOL", "DCS1"),
    ("cb_52gt_trip_cmd", "BOOL", "ECMS"),
    ("cb_52gt_closed", "BOOL", "ECMS"),
    ("cb_52st_trip_cmd", "BOOL", "ECMS"),
    ("cb_52st_closed", "BOOL", "ECMS"),
    ("gtg_power_mw", "MW", "DCS1"),
    ("gtg_speed_rpm", "rpm", "DCS1"),
    ("stg_power_w", "W", "DCS1"),
    ("gt_exhaust_mass_flow_t_h", "t/h", "DCS1"),
    ("gt_exhaust_temperature_k", "K", "DCS1"),
    ("hp_drum_level_m", "m", "DCS2"),
    ("ip_drum_level_m", "m", "DCS2"),
    ("lp_drum_level_m", "m", "DCS2"),
    ("hp_drum_pressure_pa", "Pa", "DCS2"),
    ("ip_drum_pressure_pa", "Pa", "DCS2"),
    ("lp_drum_pressure_pa", "Pa", "DCS2"),
    ("hp_steam_flow_t_h", "t/h", "DCS2"),
    ("ip_steam_flow_t_h", "t/h", "DCS2"),
    ("lp_steam_flow_t_h", "t/h", "DCS2"),
    ("hp_admission_valve_pu", "pu", "DCS1"),
    ("ip_admission_valve_pu", "pu", "DCS1"),
    ("lp_admission_multiplier_pu", "pu", "DCS1"),
    ("hp_bypass_valve_pu", "pu", "DCS2"),
    ("lp_bypass_valve_pu", "pu", "DCS2"),
    ("hp_bypass_spray_valve_pu", "pu", "DCS2"),
    ("lp_bypass_spray_valve_pu", "pu", "DCS2"),
    ("hp_bypass_steam_flow_t_h", "t/h", "DCS2"),
    ("lp_bypass_steam_flow_t_h", "t/h", "DCS2"),
    ("hp_bypass_spray_flow_t_h", "t/h", "DCS2"),
    ("lp_bypass_spray_flow_t_h", "t/h", "DCS2"),
    ("hp_feedwater_valve_pu", "pu", "DCS2"),
    ("ip_feedwater_valve_pu", "pu", "DCS2"),
    ("lp_feedwater_valve_pu", "pu", "DCS2"),
    ("condenser_pressure_pa", "Pa", "DCS2"),
    ("condenser_level_m", "m", "DCS2"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--processbus", type=Path, required=True)
    parser.add_argument("--mapping-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--require-signal", action="append", default=[])
    args = parser.parse_args()

    for path in (args.raw, args.processbus, args.mapping_review):
        if not path.is_file():
            raise ValueError(f"required handoff input does not exist: {path}")
    fields, rows = read_csv(args.processbus)
    if "time_s" not in fields or len(rows) < 2:
        raise ValueError("ProcessBus must contain time_s and at least two rows")
    times = [float(row["time_s"]) for row in rows]
    if any(not math.isfinite(value) for value in times):
        raise ValueError("ProcessBus time_s contains a non-finite value")
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("ProcessBus time_s must be strictly increasing")

    review = json.loads(args.mapping_review.read_text(encoding="utf-8"))
    resolved = review.get("resolved", {})
    if not isinstance(resolved, dict):
        raise ValueError("mapping review has no resolved signal map")
    conversions = {
        item.get("processbus_field"): item
        for item in review.get("published_unit_conversions", [])
        if isinstance(item, dict)
    }

    catalog = {name: (unit, owner) for name, unit, owner in SIGNALS}
    unknown_required = sorted(set(args.require_signal).difference(catalog))
    if unknown_required:
        raise ValueError("unknown required physical signal(s): " + ", ".join(unknown_required))

    present: list[str] = []
    for name, _unit, _owner in SIGNALS:
        if name not in fields:
            continue
        if resolved.get(name) is None:
            # Canonical-but-synthetic fields are not a physical handoff.
            continue
        if any((row.get(name) or "").strip() for row in rows):
            present.append(name)
    missing_required = sorted(set(args.require_signal).difference(present))
    if missing_required:
        raise ValueError(
            "required OpenModelica physical signals were not resolved: "
            + ", ".join(missing_required)
        )

    output_fields = [
        "source_time_ms", "time_s", "quality", "transport_status",
        "value_policy", *present,
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=output_fields)
        writer.writeheader()
        for row, time_s in zip(rows, times):
            writer.writerow({
                "source_time_ms": round(time_s * 1000),
                "time_s": row["time_s"],
                "quality": (row.get("quality") or "GOOD").strip().upper(),
                "transport_status": "RECEIVED",
                "value_policy": "EXACT_PROCESSBUS_COPY",
                **{name: row.get(name, "") for name in present},
            })

    signal_manifest = []
    for name in present:
        unit, owner = catalog[name]
        conversion = conversions.get(name, {})
        signal_manifest.append({
            "processbus_field": name,
            "unit": unit,
            "display_owner": owner,
            "raw_source_column": resolved[name],
            "normalization_multiplier": conversion.get("multiplier", 1.0),
            "provenance": "OPENMODELICA_RAW_OBSERVED",
            "handoff_value_policy": "EXACT_PROCESSBUS_STRING_COPY",
        })

    manifest = {
        "schema_version": "1.0",
        "artifact_type": "ECMS_PHYSICAL_INPUT_HANDOFF",
        "transport_mode": "FILE_HANDOFF",
        "communication_status": "PASS",
        "source_time_policy": "PRESERVED",
        "physical_value_policy": "NO_ECMS_RECALCULATION_NO_INTERPOLATION",
        "raw": {
            "file": args.raw.name,
            "sha256": sha256(args.raw),
            "mutated": False,
        },
        "processbus": {
            "file": args.processbus.name,
            "sha256": sha256(args.processbus),
            "row_count": len(rows),
        },
        "handoff": {
            "file": args.output.name,
            "sha256": sha256(args.output),
            "row_count": len(rows),
            "signal_count": len(present),
        },
        "required_signals": args.require_signal,
        "signals": signal_manifest,
    }
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"PASS: transported {len(present)} OpenModelica signals across "
        f"{len(rows)} source-time rows without ECMS recalculation"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

