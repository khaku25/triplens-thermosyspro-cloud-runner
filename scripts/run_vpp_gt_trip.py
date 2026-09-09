#!/usr/bin/env python3
"""Generate and replay the locked VPP GT_TRIP_01 scenario in one command."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run GT_TRIP_01 through the VPP Baseline v1.0 alarm/event stack."
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=PROJECT_ROOT / "config/vpp_baseline_v1.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pre-seconds", type=float, default=1.0)
    parser.add_argument("--post-seconds", type=float, default=4.0)
    parser.add_argument("--step-ms", type=int, default=1)
    args = parser.parse_args()

    if not args.baseline.is_file():
        raise ValueError("VPP baseline file does not exist")
    if args.step_ms <= 0:
        raise ValueError("--step-ms must be positive")
    if any(
        not math.isfinite(value) or value <= 0
        for value in (args.pre_seconds, args.post_seconds)
    ):
        raise ValueError("pre/post seconds must be positive and finite")

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    if baseline.get("baseline_id") != "VPP_BASELINE_V1":
        raise ValueError("only the registered VPP_BASELINE_V1 is supported")
    authority = baseline.get("authority", {})
    if authority.get("vpp_design_status") != "LOCKED":
        raise ValueError("VPP baseline must be LOCKED before scenario execution")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw = args.output_dir / "VPP.RAW.csv"
    oracle = args.output_dir / "GT_TRIP_01.expected.json"
    raw_manifest = args.output_dir / "GT_TRIP_01.raw-manifest.json"
    event_time_s = args.pre_seconds

    run_script(
        "generate_gt_trip_scenario.py",
        "--baseline", str(args.baseline),
        "--raw-output", str(raw),
        "--oracle-output", str(oracle),
        "--manifest-output", str(raw_manifest),
        "--pre-seconds", str(args.pre_seconds),
        "--post-seconds", str(args.post_seconds),
        "--step-ms", str(args.step_ms),
        "--case-id", "GT_TRIP_01",
    )
    raw_hash = sha256(raw)

    run_script(
        "vpp_alarm_engine.py",
        "--raw", str(raw),
        "--event-time", str(event_time_s),
        "--output-dir", str(args.output_dir),
        "--baseline", str(args.baseline),
        "--ecms-sampling-profile", "incident_1ms" if args.step_ms == 1 else "standard",
    )
    if sha256(raw) != raw_hash:
        raise RuntimeError("VPP RAW changed while deriving alarm/event outputs")

    # Stable presentation aliases requested by the VPP/TripLens ingestion
    # boundary.  They are exact copies, not a second alarm calculation.
    ecms_event = args.output_dir / "ECMS_EVENT.csv"
    vpp_event = args.output_dir / "VPP_EVENT.csv"
    shutil.copyfile(args.output_dir / "ECMS.csv", ecms_event)
    shutil.copyfile(args.output_dir / "VPP.EVENT.csv", vpp_event)

    event_manifest_path = args.output_dir / "VPP.MANIFEST.json"
    event_manifest = json.loads(event_manifest_path.read_text(encoding="utf-8"))
    event_manifest["presentation_exports"] = {
        "ECMS_EVENT.csv": {
            "source": "ECMS.csv",
            "copy_policy": "BYTE_IDENTICAL_ALIAS",
            "content_policy": "SPARSE_ECMS_ALARM_AND_EVENT_RECORDS_ONLY",
        },
        "VPP_EVENT.csv": {
            "source": "VPP.EVENT.csv",
            "copy_policy": "BYTE_IDENTICAL_ALIAS",
            "content_policy": "SPARSE_TIME_ORDERED_DCS1_DCS2_ECMS_ALARM_AND_EVENT_RECORDS_ONLY",
        },
    }
    for alias in (ecms_event, vpp_event):
        event_manifest["products"][alias.name] = {
            "bytes": alias.stat().st_size,
            "sha256": sha256(alias),
        }
    event_manifest_path.write_text(
        json.dumps(event_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    required = [
        raw,
        args.output_dir / "ProcessBus.csv",
        args.output_dir / "VPP.EVENT.csv",
        args.output_dir / "DCS1.csv",
        args.output_dir / "DCS2.csv",
        args.output_dir / "ECMS.csv",
        ecms_event,
        vpp_event,
        args.output_dir / "VPP.MANIFEST.json",
        raw_manifest,
        oracle,
    ]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("VPP run is incomplete: " + ", ".join(missing))

    event_manifest = json.loads(event_manifest_path.read_text(encoding="utf-8"))
    oracle_document = json.loads(oracle.read_text(encoding="utf-8"))
    if oracle_document["raw_sha256"] != raw_hash:
        raise RuntimeError("GT oracle does not identify the generated RAW")
    if event_manifest["source_sha256"] != raw_hash:
        raise RuntimeError("alarm manifest does not identify the generated RAW")
    if ecms_event.read_bytes() != (args.output_dir / "ECMS.csv").read_bytes():
        raise RuntimeError("ECMS_EVENT.csv is not an exact ECMS event export")
    if vpp_event.read_bytes() != (args.output_dir / "VPP.EVENT.csv").read_bytes():
        raise RuntimeError("VPP_EVENT.csv is not an exact unified VPP event export")

    print(
        "PASS: VPP_BASELINE_V1 GT_TRIP_01 generated and replayed; "
        f"events={event_manifest['event_count']} raw_sha256={raw_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
