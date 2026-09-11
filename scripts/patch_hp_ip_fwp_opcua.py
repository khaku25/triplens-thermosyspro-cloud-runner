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
    initialTorque=9000,
    torqueLimit=1.2e5);
  TripLens_PumpPhysics.BreakerInertialPumpDrive vppIPFWPDrive(
    nominalSpeedRpm=1400,
    J=350,
    frictionTorqueNominal=25,
    initialTorque=5000,
    torqueLimit=8e4);
  parameter Real vppHPFWPHydraulicSpeedFloorRPM(unit="rev/min") = 700
    "Numerical floor for the HP static-pump curve; shaft speed remains physical";
  parameter Real vppIPFWPHydraulicSpeedFloorRPM(unit="rev/min") = 700
    "Numerical floor for the IP static-pump curve; shaft speed remains physical";

  output Real vppFWPHPRunEnableNative(start=1, fixed=true,
    stateSelect=StateSelect.always);
  output Real vppVCBA01ClosedNative(start=1, fixed=true,
    stateSelect=StateSelect.always);
  output Real vppFWPIPRunEnableNative(start=1, fixed=true,
    stateSelect=StateSelect.always);
  output Real vppVCBB01ClosedNative(start=1, fixed=true,
    stateSelect=StateSelect.always);

  output Boolean vppHPFWPMotorEnergized;
  output Boolean vppHPFWPSpeedProven;
  output Boolean vppHPFWPRunning;
  output Real vppHPFWPSpeedRPM(unit="rev/min");
  output Real vppHPFWPHydraulicSpeedRPM(unit="rev/min");
  output Real vppHPFWPMassFlowTH(unit="t/h");
  output Real vppHPFWPVolumeFlowM3S(unit="m3/s");
  output Real vppHPFWPDeltaPPa(unit="Pa");
  output Real vppHPFWPMechanicalPowerW(unit="W");
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppHPFWPHydraulicSpeedCommand;

  output Boolean vppIPFWPMotorEnergized;
  output Boolean vppIPFWPSpeedProven;
  output Boolean vppIPFWPRunning;
  output Real vppIPFWPSpeedRPM(unit="rev/min");
  output Real vppIPFWPHydraulicSpeedRPM(unit="rev/min");
  output Real vppIPFWPMassFlowTH(unit="t/h");
  output Real vppIPFWPVolumeFlowM3S(unit="m3/s");
  output Real vppIPFWPDeltaPPa(unit="Pa");
  output Real vppIPFWPMechanicalPowerW(unit="W");
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppIPFWPHydraulicSpeedCommand;
'''

EQUATIONS = '''
  // Continuous states are the writable native OpenModelica OPC UA boundary.
  der(vppFWPHPRunEnableNative) = Modelica.Constants.eps*sin(time);
  der(vppVCBA01ClosedNative) = Modelica.Constants.eps*sin(time);
  der(vppFWPIPRunEnableNative) = Modelica.Constants.eps*sin(time);
  der(vppVCBB01ClosedNative) = Modelica.Constants.eps*sin(time);

  // Fail closed: both the DCS run permission and the breaker auxiliary
  // contact must be true before motor torque can be applied.
  vppHPFWPMotorEnergized = vppFWPHPRunEnableNative >= 0.5 and
    vppVCBA01ClosedNative >= 0.5;
  vppIPFWPMotorEnergized = vppFWPIPRunEnableNative >= 0.5 and
    vppVCBB01ClosedNative >= 0.5;

  vppHPFWPDrive.breakerClosed.signal = vppHPFWPMotorEnergized;
  vppHPFWPDrive.pumpPower.signal = PompeAlimHP.Wm;
  vppHPFWPHydraulicSpeedCommand.signal = noEvent(max(
    vppHPFWPHydraulicSpeedFloorRPM, vppHPFWPDrive.speedRpm));
  connect(vppHPFWPHydraulicSpeedCommand, PompeAlimHP.rpm_or_mpower);

  vppIPFWPDrive.breakerClosed.signal = vppIPFWPMotorEnergized;
  vppIPFWPDrive.pumpPower.signal = PompeAlimMP.Wm;
  vppIPFWPHydraulicSpeedCommand.signal = noEvent(max(
    vppIPFWPHydraulicSpeedFloorRPM, vppIPFWPDrive.speedRpm));
  connect(vppIPFWPHydraulicSpeedCommand, PompeAlimMP.rpm_or_mpower);

  vppHPFWPSpeedRPM = vppHPFWPDrive.speedRpm;
  vppHPFWPHydraulicSpeedRPM = vppHPFWPHydraulicSpeedCommand.signal;
  vppHPFWPSpeedProven = vppHPFWPSpeedRPM >= 0.9*vppHPFWPDrive.nominalSpeedRpm;
  vppHPFWPRunning = vppHPFWPMotorEnergized and vppHPFWPSpeedProven;
  vppHPFWPMassFlowTH = 3.6*PompeAlimHP.Q;
  vppHPFWPVolumeFlowM3S = PompeAlimHP.Qv;
  vppHPFWPDeltaPPa = PompeAlimHP.deltaP;
  vppHPFWPMechanicalPowerW = PompeAlimHP.Wm;

  vppIPFWPSpeedRPM = vppIPFWPDrive.speedRpm;
  vppIPFWPHydraulicSpeedRPM = vppIPFWPHydraulicSpeedCommand.signal;
  vppIPFWPSpeedProven = vppIPFWPSpeedRPM >= 0.9*vppIPFWPDrive.nominalSpeedRpm;
  vppIPFWPRunning = vppIPFWPMotorEnergized and vppIPFWPSpeedProven;
  vppIPFWPMassFlowTH = 3.6*PompeAlimMP.Q;
  vppIPFWPVolumeFlowM3S = PompeAlimMP.Qv;
  vppIPFWPDeltaPPa = PompeAlimMP.deltaP;
  vppIPFWPMechanicalPowerW = PompeAlimMP.Wm;

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
        "  // The native OPC UA server permits writes to continuous states.",
        EQUATIONS + "  // The native OPC UA server permits writes to continuous states.",
        "HP/IP FWP equation insertion",
    )

    required = (
        "vppFWPHPRunEnableNative(start=1",
        "vppVCBA01ClosedNative(start=1",
        "vppFWPIPRunEnableNative(start=1",
        "vppVCBB01ClosedNative(start=1",
        "vppHPFWPMotorEnergized = vppFWPHPRunEnableNative >= 0.5 and",
        "vppIPFWPMotorEnergized = vppFWPIPRunEnableNative >= 0.5 and",
        "connect(vppHPFWPHydraulicSpeedCommand, PompeAlimHP.rpm_or_mpower)",
        "connect(vppIPFWPHydraulicSpeedCommand, PompeAlimMP.rpm_or_mpower)",
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
