#!/usr/bin/env python3
"""Render the parameterized ThermoSysPro wrapper and OpenModelica script."""

from __future__ import annotations

import argparse
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return number


def nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a non-negative finite number")
    return number


def render(template: Path, destination: Path, replacements: dict[str, str]) -> None:
    text = template.read_text(encoding="utf-8")
    for token, value in replacements.items():
        text = text.replace(f"@{token}@", value)
    unresolved = [part for part in text.split("@") if part.isupper() and "_" in part]
    if unresolved:
        raise ValueError(f"unresolved template token(s): {', '.join(unresolved)}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    # --trip-time / --trip-ramp-duration are retained as legacy CLI names for
    # the exhaust-boundary event. They do not define canonical GT Trip semantics.
    parser.add_argument("--trip-time", type=nonnegative_float, default=600.0)
    parser.add_argument("--trip-ramp-duration", type=positive_float, default=5.0)
    parser.add_argument("--stop-time", type=positive_float, default=1000.0)
    parser.add_argument("--intervals", type=int, default=1000)
    parser.add_argument("--normal-operation", action="store_true")
    parser.add_argument(
        "--derate-only",
        action="store_true",
        help=(
            "Apply the exhaust 2184.984 t/h / 893.75 K -> 540 t/h / 550 K "
            "boundary reduction "
            "without asserting the embedded ST Trip trigger."
        ),
    )
    parser.add_argument(
        "--gt-trip",
        action="store_true",
        help=(
            "Run the canonical GT Trip profile: publish the GT Trip/breaker "
            "states from Modelica, coast the exhaust boundary to shutdown, "
            "and assert the physical ST isolation/bypass sequence."
        ),
    )
    parser.add_argument(
        "--external-trip-input",
        action="store_true",
        help=(
            "Expose the live FMU GT Trip input and suppress every scheduled "
            "Trip source. The external command becomes the only Trip cause."
        ),
    )
    parser.add_argument("--template-dir", type=Path, default=PROJECT_ROOT / "modelica")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "build")
    args = parser.parse_args()

    if sum((
        args.normal_operation, args.derate_only, args.gt_trip,
        args.external_trip_input,
    )) > 1:
        parser.error(
            "--normal-operation, --derate-only, --gt-trip and "
            "--external-trip-input are mutually exclusive"
        )
    if args.intervals < 10:
        parser.error("--intervals must be at least 10")
    if not args.normal_operation and not args.external_trip_input:
        if args.trip_time >= args.stop_time:
            parser.error("boundary event time must be earlier than --stop-time")
        if args.trip_time + args.trip_ramp_duration > args.stop_time:
            parser.error("boundary ramp must end no later than --stop-time")

    output_interval = args.stop_time / args.intervals
    stop_time = f"{args.stop_time:.12g}"
    gt_trip_enabled = "true" if args.gt_trip else "false"
    if args.normal_operation or args.external_trip_input:
        # In external mode both legacy TimeTables stay normal. The patch routes
        # the live command through its own physical exhaust states, so a lost
        # ECMS command cannot be masked by a scheduled boundary transition.
        vpp_trip_time = f"{args.stop_time + 1:.12g}"
        exhaust_flow_table = (
            f"[0,exhaustFlowNormalTH/3.6; {stop_time},exhaustFlowNormalTH/3.6]"
        )
        exhaust_temperature_table = (
            f"[0,exhaustTemperatureNormal; {stop_time},exhaustTemperatureNormal]"
        )
    elif args.gt_trip:
        vpp_trip_time = f"{args.trip_time:.12g}"
        exhaust_flow_table = (
            "[0,exhaustFlowNormalTH/3.6; "
            "eventTime,exhaustFlowNormalTH/3.6; "
            "eventTime + boundaryRampDuration,exhaustFlowTripTH/3.6; "
            f"{stop_time},exhaustFlowTripTH/3.6]"
        )
        exhaust_temperature_table = (
            "[0,exhaustTemperatureNormal; "
            "eventTime,exhaustTemperatureNormal; "
            "eventTime + boundaryRampDuration,exhaustTemperatureTrip; "
            f"{stop_time},exhaustTemperatureTrip]"
        )
    else:
        # In DERATE-only mode the exhaust boundary still changes at eventTime,
        # but the patched ThermoSysPro ST Trip trigger is moved past StopTime.
        vpp_trip_time = (
            f"{args.stop_time + 1:.12g}"
            if args.derate_only
            else f"{args.trip_time:.12g}"
        )
        exhaust_flow_table = (
            "[0,exhaustFlowNormalTH/3.6; "
            "eventTime,exhaustFlowNormalTH/3.6; "
            "eventTime + boundaryRampDuration,exhaustFlowDeratedTH/3.6; "
            f"{stop_time},exhaustFlowDeratedTH/3.6]"
        )
        exhaust_temperature_table = (
            "[0,exhaustTemperatureNormal; "
            "eventTime,exhaustTemperatureNormal; "
            "eventTime + boundaryRampDuration,exhaustTemperatureDerated; "
            f"{stop_time},exhaustTemperatureDerated]"
        )
    replacements = {
        "TRIP_TIME": f"{args.trip_time:.12g}",
        "TRIP_RAMP_DURATION": f"{args.trip_ramp_duration:.12g}",
        "STOP_TIME": stop_time,
        "VPP_TRIP_TIME": vpp_trip_time,
        "GT_TRIP_ENABLED": gt_trip_enabled,
        "EXTERNAL_TRIP_ENABLED": (
            "true" if args.external_trip_input else "false"
        ),
        "EXHAUST_FLOW_TABLE": exhaust_flow_table,
        "EXHAUST_TEMPERATURE_TABLE": exhaust_temperature_table,
        "NUMBER_OF_INTERVALS": str(args.intervals),
        "OUTPUT_INTERVAL": f"{output_interval:.12g}",
    }
    render(
        args.template_dir / "TripLens_CombinedCycle_TripTAC.mo.tpl",
        args.output_dir / "TripLens_CombinedCycle_TripTAC.mo",
        replacements,
    )
    render(args.template_dir / "run.mos.tpl", args.output_dir / "run.mos", replacements)
    live_fmu_template = args.template_dir / "build_live_fmu.mos.tpl"
    if live_fmu_template.is_file():
        render(
            live_fmu_template,
            args.output_dir / "build_live_fmu.mos",
            replacements,
        )
    native_opcua_template = args.template_dir / "build_native_opcua.mos.tpl"
    if native_opcua_template.is_file():
        render(
            native_opcua_template,
            args.output_dir / "build_native_opcua.mos",
            replacements,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
