#!/usr/bin/env python3
"""Build a label-free manifest for an unmodified OpenModelica RAW CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_raw_summary(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            columns = next(reader)
        except StopIteration as exc:
            raise ValueError("RAW CSV is empty") from exc
        if not columns:
            raise ValueError("RAW CSV header is empty")
        normalized = [column.strip().lower() for column in columns]
        if "time" not in normalized:
            raise ValueError("RAW CSV needs the native OpenModelica time column")
        time_index = normalized.index("time")
        row_count = 0
        first_time: float | None = None
        last_time: float | None = None
        previous_time: float | None = None
        duplicate_time_rows = 0
        for row_number, row in enumerate(reader, start=2):
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) != len(columns):
                raise ValueError(
                    f"RAW CSV row {row_number} has {len(row)} cells; expected {len(columns)}"
                )
            try:
                time_value = float(row[time_index])
            except ValueError as exc:
                raise ValueError(
                    f"RAW CSV row {row_number} has a non-numeric time"
                ) from exc
            if not math.isfinite(time_value):
                raise ValueError(f"RAW CSV row {row_number} has a non-finite time")
            if previous_time is not None and time_value < previous_time:
                raise ValueError("RAW CSV native time reverses")
            if previous_time is not None and time_value == previous_time:
                duplicate_time_rows += 1
            if first_time is None:
                first_time = time_value
            last_time = time_value
            previous_time = time_value
            row_count += 1
    if row_count < 2:
        raise ValueError("RAW CSV needs at least two data rows")
    return {
        "columns": columns,
        "row_count": row_count,
        "first_time_s": first_time,
        "last_time_s": last_time,
        "duplicate_native_time_rows": duplicate_time_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--sampling-profile",
        choices=("standard", "causal_100ms", "incident_1ms"),
        required=True,
    )
    parser.add_argument("--stop-time", type=float, required=True)
    parser.add_argument("--output-intervals", type=int, required=True)
    parser.add_argument("--thermosyspro-commit", required=True)
    parser.add_argument("--openmodelica-image", required=True)
    parser.add_argument("--model-variant", default="BASE_GT_EXHAUST_ADAPTER")
    parser.add_argument("--source-patch-marker")
    parser.add_argument("--patched-model-sha256")
    args = parser.parse_args()

    if not args.raw_file.is_file() or args.raw_file.stat().st_size == 0:
        parser.error("--raw-file must be a non-empty CSV")
    if not math.isfinite(args.stop_time) or args.stop_time <= 0:
        parser.error("--stop-time must be positive and finite")
    if args.output_intervals <= 0:
        parser.error("--output-intervals must be positive")
    if bool(args.source_patch_marker) != bool(args.patched_model_sha256):
        parser.error(
            "--source-patch-marker and --patched-model-sha256 must be supplied together"
        )
    if args.patched_model_sha256 and (
        len(args.patched_model_sha256) != 64
        or any(character not in "0123456789abcdef" for character in args.patched_model_sha256)
    ):
        parser.error("--patched-model-sha256 must be a lowercase SHA-256 digest")

    summary = read_raw_summary(args.raw_file)
    nominal_period_ms = args.stop_time * 1000.0 / args.output_intervals
    manifest = {
        "schema_version": "1.0",
        "artifact_type": "THERMOSYSPRO_RAW_ONLY",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "engine": "THERMOSYSPRO_OPENMODELICA",
            "thermosyspro_repository": "Dwarf-Planet-Project/ThermoSysPro",
            "thermosyspro_commit": args.thermosyspro_commit,
            "openmodelica_image": args.openmodelica_image,
            "model_variant": args.model_variant,
            "source_transform": (
                {
                    "marker": args.source_patch_marker,
                    "patched_model_sha256": args.patched_model_sha256,
                }
                if args.source_patch_marker
                else None
            ),
            "manifest_builder_python": platform.python_version(),
        },
        "sampling": {
            "profile": args.sampling_profile,
            "native_csv_output_intervals": args.output_intervals,
            "nominal_csv_period_ms": nominal_period_ms,
            "solver_step_note": "CSV output interval only; DASSL integration remains adaptive.",
        },
        "raw": {
            "file": args.raw_file.name,
            "bytes": args.raw_file.stat().st_size,
            "sha256": sha256(args.raw_file),
            **summary,
            "copy_policy": "BYTE_FOR_BYTE_FROM_OPENMODELICA_RESULT",
            "rows_modified": False,
            "columns_added": False,
            "columns_removed": False,
        },
        "boundary": {
            "action_output": ["MODELICA_RAW_PHYSICS"],
            "not_generated_by_action": [
                "PROCESSBUS",
                "DCS1",
                "DCS2",
                "ECMS",
                "INCIDENT_WINDOW",
                "IMPORTANT_CHANGES",
                "ROOT_CAUSE",
                "GROUND_TRUTH",
            ],
            "downstream_owner": "TRIPLENS_WEB_RAW_CONVERTER",
            "scenario_label_included": False,
            "root_cause_label_included": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
