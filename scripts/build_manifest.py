#!/usr/bin/env python3
"""Build a provenance manifest for a cloud simulation result bundle."""

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


def configured_trend_period_ms(output_dir: Path) -> int | None:
    """Read the copied run-specific A setting without assuming it is always 20 ms."""
    path = output_dir / "config" / "ecms_a_settings.csv"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        matches = [
            row for row in csv.DictReader(stream)
            if row.get("setting_id", "").strip() == "TREND_PERIOD_MS"
        ]
    if len(matches) != 1:
        raise ValueError("ecms_a_settings.csv must contain exactly one TREND_PERIOD_MS row")
    value = int(matches[0]["value"])
    if value <= 0:
        raise ValueError("TREND_PERIOD_MS must be greater than zero")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--trip-time", type=float, required=True)
    parser.add_argument("--trip-ramp-duration", type=float, required=True)
    parser.add_argument("--stop-time", type=float, required=True)
    parser.add_argument(
        "--sampling-profile",
        choices=("standard", "causal_100ms", "incident_1ms"),
        default="standard",
    )
    parser.add_argument("--output-intervals", type=int)
    parser.add_argument("--incident-period-ms", type=int, default=1)
    parser.add_argument("--incident-pre-ms", type=int, default=2000)
    parser.add_argument("--incident-post-ms", type=int, default=5000)
    parser.add_argument("--analysis-pre-s", type=float, default=60.0)
    parser.add_argument("--analysis-post-s", type=float, default=400.0)
    parser.add_argument("--requested-trip-time", type=float)
    parser.add_argument("--requested-trip-ramp-duration", type=float)
    parser.add_argument("--requested-stop-time", type=float)
    parser.add_argument("--requested-output-intervals", type=int)
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

    if args.output_intervals is not None and args.output_intervals <= 0:
        parser.error("--output-intervals must be greater than zero")
    if args.incident_period_ms <= 0:
        parser.error("--incident-period-ms must be greater than zero")
    if args.incident_pre_ms < 0 or args.incident_post_ms < 0:
        parser.error("incident window lengths must be non-negative")
    if args.analysis_pre_s < 0 or args.analysis_post_s < 0:
        parser.error("analysis window lengths must be non-negative")

    normal_period_ms = configured_trend_period_ms(args.output_dir)
    physics_period_ms = (
        args.stop_time * 1000.0 / args.output_intervals
        if args.output_intervals is not None else None
    )
    if physics_period_ms is not None and not math.isfinite(physics_period_ms):
        parser.error("derived physics output period is not finite")
    trip_ms = round(args.trip_time * 1000)
    stop_ms = round(args.stop_time * 1000)
    incident_start_ms = max(0, trip_ms - args.incident_pre_ms)
    incident_stop_ms = min(stop_ms, trip_ms + args.incident_post_ms)
    sampling = {
        "profile": args.sampling_profile,
        "timing_source": {
            "standard": "WORKFLOW_INPUTS",
            "causal_100ms": "WORKFLOW_INPUTS_WITH_FIXED_100MS_OUTPUT_GRID",
            "incident_1ms": "FIXED_SHORT_DIAGNOSTIC_PRESET",
        }[args.sampling_profile],
        "requested_workflow_values": {
            "trip_time_s": args.requested_trip_time,
            "trip_ramp_duration_s": args.requested_trip_ramp_duration,
            "stop_time_s": args.requested_stop_time,
            "output_intervals": args.requested_output_intervals,
        },
        "physics": {
            "output_intervals": args.output_intervals,
            "nominal_output_period_ms": physics_period_ms,
            "solver_step_note": (
                "This is the requested CSV output interval; the DASSL integration step remains adaptive."
            ),
        },
        "ecms": {
            "normal_period_ms": normal_period_ms,
            "incident_period_ms": (
                args.incident_period_ms if args.sampling_profile == "incident_1ms" else None
            ),
            "incident_pre_ms": (
                args.incident_pre_ms if args.sampling_profile == "incident_1ms" else None
            ),
            "incident_post_ms": (
                args.incident_post_ms if args.sampling_profile == "incident_1ms" else None
            ),
            "incident_window_start_ms": (
                incident_start_ms if args.sampling_profile == "incident_1ms" else None
            ),
            "incident_window_end_ms": (
                incident_stop_ms if args.sampling_profile == "incident_1ms" else None
            ),
            "value_basis": (
                "INTERPOLATED_FROM_PROCESSBUS_EXCEPT_AT_NATIVE_PHYSICS_SAMPLES"
            ),
        },
        "events": {
            "timestamp_unit": "ms",
            "sampled": False,
        },
        "causal_analysis": {
            "requested_pre_trip_s": args.analysis_pre_s,
            "requested_post_trip_s": args.analysis_post_s,
            "window_metadata_file": "incident-window.json",
            "raw_window_file": "incident-raw.csv",
            "important_changes_file": "important-changes.csv",
        },
    }

    incident_metadata_path = args.output_dir / "incident-window.json"
    if incident_metadata_path.is_file():
        incident_metadata = json.loads(incident_metadata_path.read_text(encoding="utf-8"))
        sampling["causal_analysis"]["actual_window_start_s"] = incident_metadata.get(
            "analysis_window_start_s"
        )
        sampling["causal_analysis"]["actual_window_end_s"] = incident_metadata.get(
            "analysis_window_end_s"
        )
        sampling["causal_analysis"]["first_significant_process_change_s"] = incident_metadata.get(
            "first_significant_process_change_s"
        )

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
            "dcs_alarms": "PROVISIONAL_RULE_CROSSINGS_OVER_UNMODIFIED_PROCESSBUS_VALUES",
            "incident_window": "LOSSLESS_TIME_SLICE_PLUS_AUDIT_METADATA",
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
            "dcs_alarms": "PROVISIONAL_RULE_CROSSINGS_OVER_SYNTHETIC_FIXTURE_VALUES",
            "incident_window": "LOSSLESS_TIME_SLICE_PLUS_AUDIT_METADATA",
        }

    manifest = {
        "schema_version": "3.2",
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
        "sampling": sampling,
        "provenance": provenance,
        "assumptions": [
            "ThermoSysPro CombinedCycle_TripTAC models HRSG/steam-cycle response to GT exhaust boundary conditions.",
            "Alternateur.Welec is treated as steam-turbine generator electrical power, not GT generator power.",
            "M-tag IDs and ThermoSysPro mappings are read-only model facts; published mass-flow units use t/h with an exact x3.6 boundary conversion.",
            "GTG electrical values, breaker timing, transformer ratings and protection settings are editable A assumptions.",
            "The 6.9 kV topology uses UAT-A on the GT transformer low-voltage tap and UAT-B on the ST transformer low-voltage tap.",
            "No separate SST is assumed; GT/ST main transformers may reverse-feed auxiliaries from the 154 kV grid.",
            "The words Incoming/인커밍 are used for auxiliary-bus source breakers.",
            "Unknown fault names are rejected instead of being inferred.",
            "THERMO_ADAPTER_REQUIRED commands create ECMS indications/events but do not mutate locked ThermoSysPro M outputs.",
            "DCS1/DCS2 thresholds are provisional review rules stored in config/dcs_alarm_rules.csv, never hidden constants.",
            "No pre-trip alarm is fabricated when the physical data does not cross a configured rule.",
            "The GT Trip scenario is command-initiated; the current ThermoSysPro wrapper does not create an independent pre-trip GT fault precursor.",
            *(
                [
                    "incident_1ms is a shortened 0-10 s diagnostic profile; it is not equivalent to the standard 600 s pre-trip warm-up.",
                ]
                if args.sampling_profile == "incident_1ms" else []
            ),
            *(
                [
                    "causal_100ms preserves the requested long pre-trip warm-up and post-trip horizon on an exact 100 ms physical CSV grid.",
                ]
                if args.sampling_profile == "causal_100ms" else []
            ),
        ],
        "files": files,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
