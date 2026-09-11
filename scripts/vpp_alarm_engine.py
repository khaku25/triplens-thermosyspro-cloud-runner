#!/usr/bin/env python3
"""Run the VPP alarm/event layer without embedding a blind-answer label.

The engine accepts either native simulator RAW or an already normalized
ProcessBus CSV.  Existing normalization, DCS alarm and ECMS state/protection
engines remain the authorities for their respective layers.  This module only
orchestrates them and publishes a lossless, ownership-preserving VPP.EVENT view.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VPP_EVENT_FIELDS = [
    "event_sequence",
    "event_time_ms",
    "source_time_ms",
    "time_s",
    "relative_to_event_s",
    "phase",
    "source_system",
    "source_file",
    "tag",
    "canonical_tag",
    "event_state",
    "event_class",
    "severity",
    "source_signal",
    "old_value",
    "new_value",
    "value",
    "threshold",
    "unit",
    "quality",
    "provenance",
    "rule_status",
    "description",
]
SYSTEM_ORDER = {"DCS1": 0, "DCS2": 1, "ECMS": 2}
EVENT_TAG_ALIASES = {
    "GT.TRIP.CMD": "CMD.GTG.TRIP",
    "ST.TRIP.CMD": "CMD.STG.TRIP",
}


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


def load_baseline(path: Path) -> dict[str, object]:
    baseline = json.loads(path.read_text(encoding="utf-8"))
    if baseline.get("baseline_id") != "VPP_BASELINE_V1":
        raise ValueError("baseline must identify VPP_BASELINE_V1")
    authority = baseline.get("authority")
    if not isinstance(authority, dict) or authority.get("vpp_design_status") != "LOCKED":
        raise ValueError("VPP baseline design status must be LOCKED")
    alarm = baseline.get("alarms") or baseline.get("alarm_engine")
    if not isinstance(alarm, dict):
        raise ValueError("VPP baseline is missing alarms")
    return baseline


def baseline_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"VPP baseline is missing {label}")
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def validate_baseline_rules(path: Path, alarm: dict[str, object]) -> None:
    fields, rows = read_csv(path)
    if "rule_id" not in fields:
        raise ValueError("baseline alarm catalog has no rule_id")
    ids = [row["rule_id"].strip() for row in rows]
    expected_count = int(alarm.get("rule_count", len(ids)))
    if len(ids) != expected_count:
        raise ValueError(
            f"baseline expects {expected_count} alarm rules but catalog contains {len(ids)}"
        )
    required = alarm.get("required_rule_ids", [])
    if not isinstance(required, list) or not all(isinstance(value, str) for value in required):
        raise ValueError("baseline required_rule_ids must be a string list")
    missing = set(required).difference(ids)
    if missing:
        raise ValueError("baseline alarm catalog is missing: " + ", ".join(sorted(missing)))


def detect_input_kind(path: Path) -> str:
    fields, _rows = read_csv(path)
    canonical_indicators = {
        "gt_trip_cmd", "st_trip_cmd", "stg_power_w", "hp_drum_level_m",
        "fwp_hp_trip", "ecms_bus_a_voltage_kv",
    }
    return "processbus" if "time_s" in fields and canonical_indicators.intersection(fields) else "raw"


def run_script(name: str, *arguments: str) -> None:
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / name), *arguments],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{name} failed: {detail}")


def validate_processbus(path: Path, reference_event_time_s: float) -> tuple[float, float]:
    fields, rows = read_csv(path)
    if "time_s" not in fields or len(rows) < 2:
        raise ValueError("ProcessBus must contain at least two time_s rows")
    times = [float(row["time_s"]) for row in rows]
    if any(not math.isfinite(value) for value in times):
        raise ValueError("ProcessBus time_s must be finite")
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("ProcessBus time_s must be strictly increasing")
    if not times[0] <= reference_event_time_s <= times[-1]:
        raise ValueError("reference event time is outside the ProcessBus horizon")
    return times[0], times[-1]


def event_phase(time_s: float, reference_s: float) -> str:
    if time_s < reference_s - 1e-9:
        return "PRE_EVENT"
    if math.isclose(time_s, reference_s, abs_tol=1e-9):
        return "AT_EVENT"
    return "POST_EVENT"


def normalize_dcs_event(
    row: dict[str, str], source_file: str, reference_s: float
) -> dict[str, str]:
    system = row.get("system", "").strip().upper()
    if system != source_file.removesuffix(".csv").upper():
        raise ValueError(f"{source_file} contains an event owned by {system or 'UNKNOWN'}")
    source_ms = int(row["source_time_ms"])
    time_s = source_ms / 1000.0
    return {
        "event_time_ms": row["event_time_ms"],
        "source_time_ms": str(source_ms),
        "time_s": f"{time_s:.9f}",
        "relative_to_event_s": f"{time_s - reference_s:.9f}",
        "phase": event_phase(time_s, reference_s),
        "source_system": system,
        "source_file": source_file,
        "tag": row.get("tag", ""),
        "canonical_tag": EVENT_TAG_ALIASES.get(row.get("tag", ""), row.get("tag", "")),
        "event_state": row.get("alarm_state", ""),
        "event_class": row.get("event_class", ""),
        "severity": row.get("severity", ""),
        "source_signal": row.get("source_signal", ""),
        "old_value": "",
        "new_value": "",
        "value": row.get("value", ""),
        "threshold": row.get("threshold", ""),
        "unit": row.get("unit", ""),
        "quality": row.get("quality", ""),
        "provenance": row.get("provenance", ""),
        "rule_status": row.get("rule_status", ""),
        "description": row.get("description", ""),
    }


def normalize_ecms_event(row: dict[str, str], reference_s: float) -> dict[str, str]:
    system = row.get("system", "").strip().upper()
    if system != "ECMS":
        raise ValueError(f"ECMS.csv contains an event owned by {system or 'UNKNOWN'}")
    source_ms = int(row["source_time_ms"])
    time_s = source_ms / 1000.0
    return {
        "event_time_ms": row["event_time_ms"],
        "source_time_ms": str(source_ms),
        "time_s": f"{time_s:.9f}",
        "relative_to_event_s": f"{time_s - reference_s:.9f}",
        "phase": event_phase(time_s, reference_s),
        "source_system": system,
        "source_file": "ECMS.csv",
        "tag": row.get("tag", ""),
        "canonical_tag": row.get("canonical_tag", "") or row.get("tag", ""),
        "event_state": row.get("new_value", ""),
        "event_class": row.get("event_class", ""),
        "severity": "",
        "source_signal": "",
        "old_value": row.get("old_value", ""),
        "new_value": row.get("new_value", ""),
        "value": "",
        "threshold": "",
        "unit": "",
        "quality": row.get("quality", ""),
        "provenance": row.get("provenance", ""),
        "rule_status": "",
        "description": row.get("description", ""),
    }


def write_vpp_events(
    output: Path, dcs1: Path, dcs2: Path, ecms: Path, reference_s: float
) -> tuple[int, int]:
    events: list[dict[str, str]] = []
    for path in (dcs1, dcs2):
        _fields, rows = read_csv(path)
        events.extend(normalize_dcs_event(row, path.name, reference_s) for row in rows)
    _fields, rows = read_csv(ecms)
    events.extend(normalize_ecms_event(row, reference_s) for row in rows)

    # Only exact duplicate source edges are collapsed.  Parallel DCS/ECMS
    # observations are retained because ownership is part of their identity.
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for row in events:
        key = (
            row["source_time_ms"],
            row["source_system"],
            row["canonical_tag"],
            row["event_state"],
            row["event_class"],
            row["old_value"],
            row["new_value"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)
    duplicate_count = len(events) - len(unique)
    unique.sort(
        key=lambda row: (
            int(row["source_time_ms"]),
            SYSTEM_ORDER[row["source_system"]],
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=VPP_EVENT_FIELDS)
        writer.writeheader()
        for sequence, row in enumerate(unique, start=1):
            writer.writerow({"event_sequence": sequence, **row})
    return len(unique), duplicate_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate VPP.EVENT, DCS1, DCS2 and ECMS from simulator output."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw", type=Path, help="VPP simulator RAW/ProcessBus output")
    source.add_argument("--input", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--input-kind", choices=("auto", "raw", "processbus"), default="auto")
    parser.add_argument("--event-time", type=float, required=True)
    parser.add_argument("--reference-event-time", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=PROJECT_ROOT / "config/vpp_baseline_v1.json")
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--a-settings", type=Path)
    parser.add_argument("--a-equipment", type=Path)
    parser.add_argument("--observed-gt-trip-source")
    parser.add_argument("--commands", type=Path)
    parser.add_argument("--fault-preset", default="none")
    parser.add_argument("--logic-period-ms", type=int)
    parser.add_argument(
        "--ecms-sampling-profile",
        choices=("standard", "causal_100ms", "incident_1ms"),
        default="standard",
    )
    args = parser.parse_args()
    args.input = args.raw or args.input
    if args.reference_event_time is not None and not math.isclose(
        args.event_time, args.reference_event_time, abs_tol=1e-12
    ):
        raise ValueError("--event-time and --reference-event-time disagree")
    args.reference_event_time = args.event_time
    if not args.input.is_file():
        raise ValueError("input CSV does not exist")
    if not math.isfinite(args.reference_event_time):
        raise ValueError("reference event time must be finite")
    baseline = load_baseline(args.baseline)
    alarm_baseline = baseline.get("alarms") or baseline.get("alarm_engine")
    assert isinstance(alarm_baseline, dict)
    logic_period_ms = (
        args.logic_period_ms
        if args.logic_period_ms is not None
        else int(alarm_baseline["evaluation_period_ms"])
    )
    if logic_period_ms <= 0:
        raise ValueError("logic period must be greater than zero")
    rules = args.rules or baseline_path(alarm_baseline.get("rule_catalog"), "alarm rule_catalog")
    validate_baseline_rules(rules, alarm_baseline)
    input_kind = detect_input_kind(args.input) if args.input_kind == "auto" else args.input_kind
    source_configs = baseline.get("source_configs", {})
    if not isinstance(source_configs, dict):
        raise ValueError("VPP baseline source_configs must be an object")

    source_hash = sha256(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    vpp_raw = args.output_dir / "VPP.RAW.csv"
    processbus = args.output_dir / "ProcessBus.csv"
    metadata = args.output_dir / "signal-mapping-review.json"
    dcs1 = args.output_dir / "DCS1.csv"
    dcs2 = args.output_dir / "DCS2.csv"
    ecms = args.output_dir / "ECMS.csv"
    vpp_event = args.output_dir / "VPP.EVENT.csv"
    trend = args.output_dir / "ECMS-trend.csv"
    feeders = args.output_dir / "ECMS-feeders.csv"

    if args.input.resolve() != vpp_raw.resolve():
        shutil.copyfile(args.input, vpp_raw)
    if input_kind == "raw":
        run_script(
            "normalize_processbus.py",
            "--input", str(args.input),
            "--output", str(processbus),
            "--mapping-review", str(metadata),
            "--event-time", str(args.reference_event_time),
            "--scenario-id", "",
            "--no-legacy-gt-trip-cmd",
            *(
                ["--observed-gt-trip-source", args.observed_gt_trip_source]
                if args.observed_gt_trip_source else []
            ),
        )
    else:
        if args.input.resolve() != processbus.resolve():
            shutil.copyfile(args.input, processbus)
        fields, _rows = read_csv(processbus)
        metadata.write_text(json.dumps({
            "schema_version": "1.0",
            "processbus_contract_version": "2.0",
            "input_file": args.input.name,
            "reference_event_time_s": args.reference_event_time,
            "input_kind": "processbus",
            "source_fields": fields,
            "root_cause_inferred": False,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    start_s, stop_s = validate_processbus(processbus, args.reference_event_time)
    run_script(
        "generate_dcs_alarms.py",
        "--incident-raw", str(processbus),
        "--metadata", str(metadata),
        "--rules", str(rules),
        "--trip-time", str(args.reference_event_time),
        "--logic-period-ms", str(logic_period_ms),
        "--dcs1-output", str(dcs1),
        "--dcs2-output", str(dcs2),
    )
    a_settings = args.a_settings or baseline_path(
        source_configs.get("ratings_and_protection", "config/ecms_a_settings.csv"),
        "ratings_and_protection",
    )
    a_equipment = args.a_equipment or baseline_path(
        source_configs.get("fwp_equipment", "config/ecms_a_equipment.csv"),
        "fwp_equipment",
    )
    if not a_settings.is_file():
        raise ValueError("A settings file does not exist")
    if not a_equipment.is_file():
        raise ValueError("A equipment file does not exist")
    ecms_args = [
        "--processbus", str(processbus),
        "--a-settings", str(a_settings),
        "--a-equipment", str(a_equipment),
        "--common-trip-matrix", str(baseline_path(
            source_configs.get("trip_coupling", "config/common_trip_matrix.csv"),
            "trip_coupling",
        )),
        "--event-time", str(args.reference_event_time),
        "--no-scenario-gt-trip",
        "--dcs-events", str(dcs1),
        "--dcs-events", str(dcs2),
        "--fault-preset", args.fault_preset,
        "--sampling-profile", args.ecms_sampling_profile,
        "--trend-output", str(trend),
        "--event-output", str(ecms),
        "--feeder-output", str(feeders),
    ]
    if args.commands:
        ecms_args.extend(["--commands", str(args.commands)])
    run_script("generate_ecms.py", *ecms_args)

    event_count, duplicate_count = write_vpp_events(
        vpp_event, dcs1, dcs2, ecms, args.reference_event_time
    )
    if sha256(args.input) != source_hash:
        raise RuntimeError("source simulator output changed during alarm generation")

    products = [vpp_raw, processbus, vpp_event, dcs1, dcs2, ecms, trend, feeders, metadata]
    counts = {}
    for path in (vpp_event, dcs1, dcs2, ecms):
        _fields, rows = read_csv(path)
        counts[path.name] = len(rows)
    manifest = {
        "schema_version": "1.0",
        "engine": "VPP_ALARM_ENGINE",
        "source_file": args.input.name,
        "source_sha256": source_hash,
        "source_mutated": False,
        "input_kind": input_kind,
        "reference_event_time_s": args.reference_event_time,
        "time_horizon_s": {"start": start_s, "stop": stop_s},
        "root_cause_label_injected": False,
        "physics_to_logic_policy": "ZERO_ORDER_HOLD",
        "logic_period_ms": logic_period_ms,
        "unit_contract": baseline.get("unit_contract", {}),
        "baseline": {
            "id": baseline["baseline_id"],
            "version": baseline.get("version", ""),
            "status": baseline.get("status", ""),
            "design_status": baseline.get("authority", {}).get("vpp_design_status", ""),
            "plant_approval_status": baseline.get("authority", {}).get(
                "plant_approval_status", ""
            ),
            "file": args.baseline.name,
            "sha256": sha256(args.baseline),
        },
        "a_configuration": {
            "settings_file": a_settings.name,
            "settings_sha256": sha256(a_settings),
            "equipment_file": a_equipment.name,
            "equipment_sha256": sha256(a_equipment),
            "source": "EXPLICIT_CLOUD_INPUT" if args.a_settings or args.a_equipment else "VPP_BASELINE",
        },
        "event_count": event_count,
        "exact_duplicate_edges_removed": duplicate_count,
        "event_counts_by_file": counts,
        "ownership_policy": "DCS1_DCS2_ECMS_PRESERVED_IN_SOURCE_SYSTEM",
        "products": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in products
        },
    }
    (args.output_dir / "VPP.MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"PASS: generated {event_count} VPP events; "
        f"removed {duplicate_count} exact duplicate source edges"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
