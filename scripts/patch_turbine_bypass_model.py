#!/usr/bin/env python3
"""Patch the pinned ThermoSysPro CCPP with physical HPBP/LPBP branches.

The upstream example has no turbine bypass and holds both turbine admission
valves at a constant opening.  This deterministic source transform keeps the
upstream commit pinned while adding VPP-owned fluid components, first-order
actuator states, spray-water mass/energy flow, and ST-Trip isolation.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V1"


PARAMETERS = f'''  // {MARKER}
  parameter Real vppTripTime(unit="s") = 600
    "Resolved ST Trip time for the physical GT Trip adapter";
  parameter Real vppAdmissionStroke95(unit="s") = 0.150
    "HP/IP and LP-drum admission 95 percent closing time";
  parameter Real vppHPBypassStroke95(unit="s") = 0.300
    "HPBP 95 percent opening time";
  parameter Real vppLPBypassStroke95(unit="s") = 0.400
    "LPBP 95 percent opening time";
  parameter Real vppSprayStroke95(unit="s") = 0.050
    "Spray-water actuator 95 percent opening time";
  parameter Real vppValveLeak = 1e-4
    "Numerical leakage position used to avoid a zero-flow junction singularity";
  parameter ThermoSysPro.Units.Cv vppHPBypassCvmax = 4000
    "Initial HPBP Cv calibration value";
  parameter ThermoSysPro.Units.Cv vppLPBypassCvmax = 50000
    "Initial LPBP Cv calibration value";
  parameter Real vppHPSprayRatio = 0.245289
    "HP spray-water mass flow divided by measured HPBP steam flow";
  parameter Real vppLPSprayRatio = 0.383212
    "LP spray-water mass flow divided by measured LPBP steam flow";
  parameter Real vppAdmissionTau(unit="s") =
      vppAdmissionStroke95/(-log(0.05));
  parameter Real vppHPBypassTau(unit="s") =
      vppHPBypassStroke95/(-log(0.05));
  parameter Real vppLPBypassTau(unit="s") =
      vppLPBypassStroke95/(-log(0.05));
  parameter Real vppSprayTau(unit="s") =
      vppSprayStroke95/(-log(0.05));

'''


COMPONENTS = '''
  Boolean vppSTTripLatch(start=false)
    "One-way resolved ST Trip latch for this physical scenario";
  Real vppHPAdmissionPos(start=0.8, fixed=true, min=0, max=1);
  Real vppIPAdmissionPos(start=0.8, fixed=true, min=0, max=1);
  Real vppLPDrumAdmissionMultiplier(start=1, fixed=true, min=0, max=1);
  Real vppHPBypassCmd(min=0, max=1);
  Real vppLPBypassCmd(min=0, max=1);
  Real vppHPBypassPos(start=vppValveLeak, fixed=true, min=0, max=1);
  Real vppLPBypassPos(start=vppValveLeak, fixed=true, min=0, max=1);
  Real vppHPSprayPos(start=0, fixed=true, min=0, max=1);
  Real vppLPSprayPos(start=0, fixed=true, min=0, max=1);
  Boolean vppHPBypassOpenLS;
  Boolean vppHPBypassCloseLS;
  Boolean vppLPBypassOpenLS;
  Boolean vppLPBypassCloseLS;
  Modelica.SIunits.MassFlowRate vppHPBypassMassFlow;
  Modelica.SIunits.MassFlowRate vppLPBypassMassFlow;
  Modelica.SIunits.MassFlowRate vppHPSprayMassFlow;
  Modelica.SIunits.MassFlowRate vppLPSprayMassFlow;
  Modelica.SIunits.AbsolutePressure vppHPBypassInletPressure;
  Modelica.SIunits.AbsolutePressure vppLPBypassInletPressure;
  Modelica.SIunits.AbsolutePressure vppHPBypassOutletPressure;
  Modelica.SIunits.AbsolutePressure vppLPBypassOutletPressure;
  Modelica.SIunits.Temperature vppHPBypassInletTemperature;
  Modelica.SIunits.Temperature vppLPBypassInletTemperature;
  Modelica.SIunits.Temperature vppHPBypassOutletTemperature;
  Modelica.SIunits.Temperature vppLPBypassOutletTemperature;
  Modelica.SIunits.AbsolutePressure vppCondenserPressure;
  Modelica.SIunits.Length vppCondenserLevel;

  ThermoSysPro.WaterSteam.Junctions.Splitter2 vppHPSplitter(
    P(start=12681000), h(start=3450835));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vppHPBypassValve(
    Cvmax=vppHPBypassCvmax,
    continuous_flow_reversal=true,
    Q(start=0.01),
    Cv(start=vppValveLeak*vppHPBypassCvmax),
    h(start=3450835),
    Pm(start=7703850),
    C1(P(start=12681000), h_vol(start=3450835)),
    C2(P(start=2726700), h_vol(start=3450835)));
  ThermoSysPro.WaterSteam.BoundaryConditions.SourceQ vppHPSpraySource(
    Q0=0, h0=1396866);
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppHPSprayFlowCommand;
  ThermoSysPro.WaterSteam.Junctions.Mixer2 vppHPBypassMixer(
    P(start=2726700), h(start=3046260),
    Ce1(h_vol(start=3450835)), Ce2(h_vol(start=1396866)));
  ThermoSysPro.WaterSteam.Junctions.Mixer2 vppHPColdReheatMixer(
    P(start=2726700), h(start=3046260),
    Ce1(h_vol(start=3046260)), Ce2(h_vol(start=3046260)));

  ThermoSysPro.WaterSteam.Junctions.Splitter2 vppLPSplitter(
    P(start=2548600), h(start=3523910));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vppLPBypassValve(
    Cvmax=vppLPBypassCvmax,
    continuous_flow_reversal=true,
    Q(start=0.01),
    Cv(start=vppValveLeak*vppLPBypassCvmax),
    h(start=3523910),
    Pm(start=1277368),
    C1(P(start=2548600), h_vol(start=3523910)),
    C2(P(start=6136), h_vol(start=3523910)));
  ThermoSysPro.WaterSteam.BoundaryConditions.SourceQ vppLPSpraySource(
    Q0=0, h0=550000);
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppLPSprayFlowCommand;
  ThermoSysPro.WaterSteam.Junctions.Mixer2 vppLPBypassMixer(
    P(start=6136), h(start=2700000),
    Ce1(h_vol(start=3523910)), Ce2(h_vol(start=550000)));
  ThermoSysPro.WaterSteam.Junctions.Mixer2 vppCondenserSteamMixer(
    P(start=10053), h(start=2401030),
    Ce1(h_vol(start=2401030)), Ce2(h_vol(start=2700000)));
'''


EQUATIONS = '''
  vppSTTripLatch = time >= vppTripTime;
  vppHPBypassCmd = if vppSTTripLatch then 1 else vppValveLeak;
  vppLPBypassCmd = if vppSTTripLatch then 1 else vppValveLeak;

  der(vppHPAdmissionPos) =
    ((if vppSTTripLatch then 0 else 0.8) - vppHPAdmissionPos)
      /vppAdmissionTau;
  der(vppIPAdmissionPos) =
    ((if vppSTTripLatch then 0 else 0.8) - vppIPAdmissionPos)
      /vppAdmissionTau;
  der(vppLPDrumAdmissionMultiplier) =
    ((if vppSTTripLatch then 0 else 1)
      - vppLPDrumAdmissionMultiplier)/vppAdmissionTau;
  der(vppHPBypassPos) =
    (vppHPBypassCmd - vppHPBypassPos)/vppHPBypassTau;
  der(vppLPBypassPos) =
    (vppLPBypassCmd - vppLPBypassPos)/vppLPBypassTau;
  der(vppHPSprayPos) =
    ((if vppSTTripLatch then 1 else 0) - vppHPSprayPos)/vppSprayTau;
  der(vppLPSprayPos) =
    ((if vppSTTripLatch then 1 else 0) - vppLPSprayPos)/vppSprayTau;

  vppHPBypassOpenLS = vppHPBypassPos >= 0.95;
  vppHPBypassCloseLS = vppHPBypassPos <= 0.01;
  vppLPBypassOpenLS = vppLPBypassPos >= 0.95;
  vppLPBypassCloseLS = vppLPBypassPos <= 0.01;

  vppHPBypassMassFlow = vppHPBypassValve.Q;
  vppLPBypassMassFlow = vppLPBypassValve.Q;
  vppHPSprayMassFlow = vppHPSpraySource.Q;
  vppLPSprayMassFlow = vppLPSpraySource.Q;
  vppHPBypassInletPressure = vppHPSplitter.P;
  vppLPBypassInletPressure = vppLPSplitter.P;
  vppHPBypassOutletPressure = vppHPBypassMixer.P;
  vppLPBypassOutletPressure = vppLPBypassMixer.P;
  vppHPBypassInletTemperature = vppHPSplitter.T;
  vppLPBypassInletTemperature = vppLPSplitter.T;
  vppHPBypassOutletTemperature = vppHPBypassMixer.T;
  vppLPBypassOutletTemperature = vppLPBypassMixer.T;
  vppCondenserPressure = Condenseur.P;
  vppCondenserLevel = Condenseur.yNiveau.signal;

  vanne_entree_TurbineHP.Ouv.signal = vppHPAdmissionPos;
  vanne_entree_TurbineMP.Ouv.signal = vppIPAdmissionPos;
  vanne_vapeurBP.Ouv.signal =
    regulation_Niveau_BP.SortieReelle1.signal*vppLPDrumAdmissionMultiplier;
  vppHPBypassValve.Ouv.signal = vppHPBypassPos;
  vppLPBypassValve.Ouv.signal = vppLPBypassPos;
  vppHPSprayFlowCommand.signal = noEvent(max(0, vppHPBypassValve.Q))
    *vppHPSprayRatio*vppHPSprayPos;
  vppLPSprayFlowCommand.signal = noEvent(max(0, vppLPBypassValve.Q))
    *vppLPSprayRatio*vppLPSprayPos;

  connect(vppHPSprayFlowCommand, vppHPSpraySource.IMassFlow);
  connect(vppHPSpraySource.C, vppHPBypassMixer.Ce2);
  connect(vppHPBypassValve.C2, vppHPBypassMixer.Ce1);
  connect(vppLPSprayFlowCommand, vppLPSpraySource.IMassFlow);
  connect(vppLPSpraySource.C, vppLPBypassMixer.Ce2);
  connect(vppLPBypassValve.C2, vppLPBypassMixer.Ce1);
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def replace_connect_statement(text: str, call: str, replacement: str) -> str:
    start_token = f"  connect({call})"
    start = text.find(start_token)
    if start < 0:
        raise ValueError(f"missing upstream connection: {call}")
    end = text.find(";", start)
    if end < 0:
        raise ValueError(f"unterminated upstream connection: {call}")
    if text.find(start_token, end + 1) >= 0:
        raise ValueError(f"duplicate upstream connection: {call}")
    return text[:start] + replacement + text[end + 1 :]


def patch_model(source: str) -> str:
    if MARKER in source:
        raise ValueError("source model is already patched")

    source = replace_once(
        source,
        "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        PARAMETERS + "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        "parameter insertion",
    )
    source = replace_once(
        source,
        "\nequation\n",
        COMPONENTS + "\nequation\n" + EQUATIONS,
        "component/equation insertion",
    )

    source = replace_connect_statement(
        source,
        "ConstantVanneTurbineHP.y, vanne_entree_TurbineHP.Ouv",
        "  // VPP patch owns the HP admission-valve actuator equation.",
    )
    source = replace_connect_statement(
        source,
        "ConstantVanneTurbineMP.y, vanne_entree_TurbineMP.Ouv",
        "  // VPP patch owns the IP admission-valve actuator equation.",
    )
    source = replace_connect_statement(
        source,
        "regulation_Niveau_BP.SortieReelle1, vanne_vapeurBP.Ouv",
        "  // VPP patch multiplies LP drum level demand by the Trip isolation actuator.",
    )
    source = replace_connect_statement(
        source,
        "DoubleDebitHP.Cs, vanne_entree_TurbineHP.C1",
        "  connect(DoubleDebitHP.Cs, vppHPSplitter.Ce);\n"
        "  connect(vppHPSplitter.Cs1, vanne_entree_TurbineHP.C1);\n"
        "  connect(vppHPSplitter.Cs2, vppHPBypassValve.C1);",
    )
    source = replace_connect_statement(
        source,
        "TurbineHP.Cs, MoitieDebitHP.Ce",
        "  connect(TurbineHP.Cs, vppHPColdReheatMixer.Ce1);\n"
        "  connect(vppHPBypassMixer.Cs, vppHPColdReheatMixer.Ce2);\n"
        "  connect(vppHPColdReheatMixer.Cs, MoitieDebitHP.Ce);",
    )
    source = replace_connect_statement(
        source,
        "DoubleDebitMP.Cs, vanne_entree_TurbineMP.C1",
        "  connect(DoubleDebitMP.Cs, vppLPSplitter.Ce);\n"
        "  connect(vppLPSplitter.Cs1, vanne_entree_TurbineMP.C1);\n"
        "  connect(vppLPSplitter.Cs2, vppLPBypassValve.C1);",
    )
    source = replace_connect_statement(
        source,
        "perteChargeK1.C2, CapteurDebitVapCondenseur.C1",
        "  connect(perteChargeK1.C2, vppCondenserSteamMixer.Ce1);\n"
        "  connect(vppLPBypassMixer.Cs, vppCondenserSteamMixer.Ce2);\n"
        "  connect(vppCondenserSteamMixer.Cs, CapteurDebitVapCondenseur.C1);",
    )

    required = (
        "vppHPBypassValve",
        "vppLPBypassValve",
        "vppHPSplitter",
        "vppLPSplitter",
        "vppHPColdReheatMixer",
        "vppCondenserSteamMixer",
        "der(vppHPBypassPos)",
        "der(vppLPBypassPos)",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"patched model is missing {token}")
    return source


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if not args.source.is_file():
        parser.error("--source must point to the pinned CombinedCycle_TripTAC.mo")
    original = args.source.read_text(encoding="utf-8")
    patched = patch_model(original)
    encoded = patched.encode("utf-8")
    print(f"{MARKER} sha256={sha256(encoded)} bytes={len(encoded)}")
    if args.check_only:
        return 0

    destination = args.output or args.source
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=destination.parent,
            prefix=destination.name + ".",
            suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            stream.write(patched)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
