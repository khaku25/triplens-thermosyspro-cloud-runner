#!/usr/bin/env python3
"""Wire the native HP/IP feedwater pumps to their ECMS OPC UA boundaries.

The discharge non-return valves are owned by
``patch_all_fwp_check_valves.py``.  This adapter deliberately touches only the
two native pump speed inputs, so it can reuse those physical valves without
creating a second hydraulic path.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_HP_IP_FWP_OPCUA_ADAPTER_V1"
REQUIRED_MARKERS = (
    "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V13",
    "TRIPLENS_LP_FWP_OPCUA_ADAPTER_V1",
    "TRIPLENS_ALL_FWP_CHECK_VALVES_OPCUA_V1",
)

DECLARATIONS = f'''
  // {MARKER}
  TripLens_PumpPhysics.BreakerInertialPumpDrive vppHPFWPDrive(
    nominalSpeedRpm=1400,
    J=900,
    frictionTorqueNominal=45,
    initialTorque=41810,
    torqueLimit=1.2e5);
  TripLens_PumpPhysics.BreakerInertialPumpDrive vppIPFWPDrive(
    nominalSpeedRpm=1400,
    J=350,
    frictionTorqueNominal=25,
    initialTorque=1531,
    torqueLimit=8e4);
  parameter Real vppHPFWPNominalMechanicalPowerW(unit="W") = 6125061.295700202
    "Pinned 1400 rpm HP pump load used by the causal shaft-load boundary";
  parameter Real vppIPFWPNominalMechanicalPowerW(unit="W") = 220732.6496544388
    "Pinned 1400 rpm IP pump load used by the causal shaft-load boundary";
  parameter Real vppHPIPTelemetryTimeConstantS(unit="s") = 0.02
    "Tracking-state time constant that keeps pump telemetry outside the plant DAE";
  parameter Real vppHPFWPHydraulicSpeedFloorRPM(unit="rev/min") = 700
    "Numerical floor for the HP static-pump curve; shaft speed remains physical";
  parameter Real vppIPFWPHydraulicSpeedFloorRPM(unit="rev/min") = 700
    "Numerical floor for the IP static-pump curve; shaft speed remains physical";

  input Real vppFWPHPRunEnableNative(start=1) = 1;
  input Real vppVCBA01ClosedNative(start=1) = 1;
  input Real vppFWPIPRunEnableNative(start=1) = 1;
  input Real vppVCBB01ClosedNative(start=1) = 1;

  output Boolean vppHPFWPMotorEnergized;
  output Boolean vppHPFWPSpeedProven;
  output Boolean vppHPFWPRunning;
  output Real vppHPFWPSpeedRPM(unit="rev/min");
  output Real vppHPFWPHydraulicSpeedRPM(unit="rev/min");
  output Real vppHPFWPMassFlowTH(unit="t/h");
  output Real vppHPFWPVolumeFlowM3S(start=0, fixed=true, stateSelect=StateSelect.always, unit="m3/s");
  output Real vppHPFWPDeltaPPa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppHPFWPMechanicalPowerW(unit="W");
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppHPFWPHydraulicSpeedCommand;

  output Boolean vppIPFWPMotorEnergized;
  output Boolean vppIPFWPSpeedProven;
  output Boolean vppIPFWPRunning;
  output Real vppIPFWPSpeedRPM(unit="rev/min");
  output Real vppIPFWPHydraulicSpeedRPM(unit="rev/min");
  output Real vppIPFWPMassFlowTH(unit="t/h");
  output Real vppIPFWPVolumeFlowM3S(start=0, fixed=true, stateSelect=StateSelect.always, unit="m3/s");
  output Real vppIPFWPDeltaPPa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppIPFWPMechanicalPowerW(unit="W");
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppIPFWPHydraulicSpeedCommand;
'''

EQUATIONS = '''
  // Top-level inputs are writable native OpenModelica OPC UA boundaries.

  // Fail closed: both the DCS run permission and the breaker auxiliary
  // contact must be true before motor torque can be applied.
  vppHPFWPMotorEnergized = vppFWPHPRunEnableNative >= 0.5 and
    vppVCBA01ClosedNative >= 0.5;
  vppIPFWPMotorEnergized = vppFWPIPRunEnableNative >= 0.5 and
    vppVCBB01ClosedNative >= 0.5;

  vppHPFWPDrive.breakerClosed.signal = vppHPFWPMotorEnergized;
  // Keep shaft load causal. Feeding PompeAlimHP.Wm directly back into the
  // drive closes the legacy plant's largest nonlinear initialization system.
  // The centrifugal-pump affinity law P ~ rpm^3 preserves coastdown loading
  // without adding that thermohydraulic algebraic feedback edge.
  vppHPFWPDrive.pumpPower.signal = vppHPFWPNominalMechanicalPowerW*noEvent(
    (max(vppHPFWPDrive.speedRpm, 0)/vppHPFWPDrive.nominalSpeedRpm)^3);
  vppHPFWPHydraulicSpeedCommand.signal = noEvent(max(
    vppHPFWPHydraulicSpeedFloorRPM, vppHPFWPDrive.speedRpm));
  connect(vppHPFWPHydraulicSpeedCommand, PompeAlimHP.rpm_or_mpower);

  vppIPFWPDrive.breakerClosed.signal = vppIPFWPMotorEnergized;
  vppIPFWPDrive.pumpPower.signal = vppIPFWPNominalMechanicalPowerW*noEvent(
    (max(vppIPFWPDrive.speedRpm, 0)/vppIPFWPDrive.nominalSpeedRpm)^3);
  vppIPFWPHydraulicSpeedCommand.signal = noEvent(max(
    vppIPFWPHydraulicSpeedFloorRPM, vppIPFWPDrive.speedRpm));
  connect(vppIPFWPHydraulicSpeedCommand, PompeAlimMP.rpm_or_mpower);

  vppHPFWPSpeedRPM = vppHPFWPDrive.speedRpm;
  vppHPFWPHydraulicSpeedRPM = vppHPFWPHydraulicSpeedCommand.signal;
  vppHPFWPSpeedProven = vppHPFWPSpeedRPM >= 0.9*vppHPFWPDrive.nominalSpeedRpm;
  vppHPFWPRunning = vppHPFWPMotorEnergized and vppHPFWPSpeedProven;
  vppHPFWPMassFlowTH = 3.6*PompeAlimHP.Q;
  vppHPFWPMechanicalPowerW = PompeAlimHP.Wm;
  vppIPFWPSpeedRPM = vppIPFWPDrive.speedRpm;
  vppIPFWPHydraulicSpeedRPM = vppIPFWPHydraulicSpeedCommand.signal;
  vppIPFWPSpeedProven = vppIPFWPSpeedRPM >= 0.9*vppIPFWPDrive.nominalSpeedRpm;
  vppIPFWPRunning = vppIPFWPMotorEnergized and vppIPFWPSpeedProven;
  vppIPFWPMassFlowTH = 3.6*PompeAlimMP.Q;
  vppIPFWPMechanicalPowerW = PompeAlimMP.Wm;
  // Tracking states prevent observability aliases from replacing native pump
  // iteration variables without generating periodic global DAE events.
  der(vppHPFWPVolumeFlowM3S) = (PompeAlimHP.Qv -
    vppHPFWPVolumeFlowM3S)/vppHPIPTelemetryTimeConstantS;
  der(vppHPFWPDeltaPPa) = (PompeAlimHP.deltaP -
    vppHPFWPDeltaPPa)/vppHPIPTelemetryTimeConstantS;
  der(vppIPFWPVolumeFlowM3S) = (PompeAlimMP.Qv -
    vppIPFWPVolumeFlowM3S)/vppHPIPTelemetryTimeConstantS;
  der(vppIPFWPDeltaPPa) = (PompeAlimMP.deltaP -
    vppIPFWPDeltaPPa)/vppHPIPTelemetryTimeConstantS;

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
    replacement = f"  // {MARKER}: adapter owns {call}\n"
    return text[:start] + replacement + text[end + 1:]


def patch_model(source: str) -> str:
    for marker in REQUIRED_MARKERS:
        if marker not in source:
            raise ValueError(f"required previous patch is missing: {marker}")
    if MARKER in source:
        raise ValueError("HP/IP FWP OPC UA adapter is already applied")

    source = remove_connect(source, "PompeAlimHP.rpm_or_mpower, arretPomesHP.y")
    source = remove_connect(source, "PompeAlimMP.rpm_or_mpower, arretPomesMp.y")
    source = replace_once(
        source,
        "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        DECLARATIONS + "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        "HP/IP FWP declaration insertion",
    )
    source = replace_once(
        source,
        "  // TRIPLENS_NATIVE_OPCUA_BOUNDARY_INSERTION_POINT",
        EQUATIONS + "  // TRIPLENS_NATIVE_OPCUA_BOUNDARY_INSERTION_POINT",
        "HP/IP FWP equation insertion",
    )

    required = (
        "input Real vppFWPHPRunEnableNative(start=1) = 1",
        "input Real vppVCBA01ClosedNative(start=1) = 1",
        "input Real vppFWPIPRunEnableNative(start=1) = 1",
        "input Real vppVCBB01ClosedNative(start=1) = 1",
        "vppHPFWPMotorEnergized = vppFWPHPRunEnableNative >= 0.5 and",
        "vppIPFWPMotorEnergized = vppFWPIPRunEnableNative >= 0.5 and",
        "connect(vppHPFWPHydraulicSpeedCommand, PompeAlimHP.rpm_or_mpower)",
        "connect(vppIPFWPHydraulicSpeedCommand, PompeAlimMP.rpm_or_mpower)",
        "vppHPFWPNominalMechanicalPowerW*noEvent(",
        "vppIPFWPNominalMechanicalPowerW*noEvent(",
        "vppHPFWPMassFlowTH = 3.6*PompeAlimHP.Q",
        "vppIPFWPMassFlowTH = 3.6*PompeAlimMP.Q",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"HP/IP FWP adapter missing {token}")

    # The existing all-FWP patch remains the sole owner of the physical NRVs.
    for token in (
        "connect(PompeAlimHP.C2, vppHPFWPCheckValve.C1)",
        "connect(vppHPFWPCheckValve.C2, Vanne_alimentationMPHP1.C1)",
        "connect(PompeAlimMP.C2, vppIPFWPCheckValve.C1)",
        "connect(vppIPFWPCheckValve.C2, Vanne_alimentationMPHP2.C1)",
    ):
        if token not in source:
            raise AssertionError(f"existing check-valve path is missing {token}")
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    patched = patch_model(args.source.read_text(encoding="utf-8"))
    if args.check_only:
        print(f"HP_IP_FWP_OPCUA_PATCH_PASS source={args.source}")
        return 0

    destination = args.output or args.source
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False,
            dir=destination.parent, prefix=destination.name + ".", suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            stream.write(patched)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(f"HP_IP_FWP_OPCUA_PATCH_PASS output={destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
