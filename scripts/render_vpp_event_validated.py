#!/usr/bin/env python3
"""Render the previously validated BFP physical adapter with VPP logic."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from generate_vpp_modelica_logic import generate
from render_bfp_modelica import render


ROOT = Path(__file__).resolve().parents[1]


def finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be finite")
    return number


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-time", type=finite_float, default=10.0)
    parser.add_argument("--coastdown-duration", type=finite_float, default=5.0)
    parser.add_argument("--stop-time", type=finite_float, default=70.0)
    parser.add_argument("--intervals", type=int, default=700)
    parser.add_argument("--final-rpm", type=finite_float, default=1000.0)
    parser.add_argument(
        "--rules", type=Path,
        default=ROOT / "config" / "vpp_event_logic_provisional.csv"
    )
    parser.add_argument(
        "--bindings", type=Path,
        default=ROOT / "config" / "vpp_modelica_signal_bindings.csv"
    )
    parser.add_argument(
        "--trip-matrix", type=Path,
        default=ROOT / "config" / "common_trip_matrix.csv"
    )
    parser.add_argument(
        "--timing", type=Path,
        default=ROOT / "config" / "vpp_trip_timing_provisional.csv"
    )
    parser.add_argument("--template-dir", type=Path, default=ROOT / "modelica")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build")
    args = parser.parse_args()

    if args.event_time < 0 or args.stop_time <= 0 or args.event_time >= args.stop_time:
        parser.error("event time must be inside the simulation horizon")
    if args.coastdown_duration <= 0 or args.event_time + args.coastdown_duration > args.stop_time:
        parser.error("coastdown must be positive and end inside the simulation horizon")
    if not 0 <= args.final_rpm < 1400:
        parser.error("final RPM must be in [0, 1400)")
    if args.intervals < 100:
        parser.error("--intervals must be at least 100")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rules = generate(
        rules_path=args.rules,
        bindings_path=args.bindings,
        trip_matrix_path=args.trip_matrix,
        timing_path=args.timing,
        output_path=args.output_dir / "TripLens_VPPAlarmRuntime.mo",
    )
    replacements = {
        "BFP_EVENT_TIME": f"{args.event_time:.12g}",
        "BFP_COASTDOWN_DURATION": f"{args.coastdown_duration:.12g}",
        "BFP_FINAL_RPM": f"{args.final_rpm:.12g}",
        "STOP_TIME": f"{args.stop_time:.12g}",
        "NUMBER_OF_INTERVALS": str(args.intervals),
        "OUTPUT_INTERVAL": f"{args.stop_time / args.intervals:.12g}",
    }
    render(
        args.template_dir / "TripLens_CombinedCycle_VPPEvent.mo.tpl",
        args.output_dir / "TripLens_CombinedCycle_VPPEvent.mo",
        replacements,
    )
    render(
        args.template_dir / "run_vpp_event_validated.mos.tpl",
        args.output_dir / "run_vpp_event.mos",
        replacements,
    )
    print("VPP_PHYSICAL_ADAPTER=VALIDATED_BFP_BOUNDARY")
    print(f"MODELICA_ALARM_RULES={sum(rule.kind != 'STATE' for rule in rules)}")
    print(f"EVENT_RULES={len(rules)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
