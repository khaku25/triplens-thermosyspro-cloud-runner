#!/usr/bin/env python3
"""Validate the VPP internal/public split and canonical EVENT.csv."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .build_vpp_event_bundle import (
        ROOT,
        load_contract,
        read_csv,
        sha256,
        validate_events,
    )
except ImportError:  # Direct CLI execution from scripts/.
    from build_vpp_event_bundle import (
        ROOT,
        load_contract,
        read_csv,
        sha256,
        validate_events,
    )


def validate_bundle(bundle_dir: Path, contract_path: Path) -> dict[str, object]:
    contract = load_contract(contract_path)
    public_dir = bundle_dir / "public"
    internal_dir = bundle_dir / "internal"
    event_paths = [public_dir / "VPP_EVENT.csv", public_dir / "ECMS_EVENT.csv"]
    manifest_path = internal_dir / "event-manifest.json"
    if not public_dir.is_dir():
        raise ValueError("VPP bundle is missing public/")
    if not internal_dir.is_dir():
        raise ValueError("VPP bundle is missing internal/")
    public_files = sorted(
        path.relative_to(public_dir).as_posix()
        for path in public_dir.rglob("*")
        if path.is_file()
    )
    expected_public = contract["boundary"]["public_directory_exact_files"]
    if public_files != expected_public:
        raise ValueError(
            "public/ must contain exactly VPP_EVENT.csv and ECMS_EVENT.csv; found: "
            + (", ".join(public_files) if public_files else "nothing")
        )
    if not manifest_path.is_file():
        raise ValueError("internal/event-manifest.json is missing")

    all_rows = []
    for event_path in event_paths:
        fields, rows = read_csv(event_path)
        validate_events(fields, rows, contract)
        all_rows.extend(rows)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != contract["schema_version"]:
        raise ValueError("internal manifest schema version mismatch")
    outputs = {item.get("file"): item for item in manifest.get("public_outputs", [])}
    for event_path in event_paths:
        key = f"public/{event_path.name}"
        if outputs.get(key, {}).get("sha256") != sha256(event_path):
            raise ValueError(f"internal manifest {event_path.name} hash mismatch")
    boundary = manifest.get("consumer_boundary", {})
    if boundary != {
        "alarm_console_inputs": ["VPP_EVENT.csv", "ECMS_EVENT.csv"],
        "triplens_ai_inputs": ["DCS1", "DCS2", "ECMS"],
        "raw_published_to_alarm_console": False,
        "raw_published_to_triplens_ai": False,
    }:
        raise ValueError("internal manifest consumer boundary mismatch")
    if manifest.get("scenario_answer_labels_present") is not False:
        raise ValueError("internal manifest permits or reports an answer-label leak")
    for source in manifest.get("internal_sources", []):
        if source.get("published_to_consumers") is not False:
            raise ValueError("an internal source is marked for consumer publication")
    return {
        "event_rows": len(all_rows),
        "systems": manifest.get("system_counts", {}),
        "public_files": public_files,
        "raw_published_to_consumers": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "config" / "event_contract_v1.json",
    )
    args = parser.parse_args()
    report = validate_bundle(args.bundle_dir, args.contract)
    print("VPP_EVENT_CONTRACT_PASS")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
