#!/usr/bin/env python3
"""Build a RAW-only ThermoSysPro ST Trip physical wrapper.

This ports the validated R&D semantics:
ST Trip -> close the actual HP/MP turbine admission-valve command sources ->
ThermoSysPro solves the steam-cycle rundown.

Trip itself is still defined downstream by 52ST.CLOSED=0. This wrapper supplies
only the thermodynamic secondary effect for physical RAW generation.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "vendor" / "ThermoSysPro" / "ThermoSysPro" / "Examples" / "CombinedCyclePowerPlant" / "CombinedCycle_TripTAC.mo"
OUT = ROOT / "build" / "TripLens_CombinedCycle_STTrip.mo"
RUN = ROOT / "build" / "run_st_trip.mos"


def finite_nonnegative(v: str) -> float:
    x = float(v)
    if not math.isfinite(x) or x < 0:
        raise argparse.ArgumentTypeError("must be finite and non-negative")
    return x


def finite_positive(v: str) -> float:
    x = float(v)
    if not math.isfinite(x) or x <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return x


def replace_once(text: str, pattern: re.Pattern[str], repl: str, label: str) -> str:
    text, n = pattern.subn(repl, text, count=1)
    if n != 1:
        raise SystemExit(f"{label} replacement count={n}, expected 1")
    return text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--event-time", type=finite_nonnegative, default=10.0)
    p.add_argument("--stop-time", type=finite_positive, default=70.0)
    p.add_argument("--intervals", type=int, default=700)
    args = p.parse_args()
    if args.event_time >= args.stop_time:
        p.error("--event-time must be earlier than --stop-time")
    if args.intervals < 100:
        p.error("--intervals must be at least 100")
    if not SRC.is_file():
        raise SystemExit(f"missing pinned ThermoSysPro source: {SRC}")

    text = SRC.read_text(encoding="utf-8")
    old_header = '''within ThermoSysPro.Examples.CombinedCyclePowerPlant;\nmodel CombinedCycle_TripTAC\n  "CCPP model to simulate a load variation from 100% to 50%"'''
    new_header = f'''within ThermoSysPro.Examples.CombinedCyclePowerPlant;\nblock TripLensSTConstantSource\n  parameter Real value;\n  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal y;\nequation\n  y.signal = value;\nend TripLensSTConstantSource;\n\nblock TripLensSTTripValveSource\n  parameter Real normalOpening=0.8;\n  parameter Real tripTime=10;\n  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal y;\nequation\n  // Preserve native normal opening through initialization; close after event.\n  y.signal = if initial() then normalOpening else if time >= tripTime then 0 else normalOpening;\nend TripLensSTTripValveSource;\n\nmodel TripLens_CombinedCycle_STTrip\n  "RAW-only ST thermodynamic Trip adapter; breaker semantics are downstream"'''
    if old_header not in text:
        raise SystemExit("CombinedCycle_TripTAC header not found")
    text = text.replace(old_header, new_header, 1)

    # Keep GT process boundary nominal throughout this ST-only physical test.
    pat_debit = re.compile(
        r'InstrumentationAndControl\.Blocks\.Tables\.Table1DTemps Debit\(.*?\)\s*'
        r'annotation \(Placement\(transformation\(extent=\{\{-527,-19\},\{-457,\s*55\}\}, rotation=0\)\)\);',
        re.S,
    )
    pat_temp = re.compile(
        r'InstrumentationAndControl\.Blocks\.Tables\.Table1DTemps Temperature\(.*?\)\s*'
        r'annotation \(Placement\(transformation\(extent=\{\{-527,-157\},\{\s*-457,-83\}\}, rotation=0\)\)\);',
        re.S,
    )
    text = replace_once(text, pat_debit,
        'TripLensSTConstantSource Debit(value=606.94) annotation (Placement(transformation(extent={{-527,-19},{-457,55}}, rotation=0)));',
        "GT flow source")
    text = replace_once(text, pat_temp,
        'TripLensSTConstantSource Temperature(value=893.75) annotation (Placement(transformation(extent={{-527,-157},{-457,-83}}, rotation=0)));',
        "GT temperature source")

    pat_st_hp = re.compile(
        r'ThermoSysPro\.InstrumentationAndControl\.Blocks\.Tables\.Table1DTemps\s*'
        r'ConstantVanneTurbineHP\(.*?\)\s*'
        r'annotation \(Placement\(transformation\(extent=\{\{-241,-216\},\{\s*-171,-142\}\}, rotation=0\)\)\);',
        re.S,
    )
    pat_st_mp = re.compile(
        r'ThermoSysPro\.InstrumentationAndControl\.Blocks\.Tables\.Table1DTemps\s*'
        r'ConstantVanneTurbineMP\(.*?\)\s*'
        r'annotation \(Placement\(transformation\(extent=\{\{-241,-300\},\{\s*-171,-226\}\}, rotation=0\)\)\);',
        re.S,
    )
    text = replace_once(text, pat_st_hp,
        f'TripLensSTTripValveSource ConstantVanneTurbineHP(normalOpening=0.8, tripTime={args.event_time:.12g}) annotation (Placement(transformation(extent={{{{-241,-216}},{{-171,-142}}}}, rotation=0)));',
        "ST HP admission source")
    text = replace_once(text, pat_st_mp,
        f'TripLensSTTripValveSource ConstantVanneTurbineMP(normalOpening=0.8, tripTime={args.event_time:.12g}) annotation (Placement(transformation(extent={{{{-241,-300}},{{-171,-226}}}}, rotation=0)));',
        "ST MP admission source")

    text = text.replace("end CombinedCycle_TripTAC;", "end TripLens_CombinedCycle_STTrip;", 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")

    interval = args.stop_time / args.intervals
    RUN.write_text(f'''setCommandLineOptions("--std=3.4");\nloadModel(Modelica, {{"3.2.3"}});\ngetErrorString();\nloadFile("/workspace/vendor/ThermoSysPro/ThermoSysPro/package.mo");\ngetErrorString();\nloadFile("/workspace/build/TripLens_CombinedCycle_STTrip.mo");\ngetErrorString();\ncd("/workspace/build");\nsimulate(\n  ThermoSysPro.Examples.CombinedCyclePowerPlant.TripLens_CombinedCycle_STTrip,\n  startTime=0,\n  stopTime={args.stop_time:.12g},\n  numberOfIntervals={args.intervals},\n  tolerance=1e-3,\n  method="dassl",\n  outputFormat="csv",\n  simflags="-noEventEmit",\n  fileNamePrefix="thermosyspro_st_trip",\n  variableFilter="^(time|Debit\\\\.y\\\\.signal|Temperature\\\\.y\\\\.signal|ConstantVanneTurbine(HP|MP)\\\\.y\\\\.signal|Alternateur\\\\.Welec|Ballon(HP|MP|BP)\\\\.(yLevel\\\\.signal|zl|P)|Turbine(HP|MP|BP)\\\\.Q|vanne_entree_Turbine(HP|MP)\\\\.Ouv\\\\.signal)$");\ngetErrorString();\n''', encoding="utf-8")
    print(f"WROTE {OUT}")
    print(f"WROTE {RUN}")
    print("ST_TRIP_PHYSICS=HP_MP_ADMISSION_CLOSE")
    print("TRIP_DEFINITION=52ST.CLOSED=0_DOWNSTREAM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
