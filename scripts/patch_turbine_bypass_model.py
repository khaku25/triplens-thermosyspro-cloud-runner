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


MARKER = "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V13"


PARAMETERS = f'''  // {MARKER}
  model VPPRegularizedSplitter2
    "Two-way steam splitter with bounded IF97 evaluation during Newton trials"
    parameter Modelica.SIunits.AbsolutePressure pressureFloor=500
      "IF97 evaluation floor; the connector pressure itself is not clipped";
    parameter Integer fluid=1 "1: water/steam - 2: C3H3F5";
    parameter Integer mode=0 "IF97 region";
    Modelica.SIunits.AbsolutePressure P(start=10e5, min=0);
    Modelica.SIunits.AbsolutePressure Pthermo;
    Modelica.SIunits.SpecificEnthalpy h(start=10e5);
    Modelica.SIunits.Temperature T;
    Real alpha1;
    ThermoSysPro.WaterSteam.Connectors.FluidInlet Ce;
    ThermoSysPro.WaterSteam.Connectors.FluidOutlet Cs1;
    ThermoSysPro.WaterSteam.Connectors.FluidOutlet Cs2;
    ThermoSysPro.Properties.WaterSteam.Common.ThermoProperties_ph pro;
  equation
    P = Ce.P;
    P = Cs1.P;
    P = Cs2.P;
    Ce.h_vol = h;
    Cs1.h_vol = h;
    Cs2.h_vol = h;
    0 = Ce.Q - Cs1.Q - Cs2.Q;
    0 = Ce.Q*Ce.h - Cs1.Q*Cs1.h - Cs2.Q*Cs2.h;
    alpha1 = noEvent(if abs(Ce.Q) > 1e-6 then Cs1.Q/Ce.Q else 0);

    // OpenModelica's nonlinear solver may probe p=0 while iterating even
    // though the converged plant state remains positive. ThermoSysPro IF97
    // divides by p in that trial state. Bound only the property evaluation,
    // never the physical connector pressure or the pressure-flow equation.
    Pthermo = noEvent(max(pressureFloor, P));
    pro = ThermoSysPro.Properties.Fluid.Ph(Pthermo, h, mode, fluid);
    T = pro.T;
  end VPPRegularizedSplitter2;

  model VPPRegularizedMixingVolume
    "Three-inlet header with bounded IF97 evaluation during Newton trials"
    parameter Modelica.SIunits.Volume V=1;
    parameter Modelica.SIunits.AbsolutePressure P0=1e5;
    parameter Modelica.SIunits.SpecificEnthalpy h0=1e5;
    parameter Boolean dynamic_mass_balance=false;
    parameter Boolean steady_state=true;
    parameter Integer fluid=1;
    parameter Modelica.SIunits.Density p_rho=0;
    parameter Integer mode=0;
    parameter Modelica.SIunits.AbsolutePressure pressureFloor=500
      "IF97 evaluation floor; the connector pressure itself is not clipped";
    Modelica.SIunits.Temperature T;
    Modelica.SIunits.AbsolutePressure P(start=1e5, min=0);
    Modelica.SIunits.AbsolutePressure Pthermo;
    Modelica.SIunits.SpecificEnthalpy h(start=1e5);
    Modelica.SIunits.Density rho(start=10, min=1e-6);
    Modelica.SIunits.MassFlowRate BQ;
    Modelica.SIunits.Power BH;
    ThermoSysPro.WaterSteam.Connectors.FluidInlet Ce1;
    ThermoSysPro.WaterSteam.Connectors.FluidInlet Ce2;
    ThermoSysPro.WaterSteam.Connectors.FluidInlet Ce3;
    ThermoSysPro.WaterSteam.Connectors.FluidOutlet Cs;
    ThermoSysPro.Properties.WaterSteam.Common.ThermoProperties_ph pro;
  initial equation
    if steady_state then
      if dynamic_mass_balance then
        der(P) = 0;
      end if;
      der(h) = 0;
    else
      if dynamic_mass_balance then
        P = P0;
      end if;
      h = h0;
    end if;
  equation
    assert(V > 0, "Volume non-positive");
    BQ = Ce1.Q + Ce2.Q + Ce3.Q - Cs.Q;
    if dynamic_mass_balance then
      V*(pro.ddph*der(P) + pro.ddhp*der(h)) = BQ;
    else
      0 = BQ;
    end if;
    P = Ce1.P;
    P = Ce2.P;
    P = Ce3.P;
    P = Cs.P;
    BH = Ce1.Q*Ce1.h + Ce2.Q*Ce2.h + Ce3.Q*Ce3.h - Cs.Q*Cs.h;
    if dynamic_mass_balance then
      V*((h*pro.ddph - 1)*der(P) +
        (h*pro.ddhp + rho)*der(h)) = BH;
    else
      V*rho*der(h) = BH;
    end if;
    Ce1.h_vol = h;
    Ce2.h_vol = h;
    Ce3.h_vol = h;
    Cs.h_vol = h;
    Pthermo = noEvent(max(pressureFloor, P));
    pro = ThermoSysPro.Properties.Fluid.Ph(Pthermo, h, mode, fluid);
    T = pro.T;
    rho = if p_rho > 0 then p_rho else noEvent(max(1e-6, pro.d));
  end VPPRegularizedMixingVolume;

  model VPPPressureDrivenBypassValve
    "One-way Cv valve with a numerically isolated fully closed state"
    parameter ThermoSysPro.Units.Cv Cvmax=8000;
    parameter Modelica.SIunits.Density rhoNom=10
      "Normal inlet density used to regularize the short Trip transient";
    parameter Real closedEpsilon=1e-9;
    ThermoSysPro.InstrumentationAndControl.Connectors.InputReal Ouv;
    ThermoSysPro.WaterSteam.Connectors.FluidInlet C1;
    ThermoSysPro.WaterSteam.Connectors.FluidOutlet C2;
    ThermoSysPro.Units.Cv Cv(start=0);
    ThermoSysPro.Units.DifferentialPressure deltaP;
    Modelica.SIunits.MassFlowRate Q(start=0);
  equation
    C1.Q = C2.Q;
    C1.h = C2.h;
    C1.h = C1.h_vol;
    Q = C1.Q;
    Cv = Ouv.signal*Cvmax;
    deltaP = C1.P - C2.P;

    // A fully closed valve must not pull downstream pressure/enthalpy into
    // the upstream IF97 initialization loop. Once it begins to open, the
    // branch uses the same Cv pressure-flow correlation as ControlValve.
    if noEvent(Ouv.signal <= closedEpsilon) then
      Q = 0;
    else
      Q = Cv*rhoNom
        *sqrt(noEvent(max(0, deltaP))/1.733e12);
    end if;
  end VPPPressureDrivenBypassValve;

  model VPPFixedFlowInjector
    "Ideal one-way spray injector that separates source and header states"
    ThermoSysPro.WaterSteam.Connectors.FluidInlet C1;
    ThermoSysPro.WaterSteam.Connectors.FluidOutlet C2;
  equation
    C1.P = C2.P;
    C1.Q = C2.Q;
    C1.h = C2.h;
    C1.h = C1.h_vol;
  end VPPFixedFlowInjector;

  parameter Real vppTripTime(unit="s") = 600
    "Resolved ST Trip time for the physical GT Trip adapter";
  parameter Boolean vppUseExternalTripInput = false
    "Use the inherited FMU input instead of the scheduled Trip source";
  parameter Modelica.SIunits.MassFlowRate vppGTExhaustMassFlowNormal = 606.94;
  parameter Modelica.SIunits.MassFlowRate vppGTExhaustMassFlowTrip = 50;
  parameter Modelica.SIunits.Temperature vppGTExhaustTemperatureNormal = 893.75;
  parameter Modelica.SIunits.Temperature vppGTExhaustTemperatureTrip = 450;
  parameter Real vppGTExhaustResponseTau(unit="s") = 0.667
    "First-order live-command GT exhaust response time constant";
  parameter Real vppAdmissionStroke95(unit="s") = 0.150
    "HP/IP and LP-drum admission 95 percent closing time";
  parameter Real vppHPBypassStroke95(unit="s") = 0.300
    "HPBP 95 percent opening time";
  parameter Real vppLPBypassStroke95(unit="s") = 0.400
    "LPBP 95 percent opening time";
  parameter Real vppSprayStroke95(unit="s") = 0.050
    "Spray-water actuator 95 percent opening time";
  parameter Modelica.SIunits.MassFlowRate vppSpraySeatLeak = 0
    "Fully closed pre-Trip spray flow";
  parameter Real vppAdmissionSeatLeak = 1e-3
    "Numerical 0.1 percent turbine admission-valve seat leakage";
  parameter Real vppValveLeak = 0
    "Fully closed pre-Trip bypass position";
  parameter Modelica.SIunits.Volume vppHPHeaderVolume = 1
    "Preliminary cold-reheat mixing volume";
  parameter Modelica.SIunits.Volume vppLPHeaderVolume = 50
    "Preliminary condenser-inlet steam mixing volume";
  parameter Modelica.SIunits.MassFlowRate vppHPMainFlow0 = 151.7690991976083
    "Verified pre-Trip HP steam-flow initialization point";
  parameter Modelica.SIunits.MassFlowRate vppIPMainFlow0 = 176.7893383342879
    "Verified pre-Trip hot-reheat steam-flow initialization point";
  parameter Modelica.SIunits.MassFlowRate vppCondenserSteamFlow0 =
      196.6524916480812
    "Verified pre-Trip condenser steam-flow initialization point";
  parameter Modelica.SIunits.Density vppHPSteamDensity0 = 34
    "Normal HP-main-steam density used for Trip-transient regularization";
  parameter Modelica.SIunits.Density vppHotReheatSteamDensity0 = 6.5
    "Normal hot-reheat density used for Trip-transient regularization";
  parameter ThermoSysPro.Units.Cv vppHPBypassCvmax = 1890
    "HPBP Cv calibrated to the verified normal HP steam flow";
  parameter ThermoSysPro.Units.Cv vppLPBypassCvmax = 22000
    "LPBP Cv calibrated to the verified normal hot-reheat steam flow";
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
  input Boolean vppExternalTripCommand(start=false) = false
    "Live ECMS GT Trip input exposed by the Co-Simulation FMU";
  output Real vppExternalTripCommandNative(
    start=0, fixed=true, stateSelect=StateSelect.always)
    "Writable native OPC UA GT Trip command memory";
  discrete Boolean vppSTTripLatch(start=false, fixed=true)
    "One-way resolved ST Trip latch for this physical scenario";
  Real vppGTExhaustMassFlowState(
    unit="kg/s", start=vppGTExhaustMassFlowNormal, fixed=true);
  Real vppGTExhaustTemperatureState(
    unit="K", start=vppGTExhaustTemperatureNormal, fixed=true);
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppGTExhaustMassFlowCommand;
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppGTExhaustTemperatureCommand;
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

  VPPRegularizedSplitter2 vppHPSplitter(
    mode=2,
    P(start=12681000, nominal=1.3e7),
    h(start=3450835, nominal=3.5e6),
    Ce(Q(start=vppHPMainFlow0, nominal=200),
       h(start=3450835), h_vol(start=3450835)),
    Cs1(Q(start=vppHPMainFlow0, nominal=200),
        h(start=3450835), h_vol(start=3450835)),
    Cs2(Q(start=0, nominal=200),
        h(start=3248547.5), h_vol(start=3450835)));
  VPPPressureDrivenBypassValve vppHPBypassValve(
    Cvmax=vppHPBypassCvmax,
    rhoNom=vppHPSteamDensity0,
    Q(start=0, nominal=200),
    Cv(start=vppValveLeak*vppHPBypassCvmax),
    C1(P(start=12681000), Q(start=0, nominal=200),
       h(start=3248547.5), h_vol(start=3450835)),
    C2(P(start=2726700), Q(start=0, nominal=200),
       h(start=3248547.5), h_vol(start=3046260)));
  ThermoSysPro.WaterSteam.BoundaryConditions.SourceQ vppHPSpraySource(
    Q0=vppSpraySeatLeak, h0=1396866);
  VPPFixedFlowInjector vppHPSprayInjector;
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppHPSprayFlowCommand;
  VPPRegularizedMixingVolume vppHPColdReheatVolume(
    V=vppHPHeaderVolume,
    // Steam-cycle storage already supplies the pressure states. This header
    // contributes finite thermal hold-up without duplicating an ideal-node
    // pressure state.
    dynamic_mass_balance=false,
    steady_state=true,
    mode=0,
    P(start=2726700, nominal=3e6),
    h(start=3046260, nominal=3.2e6),
    Ce1(Q(start=vppHPMainFlow0, nominal=200),
        h(start=3046260), h_vol(start=3046260)),
    Ce2(Q(start=0, nominal=200),
        h(start=3248547.5), h_vol(start=3046260)),
    Ce3(Q(start=vppSpraySeatLeak, nominal=200),
        h(start=1396866), h_vol(start=3046260)),
    Cs(Q(start=vppHPMainFlow0, nominal=200),
       h(start=3046260), h_vol(start=3046260)));

  VPPRegularizedSplitter2 vppLPSplitter(
    mode=2,
    P(start=2548600, nominal=3e6),
    h(start=3523910, nominal=3.6e6),
    Ce(Q(start=vppIPMainFlow0, nominal=200),
       h(start=3523910), h_vol(start=3523910)),
    Cs1(Q(start=vppIPMainFlow0, nominal=200),
        h(start=3523910), h_vol(start=3523910)),
    Cs2(Q(start=0, nominal=200),
        h(start=2962470), h_vol(start=3523910)));
  VPPPressureDrivenBypassValve vppLPBypassValve(
    Cvmax=vppLPBypassCvmax,
    rhoNom=vppHotReheatSteamDensity0,
    Q(start=0, nominal=200),
    Cv(start=vppValveLeak*vppLPBypassCvmax),
    C1(P(start=2548600), Q(start=0, nominal=200),
       h(start=2962470), h_vol(start=3523910)),
    C2(P(start=6136), Q(start=0, nominal=200),
       h(start=2962470), h_vol(start=2401030)));
  ThermoSysPro.WaterSteam.BoundaryConditions.SourceQ vppLPSpraySource(
    Q0=vppSpraySeatLeak, h0=550000);
  VPPFixedFlowInjector vppLPSprayInjector;
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppLPSprayFlowCommand;
  VPPRegularizedMixingVolume vppCondenserSteamVolume(
    V=vppLPHeaderVolume,
    // Condenser pressure already supplies the LP-side mass-storage state.
    // This header retains its own thermal hold-up without duplicating that
    // pressure state across an ideal (zero-pressure-drop) sensor connection.
    dynamic_mass_balance=false,
    steady_state=true,
    mode=0,
    P(start=6136, nominal=1e4),
    h(start=2401030, nominal=2.5e6),
    Ce1(Q(start=vppCondenserSteamFlow0, nominal=200),
        h(start=2401030), h_vol(start=2401030)),
    Ce2(Q(start=0, nominal=200),
        h(start=2962470), h_vol(start=2401030)),
    Ce3(Q(start=vppSpraySeatLeak, nominal=200),
        h(start=550000), h_vol(start=2401030)),
    Cs(Q(start=vppCondenserSteamFlow0, nominal=200),
       h(start=2401030), h_vol(start=2401030)));
'''


