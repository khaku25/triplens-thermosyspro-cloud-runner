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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
