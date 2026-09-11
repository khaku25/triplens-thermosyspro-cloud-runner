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
    "TRIPLENS_FMU_NATIVE_VALVE_ADAPTER_V1",
)

DECLARATIONS = f'''
  // {MARKER}
  parameter Real vppLPFWPNormalSpeedRPM = 1400;
  // Numerical hydraulic floor: the upstream pump/IF97 equations leave their
  // valid domain during a direct zero-rpm transient. Electrical de-energization
  // remains authoritative through vppLPFWPMotorEnergized=false.
  parameter Real vppLPFWPNumericalSpeedFloorRPM = 700;
  parameter Real vppLPFWPCoastdown95(unit="s") = 2.0;
  parameter Real vppLPFWPCoastdownTau(unit="s") = vppLPFWPCoastdown95/(-log(0.05));
  parameter Real vppLPFWPDischargeClose95(unit="s") = 0.2;
  parameter Real vppLPFWPDischargeCloseTau(unit="s") =
    vppLPFWPDischargeClose95/(-log(0.05));
  output Real vppLPFWPTripCommandNative(start=0, fixed=true, stateSelect=StateSelect.always);
  output Real vppLPFWPTripLatchNative(start=0, fixed=true, stateSelect=StateSelect.always);
  output Real vppVCBA02TripCommandNative(start=0, fixed=true, stateSelect=StateSelect.always);
  output Real vppVCBA02ClosedNative(start=1, fixed=true, stateSelect=StateSelect.always);
  output Boolean vppLPFWPMotorEnergized;
  output Boolean vppLPFWPSpeedProven;
  output Boolean vppLPFWPRunning;
  output Real vppLPFWPSpeedRPM(start=1400, fixed=true);
  output Real vppLPFWPDischargeMultiplier(start=1, fixed=true, min=0, max=1);
  output Real vppLPFWPMassFlowTH(unit="t/h");
  output Real vppLPFWPVolumeFlowM3S(unit="m3/s");
  output Real vppLPFWPDeltaPPa(unit="Pa");
  output Real vppLPFWPMechanicalPowerW(unit="W");
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppLPFWPSpeedCommand;

'''

EQUATIONS = '''
  der(vppLPFWPTripCommandNative) = Modelica.Constants.eps*sin(time);
  der(vppLPFWPTripLatchNative) = Modelica.Constants.eps*sin(time);
  der(vppVCBA02TripCommandNative) = Modelica.Constants.eps*sin(time);
  der(vppVCBA02ClosedNative) = Modelica.Constants.eps*sin(time);
  vppLPFWPMotorEnergized = vppVCBA02ClosedNative >= 0.5;
  der(vppLPFWPDischargeMultiplier) =
    ((if vppLPFWPMotorEnergized then 1 else 0)
      - vppLPFWPDischargeMultiplier)/vppLPFWPDischargeCloseTau;
  der(vppLPFWPSpeedRPM) =
    ((if vppLPFWPMotorEnergized then vppLPFWPNormalSpeedRPM
      else vppLPFWPNumericalSpeedFloorRPM) - vppLPFWPSpeedRPM)/vppLPFWPCoastdownTau;
  vppLPFWPSpeedCommand.signal = vppLPFWPSpeedRPM;
  connect(vppLPFWPSpeedCommand, PompeAlimBP.rpm_or_mpower);
  vppLPFWPSpeedProven = vppLPFWPSpeedRPM >= 0.9*vppLPFWPNormalSpeedRPM;
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
    source = replace_once(
        source,
        "  fmuVlvCondExtractionFb = fmuVlvCondExtractionTarget;",
        "  fmuVlvCondExtractionFb = fmuVlvCondExtractionTarget"
        "*vppLPFWPDischargeMultiplier;",
        "LP FWP discharge isolation",
    )
    source = replace_once(
        source,
        "  // The native OPC UA server permits writes to continuous states.",
        EQUATIONS + "  // The native OPC UA server permits writes to continuous states.",
        "LP FWP equation insertion",
    )
    required = (
        "output Real vppLPFWPTripCommandNative(",
        "output Real vppVCBA02ClosedNative(",
        "connect(vppLPFWPSpeedCommand, PompeAlimBP.rpm_or_mpower)",
        "fmuVlvCondExtractionTarget*vppLPFWPDischargeMultiplier",
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
