#!/usr/bin/env python3
"""Render the isolated ThermoSysPro HP boiler-feed-pump trip wrapper."""

from __future__ import annotations

import argparse
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be finite")
    return number


def render(source: Path, destination: Path, replacements: dict[str, str]) -> None:
    text = source.read_text(encoding="utf-8")
    for token, value in replacements.items():
        text = text.replace(f"@{token}@", value)
    unresolved = [part for part in text.split("@") if part.isupper() and "_" in part]
    if unresolved:
        raise ValueError("unresolved template token(s): " + ", ".join(unresolved))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trip-time", type=finite_float, default=10.0)
    parser.add_argument("--coastdown-duration", type=finite_float, default=5.0)
    parser.add_argument("--stop-time", type=finite_float, default=70.0)
    parser.add_argument("--intervals", type=int, default=100)
    parser.add_argument("--final-rpm", type=finite_float, default=1000.0)
    parser.add_argument("--template-dir", type=Path, default=PROJECT_ROOT / "modelica")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "build")
    args = parser.parse_args()

    if args.trip_time < 0 or args.stop_time <= 0 or args.trip_time >= args.stop_time:
        parser.error("trip time must be inside the simulation horizon")
    if args.coastdown_duration <= 0 or args.trip_time + args.coastdown_duration > args.stop_time:
        parser.error("coastdown must be positive and end inside the simulation horizon")
    if not 0 <= args.final_rpm < 1400:
        parser.error("final RPM must be in [0, 1400)")
    if args.intervals < 100:
        parser.error("--intervals must be at least 100")

    replacements = {
        "BFP_TRIP_TIME": f"{args.trip_time:.12g}",
        "BFP_COASTDOWN_DURATION": f"{args.coastdown_duration:.12g}",
        "BFP_FINAL_RPM": f"{args.final_rpm:.12g}",
        "STOP_TIME": f"{args.stop_time:.12g}",
        "NUMBER_OF_INTERVALS": str(args.intervals),
        "OUTPUT_INTERVAL": f"{args.stop_time / args.intervals:.12g}",
    }
    render(
        args.template_dir / "TripLens_CombinedCycle_BFPTrip.mo.tpl",
        args.output_dir / "TripLens_CombinedCycle_BFPTrip.mo",
        replacements,
    )
    render(
        args.template_dir / "run_bfp.mos.tpl",
        args.output_dir / "run_bfp.mos",
        replacements,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
