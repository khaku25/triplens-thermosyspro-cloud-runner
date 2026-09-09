#!/usr/bin/env python3
"""Validate the monitor-ready VPP RAW + Modelica event bundle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from export_vpp_events import EVENT_FIELDS


ALLOWED_FILES = {
    "VPP_RAW.csv",
    "VPP_EVENT.csv",
    "DCS1_EVENT.csv",
    "DCS2_EVENT.csv",
    "VPP_LOGIC_SNAPSHOT.csv",
    "vpp-event-manifest.json",
}
FORBIDDEN_EVENT_COLUMNS = {
    "scenario",
    "scenario_id",
    "fault",
    "fault_id",
    "root_cause",
    "ground_truth",
    "answer",
    "expected_cause",
}
EXPECTED_COLORS = {
    "TRIP": "#D71920",
    "CRITICAL": "#F97316",
    "WARNING": "#FACC15",
    "OPERATION": "#0067C5",
    "COMMUNICATION": "#7C3AED",
    "STATUS": "#64748B",
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


def validate_event_rows(path: Path) -> list[dict[str, str]]:
    fields, rows = read_csv(path)
    if fields != EVENT_FIELDS:
        raise ValueError(f"{path.name} has the wrong event schema")
    forbidden = sorted(set(fields).intersection(FORBIDDEN_EVENT_COLUMNS))
    if forbidden:
        raise ValueError(f"{path.name} contains answer/scenario columns")
    previous_key: tuple[int, int] | None = None
    for index, row in enumerate(rows, start=1):
        if row["schema_version"] != "1.0":
            raise ValueError(f"{path.name} row {index + 1} schema_version is invalid")
        try:
            sequence = int(row["event_sequence"])
            event_time_ms = int(row["event_time_ms"])
            time_s = float(row["time_s"])
            actual_value = float(row["actual_value"])
            float(row["setpoint"])
            float(row["return_setpoint"])
            float(row["delay_s"])
        except ValueError as exc:
            raise ValueError(f"{path.name} row {index + 1} has invalid numerics") from exc
        if not all(math.isfinite(value) for value in (time_s, actual_value)):
            raise ValueError(f"{path.name} row {index + 1} has non-finite data")
        if sequence <= 0 or event_time_ms < 0:
            raise ValueError(f"{path.name} row {index + 1} has invalid sequence/time")
        key = (event_time_ms, sequence)
        if previous_key is not None and key < previous_key:
            raise ValueError(f"{path.name} is not chronological")
        previous_key = key
        if row["event_id"] != f"VPP-E{sequence:06d}":
            raise ValueError(f"{path.name} row {index + 1} event_id mismatch")
        if row["system"] not in {"DCS1", "DCS2"}:
            raise ValueError(f"{path.name} row {index + 1} system is invalid")
        if row["event_state"] not in {"ACTIVE", "RETURN"}:
            raise ValueError(f"{path.name} row {index + 1} event_state is invalid")
        severity = row["severity"]
        if severity not in EXPECTED_COLORS:
            raise ValueError(f"{path.name} row {index + 1} severity is invalid")
        if row["display_color"].upper() != EXPECTED_COLORS[severity]:
            raise ValueError(f"{path.name} row {index + 1} color contract mismatch")
        if row["decision_owner"] != "MODELICA_VPP_LOGIC_RUNTIME":
            raise ValueError(f"{path.name} row {index + 1} decision owner is invalid")
        if not row["logic_version"] or not row["logic_status"]:
            raise ValueError(f"{path.name} row {index + 1} logic audit fields are empty")
        if not row["state_variable"] or not row["value_variable"]:
            raise ValueError(f"{path.name} row {index + 1} model variables are empty")
    return rows


def verify_metadata(path: Path, metadata: dict[str, object]) -> None:
    expected = {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"manifest mismatch for {path.name} {key}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.output_dir.is_dir():
        parser.error("--output-dir must exist")

    files = {
        path.relative_to(args.output_dir).as_posix(): path
        for path in args.output_dir.rglob("*")
        if path.is_file()
    }
    missing = sorted(ALLOWED_FILES.difference(files))
    unexpected = sorted(set(files).difference(ALLOWED_FILES))
    if missing:
        raise ValueError("VPP event bundle is missing: " + ", ".join(missing))
    if unexpected:
        raise ValueError("VPP event bundle has unexpected files: " + ", ".join(unexpected))

    combined = validate_event_rows(files["VPP_EVENT.csv"])
    dcs1 = validate_event_rows(files["DCS1_EVENT.csv"])
    dcs2 = validate_event_rows(files["DCS2_EVENT.csv"])
    if [row for row in combined if row["system"] == "DCS1"] != dcs1:
        raise ValueError("DCS1_EVENT.csv is not an exact routed view of VPP_EVENT.csv")
    if [row for row in combined if row["system"] == "DCS2"] != dcs2:
        raise ValueError("DCS2_EVENT.csv is not an exact routed view of VPP_EVENT.csv")
    if [int(row["event_sequence"]) for row in combined] != list(
        range(1, len(combined) + 1)
    ):
        raise ValueError("VPP_EVENT.csv event_sequence must be contiguous")

    raw_fields, raw_rows = read_csv(files["VPP_RAW.csv"])
    if "time" not in raw_fields or len(raw_rows) < 2:
        raise ValueError("VPP_RAW.csv must contain native time and at least two rows")
    if any(column in FORBIDDEN_EVENT_COLUMNS for column in raw_fields):
        raise ValueError("VPP_RAW.csv contains answer/scenario metadata")

    manifest = json.loads(files["vpp-event-manifest.json"].read_text(encoding="utf-8"))
    if manifest.get("artifact_type") != "VPP_MODELICA_EVENT_BUNDLE":
        raise ValueError("vpp-event-manifest.json has the wrong artifact_type")
    boundary = manifest.get("boundary", {})
    expected_boundary = {
        "alarm_decision_owner": "MODELICA_VPP_LOGIC_RUNTIME",
        "serializer_role": "BOOLEAN_STATE_TRANSITIONS_ONLY",
        "serializer_recalculates_thresholds": False,
        "monitor_recalculates_thresholds": False,
        "system_routing_embedded": True,
        "scenario_label_included": False,
        "root_cause_label_included": False,
    }
    for key, value in expected_boundary.items():
        if boundary.get(key) != value:
            raise ValueError(f"manifest ownership boundary mismatch for {key}")

    verify_metadata(files["VPP_RAW.csv"], manifest.get("raw", {}))
    event_metadata = manifest.get("events", {})
    for key, filename, rows in (
        ("combined", "VPP_EVENT.csv", combined),
        ("dcs1", "DCS1_EVENT.csv", dcs1),
        ("dcs2", "DCS2_EVENT.csv", dcs2),
    ):
        metadata = event_metadata.get(key, {})
        verify_metadata(files[filename], metadata)
        if metadata.get("row_count") != len(rows):
            raise ValueError(f"manifest row count mismatch for {filename}")
    verify_metadata(
        files["VPP_LOGIC_SNAPSHOT.csv"],
        manifest.get("logic", {}).get("configuration", {}),
    )
    print("VPP_EVENT_BUNDLE_PASS")
    print(f"VPP_EVENT_ROWS={len(combined)}")
    print(f"DCS1_EVENT_ROWS={len(dcs1)}")
    print(f"DCS2_EVENT_ROWS={len(dcs2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
