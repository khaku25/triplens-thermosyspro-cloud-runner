#!/usr/bin/env python3
"""Add discharge check valves and native OPC UA feedback to every plant FWP.

The pinned ThermoSysPro combined-cycle model contains exactly three physical
feedwater pumps: PompeAlimHP, PompeAlimMP (TripLens IP), and PompeAlimBP
(TripLens LP).  The LP OPC UA adapter already inserts its check valve; this
patch adds the HP/IP valves and publishes the same seven passive physical
measurements for all three valves.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_ALL_FWP_CHECK_VALVES_OPCUA_V1"
REQUIRED_MARKERS = (
    "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V13",
    "TRIPLENS_LP_FWP_OPCUA_ADAPTER_V1",
)

DECLARATIONS = f'''
  // {MARKER}
  parameter Real vppFWPCheckValveTelemetryTimeConstantS(unit="s") = 0.02
    "Tracking-state time constant for read-only hydraulic telemetry";
  TripLens_PumpPhysics.SpringLoadedCheckValve vppHPFWPCheckValve(
    closeFlow=20,
    closedResistance=1e5);
  TripLens_PumpPhysics.SpringLoadedCheckValve vppIPFWPCheckValve(
    closeFlow=5,
    closedResistance=1e5);

  output Boolean vppHPFWPCheckValveOpen;
  output Real vppHPFWPCheckValveOpening(min=0, max=1);
  output Real vppHPFWPCheckValveMassFlowTH(unit="t/h");
  output Real vppHPFWPCheckValveDeltaPPa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppHPFWPCheckValveInletPressurePa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppHPFWPCheckValveOutletPressurePa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppHPFWPCheckValveResistancePaSPerKg(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa.s/kg");

  output Boolean vppIPFWPCheckValveOpen;
  output Real vppIPFWPCheckValveOpening(min=0, max=1);
  output Real vppIPFWPCheckValveMassFlowTH(unit="t/h");
  output Real vppIPFWPCheckValveDeltaPPa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppIPFWPCheckValveInletPressurePa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppIPFWPCheckValveOutletPressurePa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppIPFWPCheckValveResistancePaSPerKg(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa.s/kg");

  output Real vppLPFWPCheckValveMassFlowTH(unit="t/h");
  output Real vppLPFWPCheckValveDeltaPPa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppLPFWPCheckValveInletPressurePa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppLPFWPCheckValveOutletPressurePa(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa");
  output Real vppLPFWPCheckValveResistancePaSPerKg(start=0, fixed=true, stateSelect=StateSelect.always, unit="Pa.s/kg");
'''

EQUATIONS = '''
  connect(PompeAlimHP.C2, vppHPFWPCheckValve.C1);
  connect(vppHPFWPCheckValve.C2, Vanne_alimentationMPHP1.C1);
  connect(PompeAlimMP.C2, vppIPFWPCheckValve.C1);
  connect(vppIPFWPCheckValve.C2, Vanne_alimentationMPHP2.C1);

  vppHPFWPCheckValveOpen = vppHPFWPCheckValve.ouvert;
  vppHPFWPCheckValveOpening = vppHPFWPCheckValve.opening;
  vppHPFWPCheckValveMassFlowTH = 3.6*vppHPFWPCheckValve.Q;

  vppIPFWPCheckValveOpen = vppIPFWPCheckValve.ouvert;
  vppIPFWPCheckValveOpening = vppIPFWPCheckValve.opening;
  vppIPFWPCheckValveMassFlowTH = 3.6*vppIPFWPCheckValve.Q;

  vppLPFWPCheckValveMassFlowTH = 3.6*vppLPFWPCheckValve.Q;
  // These four values per valve are observability-only. Fixed tracking states
  // prevent OpenModelica from replacing native hydraulic iteration variables
  // with top-level telemetry aliases in the initial nonlinear system.
  der(vppHPFWPCheckValveDeltaPPa) = (vppHPFWPCheckValve.deltaP -
    vppHPFWPCheckValveDeltaPPa)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppHPFWPCheckValveInletPressurePa) = (vppHPFWPCheckValve.C1.P -
    vppHPFWPCheckValveInletPressurePa)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppHPFWPCheckValveOutletPressurePa) = (vppHPFWPCheckValve.C2.P -
    vppHPFWPCheckValveOutletPressurePa)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppHPFWPCheckValveResistancePaSPerKg) =
    (vppHPFWPCheckValve.effectiveResistance -
    vppHPFWPCheckValveResistancePaSPerKg)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppIPFWPCheckValveDeltaPPa) = (vppIPFWPCheckValve.deltaP -
    vppIPFWPCheckValveDeltaPPa)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppIPFWPCheckValveInletPressurePa) = (vppIPFWPCheckValve.C1.P -
    vppIPFWPCheckValveInletPressurePa)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppIPFWPCheckValveOutletPressurePa) = (vppIPFWPCheckValve.C2.P -
    vppIPFWPCheckValveOutletPressurePa)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppIPFWPCheckValveResistancePaSPerKg) =
    (vppIPFWPCheckValve.effectiveResistance -
    vppIPFWPCheckValveResistancePaSPerKg)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppLPFWPCheckValveDeltaPPa) = (vppLPFWPCheckValve.deltaP -
    vppLPFWPCheckValveDeltaPPa)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppLPFWPCheckValveInletPressurePa) = (vppLPFWPCheckValve.C1.P -
    vppLPFWPCheckValveInletPressurePa)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppLPFWPCheckValveOutletPressurePa) = (vppLPFWPCheckValve.C2.P -
    vppLPFWPCheckValveOutletPressurePa)/vppFWPCheckValveTelemetryTimeConstantS;
  der(vppLPFWPCheckValveResistancePaSPerKg) =
    (vppLPFWPCheckValve.effectiveResistance -
    vppLPFWPCheckValveResistancePaSPerKg)/vppFWPCheckValveTelemetryTimeConstantS;

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
        raise ValueError(f"missing native pump discharge connection: {call}")
    end = text.find(";", start)
    if end < 0 or text.find(token, end + 1) >= 0:
        raise ValueError(f"invalid native pump discharge connection: {call}")
    replacement = f"  // {MARKER}: check valve owns {call}\n"
    return text[:start] + replacement + text[end + 1:]


def patch_model(source: str) -> str:
    for marker in REQUIRED_MARKERS:
        if marker not in source:
            raise ValueError(f"required previous patch is missing: {marker}")
    if MARKER in source:
        raise ValueError("all-FWP check-valve patch is already applied")

    # These are the only two unprotected physical pump discharges remaining;
    # LP is already rewired by patch_lp_fwp_opcua.py.
    source = remove_connect(
        source, "Vanne_alimentationMPHP1.C1, PompeAlimHP.C2"
    )
    source = remove_connect(
        source, "PompeAlimMP.C2, Vanne_alimentationMPHP2.C1"
    )
    source = replace_once(
        source,
        "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        DECLARATIONS + "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        "all-FWP check-valve declaration insertion",
    )
    source = replace_once(
        source,
        "  // TRIPLENS_NATIVE_OPCUA_BOUNDARY_INSERTION_POINT",
        EQUATIONS + "  // TRIPLENS_NATIVE_OPCUA_BOUNDARY_INSERTION_POINT",
        "all-FWP check-valve equation insertion",
    )

    for prefix in ("HP", "IP", "LP"):
        for suffix in (
            "Open", "Opening", "MassFlowTH", "DeltaPPa", "InletPressurePa",
            "OutletPressurePa", "ResistancePaSPerKg",
        ):
            token = f"vpp{prefix}FWPCheckValve{suffix}"
            if token not in source:
                raise AssertionError(f"missing OPC UA check-valve variable {token}")
    for token in (
        "connect(PompeAlimHP.C2, vppHPFWPCheckValve.C1)",
        "connect(vppHPFWPCheckValve.C2, Vanne_alimentationMPHP1.C1)",
        "connect(PompeAlimMP.C2, vppIPFWPCheckValve.C1)",
        "connect(vppIPFWPCheckValve.C2, Vanne_alimentationMPHP2.C1)",
        "connect(PompeAlimBP.C2, vppLPFWPCheckValve.C1)",
        "connect(vppLPFWPCheckValve.C2, vanne_extraction.C1)",
    ):
        if token not in source:
            raise AssertionError(f"missing physical check-valve connection {token}")
    for level in ("HP", "IP", "LP"):
        for suffix in (
            "DeltaPPa", "InletPressurePa", "OutletPressurePa",
            "ResistancePaSPerKg",
        ):
            token = f"output Real vpp{level}FWPCheckValve{suffix}(start=0, fixed=true, stateSelect=StateSelect.always"
            if token not in source:
                raise AssertionError(f"unsampled check-valve telemetry {token}")
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    patched = patch_model(args.source.read_text(encoding="utf-8"))
    if args.check_only:
        print(f"ALL_FWP_CHECK_VALVES_OPCUA_PATCH_PASS source={args.source}")
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
    print(f"ALL_FWP_CHECK_VALVES_OPCUA_PATCH_PASS output={destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
