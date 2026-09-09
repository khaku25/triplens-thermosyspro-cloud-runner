#!/usr/bin/env python3
"""Fail closed unless an Action result contains only RAW physics and its manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


ALLOWED_FILES = {"thermosyspro-raw.csv", "raw-manifest.json"}
FORBIDDEN_ARTIFACT_TOKENS = {
    "processbus",
    "dcs1",
    "dcs2",
    "ecms",
    "incident",
    "important-changes",
    "ground-truth",
    "root-cause",
}
FORBIDDEN_METADATA_COLUMNS = {
    "scenario",
    "scenario_id",
    "scenario_name",
    "scenario_type",
    "fault",
    "fault_id",
    "fault_name",
    "fault_type",
    "root_cause",
    "ground_truth",
    "answer",
    "answer_label",
    "expected_cause",
    "expected_result",
}

DYNAMIC_BYPASS_VARIANT = "HPBP_LPBP_DYNAMIC_V8"
DYNAMIC_BYPASS_COLUMNS = {
    "vppSTTripLatch",
    "vppHPAdmissionPos",
    "vppIPAdmissionPos",
    "vppLPDrumAdmissionMultiplier",
    "vppHPBypassCmd",
    "vppLPBypassCmd",
    "vppHPBypassPos",
    "vppLPBypassPos",
    "vppHPSprayPos",
    "vppLPSprayPos",
    "vppHPBypassOpenLS",
    "vppHPBypassCloseLS",
    "vppLPBypassOpenLS",
    "vppLPBypassCloseLS",
    "vppHPBypassMassFlow",
    "vppLPBypassMassFlow",
    "vppHPSprayMassFlow",
    "vppLPSprayMassFlow",
    "vppHPBypassInletPressure",
    "vppLPBypassInletPressure",
    "vppHPBypassOutletPressure",
    "vppLPBypassOutletPressure",
    "vppHPBypassInletTemperature",
    "vppLPBypassInletTemperature",
    "vppHPBypassOutletTemperature",
    "vppLPBypassOutletTemperature",
    "vppCondenserPressure",
    "vppCondenserLevel",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def parse_boolean(value: str, *, column: str, row_number: int) -> bool:
    key = value.strip().lower()
    if key in {"true", "1", "1.0"}:
        return True
    if key in {"false", "0", "0.0"}:
        return False
    raise ValueError(f"RAW CSV row {row_number} {column} is not Boolean")


def validate_dynamic_bypass(path: Path, nominal_period_ms: float) -> dict[str, float]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        missing = sorted(DYNAMIC_BYPASS_COLUMNS.difference(columns))
        if missing:
            raise ValueError(
                "dynamic bypass RAW is missing columns: " + ", ".join(missing)
            )
        rows = list(reader)

    numeric_columns = DYNAMIC_BYPASS_COLUMNS.difference(
        {
            "vppSTTripLatch",
            "vppHPBypassOpenLS",
            "vppHPBypassCloseLS",
            "vppLPBypassOpenLS",
            "vppLPBypassCloseLS",
        }
    )
    numeric: dict[str, list[float]] = {column: [] for column in numeric_columns}
    times: list[float] = []
    latch: list[bool] = []
    booleans: dict[str, list[bool]] = {
        column: []
        for column in DYNAMIC_BYPASS_COLUMNS
        if column not in numeric_columns
    }
    for row_number, row in enumerate(rows, start=2):
        try:
            current_time = float(row["time"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"RAW CSV row {row_number} has invalid time") from exc
        times.append(current_time)
        for column in numeric_columns:
            try:
                value = float(row[column])
            except ValueError as exc:
                raise ValueError(
                    f"RAW CSV row {row_number} {column} is not numeric"
                ) from exc
            if not math.isfinite(value):
                raise ValueError(
                    f"RAW CSV row {row_number} {column} is not finite"
                )
            numeric[column].append(value)
        for column in booleans:
            booleans[column].append(
                parse_boolean(row[column], column=column, row_number=row_number)
            )
        latch.append(booleans["vppSTTripLatch"][-1])

    try:
        trip_index = latch.index(True)
    except ValueError as exc:
        raise ValueError("dynamic bypass RAW never asserts vppSTTripLatch") from exc
    if trip_index == 0 or any(latch[:trip_index]) or not all(latch[trip_index:]):
        raise ValueError("vppSTTripLatch must make one false-to-true transition")

    final_limits = {
        "vppHPBypassOpenLS": True,
        "vppHPBypassCloseLS": False,
        "vppLPBypassOpenLS": True,
        "vppLPBypassCloseLS": False,
    }
    for column, expected in final_limits.items():
        if booleans[column][-1] is not expected:
            raise ValueError(f"dynamic bypass final state is wrong for {column}")
    for column in ("vppHPBypassPos", "vppLPBypassPos"):
        if numeric[column][-1] < 0.95:
            raise ValueError(f"dynamic bypass did not reach open limit: {column}")
    for column in (
        "vppHPAdmissionPos",
        "vppIPAdmissionPos",
        "vppLPDrumAdmissionMultiplier",
    ):
        if numeric[column][-1] > 0.01:
            raise ValueError(f"Trip isolation did not reach closed state: {column}")
    for column in ("vppHPBypassMassFlow", "vppLPBypassMassFlow"):
        if max(numeric[column][trip_index:]) <= 0:
            raise ValueError(f"no positive physical bypass flow was produced: {column}")
    for column in (
        "vppHPBypassInletPressure",
        "vppLPBypassInletPressure",
        "vppHPBypassOutletPressure",
        "vppLPBypassOutletPressure",
        "vppCondenserPressure",
    ):
        if min(numeric[column]) <= 0:
            raise ValueError(f"non-positive pressure in dynamic bypass RAW: {column}")

    crossings: dict[str, float] = {}
    if nominal_period_ms <= 5.0:
        trip_time = times[trip_index]
        targets = {
            "vppHPAdmissionPos": (lambda value: value <= 0.04, 0.150),
            "vppIPAdmissionPos": (lambda value: value <= 0.04, 0.150),
            "vppLPDrumAdmissionMultiplier": (lambda value: value <= 0.05, 0.150),
            "vppHPBypassPos": (lambda value: value >= 0.95, 0.300),
            "vppLPBypassPos": (lambda value: value >= 0.95, 0.400),
            "vppHPSprayPos": (lambda value: value >= 0.95, 0.050),
            "vppLPSprayPos": (lambda value: value >= 0.95, 0.050),
        }
        tolerance_s = max(0.005, 2*nominal_period_ms/1000)
        for column, (crossed, expected_s) in targets.items():
            crossing_time = next(
                (times[index] for index in range(trip_index, len(times))
                 if crossed(numeric[column][index])),
                None,
            )
            if crossing_time is None:
                raise ValueError(f"dynamic response never crosses target: {column}")
            elapsed = crossing_time - trip_time
            if abs(elapsed - expected_s) > tolerance_s:
                raise ValueError(
                    f"dynamic response timing mismatch for {column}: "
                    f"{elapsed:.6g}s, expected {expected_s:.6g}s"
                )
            crossings[column] = elapsed
    return crossings


def validate_raw_csv(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            columns = next(reader)
        except StopIteration as exc:
            raise ValueError("thermosyspro-raw.csv is empty") from exc
        column_keys = [normalized(column) for column in columns]
        forbidden = sorted(set(column_keys).intersection(FORBIDDEN_METADATA_COLUMNS))
        if forbidden:
            raise ValueError(
                "RAW CSV contains answer/scenario metadata: " + ", ".join(forbidden)
            )
        if "time" not in column_keys:
            raise ValueError("RAW CSV is missing the native time column")
        time_index = column_keys.index("time")
        previous: float | None = None
        row_count = 0
        duplicate_count = 0
        first_time: float | None = None
        last_time: float | None = None
        for row_number, row in enumerate(reader, start=2):
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) != len(columns):
                raise ValueError(
                    f"RAW CSV row {row_number} width does not match the header"
                )
            try:
                current = float(row[time_index])
            except ValueError as exc:
                raise ValueError(
                    f"RAW CSV row {row_number} time is not numeric"
                ) from exc
            if not math.isfinite(current):
                raise ValueError(f"RAW CSV row {row_number} time is not finite")
            if previous is not None and current < previous:
                raise ValueError("RAW CSV native time reverses")
            if previous is not None and current == previous:
                duplicate_count += 1
            if first_time is None:
                first_time = current
            last_time = current
            previous = current
            row_count += 1
    if row_count < 2:
        raise ValueError("RAW CSV needs at least two data rows")
    return {
        "columns": columns,
        "row_count": row_count,
        "duplicate_count": duplicate_count,
        "first_time_s": first_time,
        "last_time_s": last_time,
    }


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
    unexpected = sorted(set(files).difference(ALLOWED_FILES))
    missing = sorted(ALLOWED_FILES.difference(files))
    forbidden_named = sorted(
        relative
        for relative in files
        if any(token in relative.lower() for token in FORBIDDEN_ARTIFACT_TOKENS)
    )
    if missing:
        raise ValueError("RAW-only bundle is missing: " + ", ".join(missing))
    if unexpected:
        raise ValueError(
            "RAW-only bundle contains unexpected files: " + ", ".join(unexpected)
        )
    if forbidden_named:
        raise ValueError(
            "RAW-only bundle contains derived/answer artifacts: "
            + ", ".join(forbidden_named)
        )

    raw_path = files["thermosyspro-raw.csv"]
    manifest_path = files["raw-manifest.json"]
    raw_summary = validate_raw_csv(raw_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("artifact_type") != "THERMOSYSPRO_RAW_ONLY":
        raise ValueError("raw-manifest.json has the wrong artifact_type")
    raw = manifest.get("raw")
    if not isinstance(raw, dict):
        raise ValueError("raw-manifest.json is missing raw metadata")
    expected = {
        "file": raw_path.name,
        "bytes": raw_path.stat().st_size,
        "sha256": sha256(raw_path),
        "row_count": raw_summary["row_count"],
        "columns": raw_summary["columns"],
        "first_time_s": raw_summary["first_time_s"],
        "last_time_s": raw_summary["last_time_s"],
        "duplicate_native_time_rows": raw_summary["duplicate_count"],
        "copy_policy": "BYTE_FOR_BYTE_FROM_OPENMODELICA_RESULT",
        "rows_modified": False,
        "columns_added": False,
        "columns_removed": False,
    }
    for key, value in expected.items():
        if raw.get(key) != value:
            raise ValueError(f"raw-manifest.json mismatch for {key}")
    boundary = manifest.get("boundary")
    if not isinstance(boundary, dict):
        raise ValueError("raw-manifest.json is missing the ownership boundary")
    if boundary.get("action_output") != ["MODELICA_RAW_PHYSICS"]:
        raise ValueError("Action output boundary is not RAW-only")
    if boundary.get("scenario_label_included") is not False:
        raise ValueError("scenario labels must not be included")
    if boundary.get("root_cause_label_included") is not False:
        raise ValueError("root-cause labels must not be included")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("raw-manifest.json is missing runtime metadata")
    if runtime.get("model_variant") == DYNAMIC_BYPASS_VARIANT:
        transform = runtime.get("source_transform")
        if not isinstance(transform, dict):
            raise ValueError("dynamic bypass manifest is missing source-transform proof")
        if transform.get("marker") != "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V8":
            raise ValueError("dynamic bypass manifest has the wrong patch marker")
        digest = transform.get("patched_model_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("dynamic bypass manifest has an invalid patched-model hash")
        sampling = manifest.get("sampling")
        if not isinstance(sampling, dict):
            raise ValueError("dynamic bypass manifest is missing sampling metadata")
        crossings = validate_dynamic_bypass(
            raw_path, float(sampling["nominal_csv_period_ms"])
        )
        print(
            "DYNAMIC_BYPASS_VALIDATION_PASS "
            + json.dumps(crossings, sort_keys=True)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
