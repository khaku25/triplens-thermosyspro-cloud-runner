#!/usr/bin/env python3
"""Convert immutable RAW observations into the four TripLens input layers.

This is the reference implementation for the future web converter.  It does
not inject a scenario/root-cause label and never rewrites the source CSV.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def time_bounds(path: Path) -> tuple[float, float]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) < 2 or "time_s" not in rows[0]:
        raise ValueError("normalized ProcessBus must contain at least two time_s rows")
    return float(rows[0]["time_s"]), float(rows[-1]["time_s"])


def run_script(name: str, *arguments: str) -> None:
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / name), *arguments],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{name} failed: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--event-time", type=float, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scenario-id", default="UNSPECIFIED_OBSERVED_EVENT")
    parser.add_argument("--rules", type=Path, default=PROJECT_ROOT / "config/dcs_alarm_rules.csv")
    parser.add_argument("--commands", type=Path)
    parser.add_argument("--logic-period-ms", type=int, default=1)
    args = parser.parse_args()

    source_hash = sha256(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    processbus = args.output_dir / "ProcessBus.csv"
    review = args.output_dir / "signal-mapping-review.json"
    dcs1 = args.output_dir / "DCS1.csv"
    dcs2 = args.output_dir / "DCS2.csv"
    ecms = args.output_dir / "ECMS.csv"
    trend = args.output_dir / "ECMS-trend.csv"
    feeders = args.output_dir / "ECMS-feeders.csv"

    run_script(
        "normalize_processbus.py",
        "--input", str(args.input),
        "--output", str(processbus),
        "--mapping-review", str(review),
        "--event-time", str(args.event_time),
        "--scenario-id", args.scenario_id,
        "--no-legacy-gt-trip-cmd",
    )
    start_s, stop_s = time_bounds(processbus)
    if not start_s <= args.event_time <= stop_s:
        raise ValueError("event time is outside the normalized ProcessBus horizon")

    run_script(
        "generate_dcs_alarms.py",
        "--incident-raw", str(processbus),
        "--metadata", str(review),
        "--rules", str(args.rules),
        "--trip-time", str(args.event_time),
        "--logic-period-ms", str(args.logic_period_ms),
        "--dcs1-output", str(dcs1),
        "--dcs2-output", str(dcs2),
    )

    ecms_arguments = [
        "--processbus", str(processbus),
        "--event-time", str(args.event_time),
        "--no-scenario-gt-trip",
        "--dcs-events", str(dcs1),
        "--dcs-events", str(dcs2),
        "--sampling-profile", "incident_1ms",
        "--incident-period-ms", "1",
        "--incident-pre-ms", str(round((args.event_time - start_s) * 1000)),
        "--incident-post-ms", str(round((stop_s - args.event_time) * 1000)),
        "--trend-output", str(trend),
        "--event-output", str(ecms),
        "--feeder-output", str(feeders),
    ]
    if args.commands:
        ecms_arguments.extend(["--commands", str(args.commands)])
    run_script("generate_ecms.py", *ecms_arguments)

    if sha256(args.input) != source_hash:
        raise RuntimeError("source RAW changed during conversion")
    outputs = [processbus, dcs1, dcs2, ecms, trend, feeders, review]
    manifest = {
        "schema_version": "1.0",
        "source_file": args.input.name,
        "source_sha256": source_hash,
        "raw_mutated": False,
        "reference_event_time_s": args.event_time,
        "observation_id": args.scenario_id,
        "scenario_id_column_injected": True,
        "root_cause_or_alarm_label_injected": False,
        "logic_period_ms": args.logic_period_ms,
        "physics_to_logic_policy": "ZERO_ORDER_HOLD",
        "outputs": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in outputs
        },
    }
    (args.output_dir / "conversion-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "PASS: RAW converted to ProcessBus.csv, DCS1.csv, DCS2.csv, and ECMS.csv "
        "without modifying the source"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
