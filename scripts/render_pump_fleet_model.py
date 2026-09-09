#!/usr/bin/env python3
"""Build a TripLens model with physical motor-pump coastdown.

The pinned ThermoSysPro combined-cycle example contains three centrifugal pumps
and one fixed cooling-water mass-flow boundary. Each run retains the selected
pump's native hydraulic curve, replaces its prescribed RPM source with a
breaker/motor/shaft-inertia state, and inserts its discharge check valve. This
preserves the upstream hydraulic initialization while making coastdown dynamic.
The workflow matrix covers every available path. The cooling-water boundary
receives equivalent breaker/inertia semantics because the upstream example has
no CW hydraulic loop.
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
    text = replace_once(
        text,
        "  FlueGases.BoundaryConditions.SourceQ SourceFumees",
        "  ThermoSysPro.FlueGases.BoundaryConditions.SourceQ SourceFumees",
        "flue-gas source package path",
    )
    for source_name in ("Debit", "Temperature"):
        text = replace_once(
            text,
            "  InstrumentationAndControl.Blocks.Tables.Table1DTemps " + source_name,
            "  ThermoSysPro.InstrumentationAndControl.Blocks.Tables.Table1DTemps "
            + source_name,
            f"{source_name} table package path",
        )

    header = f'''model {MODEL_NAME}
  "Combined cycle with breaker, dynamic shaft inertia and check valves"
  parameter Integer tripTarget = {trip_target}
    "0:none, 1:HP FWP, 2:IP FWP, 3:LP/condensate path, 4:CW";
  parameter Real pumpTripTime(unit="s") = {trip_time:.12g};'''
    text = replace_once(
        text,
        f'model {MODEL_NAME}\n  "CCPP model to simulate a load variation from 100% to 50%"',
        header,
        "TripLens parameters",
    )

    target_specs = {
        1: {
            "component": "PompeAlimHP",
            "axis": "HP",
            "inertia": 500,
            "friction": 25,
            "initial_torque": 36000,
            "torque_limit": "1e5",
            "close_flow": 7,
            "closed_resistance": "1e6",
            "speed_marker": "  connect(PompeAlimHP.rpm_or_mpower, arretPomesHP.y)",
            "discharge_marker": "  connect(Vanne_alimentationMPHP1.C1, PompeAlimHP.C2)",
            "downstream": "Vanne_alimentationMPHP1.C1",
        },
        2: {
            "component": "PompeAlimMP",
            "axis": "IP",
            "inertia": 80,
            "friction": 10,
            "initial_torque": 5000,
            "torque_limit": "2e4",
            "close_flow": 2,
            "closed_resistance": "1e6",
            "speed_marker": "  connect(PompeAlimMP.rpm_or_mpower, arretPomesMp.y)",
            "discharge_marker": "  connect(PompeAlimMP.C2, Vanne_alimentationMPHP2.C1)",
            "downstream": "Vanne_alimentationMPHP2.C1",
        },
        3: {
            "component": "PompeAlimBP",
            "axis": "LP",
            "inertia": 300,
            "friction": 20,
            "initial_torque": 4200,
            "torque_limit": "6e4",
            "close_flow": 20,
            "closed_resistance": "1e5",
            "speed_marker": "  connect(PompeAlimBP.rpm_or_mpower, arretPomesBP.y)",
            "discharge_marker": "  connect(PompeAlimBP.C2, vanne_extraction.C1)",
            "downstream": "vanne_extraction.C1",
        },
    }
    selected = target_specs.get(trip_target)
    declarations: list[str] = []
    equations: list[str] = []

    if selected:
        name = str(selected["component"])
        axis = str(selected["axis"])
        initial_torque = int(selected["initial_torque"])
        pump_declaration = (
            "ThermoSysPro.WaterSteam.Machines.StaticCentrifugalPump "
            f"{name}(\n"
        )
        if text.count(pump_declaration) != 1:
            raise ValueError(f"native pump declaration is missing for {name}")
        declarations.append(f'''
  // The selected electrical state is visible in native RAW.
  Boolean breaker{axis}Closed;
  TripLens_PumpPhysics.BreakerInertialPumpDrive drive{axis}(
    nominalSpeedRpm=1400,
    J={selected["inertia"]},
    frictionTorqueNominal={selected["friction"]},
    initialTorque={initial_torque},
    torqueLimit={selected["torque_limit"]});
  TripLens_PumpPhysics.SpringLoadedCheckValve checkValve{axis}(
    closeFlow={selected["close_flow"]},
    closedResistance={selected["closed_resistance"]});
''')
        equations.append(f'''
  breaker{axis}Closed = not (time >= pumpTripTime);
  drive{axis}.breakerClosed.signal = breaker{axis}Closed;
  drive{axis}.pumpPower.signal = {name}.Wm;
  connect(drive{axis}.speedCommand, {name}.rpm_or_mpower);
''')
        text = replace_statement(
            text,
            str(selected["speed_marker"]),
            "",
            f"old {axis} speed source",
        )
        text = replace_statement(
            text,
            str(selected["discharge_marker"]),
            f"  connect({name}.C2, checkValve{axis}.C1);\n"
            f"  connect(checkValve{axis}.C2, {selected['downstream']});\n",
            f"{axis} discharge check valve",
        )
        if f"{name}.rpm_or_mpower" in text:
            raise ValueError(f"legacy prescribed-speed connection remains for {name}")
    elif trip_target == 4:
        declarations.append('''
  Boolean breakerCWClosed;
  TripLens_PumpPhysics.BoundaryMotorPump cwPumpDrive(
    nominalSpeedRpm=600,
    nominalMassFlow=29804.5,
    coastdownTime=2,
    valveTimeConstant=0.1);
''')
        equations.append('''
  breakerCWClosed = not (time >= pumpTripTime);
  cwPumpDrive.breakerClosed.signal = breakerCWClosed;
  connect(cwPumpDrive.massFlow, SourceCaloporteur.IMassFlow);
''')
    elif trip_target != 0:
        raise ValueError(f"unsupported trip target: {trip_target}")

    declaration_text = "".join(declarations)
    equation_text = "".join(equations)
    text = replace_once(
        text,
        "\nequation\n",
        declaration_text + "\nequation\n" + equation_text,
        "pump declarations and equations",
    )
    if selected and text.count(f"{name}.rpm_or_mpower") != 1:
        raise ValueError(f"unexpected speed connection count for {name}")
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
