#!/usr/bin/env python3
"""Build a TripLens model with physical motor-pump coastdown.

The pinned ThermoSysPro combined-cycle example contains three static pumps and
one fixed cooling-water mass-flow boundary.  This renderer makes a deterministic
copy, replaces all three static pumps with DynamicCentrifugalPump, inserts
discharge check valves, and connects breaker-controlled zero-torque drives.
The cooling-water boundary receives the same breaker/inertia semantics through
BoundaryMotorPump because the upstream example has no CW hydraulic loop.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_MODEL = (
    PROJECT_ROOT
    / "vendor"
    / "ThermoSysPro"
    / "ThermoSysPro"
    / "Examples"
    / "CombinedCyclePowerPlant"
    / "CombinedCycle_TripTAC.mo"
)

MODEL_NAME = "TripLens_CombinedCycle_AllPumps"

PUMP_TARGETS = {
    "NONE": 0,
    "FWP-HP": 1,
    "FWP-IP": 2,
    # The simplified upstream plant uses PompeAlimBP as both the condenser
    # extraction/LP feed path. Keep both plant names as explicit aliases.
    "FWP-LP": 3,
    "COND-PUMP": 3,
    "CW-PUMP": 4,
}

PHYSICAL_COMPONENT = {
    "NONE": "none",
    "FWP-HP": "PompeAlimHP",
    "FWP-IP": "PompeAlimMP",
    "FWP-LP": "PompeAlimBP",
    "COND-PUMP": "PompeAlimBP",
    "CW-PUMP": "SourceCaloporteur+cwPumpDrive",
}


def finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be finite")
    return number


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_statement(text: str, marker: str, replacement: str, label: str) -> str:
    """Replace a connect statement, including any graphical annotation."""
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"{label}: connection marker not found")
    if text.find(marker, start + len(marker)) >= 0:
        raise ValueError(f"{label}: connection marker is ambiguous")
    end = text.find(";\n", start)
    if end < 0:
        raise ValueError(f"{label}: unterminated connection statement")
    end += 2
    return text[:start] + replacement + text[end:]


def transform(upstream: str, *, trip_target: int, trip_time: float) -> str:
    text = replace_once(
        upstream,
        "within ThermoSysPro.Examples.CombinedCyclePowerPlant;",
        "within ;",
        "package scope",
    )
    text = replace_once(
        text,
        "model CombinedCycle_TripTAC",
        f"model {MODEL_NAME}",
        "model declaration",
    )
    text = replace_once(
        text,
        "end CombinedCycle_TripTAC;",
        f"end {MODEL_NAME};",
        "model terminator",
    )
    text = replace_once(
        text,
        "  Control.Drum_LevelControl regulation_Niveau_BP",
        "  ThermoSysPro.Examples.CombinedCyclePowerPlant.Control.Drum_LevelControl "
        "regulation_Niveau_BP",
        "LP drum controller package path",
    )

    header = f'''model {MODEL_NAME}
  "Combined cycle with breaker, shaft inertia, pump curve and check valves"
  parameter Integer tripTarget = {trip_target}
    "0:none, 1:HP FWP, 2:IP FWP, 3:LP/condensate path, 4:CW";
  parameter Real pumpTripTime(unit="s") = {trip_time:.12g};'''
    text = replace_once(
        text,
        f'model {MODEL_NAME}\n  "CCPP model to simulate a load variation from 100% to 50%"',
        header,
        "TripLens parameters",
    )

    dynamic_parameters = {
        "PompeAlimMP": "    J=80,\n    Cf0=10,\n    steady_state_mech=true,\n    dynamic_energy_balance=false,\n    continuous_flow_reversal=true,\n",
        "PompeAlimHP": "    J=500,\n    Cf0=25,\n    steady_state_mech=true,\n    dynamic_energy_balance=false,\n    continuous_flow_reversal=true,\n",
        "PompeAlimBP": "    J=300,\n    Cf0=20,\n    steady_state_mech=true,\n    dynamic_energy_balance=false,\n    continuous_flow_reversal=true,\n",
    }
    for name, parameters in dynamic_parameters.items():
        old = (
            "ThermoSysPro.WaterSteam.Machines.StaticCentrifugalPump "
            f"{name}(\n"
        )
        new = (
            "ThermoSysPro.WaterSteam.Machines.DynamicCentrifugalPump "
            f"{name}(\n{parameters}"
        )
        text = replace_once(text, old, new, f"dynamic replacement for {name}")

    declarations = '''
  // Electrical state is deliberately visible in RAW. A trip opens only the
  // selected feeder; normal pumps remain closed and speed-regulated.
  Boolean breakerHPClosed;
  Boolean breakerIPClosed;
  Boolean breakerLPClosed;
  Boolean breakerCWClosed;

  TripLens_PumpPhysics.BreakerTorqueDrive driveHP(
    nominalSpeedRpm=1400, torqueLimit=1e5);
  TripLens_PumpPhysics.BreakerTorqueDrive driveIP(
    nominalSpeedRpm=1400, torqueLimit=2e4);
  TripLens_PumpPhysics.BreakerTorqueDrive driveLP(
    nominalSpeedRpm=1400, torqueLimit=6e4);
  TripLens_PumpPhysics.BoundaryMotorPump cwPumpDrive(
    nominalSpeedRpm=600,
    nominalMassFlow=29804.5,
    coastdownTime=8,
    valveTimeConstant=0.25);

  ThermoSysPro.WaterSteam.PressureLosses.CheckValve checkValveHP(
    dPOuvert=10, dPFerme=0, k=1e-4, Qmin=1e-6,
    continuous_flow_reversal=true, mode=1);
  ThermoSysPro.WaterSteam.PressureLosses.CheckValve checkValveIP(
    dPOuvert=10, dPFerme=0, k=1e-4, Qmin=1e-6,
    continuous_flow_reversal=true, mode=1);
  ThermoSysPro.WaterSteam.PressureLosses.CheckValve checkValveLP(
    dPOuvert=10, dPFerme=0, k=1e-4, Qmin=1e-6,
    continuous_flow_reversal=true, mode=1);
'''
    text = replace_once(text, "\nequation\n", declarations + "\nequation\n", "equation section")

    equations = '''
  breakerHPClosed = not (tripTarget == 1 and time >= pumpTripTime);
  breakerIPClosed = not (tripTarget == 2 and time >= pumpTripTime);
  breakerLPClosed = not (tripTarget == 3 and time >= pumpTripTime);
  breakerCWClosed = not (tripTarget == 4 and time >= pumpTripTime);

  driveHP.breakerClosed.signal = breakerHPClosed;
  driveIP.breakerClosed.signal = breakerIPClosed;
  driveLP.breakerClosed.signal = breakerLPClosed;
  cwPumpDrive.breakerClosed.signal = breakerCWClosed;

  connect(driveHP.shaft, PompeAlimHP.M);
  connect(driveIP.shaft, PompeAlimMP.M);
  connect(driveLP.shaft, PompeAlimBP.M);
  connect(cwPumpDrive.massFlow, SourceCaloporteur.IMassFlow);
'''
    text = replace_once(text, "\nequation\n", "\nequation\n" + equations, "pump equations")

    for marker, label in (
        ("  connect(PompeAlimMP.rpm_or_mpower, arretPomesMp.y)", "old IP speed source"),
        ("  connect(PompeAlimHP.rpm_or_mpower, arretPomesHP.y)", "old HP speed source"),
        ("  connect(PompeAlimBP.rpm_or_mpower, arretPomesBP.y)", "old LP speed source"),
    ):
        text = replace_statement(text, marker, "", label)

    text = replace_statement(
        text,
        "  connect(Vanne_alimentationMPHP1.C1, PompeAlimHP.C2)",
        "  connect(PompeAlimHP.C2, checkValveHP.C1);\n"
        "  connect(checkValveHP.C2, Vanne_alimentationMPHP1.C1);\n",
        "HP discharge check valve",
    )
    text = replace_statement(
        text,
        "  connect(PompeAlimMP.C2, Vanne_alimentationMPHP2.C1)",
        "  connect(PompeAlimMP.C2, checkValveIP.C1);\n"
        "  connect(checkValveIP.C2, Vanne_alimentationMPHP2.C1);\n",
        "IP discharge check valve",
    )
    text = replace_statement(
        text,
        "  connect(PompeAlimBP.C2, vanne_extraction.C1)",
        "  connect(PompeAlimBP.C2, checkValveLP.C1);\n"
        "  connect(checkValveLP.C2, vanne_extraction.C1);\n",
        "LP discharge check valve",
    )

    forbidden = ("PompeAlimHP.rpm_or_mpower", "PompeAlimMP.rpm_or_mpower", "PompeAlimBP.rpm_or_mpower")
    leftovers = [item for item in forbidden if item in text]
    if leftovers:
        raise ValueError("legacy prescribed-speed connections remain: " + ", ".join(leftovers))
    return text


def render_mos(template: Path, destination: Path, replacements: dict[str, str]) -> None:
    text = template.read_text(encoding="utf-8")
    for token, value in replacements.items():
        text = text.replace(f"@{token}@", value)
    unresolved = [part for part in text.split("@") if part.isupper() and "_" in part]
    if unresolved:
        raise ValueError("unresolved template token(s): " + ", ".join(unresolved))
    destination.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pump-id", choices=sorted(PUMP_TARGETS), default="FWP-HP")
    parser.add_argument("--trip-time", type=finite_float, default=300.0)
    parser.add_argument("--stop-time", type=finite_float, default=420.0)
    parser.add_argument("--intervals", type=int, default=4200)
    parser.add_argument("--upstream-model", type=Path, default=UPSTREAM_MODEL)
    parser.add_argument("--template-dir", type=Path, default=PROJECT_ROOT / "modelica")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "build")
    args = parser.parse_args()

    if args.trip_time < 0 or args.stop_time <= 0 or args.trip_time >= args.stop_time:
        parser.error("trip time must be inside the simulation horizon")
    if args.intervals < 100:
        parser.error("--intervals must be at least 100")
    if not args.upstream_model.is_file():
        parser.error(f"upstream model not found: {args.upstream_model}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    source = args.upstream_model.read_text(encoding="utf-8")
    model = transform(
        source,
        trip_target=PUMP_TARGETS[args.pump_id],
        trip_time=args.trip_time,
    )
    model_path = args.output_dir / f"{MODEL_NAME}.mo"
    model_path.write_text(model, encoding="utf-8")

    prefix = "thermosyspro_pump_" + args.pump_id.lower().replace("-", "_")
    replacements = {
        "MODEL_NAME": MODEL_NAME,
        "STOP_TIME": f"{args.stop_time:.12g}",
        "NUMBER_OF_INTERVALS": str(args.intervals),
        "OUTPUT_PREFIX": prefix,
    }
    render_mos(
        args.template_dir / "run_pump_fleet.mos.tpl",
        args.output_dir / "run_pump_fleet.mos",
        replacements,
    )

    metadata = {
        "schema_version": "1.0",
        "pump_id": args.pump_id,
        "trip_target": PUMP_TARGETS[args.pump_id],
        "physical_component": PHYSICAL_COMPONENT[args.pump_id],
        "trip_time_s": args.trip_time,
        "stop_time_s": args.stop_time,
        "output_intervals": args.intervals,
        "output_prefix": prefix,
        "lp_condensate_alias": args.pump_id in {"FWP-LP", "COND-PUMP"},
    }
    (args.output_dir / "pump-scenario.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
