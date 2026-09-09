#!/usr/bin/env python3
"""Render a pump-initiated VPP model with CSV-driven logic inside Modelica."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from generate_vpp_modelica_logic import generate, load_bindings
from render_pump_fleet_model import (
    MODEL_NAME,
    PUMP_TARGETS,
    UPSTREAM_MODEL,
    render_mos,
    transform,
)


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_PUMPS = {key: value for key, value in PUMP_TARGETS.items() if key != "NONE"}


def finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be finite")
    return number


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pump-id", choices=sorted(SUPPORTED_PUMPS), default="FWP-HP")
    parser.add_argument("--event-time", type=finite_float, default=300.0)
    parser.add_argument("--stop-time", type=finite_float, default=420.0)
    parser.add_argument("--intervals", type=int, default=4200)
    parser.add_argument("--upstream-model", type=Path, default=UPSTREAM_MODEL)
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
    if args.intervals < 100:
        parser.error("--intervals must be at least 100")
    if not args.upstream_model.is_file():
        parser.error(f"upstream model not found: {args.upstream_model}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    logic_path = args.output_dir / "TripLens_VPPAlarmRuntime.mo"
    rules = generate(
        rules_path=args.rules,
        bindings_path=args.bindings,
        trip_matrix_path=args.trip_matrix,
        timing_path=args.timing,
        output_path=logic_path,
    )
    bindings = {
        binding.source_signal: binding.expression
        for binding in load_bindings(args.bindings)
    }
    model = transform(
        args.upstream_model.read_text(encoding="utf-8"),
        trip_target=SUPPORTED_PUMPS[args.pump_id],
        trip_time=args.event_time,
        vpp_runtime_bindings=bindings,
    )
    model_path = args.output_dir / f"{MODEL_NAME}.mo"
    model_path.write_text(model, encoding="utf-8")

    prefix = "triplens_vpp_event_" + args.pump_id.lower().replace("-", "_")
    render_mos(
        args.template_dir / "run_vpp_event.mos.tpl",
        args.output_dir / "run_vpp_event.mos",
        {
            "MODEL_NAME": MODEL_NAME,
            "STOP_TIME": f"{args.stop_time:.12g}",
            "NUMBER_OF_INTERVALS": str(args.intervals),
            "OUTPUT_PREFIX": prefix,
        },
    )
    print(f"VPP_MODEL={model_path}")
    print(f"VPP_LOGIC_MODEL={logic_path}")
    print(f"MODELICA_ALARM_RULES={sum(rule.kind != 'STATE' for rule in rules)}")
    print(f"EVENT_RULES={len(rules)}")
    print(f"OUTPUT_PREFIX={prefix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
