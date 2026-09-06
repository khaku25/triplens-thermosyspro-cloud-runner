#!/usr/bin/env python3
"""Build a provenance manifest for a cloud simulation result bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--trip-time", type=float, required=True)
    parser.add_argument("--trip-ramp-duration", type=float, required=True)
    parser.add_argument("--stop-time", type=float, required=True)
    parser.add_argument("--fault-preset", required=True)
    parser.add_argument("--command-scenario", default="none")
    parser.add_argument("--scenario-id", default="GT_TRIP_TAC")
    parser.add_argument(
        "--source-kind",
        choices=("thermosyspro", "synthetic_fixture"),
        default="thermosyspro",
        help="Declare whether results came from the pinned physics run or a bundled test fixture.",
    )
    parser.add_argument("--thermosyspro-commit", required=True)
    parser.add_argument("--openmodelica-image", required=True)
    args = parser.parse_args()

    files = {}
    for path in sorted(args.output_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            relative = path.relative_to(args.output_dir).as_posix()
            files[relative] = {"bytes": path.stat().st_size, "sha256": sha256(path)}

    if args.source_kind == "thermosyspro":
        runtime = {
            "engine": "THERMOSYSPRO_OPENMODELICA",
            "thermosyspro_used": True,
            "openmodelica_image": args.openmodelica_image,
            "thermosyspro_repository": "Dwarf-Planet-Project/ThermoSysPro",
            "thermosyspro_commit": args.thermosyspro_commit,
            "manifest_builder_python": platform.python_version(),
        }
        provenance = {
            "thermosyspro_raw": "PHYSICS_MODEL_OUTPUT",
            "processbus": "RENAMED_AND_NORMALIZED_MODEL_OUTPUT_PLUS_SCENARIO_TRIP_COMMAND",
            "ecms": "M_LOCKED_PLUS_A_CONFIGURED_ELECTRICAL_OBSERVATION_MODEL",
            "command_bus": "VALIDATED_USER_COMMANDS_APPLIED_TO_SUPPORTED_ELECTRICAL_STATES",
        }
    else:
        runtime = {
            "engine": "BUNDLED_SYNTHETIC_TEST_FIXTURE",
            "thermosyspro_used": False,
            "manifest_builder_python": platform.python_version(),
        }
        provenance = {
            "thermosyspro_raw": "SYNTHETIC_TEST_FIXTURE_NOT_RUNTIME_PHYSICS",
            "processbus": "NORMALIZED_SYNTHETIC_FIXTURE_PLUS_SCENARIO_TRIP_COMMAND",
            "ecms": "SYNTHETIC_DEMO_M_LOCKED_PLUS_A_CONFIGURED_ELECTRICAL_MODEL",
            "command_bus": "VALIDATED_USER_COMMANDS_APPLIED_TO_SUPPORTED_ELECTRICAL_STATES",
        }

    manifest = {
        "schema_version": "3.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario": {
            "id": args.scenario_id,
            "trip_time_s": args.trip_time,
            "trip_ramp_duration_s": args.trip_ramp_duration,
            "stop_time_s": args.stop_time,
            "fault_preset": args.fault_preset,
            "command_scenario": args.command_scenario,
        },
        "runtime": runtime,
        "provenance": provenance,
        "assumptions": [
            "ThermoSysPro CombinedCycle_TripTAC models HRSG/steam-cycle response to GT exhaust boundary conditions.",
            "Alternateur.Welec is treated as steam-turbine generator electrical power, not GT generator power.",
            "M-tag IDs, units and ThermoSysPro mappings are read-only model facts.",
            "GTG electrical values, breaker timing, transformer ratings and protection settings are editable A assumptions.",
            "The 6.9 kV topology uses UAT-A on the GT transformer low-voltage tap and UAT-B on the ST transformer low-voltage tap.",
            "No separate SST is assumed; GT/ST main transformers may reverse-feed auxiliaries from the 154 kV grid.",
            "The words Incoming/인커밍 are used for auxiliary-bus source breakers.",
            "Unknown fault names are rejected instead of being inferred.",
            "THERMO_ADAPTER_REQUIRED commands create ECMS indications/events but do not mutate locked ThermoSysPro M outputs.",
        ],
        "files": files,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
