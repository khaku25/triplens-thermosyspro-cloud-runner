#!/usr/bin/env python3
"""Add the LP feedwater-pump OPC UA boundary to the patched ThermoSysPro plant."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

MARKER = "TRIPLENS_LP_FWP_OPCUA_ADAPTER_V1"
REQUIRED_MARKERS = (
    "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V13",
)

DECLARATIONS = f'''
  // {MARKER}
  TripLens_PumpPhysics.BreakerInertialPumpDrive vppLPFWPDrive(
    nominalSpeedRpm=1400,
    J=300,
    frictionTorqueNominal=20,
    initialTorque=4200,
    torqueLimit=6e4);
  parameter Real vppLPFWPHydraulicSpeedFloorRPM(unit="rev/min") = 700
    "Numerical floor for the upstream static pump curve; shaft speed remains physical";
  TripLens_PumpPhysics.SpringLoadedCheckValve vppLPFWPCheckValve(
    closeFlow=70,
    closedResistance=1e5);
  input Real vppLPFWPTripCommandNative(start=0) = 0;
  input Real vppLPFWPTripLatchNative(start=0) = 0;
  input Real vppVCBA02TripCommandNative(start=0) = 0;
  input Real vppVCBA02ClosedNative(start=1) = 1;
  output Boolean vppLPFWPMotorEnergized;
  output Boolean vppLPFWPSpeedProven;
  output Boolean vppLPFWPRunning;
  output Real vppLPFWPSpeedRPM(unit="rev/min");
  output Real vppLPFWPHydraulicSpeedRPM(unit="rev/min");
  output Boolean vppLPFWPCheckValveOpen;
  output Real vppLPFWPCheckValveOpening(min=0, max=1);
  output Real vppLPFWPMassFlowTH(unit="t/h");
  output Real vppLPFWPVolumeFlowM3S(unit="m3/s");
  output Real vppLPFWPDeltaPPa(unit="Pa");
  output Real vppLPFWPMechanicalPowerW(unit="W");
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppLPFWPHydraulicSpeedCommand;
'''

EQUATIONS = '''
  vppLPFWPMotorEnergized = vppVCBA02ClosedNative >= 0.5;
  vppLPFWPDrive.breakerClosed.signal = vppLPFWPMotorEnergized;
  vppLPFWPDrive.pumpPower.signal = PompeAlimBP.Wm;
  vppLPFWPHydraulicSpeedCommand.signal = noEvent(max(
    vppLPFWPHydraulicSpeedFloorRPM, vppLPFWPDrive.speedRpm));
  connect(vppLPFWPHydraulicSpeedCommand, PompeAlimBP.rpm_or_mpower);
  connect(PompeAlimBP.C2, vppLPFWPCheckValve.C1);
  connect(vppLPFWPCheckValve.C2, vanne_extraction.C1);
  vppLPFWPSpeedRPM = vppLPFWPDrive.speedRpm;
  vppLPFWPHydraulicSpeedRPM = vppLPFWPHydraulicSpeedCommand.signal;
  vppLPFWPCheckValveOpen = vppLPFWPCheckValve.ouvert;
  vppLPFWPCheckValveOpening = vppLPFWPCheckValve.opening;
  vppLPFWPSpeedProven = vppLPFWPSpeedRPM >= 0.9*vppLPFWPDrive.nominalSpeedRpm;
  vppLPFWPRunning = vppLPFWPMotorEnergized and vppLPFWPSpeedProven;
  vppLPFWPMassFlowTH = 3.6*PompeAlimBP.Q;
  vppLPFWPVolumeFlowM3S = PompeAlimBP.Qv;
  vppLPFWPDeltaPPa = PompeAlimBP.deltaP;
  vppLPFWPMechanicalPowerW = PompeAlimBP.Wm;

'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def remove_connect(text: str, call: str) -> str:
    token = f"  connect({call})"
    start = text.find(token)
    if start < 0:
        raise ValueError(f"missing native automatic connection: {call}")
    end = text.find(";", start)
    if end < 0 or text.find(token, end + 1) >= 0:
        raise ValueError(f"invalid native automatic connection: {call}")
    return text[:start] + f"  // {MARKER}: adapter owns {call}\n" + text[end + 1:]


def patch_model(source: str) -> str:
    for marker in REQUIRED_MARKERS:
        if marker not in source:
            raise ValueError(f"required previous patch is missing: {marker}")
    if MARKER in source:
        raise ValueError("LP FWP OPC UA adapter is already applied")
    source = replace_once(
        source,
        "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        DECLARATIONS + "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        "LP FWP declaration insertion",
    )
    source = remove_connect(source, "PompeAlimBP.rpm_or_mpower, arretPomesBP.y")
    source = remove_connect(source, "PompeAlimBP.C2, vanne_extraction.C1")
    source = replace_once(
        source,
        "  // TRIPLENS_NATIVE_OPCUA_BOUNDARY_INSERTION_POINT",
        EQUATIONS + "  // TRIPLENS_NATIVE_OPCUA_BOUNDARY_INSERTION_POINT",
        "LP FWP equation insertion",
    )
    required = (
        "input Real vppLPFWPTripCommandNative(start=0) = 0",
        "input Real vppVCBA02ClosedNative(start=1) = 1",
        "connect(vppLPFWPHydraulicSpeedCommand, PompeAlimBP.rpm_or_mpower)",
        "vppLPFWPHydraulicSpeedFloorRPM, vppLPFWPDrive.speedRpm",
        "connect(PompeAlimBP.C2, vppLPFWPCheckValve.C1)",
        "connect(vppLPFWPCheckValve.C2, vanne_extraction.C1)",
        "vppLPFWPMassFlowTH = 3.6*PompeAlimBP.Q",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"LP FWP adapter missing {token}")
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    patched = patch_model(args.source.read_text(encoding="utf-8"))
    if args.check_only:
        print(f"LP_FWP_OPCUA_PATCH_PASS source={args.source}")
        return 0
    destination = args.output or args.source
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False,
            dir=destination.parent, prefix=destination.name + ".", suffix=".tmp"
        ) as stream:
            temporary = Path(stream.name)
            stream.write(patched)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(f"LP_FWP_OPCUA_PATCH_PASS output={destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