EQUATIONS = '''
  // The native OPC UA server permits writes to continuous states. A negligible
  // derivative keeps this command memory as a state without affecting physics.
  der(vppExternalTripCommandNative) = Modelica.Constants.eps*sin(time);
  when (vppUseExternalTripInput and
        (vppExternalTripCommand or vppExternalTripCommandNative >= 0.5)) or
       ((not vppUseExternalTripInput) and time >= vppTripTime) then
    vppSTTripLatch = true;
  end when;
  der(vppGTExhaustMassFlowState) =
    ((if vppSTTripLatch then vppGTExhaustMassFlowTrip
      else vppGTExhaustMassFlowNormal) - vppGTExhaustMassFlowState)
      /vppGTExhaustResponseTau;
  der(vppGTExhaustTemperatureState) =
    ((if vppSTTripLatch then vppGTExhaustTemperatureTrip
      else vppGTExhaustTemperatureNormal) - vppGTExhaustTemperatureState)
      /vppGTExhaustResponseTau;
  vppGTExhaustMassFlowCommand.signal = if vppUseExternalTripInput then
    vppGTExhaustMassFlowState else Debit.y.signal;
  vppGTExhaustTemperatureCommand.signal = if vppUseExternalTripInput then
    vppGTExhaustTemperatureState else Temperature.y.signal;
  vppHPBypassCmd = if vppSTTripLatch then 1 else vppValveLeak;
  vppLPBypassCmd = if vppSTTripLatch then 1 else vppValveLeak;

  der(vppHPAdmissionPos) =
    ((if vppSTTripLatch then vppAdmissionSeatLeak else 0.8)
      - vppHPAdmissionPos)
      /vppAdmissionTau;
  der(vppIPAdmissionPos) =
    ((if vppSTTripLatch then vppAdmissionSeatLeak else 0.8)
      - vppIPAdmissionPos)
      /vppAdmissionTau;
  der(vppLPDrumAdmissionMultiplier) =
    ((if vppSTTripLatch then vppAdmissionSeatLeak else 1)
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
  vppHPBypassOutletPressure = vppHPColdReheatVolume.P;
  vppLPBypassOutletPressure = vppCondenserSteamVolume.P;
  vppHPBypassInletTemperature = vppHPSplitter.T;
  vppLPBypassInletTemperature = vppLPSplitter.T;
  vppHPBypassOutletTemperature = vppHPColdReheatVolume.T;
  vppLPBypassOutletTemperature = vppCondenserSteamVolume.T;
  vppCondenserPressure = Condenseur.P;
  vppCondenserLevel = Condenseur.yNiveau.signal;

  vanne_entree_TurbineHP.Ouv.signal = vppHPAdmissionPos;
  vanne_entree_TurbineMP.Ouv.signal = vppIPAdmissionPos;
  vanne_vapeurBP.Ouv.signal =
    regulation_Niveau_BP.SortieReelle1.signal*vppLPDrumAdmissionMultiplier;
  vppHPBypassValve.Ouv.signal = vppHPBypassPos;
  vppLPBypassValve.Ouv.signal = vppLPBypassPos;
  vppHPSprayFlowCommand.signal = noEvent(max(vppSpraySeatLeak,
    max(0, vppHPBypassValve.Q)*vppHPSprayRatio*vppHPSprayPos));
  vppLPSprayFlowCommand.signal = noEvent(max(vppSpraySeatLeak,
    max(0, vppLPBypassValve.Q)*vppLPSprayRatio*vppLPSprayPos));

  connect(vppHPSprayFlowCommand, vppHPSpraySource.IMassFlow);
  connect(vppHPBypassValve.C2, vppHPColdReheatVolume.Ce2);
  connect(vppHPSpraySource.C, vppHPSprayInjector.C1);
  connect(vppHPSprayInjector.C2, vppHPColdReheatVolume.Ce3);
  connect(vppLPSprayFlowCommand, vppLPSpraySource.IMassFlow);
  connect(vppLPBypassValve.C2, vppCondenserSteamVolume.Ce2);
  connect(vppLPSpraySource.C, vppLPSprayInjector.C1);
  connect(vppLPSprayInjector.C2, vppCondenserSteamVolume.Ce3);
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
        "Temperature.y,SourceFumees. ITemperature",
        "  connect(vppGTExhaustTemperatureCommand, SourceFumees.ITemperature);",
    )
    source = replace_connect_statement(
        source,
        "Debit.y,SourceFumees. IMassFlow",
        "  connect(vppGTExhaustMassFlowCommand, SourceFumees.IMassFlow);",
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
        "  connect(TurbineHP.Cs, vppHPColdReheatVolume.Ce1);\n"
        "  connect(vppHPColdReheatVolume.Cs, MoitieDebitHP.Ce);",
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
        "  connect(perteChargeK1.C2, vppCondenserSteamVolume.Ce1);\n"
        "  connect(vppCondenserSteamVolume.Cs, CapteurDebitVapCondenseur.C1);",
    )

    required = (
        "vppHPBypassValve",
        "vppLPBypassValve",
        "vppHPSplitter",
        "vppLPSplitter",
        "vppHPColdReheatVolume",
        "vppCondenserSteamVolume",
        "der(vppHPBypassPos)",
        "der(vppLPBypassPos)",
        "vppExternalTripCommand",
        "vppGTExhaustMassFlowCommand",
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
