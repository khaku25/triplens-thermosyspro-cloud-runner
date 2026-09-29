within;

model TripLens_V42_Bypass_Acceptance
  "Fast acceptance test for the TripLens HP/LP bypass on ThermoSysPro 4.2"

  parameter Real tripTime(unit="s") = 0.05;
  parameter Real hpStroke95(unit="s") = 0.30;
  parameter Real lpStroke95(unit="s") = 0.40;
  parameter Real hpTau(unit="s") = hpStroke95/(-log(0.05));
  parameter Real lpTau(unit="s") = lpStroke95/(-log(0.05));

  parameter Real hpInletPressure(unit="Pa") = 12681000;
  parameter Real hpOutletPressure(unit="Pa") = 2726700;
  parameter Real hpEnthalpy(unit="J/kg") = 3450835;
  parameter Real hpDensity(unit="kg/m3") = 34;
  parameter ThermoSysPro.Units.xSI.Cv hpCvmax = 1890;

  parameter Real lpInletPressure(unit="Pa") = 2548600;
  parameter Real lpOutletPressure(unit="Pa") = 6136;
  parameter Real lpEnthalpy(unit="J/kg") = 3523910;
  parameter Real lpDensity(unit="kg/m3") = 6.5;
  parameter ThermoSysPro.Units.xSI.Cv lpCvmax = 22000;

  Boolean tripCommand;
  Real hpPosition(start=0, fixed=true, min=0, max=1);
  Real lpPosition(start=0, fixed=true, min=0, max=1);
  Real hpExpectedFlow(unit="kg/s");
  Real lpExpectedFlow(unit="kg/s");
  Real hpFlowRelativeError;
  Real lpFlowRelativeError;

  ThermoSysPro.WaterSteam.BoundaryConditions.SourceP hpCustomSource(
    P0=hpInletPressure, h0=hpEnthalpy, option_temperature=2);
  ThermoSysPro.WaterSteam.BoundaryConditions.SinkP hpCustomSink(
    P0=hpOutletPressure, h0=hpEnthalpy, option_temperature=2);
  TripLensUserModels_Bypass.CombinedCycle_TripTAC_Bypass.VPPPressureDrivenBypassValve
    hpBypass(
      Cvmax=hpCvmax,
      rhoNom=hpDensity,
      closedEpsilon=1e-9);

  ThermoSysPro.WaterSteam.BoundaryConditions.SourceP hpReferenceSource(
    P0=hpInletPressure, h0=hpEnthalpy, option_temperature=2);
  ThermoSysPro.WaterSteam.BoundaryConditions.SinkP hpReferenceSink(
    P0=hpOutletPressure, h0=hpEnthalpy, option_temperature=2);
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve hpReference(
    Cvmax=hpCvmax, p_rho=hpDensity, mode=2);

  ThermoSysPro.WaterSteam.BoundaryConditions.SourceP lpCustomSource(
    P0=lpInletPressure, h0=lpEnthalpy, option_temperature=2);
  ThermoSysPro.WaterSteam.BoundaryConditions.SinkP lpCustomSink(
    P0=lpOutletPressure, h0=lpEnthalpy, option_temperature=2);
  TripLensUserModels_Bypass.CombinedCycle_TripTAC_Bypass.VPPPressureDrivenBypassValve
    lpBypass(
      Cvmax=lpCvmax,
      rhoNom=lpDensity,
      closedEpsilon=1e-9);

  ThermoSysPro.WaterSteam.BoundaryConditions.SourceP lpReferenceSource(
    P0=lpInletPressure, h0=lpEnthalpy, option_temperature=2);
  ThermoSysPro.WaterSteam.BoundaryConditions.SinkP lpReferenceSink(
    P0=lpOutletPressure, h0=lpEnthalpy, option_temperature=2);
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve lpReference(
    Cvmax=lpCvmax, p_rho=lpDensity, mode=2);

equation
  tripCommand = time >= tripTime;
  der(hpPosition) = ((if tripCommand then 1 else 0) - hpPosition)/hpTau;
  der(lpPosition) = ((if tripCommand then 1 else 0) - lpPosition)/lpTau;

  hpBypass.Ouv.signal = hpPosition;
  hpReference.Ouv.signal = hpPosition;
  lpBypass.Ouv.signal = lpPosition;
  lpReference.Ouv.signal = lpPosition;

  hpExpectedFlow = hpPosition*hpCvmax*hpDensity
    *sqrt((hpInletPressure - hpOutletPressure)/1.733e12);
  lpExpectedFlow = lpPosition*lpCvmax*lpDensity
    *sqrt((lpInletPressure - lpOutletPressure)/1.733e12);
  hpFlowRelativeError = abs(hpBypass.Q - hpReference.Q)
    /max(1, abs(hpReference.Q));
  lpFlowRelativeError = abs(lpBypass.Q - lpReference.Q)
    /max(1, abs(lpReference.Q));

  assert(noEvent(hpBypass.Q >= -1e-8),
    "HP bypass produced reverse flow");
  assert(noEvent(lpBypass.Q >= -1e-8),
    "LP bypass produced reverse flow");

  connect(hpCustomSource.C, hpBypass.C1);
  connect(hpBypass.C2, hpCustomSink.C);
  connect(hpReferenceSource.C, hpReference.C1);
  connect(hpReference.C2, hpReferenceSink.C);
  connect(lpCustomSource.C, lpBypass.C1);
  connect(lpBypass.C2, lpCustomSink.C);
  connect(lpReferenceSource.C, lpReference.C1);
  connect(lpReference.C2, lpReferenceSink.C);

  annotation(experiment(StartTime=0, StopTime=0.5, Interval=0.005,
    Tolerance=1e-6));
end TripLens_V42_Bypass_Acceptance;
