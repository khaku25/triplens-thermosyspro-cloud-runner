within ;
model TripLens_CombinedCycle_TripTAC_ProcessView_v36 "CCPP model to simulate a load variation from 100% to 50%"
  // Single-class v36 physical model and dynamic OMEdit process view.
  // Existing top-level vpp* names remain compatible with the native OPC UA contract.
  // TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V13

  model VPPRegularizedSplitter2 "Two-way steam splitter with bounded IF97 evaluation during Newton trials"
    parameter Modelica.SIunits.AbsolutePressure pressureFloor = 500 "IF97 evaluation floor; the connector pressure itself is not clipped";
    parameter Integer fluid = 1 "1: water/steam - 2: C3H3F5";
    parameter Integer mode = 0 "IF97 region";
    Modelica.SIunits.AbsolutePressure P(start = 10e5, min = 0);
    Modelica.SIunits.AbsolutePressure Pthermo;
    Modelica.SIunits.SpecificEnthalpy h(start = 10e5);
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

  model VPPRegularizedMixingVolume "Three-inlet header with bounded IF97 evaluation during Newton trials"
    parameter Modelica.SIunits.Volume V = 1;
    parameter Modelica.SIunits.AbsolutePressure P0 = 1e5;
    parameter Modelica.SIunits.SpecificEnthalpy h0 = 1e5;
    parameter Boolean dynamic_mass_balance = false;
    parameter Boolean steady_state = true;
    parameter Integer fluid = 1;
    parameter Modelica.SIunits.Density p_rho = 0;
    parameter Integer mode = 0;
    parameter Modelica.SIunits.AbsolutePressure pressureFloor = 500 "IF97 evaluation floor; the connector pressure itself is not clipped";
    Modelica.SIunits.Temperature T;
    Modelica.SIunits.AbsolutePressure P(start = 1e5, min = 0);
    Modelica.SIunits.AbsolutePressure Pthermo;
    Modelica.SIunits.SpecificEnthalpy h(start = 1e5);
    Modelica.SIunits.Density rho(start = 10, min = 1e-6);
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
      V*((h*pro.ddph - 1)*der(P) + (h*pro.ddhp + rho)*der(h)) = BH;
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

  model VPPPressureDrivenBypassValve "One-way Cv valve with a numerically isolated fully closed state"
    parameter ThermoSysPro.Units.Cv Cvmax = 8000;
    parameter Modelica.SIunits.Density rhoNom = 10 "Normal inlet density used to regularize the short Trip transient";
    parameter Real closedEpsilon = 1e-9;
    ThermoSysPro.InstrumentationAndControl.Connectors.InputReal Ouv;
    ThermoSysPro.WaterSteam.Connectors.FluidInlet C1;
    ThermoSysPro.WaterSteam.Connectors.FluidOutlet C2;
    ThermoSysPro.Units.Cv Cv(start = 0);
    ThermoSysPro.Units.DifferentialPressure deltaP;
    Modelica.SIunits.MassFlowRate Q(start = 0);
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
      Q = Cv*rhoNom*sqrt(noEvent(max(0, deltaP))/1.733e12);
    end if;
  end VPPPressureDrivenBypassValve;

  model VPPFixedFlowInjector "Ideal one-way spray injector that separates source and header states"
    ThermoSysPro.WaterSteam.Connectors.FluidInlet C1;
    ThermoSysPro.WaterSteam.Connectors.FluidOutlet C2;
  equation
    C1.P = C2.P;
    C1.Q = C2.Q;
    C1.h = C2.h;
    C1.h = C1.h_vol;
  end VPPFixedFlowInjector;

  parameter Real vppTripTime(unit = "s") = 600 "Resolved ST Trip time for the physical GT Trip adapter";
  parameter Boolean vppUseExternalTripInput = true "Use the inherited FMU input instead of the scheduled Trip source";
  parameter Modelica.SIunits.MassFlowRate vppGTExhaustMassFlowNormal = 606.94;
  parameter Modelica.SIunits.MassFlowRate vppGTExhaustMassFlowTrip = 50;
  parameter Modelica.SIunits.Temperature vppGTExhaustTemperatureNormal = 893.75;
  parameter Modelica.SIunits.Temperature vppGTExhaustTemperatureTrip = 450;
  parameter Real vppGTExhaustResponseTau(unit = "s") = 0.667 "First-order live-command GT exhaust response time constant";
  // The trip valves are physical first-order actuators.  A sub-200 ms
  // admission closure against the finite HRSG volumes creates a numerical
  // pressure impulse in the pinned ThermoSysPro 3.1 two-phase pipes; these
  // plant-realistic stroke times preserve the trip while keeping absolute
  // pressure positive through the 100 s validation window.
  parameter Real vppAdmissionStroke95(unit = "s") = 1.000 "HP/IP and LP-drum admission 95 percent closing time";
  parameter Real vppHPBypassStroke95(unit = "s") = 2.000 "HPBP 95 percent opening time";
  parameter Real vppLPBypassStroke95(unit = "s") = 2.000 "LPBP 95 percent opening time";
  parameter Real vppSprayStroke95(unit = "s") = 0.500 "Spray-water actuator 95 percent opening time";
  parameter Modelica.SIunits.MassFlowRate vppSpraySeatLeak = 0 "Fully closed pre-Trip spray flow";
  parameter Real vppAdmissionSeatLeak = 1e-3 "Numerical 0.1 percent turbine admission-valve seat leakage";
  parameter Real vppValveLeak = 0 "Fully closed pre-Trip bypass position";
  parameter Modelica.SIunits.Volume vppHPHeaderVolume = 1 "Preliminary cold-reheat mixing volume";
  parameter Modelica.SIunits.Volume vppLPHeaderVolume = 50 "Preliminary condenser-inlet steam mixing volume";
  parameter Modelica.SIunits.MassFlowRate vppHPMainFlow0 = 151.7690991976083 "Verified pre-Trip HP steam-flow initialization point";
  parameter Modelica.SIunits.MassFlowRate vppIPMainFlow0 = 176.7893383342879 "Verified pre-Trip hot-reheat steam-flow initialization point";
  parameter Modelica.SIunits.MassFlowRate vppCondenserSteamFlow0 = 196.6524916480812 "Verified pre-Trip condenser steam-flow initialization point";
  parameter Modelica.SIunits.Density vppHPSteamDensity0 = 34 "Normal HP-main-steam density used for Trip-transient regularization";
  parameter Modelica.SIunits.Density vppHotReheatSteamDensity0 = 6.5 "Normal hot-reheat density used for Trip-transient regularization";
  parameter ThermoSysPro.Units.Cv vppHPBypassCvmax = 1890 "HPBP Cv calibrated to the verified normal HP steam flow";
  parameter ThermoSysPro.Units.Cv vppLPBypassCvmax = 22000 "LPBP Cv calibrated to the verified normal hot-reheat steam flow";
  parameter Real vppHPSprayRatio = 0.245289 "HP spray-water mass flow divided by measured HPBP steam flow";
  parameter Real vppLPSprayRatio = 0.383212 "LP spray-water mass flow divided by measured LPBP steam flow";
  parameter Real vppAdmissionTau(unit = "s") = vppAdmissionStroke95/(-log(0.05));
  parameter Real vppHPBypassTau(unit = "s") = vppHPBypassStroke95/(-log(0.05));
  parameter Real vppLPBypassTau(unit = "s") = vppLPBypassStroke95/(-log(0.05));
  parameter Real vppSprayTau(unit = "s") = vppSprayStroke95/(-log(0.05));
  // TRIPLENS_LP_FWP_OPCUA_ADAPTER_V1
  TripLens_PumpPhysics.BreakerInertialPumpDrive vppLPFWPDrive(nominalSpeedRpm = 1400, J = 300, frictionTorqueNominal = 20, initialTorque = 4200, torqueLimit = 6e4) annotation(
    Placement(visible = false, transformation(extent = {{700, -500}, {740, -470}})));
  parameter Real vppLPFWPHydraulicSpeedFloorRPM(unit = "rev/min") = 700 "Numerical floor for the upstream static pump curve; shaft speed remains physical";
  // TRIPLENS_CHECK_VALVE_HVOL_INIT_V2: match the native LP pump discharge
  // control-volume enthalpy at the common adapter boundary.
  TripLens_PumpPhysics.SpringLoadedCheckValve vppLPFWPCheckValve(
    closeFlow = 70, closedResistance = 1e5,
    C1(h_vol(start = 194669.0)), C2(h_vol(start = 194669.0))) annotation(
    Placement(visible = false, transformation(extent = {{739, -446}, {759, -426}})));
  // TRIPLENS_LP_BFP_OPERATOR_CHAIN_V1
  input Real vppLPFWPTripPushbuttonNative(start=0)
    "Operator LP BFP Trip pushbutton; external OPC UA input";
  input Real vppLPFWPResetPushbuttonNative(start=0)
    "Operator LP BFP reset pushbutton; external OPC UA input";
  output Real vppLPFWPTripCommandNative
    "LP BFP Trip command generated from operator pushbutton";
  output Real vppLPFWPTripLatchNative
    "Latched LP BFP protection state";
  output Real vppVCBA02TripCommandNative
    "VCB-A02 Trip command generated by the LP BFP Trip latch";
  discrete Real vppLPFWPTripLatchState(start=0, fixed=true)
    "Internal LP BFP Trip latch memory";
  input Real vppVCBA02ClosedNative(start = 1);
  output Boolean vppLPFWPMotorEnergized;
  output Boolean vppLPFWPSpeedProven;
  output Boolean vppLPFWPRunning;
  output Real vppLPFWPSpeedRPM(unit = "rev/min");
  output Real vppLPFWPHydraulicSpeedRPM(unit = "rev/min");
  output Boolean vppLPFWPCheckValveOpen;
  output Real vppLPFWPCheckValveOpening(min = 0, max = 1);
  output Real vppLPFWPMassFlowTH(unit = "t/h");
  output Real vppLPFWPVolumeFlowM3S(unit = "m3/s");
  output Real vppLPFWPDeltaPPa(unit = "Pa");
  output Real vppLPFWPMechanicalPowerW(unit = "W");
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppLPFWPHydraulicSpeedCommand annotation(
    Placement(visible = false, transformation(extent = {{660, -500}, {690, -470}})));
  // TRIPLENS_HP_IP_FWP_INERTIAL_DRIVES_V8_6
  // HP/IP now use the same validated breaker/inertia boundary as LP.  The
  // legacy Ramp drivers are removed below so a BFP trip can actually remove
  // motor torque, reduce pump speed, close the discharge NRV and lower drum
  // inventory.  The numerical floor keeps the StaticCentrifugalPump finite
  // at standstill; the exposed shaft speed remains the physical state.
  TripLens_PumpPhysics.BreakerInertialPumpDrive vppHPFWPDrive(
    nominalSpeedRpm = 1400, J = 300, frictionTorqueNominal = 20,
    initialTorque = 24000, torqueLimit = 8e4) annotation(
    Placement(visible = false, transformation(extent = {{660, -40}, {700, -10}})));
  // TRIPLENS_IP_BFP_COASTDOWN_V8_7: the IP train is materially smaller than
  // the LP reference train.  Its lower rotating inertia preserves the same
  // breaker -> shaft -> static-pump boundary while targeting the existing 700
  // rpm numerical pump-curve floor inside the dedicated 45 s equipment-only
  // proof window.  The action run remains the physical acceptance check.
  TripLens_PumpPhysics.BreakerInertialPumpDrive vppIPFWPDrive(
    nominalSpeedRpm = 1400, J = 100, frictionTorqueNominal = 20,
    initialTorque = 12000, torqueLimit = 8e4) annotation(
    Placement(visible = false, transformation(extent = {{660, 0}, {700, 30}})));
  parameter Real vppHPFWPHydraulicSpeedFloorRPM(unit = "rev/min") = 700
    "Numerical floor for the HP upstream static pump curve";
  parameter Real vppIPFWPHydraulicSpeedFloorRPM(unit = "rev/min") = 700
    "Numerical floor for the IP upstream static pump curve";
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppHPFWPHydraulicSpeedCommand annotation(
      Placement(visible = false, transformation(extent = {{620, -40}, {650, -10}})));
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
    vppIPFWPHydraulicSpeedCommand annotation(
      Placement(visible = false, transformation(extent = {{620, 0}, {650, 30}})));
  output Real vppHPFWPHydraulicSpeedRPM(unit = "rev/min");
  output Real vppIPFWPHydraulicSpeedRPM(unit = "rev/min");
  // TRIPLENS_ALL_FWP_CHECK_VALVES_OPCUA_V1
  // TRIPLENS_CHECK_VALVE_HVOL_INIT_V2: HP pump discharge start state.
  TripLens_PumpPhysics.SpringLoadedCheckValve vppHPFWPCheckValve(
    closeFlow = 20, closedResistance = 1e5,
    C1(h_vol(start = 630000.0)), C2(h_vol(start = 630000.0))) annotation(
    Placement(visible = false, transformation(extent = {{747, -82}, {767, -62}})));
  // TRIPLENS_CHECK_VALVE_HVOL_INIT_V2: IP pump discharge start state.
  TripLens_PumpPhysics.SpringLoadedCheckValve vppIPFWPCheckValve(
    closeFlow = 5, closedResistance = 1e5,
    C1(h_vol(start = 561000.0)), C2(h_vol(start = 561000.0))) annotation(
    Placement(visible = false, transformation(extent = {{747, -122}, {767, -102}})));
  output Boolean vppHPFWPCheckValveOpen;
  output Real vppHPFWPCheckValveOpening(min = 0, max = 1);
  output Real vppHPFWPCheckValveMassFlowTH(unit = "t/h");
  output Real vppHPFWPCheckValveDeltaPPa(unit = "Pa");
  output Real vppHPFWPCheckValveInletPressurePa(unit = "Pa");
  output Real vppHPFWPCheckValveOutletPressurePa(unit = "Pa");
  output Real vppHPFWPCheckValveResistancePaSPerKg(unit = "Pa.s/kg");
  output Boolean vppIPFWPCheckValveOpen;
  output Real vppIPFWPCheckValveOpening(min = 0, max = 1);
  output Real vppIPFWPCheckValveMassFlowTH(unit = "t/h");
  output Real vppIPFWPCheckValveDeltaPPa(unit = "Pa");
  output Real vppIPFWPCheckValveInletPressurePa(unit = "Pa");
  output Real vppIPFWPCheckValveOutletPressurePa(unit = "Pa");
  output Real vppIPFWPCheckValveResistancePaSPerKg(unit = "Pa.s/kg");
  output Real vppLPFWPCheckValveMassFlowTH(unit = "t/h");
  output Real vppLPFWPCheckValveDeltaPPa(unit = "Pa");
  output Real vppLPFWPCheckValveInletPressurePa(unit = "Pa");
  output Real vppLPFWPCheckValveOutletPressurePa(unit = "Pa");
  output Real vppLPFWPCheckValveResistancePaSPerKg(unit = "Pa.s/kg");
  // TRIPLENS_ECMS_5605_SINGLE_SERVER_NODES_V1
  // Writable OpenModelica states. They are intentionally isolated from
  // the ThermoSysPro hydraulic equations so the proven NLS is unchanged.
  input Real vppECMS52GTClosedCommandNative(start = 1);
  input Real vppECMS52STClosedCommandNative(start = 1);
  input Real vppECMSCBInAClosedCommandNative(start = 1);
  input Real vppECMSCBInBClosedCommandNative(start = 1);
  input Real vppECMSCBTieClosedCommandNative(start = 0);
  input Real vppVCBA01ClosedNative(start = 1);
  input Real vppVCBB01ClosedNative(start = 1);
  output Boolean vppECMSCBInAClosed;
  output Boolean vppECMSCBInBClosed;
  output Boolean vppECMSCBTieClosed;
  output Boolean vppECMSBusAAvailable;
  output Boolean vppECMSBusBAvailable;
  output Boolean vppECMSVCBA01Closed;
  output Boolean vppECMSVCBA02Closed;
  output Boolean vppECMSVCBB01Closed;
  // TRIPLENS_OPCUA_RUN_DRIVEN_LIVE_V2: 56 unbound real command inputs; no Boolean input-index collision
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2
  // Only the four writable commands are independent states.
  // Cv, flow and dP are algebraic aliases: no telemetry dynamics enter initialization.
  // TRIPLENS_DRUM_FAULT_STROKE_V8_8: a drum fault must remain a physical
  // valve movement, not a discontinuous Cv jump.  ThermoSysPro's static
  // ControlValve algebra divides by Cv^2, so a finite 5% seat-leak opening
  // and a two-second stroke avoid the singularity without changing normal
  // automatic/manual commands.  Fault inputs remain excluded from RAW.csv.
  parameter Real vppDrumFaultValveMinimumOpening(min = 0, max = 0.1) = 0.05
    "Finite valve opening retained only during a drum fault override";
  parameter Modelica.SIunits.Time vppDrumFaultValveStrokeTime(min = 0.1) = 2
    "Physical travel time used only while a drum-fault override is active";
  // TRIPLENS_DRUM_INVENTORY_FAULT_PATH_V1
  // The 12-scenario verifier drives these commands through three spare
  // DynamicDrum liquid connections.  A positive command is a finite physical
  // makeup inflow; a negative command is a finite liquid-loss outflow.  They
  // never write the drum level, protection cause or trip latch directly.
  parameter Modelica.SIunits.MassFlowRate vppHPDrumInventoryFaultCapacity = 250
    "Maximum HP physical drum inventory disturbance";
  parameter Modelica.SIunits.MassFlowRate vppIPDrumInventoryFaultCapacity = 250
    "Maximum IP physical drum inventory disturbance";
  parameter Modelica.SIunits.MassFlowRate vppLPDrumInventoryFaultCapacity = 160
    "Maximum LP physical drum inventory disturbance";
  input Real vppHPDrumInventoryFaultEnableNative(start=0);
  input Real vppHPDrumInventoryFaultValueNative(start=0, min=-1, max=1);
  output Boolean vppHPDrumInventoryFaultActive;
  output Real vppHPDrumInventoryDisturbanceMassFlowTH(unit="t/h");
  input Real vppIPDrumInventoryFaultEnableNative(start=0);
  input Real vppIPDrumInventoryFaultValueNative(start=0, min=-1, max=1);
  output Boolean vppIPDrumInventoryFaultActive;
  output Real vppIPDrumInventoryDisturbanceMassFlowTH(unit="t/h");
  input Real vppLPDrumInventoryFaultEnableNative(start=0);
  input Real vppLPDrumInventoryFaultValueNative(start=0, min=-1, max=1);
  output Boolean vppLPDrumInventoryFaultActive;
  output Real vppLPDrumInventoryDisturbanceMassFlowTH(unit="t/h");
  input Real vppVlvHPFWCVModeAutoNative(start=1);
  input Real vppVlvHPFWCVManualCmdNative(start=0.8, min=0, max=1);
  input Real vppVlvHPFWCVFaultEnableNative(start=0);
  input Real vppVlvHPFWCVFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvHPFWCVAutoCmd(min=0, max=1);
  output Real vppVlvHPFWCVCmd(min=0, max=1);
  output Real vppVlvHPFWCVFb(min=0, max=1);
  output Real vppVlvHPFWCVDeviation;
  output Boolean vppVlvHPFWCVFaultActive;
  output Real vppVlvHPFWCVCv;
  output Real vppVlvHPFWCVMassFlowTH(unit="t/h");
  output Real vppVlvHPFWCVDPPa(unit="Pa");
  Real vppVlvHPFWCVTarget(min=0, max=1);
  Real vppVlvHPFWCVFaultStroke(min=0, max=1, start=0.8, fixed=true);
  input Real vppVlvHPSteamModeAutoNative(start=1);
  input Real vppVlvHPSteamManualCmdNative(start=0.5, min=0, max=1);
  input Real vppVlvHPSteamFaultEnableNative(start=0);
  input Real vppVlvHPSteamFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvHPSteamAutoCmd(min=0, max=1);
  output Real vppVlvHPSteamCmd(min=0, max=1);
  output Real vppVlvHPSteamFb(min=0, max=1);
  output Real vppVlvHPSteamDeviation;
  output Boolean vppVlvHPSteamFaultActive;
  output Real vppVlvHPSteamCv;
  output Real vppVlvHPSteamMassFlowTH(unit="t/h");
  output Real vppVlvHPSteamDPPa(unit="Pa");
  Real vppVlvHPSteamTarget(min=0, max=1);
  Real vppVlvHPSteamFaultStroke(min=0, max=1, start=0.5, fixed=true);
  input Real vppVlvIPFWCVModeAutoNative(start=1);
  input Real vppVlvIPFWCVManualCmdNative(start=0.8, min=0, max=1);
  input Real vppVlvIPFWCVFaultEnableNative(start=0);
  input Real vppVlvIPFWCVFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvIPFWCVAutoCmd(min=0, max=1);
  output Real vppVlvIPFWCVCmd(min=0, max=1);
  output Real vppVlvIPFWCVFb(min=0, max=1);
  output Real vppVlvIPFWCVDeviation;
  output Boolean vppVlvIPFWCVFaultActive;
  output Real vppVlvIPFWCVCv;
  output Real vppVlvIPFWCVMassFlowTH(unit="t/h");
  output Real vppVlvIPFWCVDPPa(unit="Pa");
  Real vppVlvIPFWCVTarget(min=0, max=1);
  Real vppVlvIPFWCVFaultStroke(min=0, max=1, start=0.8, fixed=true);
  input Real vppVlvIPSteamModeAutoNative(start=1);
  input Real vppVlvIPSteamManualCmdNative(start=0.5, min=0, max=1);
  input Real vppVlvIPSteamFaultEnableNative(start=0);
  input Real vppVlvIPSteamFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvIPSteamAutoCmd(min=0, max=1);
  output Real vppVlvIPSteamCmd(min=0, max=1);
  output Real vppVlvIPSteamFb(min=0, max=1);
  output Real vppVlvIPSteamDeviation;
  output Boolean vppVlvIPSteamFaultActive;
  output Real vppVlvIPSteamCv;
  output Real vppVlvIPSteamMassFlowTH(unit="t/h");
  output Real vppVlvIPSteamDPPa(unit="Pa");
  Real vppVlvIPSteamTarget(min=0, max=1);
  Real vppVlvIPSteamFaultStroke(min=0, max=1, start=0.5, fixed=true);
  input Real vppVlvLPSteamModeAutoNative(start=1);
  input Real vppVlvLPSteamManualCmdNative(start=0.8, min=0, max=1);
  input Real vppVlvLPSteamFaultEnableNative(start=0);
  input Real vppVlvLPSteamFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvLPSteamAutoCmd(min=0, max=1);
  output Real vppVlvLPSteamCmd(min=0, max=1);
  output Real vppVlvLPSteamFb(min=0, max=1);
  output Real vppVlvLPSteamDeviation;
  output Boolean vppVlvLPSteamFaultActive;
  output Real vppVlvLPSteamCv;
  output Real vppVlvLPSteamMassFlowTH(unit="t/h");
  output Real vppVlvLPSteamDPPa(unit="Pa");
  Real vppVlvLPSteamTarget(min=0, max=1);
  Real vppVlvLPSteamFaultStroke(min=0, max=1, start=0.8, fixed=true);
  input Real vppVlvLPFWModeAutoNative(start=1);
  input Real vppVlvLPFWManualCmdNative(start=0.5, min=0, max=1);
  input Real vppVlvLPFWFaultEnableNative(start=0);
  input Real vppVlvLPFWFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvLPFWAutoCmd(min=0, max=1);
  output Real vppVlvLPFWCmd(min=0, max=1);
  output Real vppVlvLPFWFb(min=0, max=1);
  output Real vppVlvLPFWDeviation;
  output Boolean vppVlvLPFWFaultActive;
  output Real vppVlvLPFWCv;
  output Real vppVlvLPFWMassFlowTH(unit="t/h");
  output Real vppVlvLPFWDPPa(unit="Pa");
  Real vppVlvLPFWTarget(min=0, max=1);
  Real vppVlvLPFWFaultStroke(min=0, max=1, start=0.5, fixed=true);
  input Real vppVlvLPToHPIPFWModeAutoNative(start=1);
  input Real vppVlvLPToHPIPFWManualCmdNative(start=1, min=0, max=1);
  input Real vppVlvLPToHPIPFWFaultEnableNative(start=0);
  input Real vppVlvLPToHPIPFWFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvLPToHPIPFWAutoCmd(min=0, max=1);
  output Real vppVlvLPToHPIPFWCmd(min=0, max=1);
  output Real vppVlvLPToHPIPFWFb(min=0, max=1);
  output Real vppVlvLPToHPIPFWDeviation;
  output Boolean vppVlvLPToHPIPFWFaultActive;
  output Real vppVlvLPToHPIPFWCv;
  output Real vppVlvLPToHPIPFWMassFlowTH(unit="t/h");
  output Real vppVlvLPToHPIPFWDPPa(unit="Pa");
  Real vppVlvLPToHPIPFWTarget(min=0, max=1);
  input Real vppVlvCondExtractionModeAutoNative(start=1);
  input Real vppVlvCondExtractionManualCmdNative(start=0.8, min=0, max=1);
  input Real vppVlvCondExtractionFaultEnableNative(start=0);
  input Real vppVlvCondExtractionFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvCondExtractionAutoCmd(min=0, max=1);
  output Real vppVlvCondExtractionCmd(min=0, max=1);
  output Real vppVlvCondExtractionFb(min=0, max=1);
  output Real vppVlvCondExtractionDeviation;
  output Boolean vppVlvCondExtractionFaultActive;
  output Real vppVlvCondExtractionCv;
  output Real vppVlvCondExtractionMassFlowTH(unit="t/h");
  output Real vppVlvCondExtractionDPPa(unit="Pa");
  Real vppVlvCondExtractionTarget(min=0, max=1);
  input Real vppVlvHPTurbAdmModeAutoNative(start=1);
  input Real vppVlvHPTurbAdmManualCmdNative(start=0.8, min=0, max=1);
  input Real vppVlvHPTurbAdmFaultEnableNative(start=0);
  input Real vppVlvHPTurbAdmFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvHPTurbAdmAutoCmd(min=0, max=1);
  output Real vppVlvHPTurbAdmCmd(min=0, max=1);
  output Real vppVlvHPTurbAdmFb(min=0, max=1);
  output Real vppVlvHPTurbAdmDeviation;
  output Boolean vppVlvHPTurbAdmFaultActive;
  output Real vppVlvHPTurbAdmCv;
  output Real vppVlvHPTurbAdmMassFlowTH(unit="t/h");
  output Real vppVlvHPTurbAdmDPPa(unit="Pa");
  Real vppVlvHPTurbAdmTarget(min=0, max=1);
  input Real vppVlvHPFWIsoModeAutoNative(start=1);
  input Real vppVlvHPFWIsoManualCmdNative(start=0.8, min=0, max=1);
  input Real vppVlvHPFWIsoFaultEnableNative(start=0);
  input Real vppVlvHPFWIsoFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvHPFWIsoAutoCmd(min=0, max=1);
  output Real vppVlvHPFWIsoCmd(min=0, max=1);
  output Real vppVlvHPFWIsoFb(min=0, max=1);
  output Real vppVlvHPFWIsoDeviation;
  output Boolean vppVlvHPFWIsoFaultActive;
  output Real vppVlvHPFWIsoCv;
  output Real vppVlvHPFWIsoMassFlowTH(unit="t/h");
  output Real vppVlvHPFWIsoDPPa(unit="Pa");
  Real vppVlvHPFWIsoTarget(min=0, max=1);
  input Real vppVlvIPFWIsoModeAutoNative(start=1);
  input Real vppVlvIPFWIsoManualCmdNative(start=0.8, min=0, max=1);
  input Real vppVlvIPFWIsoFaultEnableNative(start=0);
  input Real vppVlvIPFWIsoFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvIPFWIsoAutoCmd(min=0, max=1);
  output Real vppVlvIPFWIsoCmd(min=0, max=1);
  output Real vppVlvIPFWIsoFb(min=0, max=1);
  output Real vppVlvIPFWIsoDeviation;
  output Boolean vppVlvIPFWIsoFaultActive;
  output Real vppVlvIPFWIsoCv;
  output Real vppVlvIPFWIsoMassFlowTH(unit="t/h");
  output Real vppVlvIPFWIsoDPPa(unit="Pa");
  Real vppVlvIPFWIsoTarget(min=0, max=1);
  input Real vppVlvIPTurbAdmModeAutoNative(start=1);
  input Real vppVlvIPTurbAdmManualCmdNative(start=0.8, min=0, max=1);
  input Real vppVlvIPTurbAdmFaultEnableNative(start=0);
  input Real vppVlvIPTurbAdmFaultValueNative(start=0, min=0, max=1);
  output Real vppVlvIPTurbAdmAutoCmd(min=0, max=1);
  output Real vppVlvIPTurbAdmCmd(min=0, max=1);
  output Real vppVlvIPTurbAdmFb(min=0, max=1);
  output Real vppVlvIPTurbAdmDeviation;
  output Boolean vppVlvIPTurbAdmFaultActive;
  output Real vppVlvIPTurbAdmCv;
  output Real vppVlvIPTurbAdmMassFlowTH(unit="t/h");
  output Real vppVlvIPTurbAdmDPPa(unit="Pa");
  Real vppVlvIPTurbAdmTarget(min=0, max=1);
  parameter Real CstHP(fixed = false, start = 7618660.65374636) "Stodola's ellipse coefficient HP";
  parameter Real CstMP(fixed = false, start = 278905.664031036) "Stodola's ellipse coefficient MP";
  parameter Real CstBP(fixed = false, start = 13491.6445678148) "Stodola's ellipse coefficient BP";
  //parameter Modelica.SIunits.AbsolutePressure PoutPumpEx(fixed=false,start=22e5)"Flow pressure at the outlet of the pump";
  //parameter Modelica.SIunits.Length zc(fixed=false,start=1.5) "Condenser water level";
  parameter ThermoSysPro.Units.Cv CvmaxValveAHP(fixed = false, start = 135) "Maximum CV: alim. valve HP Drum  ";
  parameter ThermoSysPro.Units.Cv CvmaxValveAMP(fixed = false, start = 70) "Maximum CV: alim. valve MP Drum ";
  parameter ThermoSysPro.Units.Cv CvmaxValveVBP(fixed = false, start = 32000) "Maximum CV: steam valve BP Drum ";
  parameter Real Encras_SHP1(fixed = false, start = 1) "Sur HP1: heat exchange fouling coefficient";
  parameter Real Encras_SHP2(fixed = false, start = 1) "Sur HP2: heat exchange fouling coefficient";
  parameter Real Encras_SHP3(fixed = false, start = 1) "Sur HP3: heat exchange fouling coefficient";
  parameter Real Encras_EHP1(fixed = false, start = 1) "Eco HP1: heat exchange fouling coefficient";
  parameter Real Encras_EHP2(fixed = false, start = 1) "Eco HP2: heat exchange fouling coefficient";
  parameter Real Encras_EHP3(fixed = false, start = 1) "Eco HP3: heat exchange fouling coefficient";
  parameter Real Encras_EHP4(fixed = false, start = 1) "Eco HP4: heat exchange fouling coefficient";
  parameter Real Encras_SMP1(fixed = false, start = 1) "Sur MP1: heat exchange fouling coefficient";
  parameter Real Encras_SMP2(fixed = false, start = 1) "Sur MP2: heat exchange fouling coefficient";
  parameter Real Encras_SMP3(fixed = false, start = 1) "Sur MP3: heat exchange fouling coefficient";
  parameter Real Encras_EMP(fixed = false, start = 1) "Eco MP: heat exchange fouling coefficient";
  parameter Real Encras_EvHP(fixed = false, start = 1) "Evapo HP: heat exchange fouling coefficient";
  parameter Real Encras_EvMP(fixed = false, start = 1) "Evapo MP: heat exchange fouling coefficient";
  parameter Real Encras_EvBP(fixed = false, start = 1) "Evapo BP: heat exchange fouling coefficient";
  parameter Real Encras_SBP(fixed = false, start = 1) "Sur BP: heat exchange fouling coefficient";
  parameter Real Encras_EBP(fixed = false, start = 1) "Eco BP: heat exchange fouling coefficient";
  parameter Real KgainChargeHP(fixed = false, start = 720.183) "HP: Friction pressure loss coefficient";
  parameter Real KgainChargeMP(fixed = false, start = 1090.9) "MP: Friction pressure loss coefficient";
  parameter Real Kin_SMP2(fixed = false, start = 10.) "SMPin: Friction pressure loss coefficient";
  parameter Real K_PerteChargeZero2(fixed = false, start = 1e-4) "TurbineMP out: Friction pressure loss coefficient";
  parameter ThermoSysPro.Units.Cv Cvmax_THP(fixed = false, start = 8000) "Maximum CV input Turbine HP ";
  parameter ThermoSysPro.Units.Cv Cvmax_TMP(fixed = false, start = 1500) "Maximum CV input Turbine MP ";
  /*
    parameter ThermoSysPro.Units.Cv CvmaxWater(fixed=false,start=670.775)
      "Maximum CV (active if mode_caract=0)";
    parameter Real LambdaPipe(fixed=false,start=0.085)
      "Friction pressure loss coefficient (active if lambda_fixed=true)";
    parameter Real SteamValveOuv(fixed=false,start=0.4933)
      "Position of the SteamValve (between 0 and 1) ";
     parameter Modelica.SIunits.AbsolutePressure PoutPump(fixed=false,start=13e5)
      "Flow pressure at the outlet of the pump";
  */
  ThermoSysPro.WaterSteam.Volumes.DynamicDrum BallonHP(L = 16.27, Vertical = false, hl(fixed = false, start = 1474422.14552527), hv(fixed = false, start = 2666558.75582585), Vv(fixed = false), R = 1.05, xmv(fixed = false), zl(start = 1.05, fixed = true), Mp = 5000, Kpa = 5, Kvl = 1000, P(fixed = false, start = 12703151.296069), Pfond(start = 12703151.3), Tp(start = 596.92486029448)) annotation(
    Placement(visible = false, transformation(extent = {{5, 10}, {-35, 50}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_alimentationHP(Cvmax = CvmaxValveAHP, C1(P(start = 12721657.0), h_vol(start = 1396865.59043578)), h(start = 1398000), Cv(start = 178), Pm(start = 13050700)) annotation(
    Placement(visible = false, transformation(extent = {{45, 46}, {25, 66}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Constante constante_vanne_vapeurHP(k = 0.5) annotation(
    Placement(visible = false, transformation(extent = {{-51, 70}, {-61, 78}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_vapeurHP(Cvmax = 47829.4, mode = 0, C2(h_vol(start = 2666558.75582585)), h(start = 2674000), Cv(start = 23914.7), Pm(start = 12721657.16928)) annotation(
    Placement(visible = false, transformation(extent = {{-55, 46}, {-75, 66}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss GainChargeHP(z2 = 0, mode = 1, Q(start = 150, fixed = true), z1 = 10.83, K = KgainChargeHP, C2(P(start = 12768600.0)), h(start = 1474422.14552527), Pm(start = 12704000)) annotation(
    Placement(visible = false, transformation(origin = {-5, -90}, extent = {{-10, -10}, {10, 10}}, rotation = 180)));
  ThermoSysPro.WaterSteam.Volumes.VolumeC VolumeEvapHP(mode = 1, V = 5, h(start = 1474422.14552527), P(start = 12704000)) annotation(
    Placement(visible = false, transformation(extent = {{-25, -100}, {-45, -80}}, rotation = 0)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases EvaporateurHP(Dint = 32.8e-3, Ntubes = 1476, L = 20.7, ExchangerWall(e = 0.0026, lambda = 47, dW1(start = {-5.74e7, -2.67e7, -1.24e7}), Tp(start = {607.668721736158, 605.187884376142, 603.825778846274}), Tp1(start = {606.357, 604.602, 603.578})), Ns = 3, ExchangerFlueGasesMetal(Dext = 0.038, step_L = 0.092, step_T = 0.0869, St = 1, Fa = 1, K(fixed = true, start = 37.69), CSailettes = 11.86442072, p_rho = 1.05, Encras = Encras_EvHP, DeltaT(start = {106, 49, 23}), T(start = {755.54821777344, 673.68082608925, 635.57157972092, 618.19360351563}), Tm(start = {643.15, 633.15, 626.621}), Tp(start = {609.11670087771, 605.86035558168, 604.13687003529})), TwoPhaseFlowPipe(advection = false, rugosrel = 5e-6, z2 = 10.83, option_temperature = 2, continuous_flow_reversal = true, inertia = true, dW1(start = {5.74e7, 2.67e7, 1.24e7}), h(start = {1459929.875, 1760591.32331318, 1893494.15765019, 1954976.19646134, 1459929.875}), hb(start = {1459929.875, 1760591.32331318, 1893494.15765019, 1954976.19646134}), P(start = {12758125, 12740000, 12734000, 12730000, 12726787}))) annotation(
    Placement(visible = false, transformation(origin = {-47, -50}, extent = {{-20, -20}, {20, 20}}, rotation = 90)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases EconomiseurHP4(Ns = 3, L = 20.726, Dint = 0.0266, Ntubes = 246, ExchangerWall(e = 0.0026, lambda = 47, dW1(start = {-3.5e6, -2.63e6, -2e6}), Tp(start = {576.803345033827, 581.933438017921, 585.694098500999}), Tp1(start = {575.762, 580.856, 584.579})), Cws1(P(start = 13703700.0), h_vol(start = 1306078.18827954)), Cws2(h_vol(start = 1406865.59043578)), ExchangerFlueGasesMetal(Dext = 0.0318, step_L = 0.111, step_T = 0.0869, St = 1, Fa = 1, CSailettes = 11.39069779, K(fixed = true, start = 47.53), p_rho = 1.06, Encras = Encras_EHP4, DeltaT(start = {38, 29, 22}), T(start = {618.19360351563, 612.7722894387, 608.97249438439, 606.41162109375}), Tm(start = {623.15, 613.15, 607.844}), Tp(start = {577.44979072627, 582.41942947968, 586.06092597683})), TwoPhaseFlowPipe(advection = false, rugosrel = 5e-6, z1 = 10.83, z2 = 0, option_temperature = 2, inertia = true, dW1(start = {3.5e6, 2.63e6, 2e6}), h(start = {1291418.875, 1336078.18827954, 1370718.78680301, 1396865.59043578, 1398251.0}), hb(start = {1291418.875, 1336078.18827954, 1370718.78680301, 1396865.59043578}), P(start = {13301176, 13320000, 13338000, 13357000, 13374658}))) annotation(
    Placement(visible = false, transformation(origin = {53, -50}, extent = {{20, -20}, {-20, 20}}, rotation = 270)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases SurchauffeurHP1(Ns = 3, L = 20.4, Dint = 0.0324, Ntubes = 246, ExchangerWall(e = 0.0028, lambda = 37.61, dW1(start = {-9.8e6, -7.7e6, -5.9e6}), Tp(start = {629.445777860324, 651.664976699235, 671.075818762815}), Tp1(start = {629, 651, 670.})), Cws1(h_vol(start = 2665000.0)), Cws2(P(start = 12720900.0), h_vol(start = 2981170.0)), ExchangerFlueGasesMetal(Dext = 0.038, step_L = 0.111, step_T = 0.0869, St = 1, Fa = 1, CSailettes = 10.25056, K(fixed = true, start = 34.71), p_rho = 1.04, Encras = Encras_SHP1, DeltaT(start = {138, 108, 84}), T(start = {788.2431640625, 774.65344332519, 763.17487871399, 755.54821777344}), Tm(start = {778.15, 768.15, 759.527}), Tp(start = {631.68675322573, 653.38616970968, 672.36458008039})), TwoPhaseFlowPipe(advection = false, rugosrel = 5e-6, z1 = 10.83, option_temperature = 2, inertia = true, dW1(start = {9.8e6, 7.7e6, 5.9e6}), h(start = {2664757.0, 2808108.09290342, 2916825.81170239, 2998229.34382983, 2973076.25}), hb(start = {2664757.0, 2808108.09290342, 2916825.81170239, 2998229.34382983}), P(start = {12723762, 12723600, 12723500, 12720000, 12719000}))) annotation(
    Placement(visible = false, transformation(origin = {-87, -50}, extent = {{-20, 20}, {20, -20}}, rotation = 270)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases EconomiseurHP3(Dint = 26.6e-3, Ntubes = 1476, Ns = 3, ExchangerWall(e = 2.6e-3, lambda = 47, dW1(start = {-1.6e7, -5.6e6, -2.1e6}), Tp(start = {556.530623976228, 563.226831750573, 565.575075374951}), Tp1(start = {555.49, 562.473, 564.857})), L = 20.726, ExchangerFlueGasesMetal(Dext = 31.8e-3, step_L = 74e-3, step_T = 86.9e-3, Fa = 1, CSailettes = 12.451, K(fixed = true, start = 36.0300000000857), p_rho = 1.08, Encras = Encras_EHP3, St = 5, DeltaT(start = {34, 12, 4.4}), T(start = {602.67193603516, 579.67183226637, 571.50875350574, 568.81030273438}), Tm(start = {593.15, 583.15, 571.919}), Tp(start = {557.01185690541, 563.39937105652, 565.63731055685})), TwoPhaseFlowPipe(rugosrel = 5e-6, z2 = 0, advection = false, z1 = 10.767, inertia = true, dW1(start = {1.6e7, 5.6e6, 2.1e6}), h(start = {986348.9375, 1189594.8774342, 1263384.6284551, 1290000.70037855, 1291418.875}), hb(start = {986348.9375, 1189594.8774342, 1263384.6284551, 1290000.70037855}), P(start = {13219333, 13241000, 13261000, 13282000, 13301176}))) annotation(
    Placement(visible = false, transformation(origin = {173, -50}, extent = {{20, -20}, {-20, 20}}, rotation = 90)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases EconomiseurHP2(Dint = 26.6e-3, Ns = 3, ExchangerWall(e = 2.6e-3, lambda = 47, dW1(start = {-5e6, -3e6, -2.e6}), Tp(start = {490.631370193221, 498.229397165878, 502.978053774656}), Tp1(start = {490, 497.024, 501.871})), L = 20.767, Ntubes = 1107, ExchangerFlueGasesMetal(Dext = 31.8e-3, step_T = 86.9e-3, Fa = 1, step_L = 111e-3, CSailettes = 2.76134577, K(fixed = true, start = 65.5300000000393), p_rho = 1.11, Encras = Encras_EHP2, St = 5, DeltaT(start = {36, 23, 14}), T(start = {531.16070556641, 523.74706132958, 519.01561663699, 516.31256103516}), Tm(start = {538.15, 528.15, 521.399}), Tp(start = {490.84070882241, 498.36081646341, 503.06064272486})), TwoPhaseFlowPipe(rugosrel = 5e-6, z2 = 0, advection = false, z1 = 10.767, inertia = true, dW1(start = {5e6, 3e6, 2.e6}), h(start = {854494.5625, 915007.018247822, 957243.396653824, 983786.364226731, 986348.9375}), hb(start = {854494.5625, 915007.018247822, 957243.396653824, 983786.364226731}), P(start = {13129352, 13152000, 13175000, 13197000, 13219333}))) annotation(
    Placement(visible = false, transformation(origin = {373, -50}, extent = {{-20, -20}, {20, 20}}, rotation = 90)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases EconomiseurHP1(Dint = 26.6e-3, Ns = 3, ExchangerWall(e = 2.6e-3, lambda = 47, dW1(start = {-9.9999e6, -5e6, -2.4e6}), Tp(start = {458.958585923538, 468.506814782426, 473.132256983258}), Tp1(start = {458.001, 467.576, 472.607})), L = 20.726, Ntubes = 1107, Cws1(h_vol(start = 723821.0)), ExchangerFlueGasesMetal(Dext = 31.8e-3, step_L = 74e-3, step_T = 86.9e-3, Fa = 1, CSailettes = 8.30057632, K(fixed = true, start = 40.24), p_rho = 1.13, Encras = Encras_EHP1, St = 5, DeltaT(start = {41, 20, 10}), T(start = {509.31488037109, 491.44087131458, 484.15889910859, 482.59533691406}), Tm(start = {503.15, 498.15, 494.131}), Tp(start = {459.37586976399, 468.70800090382, 473.22896941053})), TwoPhaseFlowPipe(rugosrel = 5e-6, z2 = 0, z1 = 10.767, inertia = true, dW1(start = {9.9999e6, 5e6, 2.4e6}), h(start = {618651.9375, 752176.893518976, 816707.727773953, 847728.424287614, 854494.5625}), hb(start = {618651.9375, 752176.893518976, 816707.727773953, 847728.424287614}), advection = true, dynamic_mass_balance = true, P(start = {13034956, 13060000, 13080000, 13100000, 13129352}))) annotation(
    Placement(visible = false, transformation(origin = {493, -50}, extent = {{20, -20}, {-20, 20}}, rotation = 90)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases SurchauffeurHP2(Ns = 3, L = 20.4, Dint = 32e-3, Ntubes = 246, ExchangerWall(e = 3e-3, lambda = 27, dW1(start = {-8.8e6, -6.6e6, -4.9e6}), Tp(start = {714.604505161814, 740.492493660215, 759.200099714419}), Tp1(start = {710.485, 734.082, 752.527})), Cws2(P(start = 127113000.0), h_vol(start = 3254970.0)), ExchangerFlueGasesMetal(step_T = 86.9e-3, Fa = 1, Dext = 38e-3, step_L = 111e-3, K(fixed = true, start = 34.74), CSailettes = 10.2505424803872, p_rho = 1.02, Encras = Encras_SHP2, St = 5, DeltaT(start = {124, 93, 70}), T(start = {850.64624023438, 839.40882309811, 830.36536707939, 822.68170166016}), Tm(start = {843.15, 833.15, 825.24}), Tp(start = {717.48312916257, 742.56566858011, 760.69152533026})), TwoPhaseFlowPipe(rugosrel = 5e-6, z2 = 0, advection = false, z1 = 10.83, inertia = true, dW1(start = {8.8e6, 6.6e6, 4.9e6}), h(start = {2973076.25, 3118965.9792171, 3205920.08101435, 3268474.17308722, 3240813.5}), hb(start = {2973076.25, 3118965.9792171, 3205920.08101435, 3268474.17308722}), P(start = {12720371, 12718000, 12716000, 12714000, 12711007}))) annotation(
    Placement(visible = false, transformation(origin = {-207, -50}, extent = {{-20, -20}, {20, 20}}, rotation = 90)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases SurchauffeurHP3(Ns = 3, L = 20.4, Ntubes = 246, ExchangerWall(lambda = 27, e = 5e-3, dW1(start = {-6.3e6, -4.7e6, -3.6e6}), Tp(start = {793.335674512128, 811.477076678823, 824.721389633254}), Tp1(start = {783.815, 803.639, 818.56})), Dint = 28e-3, Cws2(h_vol(start = 3446260.0)), ExchangerFlueGasesMetal(step_T = 86.9e-3, Fa = 1, Dext = 38e-3, step_L = 111e-3, K(fixed = true, start = 49.33), CSailettes = 6.59672842597229, p_rho = 1, Encras = Encras_SHP3, St = 5, DeltaT(start = {97, 73, 55}), T(start = {894.21850585938, 885.5393240412, 879.47464880089, 874.32891845703}), Tm(start = {893.15, 883.15, 875.939}), Tp(start = {796.82789474964, 814.05266276572, 826.6253996051})), TwoPhaseFlowPipe(rugosrel = 5e-6, z2 = 0, advection = false, z1 = 10.726, inertia = true, dW1(start = {6.3e6, 4.7e6, 3.6e6}), h(start = {3240813.5, 3348361.34780186, 3407279.82422176, 3450835.48993987, 3433271.25}), hb(start = {3240813.5, 3348361.34780186, 3407279.82422176, 3450835.48993987}), P(start = {12711007, 12704000, 12697000, 12689000, 12681000}))) annotation(
    Placement(visible = false, transformation(origin = {-327, -50}, extent = {{20, -20}, {-20, 20}}, rotation = 90)));
  ThermoSysPro.WaterSteam.Volumes.DynamicDrum BallonMP(L = 16.27, Vertical = false, P0 = 27.29e5, hl(fixed = false, start = 978914.570821827), hv(fixed = false, start = 2799158.13966473), Vv(fixed = false), R = 1.05, P(fixed = false, start = 2732895.21562269), zl(start = 1.05, fixed = true), Kpa = 5, Mp = 5000, Kvl = 1000, Pfond(start = 2732995.0), Tp(start = 500.955757665063)) annotation(
    Placement(visible = false, transformation(extent = {{325, 10}, {287, 50}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Constante constante_vanne_vapeurMP(k = 0.5) annotation(
    Placement(visible = false, transformation(extent = {{271, 70}, {259, 80}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_alimentationMP(Cvmax = CvmaxValveAMP, C1(P(start = 2752995.0), h_vol(start = 892414.570867188)), h(start = 944000), Cv(start = 28), Pm(start = 2975000)) annotation(
    Placement(visible = false, transformation(extent = {{365, 46}, {345, 66}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_vapeurMP(Cvmax = 47829.4, mode = 0, C2(h_vol(start = 2799158.13966473)), h(fixed = false, start = 2798000), Cv(start = 23914.7), Pm(fixed = false, start = 2731689.4244255)) annotation(
    Placement(visible = false, transformation(extent = {{265, 46}, {245, 66}}, rotation = 0)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases EvaporateurMP(Dint = 32.8e-3, L = 20.767, Ntubes = 738, ExchangerWall(e = 2.6e-3, lambda = 47, dW1(start = {-9.7e7, -7.6e6, -5.8e6}), Tp(start = {504.957792851478, 504.19488464586, 503.59993822766}), Tp1(start = {504.427, 503.806, 503.304})), Ns = 3, TwoPhaseFlowPipe(advection = false, rugosrel = 5e-6, z1 = 0, z2 = 10.83, continuous_flow_reversal = true, inertia = true, dW1(start = {9.7e7, 7.6e6, 5.8e6}), P(start = {2773367.5, 2754933.93610513, 2745233.82043873, 2738517.46232967, 2733824.75}), h(start = {980708.125, 1028103.09460604, 1066178.43156513, 1095633.31556464, 980708.125}), hb(start = {980708.125, 1028103.09460604, 1066178.43156513, 1095633.31556464})), Cws1(P(start = 2773640.0)), ExchangerFlueGasesMetal(K(fixed = true, start = 30.22), Dext = 38e-3, step_L = 111e-3, step_T = 86.9e-3, Fa = 1, CSailettes = 10.0676093, p_rho = 1.1, Encras = Encras_EvMP, St = 5, DeltaT(start = {53, 41, 32}), T(start = {565.24822998047, 551.20973998682, 539.98034586472, 531.16070556641}), Tm(start = {553.15, 543.15, 536.901}), Tp(start = {505.45492567199, 504.57970000924, 503.89762940507}))) annotation(
    Placement(visible = false, transformation(origin = {273, -50}, extent = {{-20, -20}, {20, 20}}, rotation = 90)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss GainChargeMP(z2 = 0, z1 = 10.83, mode = 1, Q(start = 150, fixed = true), K = KgainChargeMP, Pm(start = 2734000), h(start = 978914.570821827)) annotation(
    Placement(visible = false, transformation(origin = {315, -90}, extent = {{-10, -10}, {10, 10}}, rotation = 180)));
  ThermoSysPro.WaterSteam.Volumes.VolumeC VolumeEvapMP(mode = 1, V = 5, h(start = 978914.570821827), P(start = 2734000)) annotation(
    Placement(visible = false, transformation(extent = {{295, -100}, {275, -80}}, rotation = 0)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases EconomiseurMP(ExchangerWall(e = 2.6e-3, lambda = 47, dW1(start = {-3e6, -1.4e6, -740379}), Tp(start = {457.584681885759, 475.409334769727, 486.332585528225}), Tp1(start = {456.76, 474.926, 485.122})), L = 20.726, Ns = 3, Dint = 26.6e-3, Ntubes = 246, Cws1(h_vol(start = 671235.0)), Cws2(h_vol(start = 977376.0)), ExchangerFlueGasesMetal(step_L = 111e-3, step_T = 86.9e-3, Fa = 1, Dext = 31.8e-3, K(fixed = true, start = 47.78), CSailettes = 7.16188651, p_rho = 1.12, Encras = Encras_EMP, St = 5, DeltaT(start = {45, 24, 13}), T(start = {516.31256103516, 511.25046295073, 508.31162431247, 509.31488037109}), Tm(start = {533.15, 523.15, 514.647}), Tp(start = {458.18343678065, 475.77644311925, 486.55770446184})), TwoPhaseFlowPipe(advection = false, rugosrel = 5e-6, z1 = 10.767, z2 = 0, inertia = true, dW1(start = {3e6, 1.4e6, 740379}), h(start = {565108.5, 727745.440528479, 829820.124314816, 892414.570867187, 944505.4375}), hb(start = {565108.5, 727745.440528479, 829820.124314816, 892414.570867187}), P(start = {3124229.75, 3148000, 3172000, 3195000, 3216977.75}))) annotation(
    Placement(visible = false, transformation(origin = {433, -50}, extent = {{-20, -20}, {20, 20}}, rotation = 90)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases SurchauffeurMP1(ExchangerWall(e = 2.6e-3, lambda = 47, dW1(start = {-1.3e6, -0.80263e6, -501864}), Tp(start = {557.102699668877, 574.070651369638, 584.64928514972}), Tp1(start = {556.102699668877, 573.070651369638, 583.64928514972})), L = 20.726, Ns = 3, Dint = 32.8e-3, Ntubes = 123, Cws1(h_vol(start = 2800000.0)), ExchangerFlueGasesMetal(step_L = 111e-3, step_T = 86.9e-3, Fa = 1, Dext = 31.8e-3, K(fixed = true, start = 22.09), CSailettes = 14.46509765, p_rho = 1.07, Encras = Encras_SMP1, St = 5, DeltaT(start = {45, 30, 19}), T(start = {606.41162109375, 604.22099235915, 603.06310204059, 602.67193603516}), Tm(start = {623.15, 613.15, 603.024}), Tp(start = {557.49575399383, 574.31250418519, 584.79699207547})), TwoPhaseFlowPipe(advection = false, rugosrel = 5e-6, z2 = 0, z1 = 10.77, inertia = true, dW1(start = {1.3e6, 0.80263e6, 501864}), h(start = {2798574.75, 2904836.50693844, 2969862.15109307, 3009575.30461156, 3040562.25}), hb(start = {2798574.75, 2904836.50693844, 2969862.15109307, 3009575.30461156}), P(start = {2731326.25, 2729591.6901521, 2728654.3204706, 2727686.1714029, 2726700}))) annotation(
    Placement(visible = false, transformation(origin = {113, -50}, extent = {{20, -20}, {-20, 20}}, rotation = 90)));
  ThermoSysPro.WaterSteam.Volumes.VolumeB MelangeurHPMP(Ce1(h(start = 3091610.0)), h(start = 3042573.51976705), P(start = 2726000)) annotation(
    Placement(visible = false, transformation(origin = {115, -110}, extent = {{-10, 10}, {10, -10}}, rotation = 90)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases SurchauffeurMP2(Ns = 3, L = 20.4, Dint = 39.3e-3, Ntubes = 369, ExchangerWall(e = 2.6e-3, lambda = 36.86, dW1(start = {-1.15e7, -7.9e6, -5.5e6}), Tp(start = {689.66516778766, 716.376344387713, 734.591437191304}), Tp1(start = {687.7, 713.5, 731.5})), Cws1(P(start = 2576650.0), h_vol(start = 3078800.0)), Cws2(P(start = 2558540.0), h_vol(start = 3342910.0)), ExchangerFlueGasesMetal(step_T = 86.9e-3, Fa = 1, Dext = 44.5e-3, step_L = 92e-3, K(fixed = true, start = 45.22), CSailettes = 5.814209831, p_rho = 1.03, Encras = Encras_SMP2, St = 5, DeltaT(start = {125, 86, 60}), T(start = {822.68170166016, 807.90772072705, 797.00284433443, 788.2431640625}), Tm(start = {813.15, 803.15, 792.527}), Tp(start = {690.93545553661, 717.24269857866, 735.18209370035})), TwoPhaseFlowPipe(advection = false, z2 = 0, z1 = 10.83, rugosrel = 1e-5, inertia = true, dW1(start = {1.15e7, 7.9e6, 5.5e6}), h(start = {3040562.25, 3176242.27636476, 3267406.25678814, 3329559.35651389, 3321940.75}), hb(start = {3040562.25, 3176242.27636476, 3267406.25678814, 3329559.35651389}), P(start = {2575582.5, 2572000, 2568000, 2563000, 2558239}))) annotation(
    Placement(visible = false, transformation(origin = {-147, -50}, extent = {{-20, -20}, {20, 20}}, rotation = 90)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases SurchauffeurMP3(Ns = 3, L = 20.4, Ntubes = 369, Dint = 45.6e-3, ExchangerWall(e = 2.6e-3, lambda = 27, dW1(start = {-8e6, -5.5e6, -3.8e6}), Tp(start = {788.901616786331, 805.674094596818, 817.083010473709}), Tp1(start = {786.717, 804.102, 815.901})), Cws2(h_vol(start = 3529920.0)), ExchangerFlueGasesMetal(step_T = 86.9e-3, Fa = 1, step_L = 92e-3, Dext = 50.8e-3, K(fixed = true, start = 43.23), CSailettes = 5.695842178, p_rho = 1.01, Encras = Encras_SMP3, St = 5, DeltaT(start = {82, 56, 38}), T(start = {874.32891845703, 864.2444076086, 856.92248545484, 850.64624023438}), Tm(start = {873.15, 863.15, 853.059}), Tp(start = {789.92521486539, 806.37044583028, 817.55662835373})), TwoPhaseFlowPipe(advection = false, z2 = 0, z1 = 10.83, rugosrel = 1e-5, inertia = true, dW1(start = {8e6, 5.5e6, 3.8e6}), h(start = {3321940.75, 3420707.89900972, 3482716.02631475, 3524890.37222916, 3517975.25}), hb(start = {3321940.75, 3420707.89900972, 3482716.02631475, 3524890.37222916}), P(start = {2558239, 2556000, 2554000, 2552000, 2548600}))) annotation(
    Placement(visible = false, transformation(origin = {-267, -50}, extent = {{20, -20}, {-20, 20}}, rotation = 90)));
  ThermoSysPro.WaterSteam.Volumes.DynamicDrum BallonBP(Vertical = false, P0 = 5e5, Vv(fixed = false), L = 8, hl(fixed = false, start = 549249.519022482), hv(fixed = false, start = 2709858.97470349), R = 2, P(fixed = false, start = 563775.329209196), zl(start = 1.75, fixed = true), Kpa = 5, Mp = 5000, Kvl = 1000, Pfond(start = 564775.0), Tp(start = 406.411032587651)) annotation(
    Placement(visible = false, transformation(extent = {{585, 10}, {545, 50}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Constante constante_vanne_vapeurBP(k = 0.5) annotation(
    Placement(visible = false, transformation(extent = {{633, 76}, {621, 86}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_vapeurBP(p_rho = 3, Cvmax = CvmaxValveVBP, C2(P(start = 503542.0), h_vol(start = 2709858.97470349)), h(start = 2685000), Cv(start = 1), Pm(start = 498000)) annotation(
    Placement(visible = false, transformation(extent = {{525, 46}, {505, 66}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_alimentationBP(Cvmax = 285, C1(h_vol(start = 511900.0)), h(fixed = false, start = 509000), Cv(start = 142.5), Pm(fixed = false, start = 969800)) annotation(
    Placement(visible = false, transformation(extent = {{617, 44}, {597, 64}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss GainChargeBP(z2 = 0, z1 = 10.767, Q(start = 50, fixed = false), K = 32766, mode = 1, pro(d(start = 934.452746556487)), Pm(start = 564000), h(start = 549249.519022482)) annotation(
    Placement(visible = false, transformation(origin = {577, -90}, extent = {{-10, -10}, {10, 10}}, rotation = 180)));
  ThermoSysPro.WaterSteam.Volumes.VolumeC VolumeEvapBP(h(start = 549249.519022482), mode = 1, V = 5, P(start = 564000)) annotation(
    Placement(visible = false, transformation(extent = {{559, -100}, {539, -80}}, rotation = 0)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases EvaporateurBP(Dint = 32.8e-3, ExchangerWall(e = 2.6e-3, lambda = 47, dW1(start = {-1.24e7, -8.5e6, -5.8e6}), Tp(start = {433.127441964236, 432.076030201586, 431.28112439162}), Tp1(start = {432.956, 431.127, 430.61})), L = 20.726, Ntubes = 984, Ns = 3, ExchangerFlueGasesMetal(Dext = 38e-3, step_T = 86.9e-3, Fa = 1, step_L = 138e-3, K(fixed = true, start = 30.62), CSailettes = 11.07985, p_rho = 1.14, Encras = Encras_EvBP, St = 5, DeltaT(start = {45, 31, 21}), T(start = {482.59533691406, 464.53146753441, 453.496360082, 442.5893859863}), Tm(start = {483.15, 478.15, 472.098}), Tp(start = {433.5360639938, 432.3549425205, 431.471976456})), TwoPhaseFlowPipe(advection = false, rugosrel = 5e-6, z1 = 0, z2 = 10.767, continuous_flow_reversal = true, inertia = true, dW1(start = {1.24e7, 8.5e6, 5.8e6}), h(start = {550075.0, 765243.011613326, 912673.256542569, 1013555.73710231, 550075.0}), hb(start = {550075.0, 765243.011613326, 912673.256542569, 1013555.73710231}), Q(start = {49.787311368631, 49.787311368631, 49.787311368631, 49.787311368631}), P(start = {512583.375, 488000, 487000, 486000, 485588.46875}))) annotation(
    Placement(visible = false, transformation(origin = {533, -50}, extent = {{-20, -20}, {20, 20}}, rotation = 90)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Constante constante_ballonBP(k = 1) annotation(
    Placement(visible = false, transformation(extent = {{709, 6}, {695, 18}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve Vanne_alimentationMPHP(mode = 1, Cvmax = 308.931, C1(h_vol(start = 549249.519022482)), h(start = 550000), Cv(start = 308.931), Pm(start = 490000)) annotation(
    Placement(visible = false, transformation(extent = {{677, -14}, {697, 6}}, rotation = 0)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases SurchauffeurBP(Ns = 3, L = 20.726, Dint = 39.3e-3, Ntubes = 123, ExchangerWall(e = 2.6e-3, lambda = 47, dW1(start = {-1.1e6, -782901, -559798}), Tp(start = {489.606851797367, 513.610203520748, 530.080624448955}), Tp1(start = {488.486, 512.197, 529.53})), Cws1(h_vol(start = 2642240.0)), Cws2(h_vol(start = 2979330.0)), ExchangerFlueGasesMetal(step_T = 86.9e-3, Fa = 1, Dext = 44.5e-3, step_L = 222.1e-3, K(fixed = true, start = 30.46), CSailettes = 3.25763059984175, p_rho = 1.09, Encras = Encras_SBP, St = 5, DeltaT(start = {92, 66, 47}), T(start = {568.81030273438, 567.21003420557, 566.29303411055, 565.24822998047}), Tm(start = {583.15, 573.15, 568.703}), Tp(start = {489.84170505864, 513.76963980951, 530.18834052149})), TwoPhaseFlowPipe(advection = false, z2 = 0, rugosrel = 1e-5, z1 = 10.767, inertia = true, dW1(start = {1.1e6, 782901, 559798}), h(start = {2684673.5, 2819292.38908571, 2893584.12921908, 2943776.05560762, 2914520.25}), hb(start = {2684673.5, 2819292.38908571, 2893584.12921908, 2943776.05560762}), P(start = {510622.6875, 505757.57962259, 504477.27858572, 503172.36919354, 501850}))) annotation(
    Placement(visible = false, transformation(origin = {233, -50}, extent = {{20, -20}, {-20, 20}}, rotation = 90)));
  ThermoSysPro.FlueGases.BoundaryConditions.SinkP PuitsFumees(P0 = 1.013e5) annotation(
    Placement(visible = false, transformation(origin = {689, -50}, extent = {{10, -10}, {-10, 10}}, rotation = 180)));
  ThermoSysPro.MultiFluids.HeatExchangers.DynamicExchangerWaterSteamFlueGases EconomiseurBP(Ns = 3, Dint = 32.8e-3, ExchangerWall(e = 2.6e-3, lambda = 47, dW1(start = {-2.45e7, -5.5e6, -1.17e6}), Tp(start = {398.142807363473, 393.825926964772, 392.943738968771}), Tp1(start = {397.622, 392.348, 391.516})), Ntubes = 3444, L = 20.726, Cws1(h_vol(start = 195526.0)), Cws2(h_vol(start = 588078.0)), ExchangerFlueGasesMetal(step_T = 86.9e-3, Fa = 1, Dext = 38e-3, step_L = 92e-3, K(fixed = true, start = 31.53), CSailettes = 11.673758598919, p_rho = 1.15, Encras = Encras_EBP, St = 5, DeltaT(start = {23.5, 5.3, 1.1}), T(start = {442.5893859863, 403.9873508455, 395.0465605839, 395.464630127}), Tm(start = {423.15, 418.15, 414.742}), Tp(start = {398.4437772187, 393.8897987349, 392.9569515805})), TwoPhaseFlowPipe(advection = false, rugosrel = 5e-6, z1 = 0, z2 = 10.767, inertia = true, dW1(start = {2.45e7, 5.5e6, 1.17e6}), h(start = {194584.515625, 462556.370989432, 494648.45288738, 501287.069880104, 509237.875}), hb(start = {194584.515625, 462556.370989432, 494648.45288738, 501287.069880104}), P(start = {1540571.25, 1500000, 1480000, 1450000, 1429595.375}))) annotation(
    Placement(visible = false, transformation(origin = {647, -50}, extent = {{-20, -20}, {20, 20}}, rotation = 90)));
  ThermoSysPro.WaterSteam.Machines.StodolaTurbine TurbineHP(regularizePressureCrossover = true, W_fric = 1, eta_stato = 1, eta_is(start = 0.88057), Qmax = 140, eta_is_nom = 0.88057, eta_is_min = 0.75, Cst(start = 8182844.56002535) = CstHP, pros(d(start = 10.0)), Hrs(start = 3046260), Pe(fixed = true, start = 12431000), Ps(fixed = false, start = 2726700)) annotation(
    Placement(visible = false, transformation(extent = {{-35, -250}, {5, -210}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Machines.StodolaTurbine TurbineMP(regularizePressureCrossover = true, W_fric = 1, eta_stato = 1, eta_is(start = 0.9625), Qmax = 150, eta_is_nom = 0.9625, eta_is_min = 0.75, Cst(start = 256335.364995961) = CstMP, pros(d(start = 30.0)), Hrs(start = 3029780), Pe(fixed = true, start = 2548500), Ps(fixed = false, start = 476800)) annotation(
    Placement(visible = false, transformation(extent = {{285, -250}, {325, -210}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Volumes.VolumeC MelangeurPostTMP1(h(start = 2997231.36734756), P(start = 476799.99999954), Ce1(h(start = 3029780))) annotation(
    Placement(visible = false, transformation(origin = {385, -230}, extent = {{10, -10}, {-10, 10}}, rotation = 180)));
  ThermoSysPro.WaterSteam.Machines.StodolaTurbine TurbineBP(regularizePressureCrossover = true, W_fric = 1, eta_stato = 1, eta_is(start = 0.9538), Qmax = 150, eta_is_nom = 0.9538, eta_is_min = 0.75, Cst(start = 11944.9445735985) = CstBP, Cs(h(start = 2400000.0)), Hrs(start = 2401030), Pe(fixed = true, start = 476799.99999954), Ps(start = 10053)) annotation(
    Placement(visible = false, transformation(extent = {{543, -250}, {583, -210}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Junctions.MassFlowMultiplier DoubleDebitHP(alpha = 2) annotation(
    Placement(visible = false, transformation(origin = {-325, -100}, extent = {{-10, -10}, {10, 10}}, rotation = 270)));
  ThermoSysPro.WaterSteam.Junctions.MassFlowMultiplier DoubleDebitMP(alpha = 2) annotation(
    Placement(visible = false, transformation(origin = {-265, -100}, extent = {{-10, -10}, {10, 10}}, rotation = 270)));
  ThermoSysPro.WaterSteam.Junctions.MassFlowMultiplier MoitieDebitHP(alpha = 0.5, Ce(h(start = 3046260)), P(start = 2726700)) annotation(
    Placement(visible = false, transformation(extent = {{81, -180}, {101, -160}}, rotation = 0)));
  ThermoSysPro.WaterSteam.HeatExchangers.SimpleDynamicCondenser Condenseur(D = 0.018, V = 1000, A = 100, lambda = 0.01, ntubes = 28700, continuous_flow_reversal = true, Vf0 = 0.15, steady_state = false, yNiveau(signal(start = 1.5)), Cse(h(start = 128076)), P(fixed = false, start = 6136), Pfond(start = 6200)) annotation(
    Placement(visible = false, transformation(extent = {{604, -384}, {684, -304}}, rotation = 0)));
  ThermoSysPro.WaterSteam.BoundaryConditions.SourceQ SourceCaloporteur(h0 = 113.38e3, Q0 = 29804.5) annotation(
    Placement(visible = false, transformation(extent = {{539, -377}, {587, -329}}, rotation = 0)));
  ThermoSysPro.WaterSteam.BoundaryConditions.SinkP PuitsCaloporteur annotation(
    Placement(visible = false, transformation(extent = {{703, -374}, {747, -330}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss perteChargeK1(K = 1e-4, h(start = 2400000), C1(h_vol(start = 2400000), h(start = 2400000)), Pm(start = 10026)) annotation(
    Placement(visible = false, transformation(extent = {{607, -240}, {627, -220}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Volumes.VolumeC VolumeCond1(mode = 1, Ce3(h(start = 163768.700887002)), h(start = 163768.700887002), P(start = 1540500)) annotation(
    Placement(visible = false, transformation(origin = {869, -318}, extent = {{10, -10}, {-10, 10}}, rotation = 270)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss perteChargeKCond1(K = 1e-4, mode = 1, pro(d(start = 993.470128235971)), Pm(start = 1540000)) annotation(
    Placement(visible = false, transformation(origin = {869, -270}, extent = {{12, -12}, {-12, 12}}, rotation = 270)));
  ThermoSysPro.WaterSteam.Volumes.VolumeA VolumeAlimMPHP(mode = 1, h(start = 549249.519022482), P(start = 322430)) annotation(
    Placement(visible = false, transformation(extent = {{709, -20}, {729, 0}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Machines.StaticCentrifugalPump PompeAlimMP(a3 = 350, b1(fixed = true) = -3.7751, a1 = -244551, Q(fixed = false), mode = 1, C1(h_vol(start = 576000.0)), C2(h_vol(start = 561000.0)), Qv(start = 0.0207237016869104), pro(d(start = 930.0)), Pm(start = 1725850)) annotation(
    Placement(visible = false, transformation(extent = {{771, -20}, {791, 0}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Machines.StaticCentrifugalPump PompeAlimHP(a3 = 1600, a1 = -28056.2, b1 = -12.7952660447433, Q(fixed = false), mode = 1, C1(h_vol(start = 561000.0)), C2(h_vol(start = 630000.0)), Qv(start = 0.0810383142105344), pro(d(start = 929.0)), Pm(start = 6774000)) annotation(
    Placement(visible = false, transformation(extent = {{771, -60}, {791, -40}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Junctions.MassFlowMultiplier MoitieDebitBP(alpha = 0.5, h(start = 194585), P(start = 1540500), Cs(h(start = 194585))) annotation(
    Placement(visible = false, transformation(extent = {{839, -328}, {853, -308}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Junctions.MassFlowMultiplier DoubleDebitBP(alpha = 2) annotation(
    Placement(visible = false, transformation(origin = {235, -100}, extent = {{-10, -10}, {10, 10}}, rotation = 270)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss PerteChargeZero2(z2 = 0, mode = 0, z1 = 0, K = K_PerteChargeZero2, h(start = 3000000), C1(h_vol(start = 3000000), h(start = 3000000), P(fixed = true, start = 501850)), Pm(start = 490000)) annotation(
    Placement(visible = false, transformation(origin = {311, -278}, extent = {{10, -10}, {-10, 10}}, rotation = 180)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss perteChargeK3(K = 1e-4, mode = 1, Pm(start = 372718)) annotation(
    Placement(visible = false, transformation(origin = {747, -50}, extent = {{10, -10}, {-10, 10}}, rotation = 180)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss perteChargeK8(K = 1e-4, mode = 1, Pm(start = 372718)) annotation(
    Placement(visible = false, transformation(origin = {747, -10}, extent = {{10, -10}, {-10, 10}}, rotation = 180)));
  ThermoSysPro.WaterSteam.Machines.Generator Alternateur annotation(
    Placement(visible = false, transformation(extent = {{369, -448}, {489, -348}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss perteChargeK(K = 1e-4, mode = 1, C1(h_vol(start = 153206.462779274)), C2(h_vol(start = 153206.462779274)), pro(d(start = 993.441492649513)), Pm(start = 6200)) annotation(
    Placement(visible = false, transformation(extent = {{669, -446}, {689, -426}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Machines.StaticCentrifugalPump PompeAlimBP(Qv(start = 0.193483547611118), mode = 1, a3 = 400, a1(fixed = true) = -6000, Q(start = 194.502, fixed = false), C2(h_vol(start = 194669.0)), Pm(start = 800000)) annotation(
    Placement(visible = false, transformation(extent = {{709, -446}, {729, -426}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss perteChargeK2(K = 1e-4, mode = 1, pro(d(start = 994.045785814739)), C1(h_vol(start = 194585), h(start = 194585)), Pm(start = 1546000)) annotation(
    Placement(visible = false, transformation(extent = {{807, -446}, {827, -426}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_extraction(mode = 1, Cvmax = 2000, h(start = 194500), Cv(start = 2000), Pm(start = 1549000)) annotation(
    Placement(visible = false, transformation(extent = {{769, -440}, {789, -420}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Sensors.SensorQ CapteurDebitVapHP(C1(h_vol(start = 2674000), h(start = 2674000))) annotation(
    Placement(visible = false, transformation(origin = {-91, 8}, extent = {{-6, 6}, {6, -6}}, rotation = 270)));
  ThermoSysPro.WaterSteam.Sensors.SensorQ CapteurDebitEauHP(C2(h_vol(start = 1398000), h(start = 1398000))) " " annotation(
    Placement(visible = false, transformation(origin = {58.5, 32}, extent = {{6, -6.5}, {-6, 6.5}}, rotation = 270)));
  ThermoSysPro.WaterSteam.Sensors.SensorQ CapteurDebitEauMP(C2(h_vol(start = 944000), h(start = 944000))) annotation(
    Placement(visible = false, transformation(extent = {{391, 49}, {376, 63}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Sensors.SensorQ CapteurDebitVapMP(C1(h_vol(start = 2798000), h(start = 2798000))) annotation(
    Placement(visible = false, transformation(origin = {203, 56}, extent = {{-8, 8}, {8, -8}}, rotation = 180)));
  ThermoSysPro.WaterSteam.Sensors.SensorQ CapteurDebitVapBP(C2(h_vol(start = 2685000), h(start = 2685000))) annotation(
    Placement(visible = false, transformation(origin = {481, 56}, extent = {{-8, 8}, {8, -8}}, rotation = 180)));
  ThermoSysPro.WaterSteam.Sensors.SensorQ CapteurDebitEauBP(C2(h_vol(start = 550000), h(start = 550000))) annotation(
    Placement(visible = false, transformation(origin = {630.5, 34}, extent = {{6, -6.5}, {-6, 6.5}}, rotation = 270)));
  ThermoSysPro.WaterSteam.Sensors.SensorQ CapteurDebitEauBPsortie(C2(h_vol(start = 550000), h(start = 550000))) annotation(
    Placement(visible = false, transformation(extent = {{654, -11}, {667, 1}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Sensors.SensorQ CapteurDebitEauCondenseur(C2(h_vol(start = 194585), h(start = 194585))) annotation(
    Placement(visible = false, transformation(origin = {652.5, -412}, extent = {{-10, -6.5}, {10, 6.5}}, rotation = 270)));
  ThermoSysPro.WaterSteam.Sensors.SensorQ CapteurDebitVapCondenseur(C2(h_vol(start = 2401000), h(start = 2401000))) annotation(
    Placement(visible = false, transformation(origin = {651.5, -264}, extent = {{-10, -6.5}, {10, 6.5}}, rotation = 270)));
  ThermoSysPro.WaterSteam.PressureLosses.PipePressureLoss lumpedStraightPipeK2(K = Kin_SMP2, Pm(start = 2651000), C1(P(fixed = true, start = 2726700), h_vol(start = 3046000), h(start = 3046000))) annotation(
    Placement(visible = false, transformation(extent = {{81, -120}, {61, -100}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_entree_TurbineHP(mode = 0, C1(P(fixed = true, start = 12680999.9999969)), Cvmax = Cvmax_THP, h(fixed = false, start = 3433000), Cv(start = 10875), Pm(fixed = false, start = 12550000)) annotation(
    Placement(visible = false, transformation(extent = {{-157, -234}, {-137, -214}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Constante ConsigneNiveauEauHP(k = 1.05) annotation(
    Placement(visible = false, transformation(extent = {{-191, 113}, {-157, 131}}, rotation = 0)));
  ThermoSysPro.Examples.CombinedCyclePowerPlant.Control.Drum_LevelControl regulation_Niveau_HP(pIsat(Ti = 500, Limiteur1(u(signal(start = 0.8)))), add(k1 = -1, k2 = +1), Ti = 500, minval = 0.007) annotation(
    Placement(visible = false, transformation(extent = {{-73, 106}, {-53, 126}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Constante ConsigneNiveauEauMP(k = 1.05) annotation(
    Placement(visible = false, transformation(extent = {{140, 113}, {174, 131}}, rotation = 0)));
  ThermoSysPro.Examples.CombinedCyclePowerPlant.Control.Drum_LevelControl regulation_Niveau_MP(pIsat(Ti = 500, Limiteur1(u(signal(start = 0.8)))), add(k1 = -1, k2 = +1), Ti = 500) annotation(
    Placement(visible = false, transformation(extent = {{229, 106}, {249, 126}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Constante ConsigneNiveauEauBP(k = 1.75) annotation(
    Placement(visible = false, transformation(extent = {{437, 126}, {471, 144}}, rotation = 0)));
  ThermoSysPro.Examples.CombinedCyclePowerPlant.Control.Drum_LevelControl regulation_Niveau_BP(add(k1 = -1, k2 = +1), pIsat(Ti = 500, Limiteur1(u(signal(start = 0.8)))), Ti = 10, minval = 0.006) annotation(
    Placement(visible = false, transformation(extent = {{535, 108}, {555, 128}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Constante ConsigneNiveauCondenseur1(k = 1.5) annotation(
    Placement(visible = false, transformation(extent = {{683, -246}, {707, -230}}, rotation = 0)));
  ThermoSysPro.Examples.CombinedCyclePowerPlant.Control.Condenser_LevelControl regulation_Niveau_Condenseur(pIsat(Ti = 500, Limiteur1(u(signal(start = 0.8)))), add(k1 = +1, k2 = -1)) annotation(
    Placement(visible = false, transformation(extent = {{725, -282}, {745, -262}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Tables.Table1DTemps ConstantVanneTurbineHP(Table = [0, 0.8; 10, 0.8; 600, 0.8; 650, 0.8; 3000, 0.8; 3100, 0.8]) annotation(
    Placement(visible = false, transformation(extent = {{-241, -216}, {-171, -142}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Rampe arretPomesMp(Initialvalue = 1400, Duration = 1000, Starttime = 4000, Finalvalue = 1000) annotation(
    Placement(visible = false, transformation(extent = {{911, -42}, {873, -10}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Rampe arretPomesHP(Initialvalue = 1400, Starttime = 4000, Duration = 1000, Finalvalue = 700) annotation(
    Placement(visible = false, transformation(extent = {{912, -96}, {874, -64}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Rampe arretPomesBP(Initialvalue = 1400, Finalvalue = 1000, Duration = 1000, Starttime = 200000) annotation(
    Placement(visible = false, transformation(extent = {{912, -458}, {874, -426}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Volumes.VolumeC VolumeECO_HP1_2(mode = 1, V = 1, h0 = 988332, h(start = 988332), dynamic_mass_balance = true, P0 = 7010000, P(start = 13129000)) annotation(
    Placement(visible = false, transformation(extent = {{423, -98}, {403, -78}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Volumes.VolumeC VolumeECO_HP2_3(mode = 1, V = 1, h0 = 983786, h(start = 983786), dynamic_mass_balance = true, P0 = 7000000, P(start = 13219000)) annotation(
    Placement(visible = false, transformation(extent = {{219, -20}, {199, 0}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve Vanne_alimentationMPHP1(mode = 1, Cvmax = 308.931, h(start = 618600), Cv(start = 308.931), Pm(start = 13130000)) annotation(
    Placement(visible = false, transformation(extent = {{721, -98}, {697, -122}}, rotation = 0)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve Vanne_alimentationMPHP2(mode = 1, Cvmax = 308.931, h(start = 565000), Cv(start = 308.931), Pm(start = 3126000)) annotation(
    Placement(visible = false, transformation(extent = {{771, -138}, {747, -162}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Rampe arretPomesMp1(Initialvalue = 0.8, Duration = 1000, Starttime = 3000, Finalvalue = 0.005) annotation(
    Placement(visible = false, transformation(extent = {{913, -150}, {875, -118}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Sources.Rampe arretPomesHP1(Initialvalue = 0.8, Duration = 1000, Starttime = 3000, Finalvalue = 0.005) annotation(
    Placement(visible = false, transformation(extent = {{913, -194}, {875, -162}}, rotation = 0)));
  ThermoSysPro.WaterSteam.Volumes.VolumeD VolumePreTHP(h0 = 3e6, h(start = 3450835.48993987), dynamic_mass_balance = true, P0 = 12700000, P(start = 12700000)) annotation(
    Placement(visible = false, transformation(origin = {-85, -230}, extent = {{10, -10}, {-10, 10}}, rotation = 180)));
  ThermoSysPro.WaterSteam.Volumes.VolumeC MelangeurPreTMP(h0 = 3523910, h(start = 3523910.30137915), dynamic_mass_balance = true, P0 = 2400000, P(start = 2400000)) annotation(
    Placement(visible = false, transformation(origin = {-83, -314}, extent = {{10, -10}, {-10, 10}}, rotation = 180)));
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_entree_TurbineMP(mode = 0, C1(P(fixed = true, start = 25.486e5)), Cvmax = Cvmax_TMP, h(fixed = false, start = 3518000), Cv(start = 3.312e6), Pm(fixed = false, start = 2547000)) annotation(
    Placement(visible = false, transformation(extent = {{-157, -318}, {-137, -298}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Tables.Table1DTemps ConstantVanneTurbineMP(Table = [0, 0.8; 10, 0.8; 600, 0.8; 2000, 0.8; 3000, 0.8; 3100, 0.8]) annotation(
    Placement(visible = false, transformation(extent = {{-241, -300}, {-171, -226}}, rotation = 0)));
  ThermoSysPro.Thermal.BoundaryConditions.HeatSource heatSource(T0 = {303.16}) annotation(
    Placement(visible = false, transformation(extent = {{-28, 68}, {-2, 98}}, rotation = 0)));
  ThermoSysPro.Thermal.BoundaryConditions.HeatSource heatSource1(T0 = {303.16}) annotation(
    Placement(visible = false, transformation(extent = {{293, 68}, {319, 98}}, rotation = 0)));
  ThermoSysPro.Thermal.BoundaryConditions.HeatSource heatSource2(T0 = {303.16}) annotation(
    Placement(visible = false, transformation(extent = {{552, 64}, {578, 94}}, rotation = 0)));
  ThermoSysPro.FlueGases.BoundaryConditions.SourceQ SourceFumees(Xco2 = 0.0613, Xso2 = 0, Xh2o = 0.0706, T0 = 893.75, Xo2 = 0.1380, Q0 = 606.94) annotation(
    Placement(visible = false, transformation(extent = {{-473, -91}, {-371, -7}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Tables.Table1DTemps Debit(Table = [0, 606.94; 10, 606.94; 600, 50; 650, 50]) annotation(
    Placement(visible = false, transformation(extent = {{-527, -19}, {-457, 55}}, rotation = 0)));
  ThermoSysPro.InstrumentationAndControl.Blocks.Tables.Table1DTemps Temperature(Table = [0, 893.75; 10, 893.75; 600, 423; 650, 423]) annotation(
    Placement(visible = false, transformation(extent = {{-527, -157}, {-457, -83}}, rotation = 0)));
  // TRIPLENS_PROTECTION_MATRIX_V8: genuine Real OPC UA protection inputs
  parameter Boolean vppExternalTripCommand = false
    "Legacy Boolean FMU command is frozen to avoid mixed-input OPC UA indexing";
  input Real vppExternalTripCommandNative(start=0, min=0, max=1)
    "Operator/DCS direct GT Trip command; writable OPC UA input";
  input Real vppExternalSTTripCommandNative(start=0, min=0, max=1)
    "Operator/DCS direct ST Trip command; writable OPC UA input";
  input Real vppGTTripResetNative(start=0, min=0, max=1)
    "GT Trip latch reset pulse; clear initiating cause first";
  input Real vppSTTripResetNative(start=0, min=0, max=1)
    "ST Trip latch reset pulse; GT latch must be clear";
  discrete Boolean vppGTTripLatchInternal(start=false, fixed=true)
    "Independent GT Trip latch";
  discrete Boolean vppSTTripLatch(start=false, fixed=true)
    "Independent ST Trip latch";
  discrete Boolean vppGTBreakerOpenCauseState(start=false, fixed=true)
    "Latched 52GT-open-while-running initiating cause";
  discrete Real vppSTTripAssertTime(unit="s", start=0, fixed=true);
  discrete Real vppHPDrumHHAssertTime(unit="s", start=-1, fixed=true);
  discrete Real vppIPDrumHHAssertTime(unit="s", start=-1, fixed=true);
  discrete Real vppLPDrumHHAssertTime(unit="s", start=-1, fixed=true);
  discrete Real vppHPDrumLLAssertTime(unit="s", start=-1, fixed=true);
  discrete Real vppIPDrumLLAssertTime(unit="s", start=-1, fixed=true);
  discrete Real vppLPDrumLLAssertTime(unit="s", start=-1, fixed=true);
  Real vppGTExhaustMassFlowState(unit = "kg/s", start = vppGTExhaustMassFlowNormal, fixed = true);
  Real vppGTExhaustTemperatureState(unit = "K", start = vppGTExhaustTemperatureNormal, fixed = true);
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppGTExhaustMassFlowCommand;
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppGTExhaustTemperatureCommand;
  output Real vppHPAdmissionPos(start = 0.8, fixed = true, min = 0, max = 1);
  output Real vppIPAdmissionPos(start = 0.8, fixed = true, min = 0, max = 1);
  output Real vppLPDrumAdmissionMultiplier(start = 1, fixed = true, min = 0, max = 1);
  output Real vppHPBypassCmd(min = 0, max = 1);
  output Real vppLPBypassCmd(min = 0, max = 1);
  output Real vppHPBypassPos(start = vppValveLeak, fixed = true, min = 0, max = 1);
  output Real vppLPBypassPos(start = vppValveLeak, fixed = true, min = 0, max = 1);
  output Real vppHPSprayPos(start = 0, fixed = true, min = 0, max = 1);
  output Real vppLPSprayPos(start = 0, fixed = true, min = 0, max = 1);
  output Boolean vppHPBypassOpenLS;
  output Boolean vppHPBypassCloseLS;
  output Boolean vppLPBypassOpenLS;
  output Boolean vppLPBypassCloseLS;
  output Modelica.SIunits.MassFlowRate vppHPBypassMassFlow;
  output Modelica.SIunits.MassFlowRate vppLPBypassMassFlow;
  output Modelica.SIunits.MassFlowRate vppHPSprayMassFlow;
  output Modelica.SIunits.MassFlowRate vppLPSprayMassFlow;
  output Modelica.SIunits.AbsolutePressure vppHPBypassInletPressure;
  output Modelica.SIunits.AbsolutePressure vppLPBypassInletPressure;
  output Modelica.SIunits.AbsolutePressure vppHPBypassOutletPressure;
  output Modelica.SIunits.AbsolutePressure vppLPBypassOutletPressure;
  output Modelica.SIunits.Temperature vppHPBypassInletTemperature;
  output Modelica.SIunits.Temperature vppLPBypassInletTemperature;
  output Modelica.SIunits.Temperature vppHPBypassOutletTemperature;
  output Modelica.SIunits.Temperature vppLPBypassOutletTemperature;
  output Modelica.SIunits.AbsolutePressure vppCondenserPressure;
  output Modelica.SIunits.Length vppCondenserLevel;
  // TRIPLENS_PROCESS_VIEW_V36: canonical native OPC UA aliases for the dynamic
  // operator view. Every alias below is connected to a solved plant variable;
  // none is a timing-only value recreated by the client.
  parameter Real vppGTTripCommandDelay(unit = "s") = 0.055;
  parameter Real vppGTBreakerOpenDelay(unit = "s") = 0.080;
  parameter Real vppSTBreakerOpenDelay(unit = "s") = 0.100;
  parameter Real vppGTGPowerNormalMW(unit = "MW") = 160.0;
  parameter Real vppGTGPowerDecayTau(unit = "s") = 0.35;
  parameter Real vppGTGSpeedNormalRPM = 3600.0;
  parameter Real vppGTGCoastdownTau(unit = "s") = 1.2;
  parameter Real vppDrumTripDelay(unit="s") = 0.5
    "Persistence required for all drum HH/LL common-trip causes";
  parameter Real vppHPDrumHHSetpoint(unit="m") = 1.25;
  parameter Real vppIPDrumHHSetpoint(unit="m") = 1.25;
  parameter Real vppLPDrumHHSetpoint(unit="m") = 1.95;
  parameter Real vppHPDrumLLSetpoint(unit="m") = 0.85;
  parameter Real vppIPDrumLLSetpoint(unit="m") = 0.85;
  parameter Real vppLPDrumLLSetpoint(unit="m") = 1.55;
  discrete Real vppGTTripAssertTime(unit="s", start=0, fixed=true);
  output Boolean vppHPDrumHHRaw;
  output Boolean vppIPDrumHHRaw;
  output Boolean vppLPDrumHHRaw;
  output Boolean vppHPDrumLLRaw;
  output Boolean vppIPDrumLLRaw;
  output Boolean vppLPDrumLLRaw;
  output Boolean vppCauseDirectGTTrip;
  output Boolean vppCauseGTBreakerOpenWhileRunning;
  output Boolean vppCauseDirectSTTrip;
  output Boolean vppCauseHPDrumHH;
  output Boolean vppCauseIPDrumHH;
  output Boolean vppCauseLPDrumHH;
  output Boolean vppCauseHPDrumLL;
  output Boolean vppCauseIPDrumLL;
  output Boolean vppCauseLPDrumLL;
  output Boolean vppGTTripRequest;
  output Boolean vppSTTripRequest;
  // TRIPLENS_PROTECTION_LOGIC_STABLE_V8_5: independent protection logic;
  // HP/IP hydraulic coastdown is supplied by the V8.5.3 inertial adapters.
  // Independent HP/IP BFP operator protection chains.
  input Real vppHPFWPTripPushbuttonNative(start=0, min=0, max=1)
    "Operator HP BFP Trip pushbutton; writable OPC UA input";
  input Real vppHPFWPResetPushbuttonNative(start=0, min=0, max=1)
    "Operator HP BFP reset pushbutton; breaker must be commanded OPEN";
  input Real vppIPFWPTripPushbuttonNative(start=0, min=0, max=1)
    "Operator IP BFP Trip pushbutton; writable OPC UA input";
  input Real vppIPFWPResetPushbuttonNative(start=0, min=0, max=1)
    "Operator IP BFP reset pushbutton; breaker must be commanded OPEN";
  output Real vppHPFWPTripCommandNative;
  output Real vppHPFWPTripLatchNative;
  output Real vppVCBA01TripCommandNative;
  output Real vppIPFWPTripCommandNative;
  output Real vppIPFWPTripLatchNative;
  output Real vppVCBB01TripCommandNative;
  discrete Real vppHPFWPTripLatchState(start=0, fixed=true);
  discrete Real vppIPFWPTripLatchState(start=0, fixed=true);
  output Boolean vppHPFWPMotorEnergized;
  output Boolean vppIPFWPMotorEnergized;
  output Real vppHPFWPSpeedRPM(unit="rev/min");
  output Real vppIPFWPSpeedRPM(unit="rev/min");
  output Boolean vppHPFWPSpeedProven;
  output Boolean vppIPFWPSpeedProven;
  output Boolean vppGTTripCmd;
  output Boolean vppGTTripLatch;
  output Boolean vpp52GTTripCmd;
  output Boolean vpp52GTClosed;
  output Boolean vpp52STTripCmd;
  output Boolean vpp52STClosed;
  output Boolean vppSTTripLatchPublished;
  output Real vppGTGPowerMW(unit = "MW") "Reduced-order GT electrical output";
  output Real vppGTGSpeedRPM "Reduced-order GT shaft speed in rpm";
  output Real vppGTExhaustMassFlowTH(unit = "t/h");
  output Real vppGTExhaustTemperatureK(unit = "K");
  output Real vppHPTurbineSteamFlowTH(unit = "t/h");
  output Real vppIPTurbineSteamFlowTH(unit = "t/h");
  output Real vppLPTurbineSteamFlowTH(unit = "t/h");
  output Real vppHPBypassMassFlowTH(unit = "t/h");
  output Real vppLPBypassMassFlowTH(unit = "t/h");
  output Real vppHPSprayMassFlowTH(unit = "t/h");
  output Real vppLPSprayMassFlowTH(unit = "t/h");
  // Additional v36-only drum and pump observability aliases.
  output Real vppHPDrumLevelM(unit = "m");
  output Real vppIPDrumLevelM(unit = "m");
  output Real vppLPDrumLevelM(unit = "m");
  output Real vppHPDrumPressurePa(unit = "Pa");
  output Real vppIPDrumPressurePa(unit = "Pa");
  output Real vppLPDrumPressurePa(unit = "Pa");
  output Real vppHPFWPMassFlowTH(unit = "t/h");
  output Real vppIPFWPMassFlowTH(unit = "t/h");
  output Real vppHPFWPDeltaPPa(unit = "Pa");
  output Real vppIPFWPDeltaPPa(unit = "Pa");
  output Real vppHPFWPSpeedCommandRPM(unit = "rev/min");
  output Real vppIPFWPSpeedCommandRPM(unit = "rev/min");
  output Boolean vppHPFWPRunning;
  output Boolean vppIPFWPRunning;
  output Boolean vppSTTripLatched;
  VPPRegularizedSplitter2 vppHPSplitter(mode = 2, P(start = 12681000, nominal = 1.3e7), h(start = 3450835, nominal = 3.5e6), Ce(Q(start = vppHPMainFlow0, nominal = 200), h(start = 3450835), h_vol(start = 3450835)), Cs1(Q(start = vppHPMainFlow0, nominal = 200), h(start = 3450835), h_vol(start = 3450835)), Cs2(Q(start = 0, nominal = 200), h(start = 3248547.5), h_vol(start = 3450835))) annotation(
    Placement(visible = false, transformation(extent = {{-190, -240}, {-170, -220}})));
  VPPPressureDrivenBypassValve vppHPBypassValve(Cvmax = vppHPBypassCvmax, rhoNom = vppHPSteamDensity0, Q(start = 0, nominal = 200), Cv(start = vppValveLeak*vppHPBypassCvmax), C1(P(start = 12681000), Q(start = 0, nominal = 200), h(start = 3248547.5), h_vol(start = 3450835)), C2(P(start = 2726700), Q(start = 0, nominal = 200), h(start = 3248547.5), h_vol(start = 3046260))) annotation(
    Placement(visible = false, transformation(extent = {{-120, -210}, {-80, -190}})));
  ThermoSysPro.WaterSteam.BoundaryConditions.SourceQ vppHPSpraySource(Q0 = vppSpraySeatLeak, h0 = 1396866) annotation(
    Placement(visible = false, transformation(extent = {{-20, -270}, {20, -250}})));
  VPPFixedFlowInjector vppHPSprayInjector annotation(
    Placement(visible = false, transformation(extent = {{0, -270}, {20, -250}})));
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppHPSprayFlowCommand annotation(
    Placement(visible = false, transformation(extent = {{-80, -270}, {-60, -250}})));
  VPPRegularizedMixingVolume vppHPColdReheatVolume(V = vppHPHeaderVolume,  // Steam-cycle storage already supplies the pressure states. This header
 // contributes finite thermal hold-up without duplicating an ideal-node
 // pressure state.
  dynamic_mass_balance = false, steady_state = true, mode = 0, P(start = 2726700, nominal = 3e6), h(start = 3046260, nominal = 3.2e6), Ce1(Q(start = vppHPMainFlow0, nominal = 200), h(start = 3046260), h_vol(start = 3046260)), Ce2(Q(start = 0, nominal = 200), h(start = 3248547.5), h_vol(start = 3046260)), Ce3(Q(start = vppSpraySeatLeak, nominal = 200), h(start = 1396866), h_vol(start = 3046260)), Cs(Q(start = vppHPMainFlow0, nominal = 200), h(start = 3046260), h_vol(start = 3046260))) annotation(
    Placement(visible = false, transformation(extent = {{20, -216}, {40, -196}})));
  VPPRegularizedSplitter2 vppLPSplitter(mode = 2, P(start = 2548600, nominal = 3e6), h(start = 3523910, nominal = 3.6e6), Ce(Q(start = vppIPMainFlow0, nominal = 200), h(start = 3523910), h_vol(start = 3523910)), Cs1(Q(start = vppIPMainFlow0, nominal = 200), h(start = 3523910), h_vol(start = 3523910)), Cs2(Q(start = 0, nominal = 200), h(start = 2962470), h_vol(start = 3523910))) annotation(
    Placement(visible = false, transformation(extent = {{-190, -324}, {-170, -304}})));
  VPPPressureDrivenBypassValve vppLPBypassValve(Cvmax = vppLPBypassCvmax, rhoNom = vppHotReheatSteamDensity0, Q(start = 0, nominal = 200), Cv(start = vppValveLeak*vppLPBypassCvmax), C1(P(start = 2548600), Q(start = 0, nominal = 200), h(start = 2962470), h_vol(start = 3523910)), C2(P(start = 6136), Q(start = 0, nominal = 200), h(start = 2962470), h_vol(start = 2401030))) annotation(
    Placement(visible = false, transformation(extent = {{320, -338}, {360, -318}})));
  ThermoSysPro.WaterSteam.BoundaryConditions.SourceQ vppLPSpraySource(Q0 = vppSpraySeatLeak, h0 = 550000) annotation(
    Placement(visible = false, transformation(extent = {{520, -370}, {560, -350}})));
  VPPFixedFlowInjector vppLPSprayInjector annotation(
    Placement(visible = false, transformation(extent = {{570, -370}, {590, -350}})));
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppLPSprayFlowCommand annotation(
    Placement(visible = false, transformation(extent = {{470, -370}, {490, -350}})));
  // Physical liquid make-up / loss sources connected only to the unused
  // DynamicDrum Ce2 ports.  The source Q is the physical disturbance; an
  // ideal injector isolates the source boundary from the drum pressure.
  ThermoSysPro.WaterSteam.BoundaryConditions.SourceQ vppHPDrumInventoryFaultSource(Q0 = 0, h0 = 1474422) annotation(
    Placement(visible = false, transformation(extent = {{-80, -410}, {-40, -390}})));
  VPPFixedFlowInjector vppHPDrumInventoryFaultInjector annotation(
    Placement(visible = false, transformation(extent = {{-30, -410}, {-10, -390}})));
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppHPDrumInventoryFaultFlowCommand annotation(
    Placement(visible = false, transformation(extent = {{-130, -410}, {-110, -390}})));
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppHPDrumInventoryFaultEnthalpyCommand annotation(
    Placement(visible = false, transformation(extent = {{-130, -440}, {-110, -420}})));
  ThermoSysPro.WaterSteam.BoundaryConditions.SourceQ vppIPDrumInventoryFaultSource(Q0 = 0, h0 = 978915) annotation(
    Placement(visible = false, transformation(extent = {{80, -410}, {120, -390}})));
  VPPFixedFlowInjector vppIPDrumInventoryFaultInjector annotation(
    Placement(visible = false, transformation(extent = {{130, -410}, {150, -390}})));
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppIPDrumInventoryFaultFlowCommand annotation(
    Placement(visible = false, transformation(extent = {{30, -410}, {50, -390}})));
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppIPDrumInventoryFaultEnthalpyCommand annotation(
    Placement(visible = false, transformation(extent = {{30, -440}, {50, -420}})));
  ThermoSysPro.WaterSteam.BoundaryConditions.SourceQ vppLPDrumInventoryFaultSource(Q0 = 0, h0 = 549250) annotation(
    Placement(visible = false, transformation(extent = {{240, -410}, {280, -390}})));
  VPPFixedFlowInjector vppLPDrumInventoryFaultInjector annotation(
    Placement(visible = false, transformation(extent = {{290, -410}, {310, -390}})));
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppLPDrumInventoryFaultFlowCommand annotation(
    Placement(visible = false, transformation(extent = {{190, -410}, {210, -390}})));
  ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal vppLPDrumInventoryFaultEnthalpyCommand annotation(
    Placement(visible = false, transformation(extent = {{190, -440}, {210, -420}})));
  VPPRegularizedMixingVolume vppCondenserSteamVolume(V = vppLPHeaderVolume,  // Condenser pressure already supplies the LP-side mass-storage state.
 // This header retains its own thermal hold-up without duplicating that
 // pressure state across an ideal (zero-pressure-drop) sensor connection.
  dynamic_mass_balance = false, steady_state = true, mode = 0, P(start = 6136, nominal = 1e4), h(start = 2401030, nominal = 2.5e6), Ce1(Q(start = vppCondenserSteamFlow0, nominal = 200), h(start = 2401030), h_vol(start = 2401030)), Ce2(Q(start = 0, nominal = 200), h(start = 2962470), h_vol(start = 2401030)), Ce3(Q(start = vppSpraySeatLeak, nominal = 200), h(start = 550000), h_vol(start = 2401030)), Cs(Q(start = vppCondenserSteamFlow0, nominal = 200), h(start = 2401030), h_vol(start = 2401030))) annotation(
    Placement(visible = false, transformation(extent = {{620, -306}, {660, -286}})));
equation
  // TRIPLENS_ECMS_5605_SINGLE_SERVER_NODES_V1: electrically isolated command memory and feedback
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: command states
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: selection, physical drive and direct telemetry
  vppVlvHPFWCVAutoCmd = noEvent(min(1, max(0, regulation_Niveau_HP.SortieReelle1.signal)));
  vppVlvHPFWCVCmd = if noEvent(vppVlvHPFWCVModeAutoNative >= 0.5) then noEvent(min(1, max(0, regulation_Niveau_HP.SortieReelle1.signal))) else noEvent(min(1, max(0, vppVlvHPFWCVManualCmdNative)));
  der(vppVlvHPFWCVFaultStroke) = ((if noEvent(vppVlvHPFWCVFaultEnableNative >= 0.5) then noEvent(min(1, max(vppDrumFaultValveMinimumOpening, min(1, max(0, vppVlvHPFWCVFaultValueNative))))) else vppVlvHPFWCVCmd) - vppVlvHPFWCVFaultStroke)/vppDrumFaultValveStrokeTime;
  vppVlvHPFWCVTarget = if noEvent(vppVlvHPFWCVFaultEnableNative >= 0.5) then vppVlvHPFWCVFaultStroke else vppVlvHPFWCVCmd;
  vanne_alimentationHP.Ouv.signal = vppVlvHPFWCVTarget;
  vppVlvHPFWCVFb = noEvent(if abs(vanne_alimentationHP.Cvmax) > Modelica.Constants.eps then vanne_alimentationHP.Cv/vanne_alimentationHP.Cvmax else 0);
  vppVlvHPFWCVDeviation = vppVlvHPFWCVCmd - vppVlvHPFWCVFb;
  vppVlvHPFWCVFaultActive = vppVlvHPFWCVFaultEnableNative >= 0.5;
  vppVlvHPFWCVCv = vanne_alimentationHP.Cv;
  vppVlvHPFWCVMassFlowTH = 3.6*vanne_alimentationHP.Q;
  vppVlvHPFWCVDPPa = vanne_alimentationHP.C1.P - vanne_alimentationHP.C2.P;
  vppVlvHPSteamAutoCmd = noEvent(min(1, max(0, constante_vanne_vapeurHP.y.signal))) - 1*Modelica.Constants.eps*(1 - cos(time));
  vppVlvHPSteamCmd = if noEvent(vppVlvHPSteamModeAutoNative >= 0.5) then noEvent(min(1, max(0, constante_vanne_vapeurHP.y.signal))) else noEvent(min(1, max(0, vppVlvHPSteamManualCmdNative)));
  der(vppVlvHPSteamFaultStroke) = ((if noEvent(vppVlvHPSteamFaultEnableNative >= 0.5) then noEvent(min(1, max(vppDrumFaultValveMinimumOpening, min(1, max(0, vppVlvHPSteamFaultValueNative))))) else vppVlvHPSteamCmd) - vppVlvHPSteamFaultStroke)/vppDrumFaultValveStrokeTime;
  vppVlvHPSteamTarget = if noEvent(vppVlvHPSteamFaultEnableNative >= 0.5) then vppVlvHPSteamFaultStroke else vppVlvHPSteamCmd;
  vanne_vapeurHP.Ouv.signal = vppVlvHPSteamTarget;
  vppVlvHPSteamFb = noEvent(if abs(vanne_vapeurHP.Cvmax) > Modelica.Constants.eps then vanne_vapeurHP.Cv/vanne_vapeurHP.Cvmax else 0);
  vppVlvHPSteamDeviation = vppVlvHPSteamCmd - vppVlvHPSteamFb;
  vppVlvHPSteamFaultActive = vppVlvHPSteamFaultEnableNative >= 0.5;
  vppVlvHPSteamCv = vanne_vapeurHP.Cv;
  vppVlvHPSteamMassFlowTH = 3.6*vanne_vapeurHP.Q;
  vppVlvHPSteamDPPa = vanne_vapeurHP.C1.P - vanne_vapeurHP.C2.P;
  vppVlvIPFWCVAutoCmd = noEvent(min(1, max(0, regulation_Niveau_MP.SortieReelle1.signal)));
  vppVlvIPFWCVCmd = if noEvent(vppVlvIPFWCVModeAutoNative >= 0.5) then noEvent(min(1, max(0, regulation_Niveau_MP.SortieReelle1.signal))) else noEvent(min(1, max(0, vppVlvIPFWCVManualCmdNative)));
  der(vppVlvIPFWCVFaultStroke) = ((if noEvent(vppVlvIPFWCVFaultEnableNative >= 0.5) then noEvent(min(1, max(vppDrumFaultValveMinimumOpening, min(1, max(0, vppVlvIPFWCVFaultValueNative))))) else vppVlvIPFWCVCmd) - vppVlvIPFWCVFaultStroke)/vppDrumFaultValveStrokeTime;
  vppVlvIPFWCVTarget = if noEvent(vppVlvIPFWCVFaultEnableNative >= 0.5) then vppVlvIPFWCVFaultStroke else vppVlvIPFWCVCmd;
  vanne_alimentationMP.Ouv.signal = vppVlvIPFWCVTarget;
  vppVlvIPFWCVFb = noEvent(if abs(vanne_alimentationMP.Cvmax) > Modelica.Constants.eps then vanne_alimentationMP.Cv/vanne_alimentationMP.Cvmax else 0);
  vppVlvIPFWCVDeviation = vppVlvIPFWCVCmd - vppVlvIPFWCVFb;
  vppVlvIPFWCVFaultActive = vppVlvIPFWCVFaultEnableNative >= 0.5;
  vppVlvIPFWCVCv = vanne_alimentationMP.Cv;
  vppVlvIPFWCVMassFlowTH = 3.6*vanne_alimentationMP.Q;
  vppVlvIPFWCVDPPa = vanne_alimentationMP.C1.P - vanne_alimentationMP.C2.P;
  vppVlvIPSteamAutoCmd = noEvent(min(1, max(0, constante_vanne_vapeurMP.y.signal))) - 2*Modelica.Constants.eps*(1 - cos(time));
  vppVlvIPSteamCmd = if noEvent(vppVlvIPSteamModeAutoNative >= 0.5) then noEvent(min(1, max(0, constante_vanne_vapeurMP.y.signal))) else noEvent(min(1, max(0, vppVlvIPSteamManualCmdNative)));
  der(vppVlvIPSteamFaultStroke) = ((if noEvent(vppVlvIPSteamFaultEnableNative >= 0.5) then noEvent(min(1, max(vppDrumFaultValveMinimumOpening, min(1, max(0, vppVlvIPSteamFaultValueNative))))) else vppVlvIPSteamCmd) - vppVlvIPSteamFaultStroke)/vppDrumFaultValveStrokeTime;
  vppVlvIPSteamTarget = if noEvent(vppVlvIPSteamFaultEnableNative >= 0.5) then vppVlvIPSteamFaultStroke else vppVlvIPSteamCmd;
  vanne_vapeurMP.Ouv.signal = vppVlvIPSteamTarget;
  vppVlvIPSteamFb = noEvent(if abs(vanne_vapeurMP.Cvmax) > Modelica.Constants.eps then vanne_vapeurMP.Cv/vanne_vapeurMP.Cvmax else 0);
  vppVlvIPSteamDeviation = vppVlvIPSteamCmd - vppVlvIPSteamFb;
  vppVlvIPSteamFaultActive = vppVlvIPSteamFaultEnableNative >= 0.5;
  vppVlvIPSteamCv = vanne_vapeurMP.Cv;
  vppVlvIPSteamMassFlowTH = 3.6*vanne_vapeurMP.Q;
  vppVlvIPSteamDPPa = vanne_vapeurMP.C1.P - vanne_vapeurMP.C2.P;
  vppVlvLPSteamAutoCmd = noEvent(min(1, max(0, regulation_Niveau_BP.SortieReelle1.signal*vppLPDrumAdmissionMultiplier)));
  vppVlvLPSteamCmd = if noEvent(vppVlvLPSteamModeAutoNative >= 0.5) then noEvent(min(1, max(0, regulation_Niveau_BP.SortieReelle1.signal*vppLPDrumAdmissionMultiplier))) else noEvent(min(1, max(0, vppVlvLPSteamManualCmdNative)));
  der(vppVlvLPSteamFaultStroke) = ((if noEvent(vppVlvLPSteamFaultEnableNative >= 0.5) then noEvent(min(1, max(vppDrumFaultValveMinimumOpening, min(1, max(0, vppVlvLPSteamFaultValueNative))))) else vppVlvLPSteamCmd) - vppVlvLPSteamFaultStroke)/vppDrumFaultValveStrokeTime;
  vppVlvLPSteamTarget = if noEvent(vppVlvLPSteamFaultEnableNative >= 0.5) then vppVlvLPSteamFaultStroke else vppVlvLPSteamCmd;
  vanne_vapeurBP.Ouv.signal = vppVlvLPSteamTarget;
  vppVlvLPSteamFb = noEvent(if abs(vanne_vapeurBP.Cvmax) > Modelica.Constants.eps then vanne_vapeurBP.Cv/vanne_vapeurBP.Cvmax else 0);
  vppVlvLPSteamDeviation = vppVlvLPSteamCmd - vppVlvLPSteamFb;
  vppVlvLPSteamFaultActive = vppVlvLPSteamFaultEnableNative >= 0.5;
  vppVlvLPSteamCv = vanne_vapeurBP.Cv;
  vppVlvLPSteamMassFlowTH = 3.6*vanne_vapeurBP.Q;
  vppVlvLPSteamDPPa = vanne_vapeurBP.C1.P - vanne_vapeurBP.C2.P;
  vppVlvLPFWAutoCmd = noEvent(min(1, max(0, constante_vanne_vapeurBP.y.signal))) - 3*Modelica.Constants.eps*(1 - cos(time));
  vppVlvLPFWCmd = if noEvent(vppVlvLPFWModeAutoNative >= 0.5) then noEvent(min(1, max(0, constante_vanne_vapeurBP.y.signal))) else noEvent(min(1, max(0, vppVlvLPFWManualCmdNative)));
  der(vppVlvLPFWFaultStroke) = ((if noEvent(vppVlvLPFWFaultEnableNative >= 0.5) then noEvent(min(1, max(vppDrumFaultValveMinimumOpening, min(1, max(0, vppVlvLPFWFaultValueNative))))) else vppVlvLPFWCmd) - vppVlvLPFWFaultStroke)/vppDrumFaultValveStrokeTime;
  vppVlvLPFWTarget = if noEvent(vppVlvLPFWFaultEnableNative >= 0.5) then vppVlvLPFWFaultStroke else vppVlvLPFWCmd;
  vanne_alimentationBP.Ouv.signal = vppVlvLPFWTarget;
  vppVlvLPFWFb = noEvent(if abs(vanne_alimentationBP.Cvmax) > Modelica.Constants.eps then vanne_alimentationBP.Cv/vanne_alimentationBP.Cvmax else 0);
  vppVlvLPFWDeviation = vppVlvLPFWCmd - vppVlvLPFWFb;
  vppVlvLPFWFaultActive = vppVlvLPFWFaultEnableNative >= 0.5;
  vppVlvLPFWCv = vanne_alimentationBP.Cv;
  vppVlvLPFWMassFlowTH = 3.6*vanne_alimentationBP.Q;
  vppVlvLPFWDPPa = vanne_alimentationBP.C1.P - vanne_alimentationBP.C2.P;
  vppVlvLPToHPIPFWAutoCmd = noEvent(min(1, max(0, constante_ballonBP.y.signal))) - 4*Modelica.Constants.eps*(1 - cos(time));
  vppVlvLPToHPIPFWCmd = if noEvent(vppVlvLPToHPIPFWModeAutoNative >= 0.5) then noEvent(min(1, max(0, constante_ballonBP.y.signal))) else noEvent(min(1, max(0, vppVlvLPToHPIPFWManualCmdNative)));
  vppVlvLPToHPIPFWTarget = if noEvent(vppVlvLPToHPIPFWFaultEnableNative >= 0.5) then noEvent(min(1, max(0, vppVlvLPToHPIPFWFaultValueNative))) else vppVlvLPToHPIPFWCmd;
  Vanne_alimentationMPHP.Ouv.signal = vppVlvLPToHPIPFWTarget;
  vppVlvLPToHPIPFWFb = noEvent(if abs(Vanne_alimentationMPHP.Cvmax) > Modelica.Constants.eps then Vanne_alimentationMPHP.Cv/Vanne_alimentationMPHP.Cvmax else 0);
  vppVlvLPToHPIPFWDeviation = vppVlvLPToHPIPFWCmd - vppVlvLPToHPIPFWFb;
  vppVlvLPToHPIPFWFaultActive = vppVlvLPToHPIPFWFaultEnableNative >= 0.5;
  vppVlvLPToHPIPFWCv = Vanne_alimentationMPHP.Cv;
  vppVlvLPToHPIPFWMassFlowTH = 3.6*Vanne_alimentationMPHP.Q;
  vppVlvLPToHPIPFWDPPa = Vanne_alimentationMPHP.C1.P - Vanne_alimentationMPHP.C2.P;
  vppVlvCondExtractionAutoCmd = noEvent(min(1, max(0, regulation_Niveau_Condenseur.SortieReelle1.signal)));
  vppVlvCondExtractionCmd = if noEvent(vppVlvCondExtractionModeAutoNative >= 0.5) then noEvent(min(1, max(0, regulation_Niveau_Condenseur.SortieReelle1.signal))) else noEvent(min(1, max(0, vppVlvCondExtractionManualCmdNative)));
  vppVlvCondExtractionTarget = if noEvent(vppVlvCondExtractionFaultEnableNative >= 0.5) then noEvent(min(1, max(0, vppVlvCondExtractionFaultValueNative))) else vppVlvCondExtractionCmd;
  vanne_extraction.Ouv.signal = vppVlvCondExtractionTarget;
  vppVlvCondExtractionFb = noEvent(if abs(vanne_extraction.Cvmax) > Modelica.Constants.eps then vanne_extraction.Cv/vanne_extraction.Cvmax else 0);
  vppVlvCondExtractionDeviation = vppVlvCondExtractionCmd - vppVlvCondExtractionFb;
  vppVlvCondExtractionFaultActive = vppVlvCondExtractionFaultEnableNative >= 0.5;
  vppVlvCondExtractionCv = vanne_extraction.Cv;
  vppVlvCondExtractionMassFlowTH = 3.6*vanne_extraction.Q;
  vppVlvCondExtractionDPPa = vanne_extraction.C1.P - vanne_extraction.C2.P;
  vppVlvHPTurbAdmAutoCmd = noEvent(min(1, max(0, vppHPAdmissionPos)));
  vppVlvHPTurbAdmCmd = if noEvent(vppVlvHPTurbAdmModeAutoNative >= 0.5) then noEvent(min(1, max(0, vppHPAdmissionPos))) else noEvent(min(1, max(0, vppVlvHPTurbAdmManualCmdNative)));
  vppVlvHPTurbAdmTarget = if noEvent(vppVlvHPTurbAdmFaultEnableNative >= 0.5) then noEvent(min(1, max(0, vppVlvHPTurbAdmFaultValueNative))) else vppVlvHPTurbAdmCmd;
  vanne_entree_TurbineHP.Ouv.signal = vppVlvHPTurbAdmTarget;
  vppVlvHPTurbAdmFb = noEvent(if abs(vanne_entree_TurbineHP.Cvmax) > Modelica.Constants.eps then vanne_entree_TurbineHP.Cv/vanne_entree_TurbineHP.Cvmax else 0);
  vppVlvHPTurbAdmDeviation = vppVlvHPTurbAdmCmd - vppVlvHPTurbAdmFb;
  vppVlvHPTurbAdmFaultActive = vppVlvHPTurbAdmFaultEnableNative >= 0.5;
  vppVlvHPTurbAdmCv = vanne_entree_TurbineHP.Cv;
  vppVlvHPTurbAdmMassFlowTH = 3.6*vanne_entree_TurbineHP.Q;
  vppVlvHPTurbAdmDPPa = vanne_entree_TurbineHP.C1.P - vanne_entree_TurbineHP.C2.P;
  vppVlvHPFWIsoAutoCmd = noEvent(min(1, max(0, arretPomesMp1.y.signal)));
  vppVlvHPFWIsoCmd = if noEvent(vppVlvHPFWIsoModeAutoNative >= 0.5) then noEvent(min(1, max(0, arretPomesMp1.y.signal))) else noEvent(min(1, max(0, vppVlvHPFWIsoManualCmdNative)));
  vppVlvHPFWIsoTarget = if noEvent(vppVlvHPFWIsoFaultEnableNative >= 0.5) then noEvent(min(1, max(0, vppVlvHPFWIsoFaultValueNative))) else vppVlvHPFWIsoCmd;
  Vanne_alimentationMPHP1.Ouv.signal = vppVlvHPFWIsoTarget;
  vppVlvHPFWIsoFb = noEvent(if abs(Vanne_alimentationMPHP1.Cvmax) > Modelica.Constants.eps then Vanne_alimentationMPHP1.Cv/Vanne_alimentationMPHP1.Cvmax else 0);
  vppVlvHPFWIsoDeviation = vppVlvHPFWIsoCmd - vppVlvHPFWIsoFb;
  vppVlvHPFWIsoFaultActive = vppVlvHPFWIsoFaultEnableNative >= 0.5;
  vppVlvHPFWIsoCv = Vanne_alimentationMPHP1.Cv;
  vppVlvHPFWIsoMassFlowTH = 3.6*Vanne_alimentationMPHP1.Q;
  vppVlvHPFWIsoDPPa = Vanne_alimentationMPHP1.C1.P - Vanne_alimentationMPHP1.C2.P;
  vppVlvIPFWIsoAutoCmd = noEvent(min(1, max(0, arretPomesHP1.y.signal)));
  vppVlvIPFWIsoCmd = if noEvent(vppVlvIPFWIsoModeAutoNative >= 0.5) then noEvent(min(1, max(0, arretPomesHP1.y.signal))) else noEvent(min(1, max(0, vppVlvIPFWIsoManualCmdNative)));
  vppVlvIPFWIsoTarget = if noEvent(vppVlvIPFWIsoFaultEnableNative >= 0.5) then noEvent(min(1, max(0, vppVlvIPFWIsoFaultValueNative))) else vppVlvIPFWIsoCmd;
  Vanne_alimentationMPHP2.Ouv.signal = vppVlvIPFWIsoTarget;
  vppVlvIPFWIsoFb = noEvent(if abs(Vanne_alimentationMPHP2.Cvmax) > Modelica.Constants.eps then Vanne_alimentationMPHP2.Cv/Vanne_alimentationMPHP2.Cvmax else 0);
  vppVlvIPFWIsoDeviation = vppVlvIPFWIsoCmd - vppVlvIPFWIsoFb;
  vppVlvIPFWIsoFaultActive = vppVlvIPFWIsoFaultEnableNative >= 0.5;
  vppVlvIPFWIsoCv = Vanne_alimentationMPHP2.Cv;
  vppVlvIPFWIsoMassFlowTH = 3.6*Vanne_alimentationMPHP2.Q;
  vppVlvIPFWIsoDPPa = Vanne_alimentationMPHP2.C1.P - Vanne_alimentationMPHP2.C2.P;
  vppVlvIPTurbAdmAutoCmd = noEvent(min(1, max(0, vppIPAdmissionPos)));
  vppVlvIPTurbAdmCmd = if noEvent(vppVlvIPTurbAdmModeAutoNative >= 0.5) then noEvent(min(1, max(0, vppIPAdmissionPos))) else noEvent(min(1, max(0, vppVlvIPTurbAdmManualCmdNative)));
  vppVlvIPTurbAdmTarget = if noEvent(vppVlvIPTurbAdmFaultEnableNative >= 0.5) then noEvent(min(1, max(0, vppVlvIPTurbAdmFaultValueNative))) else vppVlvIPTurbAdmCmd;
  vanne_entree_TurbineMP.Ouv.signal = vppVlvIPTurbAdmTarget;
  vppVlvIPTurbAdmFb = noEvent(if abs(vanne_entree_TurbineMP.Cvmax) > Modelica.Constants.eps then vanne_entree_TurbineMP.Cv/vanne_entree_TurbineMP.Cvmax else 0);
  vppVlvIPTurbAdmDeviation = vppVlvIPTurbAdmCmd - vppVlvIPTurbAdmFb;
  vppVlvIPTurbAdmFaultActive = vppVlvIPTurbAdmFaultEnableNative >= 0.5;
  vppVlvIPTurbAdmCv = vanne_entree_TurbineMP.Cv;
  vppVlvIPTurbAdmMassFlowTH = 3.6*vanne_entree_TurbineMP.Q;
  vppVlvIPTurbAdmDPPa = vanne_entree_TurbineMP.C1.P - vanne_entree_TurbineMP.C2.P;
  vppECMSCBInAClosed = vppECMSCBInAClosedCommandNative >= 0.5;
  vppECMSCBInBClosed = vppECMSCBInBClosedCommandNative >= 0.5;
  vppECMSCBTieClosed = vppECMSCBTieClosedCommandNative >= 0.5;
  vppECMSBusAAvailable = vppECMSCBInAClosed or (vppECMSCBTieClosed and vppECMSCBInBClosed);
  vppECMSBusBAvailable = vppECMSCBInBClosed or (vppECMSCBTieClosed and vppECMSCBInAClosed);
  vppECMSVCBA01Closed = vppVCBA01TripCommandNative < 0.5 and vppVCBA01ClosedNative >= 0.5 and vppECMSBusAAvailable;
  vppECMSVCBA02Closed = vppVCBA02TripCommandNative < 0.5 and vppVCBA02ClosedNative >= 0.5 and vppECMSBusAAvailable;
  vppECMSVCBB01Closed = vppVCBB01TripCommandNative < 0.5 and vppVCBB01ClosedNative >= 0.5 and vppECMSBusBAvailable;
// Canonical protection and plant-flow aliases used by the native OPC UA
// client. They are evaluated from the same Modelica solution as the plant.
  // TRIPLENS_HP_IP_BFP_OPERATOR_CHAINS_V8
  // V8.5 keeps the proven V7 HP/IP pump speed connections intact.
  vppHPFWPTripCommandNative =
    if vppHPFWPTripPushbuttonNative >= 0.5 then 1 else 0;
  vppHPFWPTripLatchNative = vppHPFWPTripLatchState;
  vppVCBA01TripCommandNative = vppHPFWPTripLatchState;
  vppIPFWPTripCommandNative =
    if vppIPFWPTripPushbuttonNative >= 0.5 then 1 else 0;
  vppIPFWPTripLatchNative = vppIPFWPTripLatchState;
  vppVCBB01TripCommandNative = vppIPFWPTripLatchState;
  when vppHPFWPResetPushbuttonNative >= 0.5 and
      vppHPFWPTripPushbuttonNative < 0.5 and
      vppVCBA01ClosedNative < 0.5 then
    vppHPFWPTripLatchState = 0;
  elsewhen vppHPFWPTripPushbuttonNative >= 0.5 then
    vppHPFWPTripLatchState = 1;
  end when;
  when vppIPFWPResetPushbuttonNative >= 0.5 and
      vppIPFWPTripPushbuttonNative < 0.5 and
      vppVCBB01ClosedNative < 0.5 then
    vppIPFWPTripLatchState = 0;
  elsewhen vppIPFWPTripPushbuttonNative >= 0.5 then
    vppIPFWPTripLatchState = 1;
  end when;
  // TRIPLENS_PROTECTION_MATRIX_V8: nine explicit causes and two requests
  vppHPDrumHHRaw = vppHPDrumLevelM >= vppHPDrumHHSetpoint;
  vppIPDrumHHRaw = vppIPDrumLevelM >= vppIPDrumHHSetpoint;
  vppLPDrumHHRaw = vppLPDrumLevelM >= vppLPDrumHHSetpoint;
  vppHPDrumLLRaw = vppHPDrumLevelM <= vppHPDrumLLSetpoint;
  vppIPDrumLLRaw = vppIPDrumLevelM <= vppIPDrumLLSetpoint;
  vppLPDrumLLRaw = vppLPDrumLevelM <= vppLPDrumLLSetpoint;
  vppCauseDirectGTTrip = if vppUseExternalTripInput then
    vppExternalTripCommandNative >= 0.5 else time >= vppTripTime;
  vppCauseGTBreakerOpenWhileRunning = vppGTBreakerOpenCauseState;
  vppCauseDirectSTTrip = vppExternalSTTripCommandNative >= 0.5;
  vppCauseHPDrumHH = vppHPDrumHHRaw and vppHPDrumHHAssertTime >= 0 and
    time >= vppHPDrumHHAssertTime + vppDrumTripDelay;
  vppCauseIPDrumHH = vppIPDrumHHRaw and vppIPDrumHHAssertTime >= 0 and
    time >= vppIPDrumHHAssertTime + vppDrumTripDelay;
  vppCauseLPDrumHH = vppLPDrumHHRaw and vppLPDrumHHAssertTime >= 0 and
    time >= vppLPDrumHHAssertTime + vppDrumTripDelay;
  vppCauseHPDrumLL = vppHPDrumLLRaw and vppHPDrumLLAssertTime >= 0 and
    time >= vppHPDrumLLAssertTime + vppDrumTripDelay;
  vppCauseIPDrumLL = vppIPDrumLLRaw and vppIPDrumLLAssertTime >= 0 and
    time >= vppIPDrumLLAssertTime + vppDrumTripDelay;
  vppCauseLPDrumLL = vppLPDrumLLRaw and vppLPDrumLLAssertTime >= 0 and
    time >= vppLPDrumLLAssertTime + vppDrumTripDelay;
  vppGTTripRequest = vppCauseDirectGTTrip or
    vppCauseGTBreakerOpenWhileRunning or vppCauseHPDrumLL or
    vppCauseIPDrumLL or vppCauseLPDrumLL;
  vppSTTripRequest = vppGTTripRequest or vppCauseDirectSTTrip or
    vppCauseHPDrumHH or vppCauseIPDrumHH or vppCauseLPDrumHH;
  vppGTTripCmd = vppGTTripRequest;
  vppGTTripLatch = vppGTTripLatchInternal;
  vppSTTripLatchPublished = vppSTTripLatch;
  vpp52GTTripCmd = vppGTTripLatchInternal and
    time >= vppGTTripAssertTime + vppGTTripCommandDelay;
  vpp52GTClosed = vppECMS52GTClosedCommandNative >= 0.5 and not
    (vppGTTripLatchInternal and time >= vppGTTripAssertTime + vppGTBreakerOpenDelay);
  vpp52STTripCmd = vppSTTripLatch;
  vpp52STClosed = vppECMS52STClosedCommandNative >= 0.5 and not
    (vppSTTripLatch and time >= vppSTTripAssertTime + vppSTBreakerOpenDelay);
  vppGTGPowerMW = if not vppGTTripLatchInternal then vppGTGPowerNormalMW
    else if vpp52GTClosed then vppGTGPowerNormalMW*exp(-max(0, time -
      vppGTTripAssertTime)/vppGTGPowerDecayTau) else 0;
  vppGTGSpeedRPM = if not vppGTTripLatchInternal or vpp52GTClosed then
    vppGTGSpeedNormalRPM else vppGTGSpeedNormalRPM*exp(-max(0, time -
      vppGTTripAssertTime - vppGTBreakerOpenDelay)/vppGTGCoastdownTau);
  vppGTExhaustMassFlowTH = 3.6*vppGTExhaustMassFlowCommand.signal;
  vppGTExhaustTemperatureK = vppGTExhaustTemperatureCommand.signal;
  vppHPTurbineSteamFlowTH = 3.6*TurbineHP.Q;
  vppIPTurbineSteamFlowTH = 3.6*TurbineMP.Q;
  vppLPTurbineSteamFlowTH = 3.6*TurbineBP.Q;
  vppHPBypassMassFlowTH = 3.6*vppHPBypassMassFlow;
  vppLPBypassMassFlowTH = 3.6*vppLPBypassMassFlow;
  vppHPSprayMassFlowTH = 3.6*vppHPSprayMassFlow;
  vppLPSprayMassFlowTH = 3.6*vppLPSprayMassFlow;
// Additional v36-only aliases used by DynamicSelect and OPC UA browse.
  vppHPDrumLevelM = BallonHP.yLevel.signal;
  vppIPDrumLevelM = BallonMP.yLevel.signal;
  vppLPDrumLevelM = BallonBP.yLevel.signal;
  // TRIPLENS_DRUM_INVENTORY_FAULT_PATH_V1: finite, mass-balanced physical
  // disturbance.  The raw level remains the only protection measurement.
  vppHPDrumInventoryFaultActive = vppHPDrumInventoryFaultEnableNative >= 0.5;
  vppHPDrumInventoryFaultFlowCommand.signal = noEvent(if
      vppHPDrumInventoryFaultActive then vppHPDrumInventoryFaultCapacity*
      min(1, max(-1, vppHPDrumInventoryFaultValueNative)) else 0);
  vppHPDrumInventoryFaultEnthalpyCommand.signal = BallonHP.hl;
  vppHPDrumInventoryDisturbanceMassFlowTH = 3.6*vppHPDrumInventoryFaultSource.Q;
  vppIPDrumInventoryFaultActive = vppIPDrumInventoryFaultEnableNative >= 0.5;
  vppIPDrumInventoryFaultFlowCommand.signal = noEvent(if
      vppIPDrumInventoryFaultActive then vppIPDrumInventoryFaultCapacity*
      min(1, max(-1, vppIPDrumInventoryFaultValueNative)) else 0);
  vppIPDrumInventoryFaultEnthalpyCommand.signal = BallonMP.hl;
  vppIPDrumInventoryDisturbanceMassFlowTH = 3.6*vppIPDrumInventoryFaultSource.Q;
  vppLPDrumInventoryFaultActive = vppLPDrumInventoryFaultEnableNative >= 0.5;
  vppLPDrumInventoryFaultFlowCommand.signal = noEvent(if
      vppLPDrumInventoryFaultActive then vppLPDrumInventoryFaultCapacity*
      min(1, max(-1, vppLPDrumInventoryFaultValueNative)) else 0);
  vppLPDrumInventoryFaultEnthalpyCommand.signal = BallonBP.hl;
  vppLPDrumInventoryDisturbanceMassFlowTH = 3.6*vppLPDrumInventoryFaultSource.Q;
  vppHPDrumPressurePa = BallonHP.P;
  vppIPDrumPressurePa = BallonMP.P;
  vppLPDrumPressurePa = BallonBP.P;
  vppHPFWPMassFlowTH = vppHPFWPCheckValveMassFlowTH;
  vppIPFWPMassFlowTH = vppIPFWPCheckValveMassFlowTH;
  vppHPFWPDeltaPPa = PompeAlimHP.deltaP;
  vppIPFWPDeltaPPa = PompeAlimMP.deltaP;
  vppHPFWPSpeedCommandRPM = vppHPFWPHydraulicSpeedCommand.signal;
  vppIPFWPSpeedCommandRPM = vppIPFWPHydraulicSpeedCommand.signal;
  vppHPFWPMotorEnergized = vppECMSVCBA01Closed;
  vppIPFWPMotorEnergized = vppECMSVCBB01Closed;
  vppHPFWPDrive.breakerClosed.signal = vppHPFWPMotorEnergized;
  vppIPFWPDrive.breakerClosed.signal = vppIPFWPMotorEnergized;
  vppHPFWPDrive.pumpPower.signal = PompeAlimHP.Wm;
  vppIPFWPDrive.pumpPower.signal = PompeAlimMP.Wm;
  // TRIPLENS_HP_IP_V7_NORMAL_SPEED_BOUNDARY_V8_8: retain the exact V7 Ramp
  // command during normal operation.  Only after its own VCB opens does the
  // same pump input follow the independently integrated shaft speed.  This
  // preserves the proven pre-trip plant operating point and confines the
  // V8 adapter to the physical coastdown interval.
  vppHPFWPHydraulicSpeedCommand.signal = if vppHPFWPMotorEnergized then
    arretPomesHP.y.signal else noEvent(max(vppHPFWPHydraulicSpeedFloorRPM,
    vppHPFWPDrive.speedRpm));
  vppIPFWPHydraulicSpeedCommand.signal = if vppIPFWPMotorEnergized then
    arretPomesMp.y.signal else noEvent(max(vppIPFWPHydraulicSpeedFloorRPM,
    vppIPFWPDrive.speedRpm));
  vppHPFWPSpeedRPM = vppHPFWPDrive.speedRpm;
  vppIPFWPSpeedRPM = vppIPFWPDrive.speedRpm;
  vppHPFWPHydraulicSpeedRPM = vppHPFWPHydraulicSpeedCommand.signal;
  vppIPFWPHydraulicSpeedRPM = vppIPFWPHydraulicSpeedCommand.signal;
  vppHPFWPSpeedProven = vppHPFWPSpeedRPM >= 0.9*vppHPFWPDrive.nominalSpeedRpm;
  vppIPFWPSpeedProven = vppIPFWPSpeedRPM >= 0.9*vppIPFWPDrive.nominalSpeedRpm;
  // Keep HP/IP running proof identical to the validated LP boundary.  Flow
  // remains an independent physical feedback/alarm, so a transient flow
  // reversal cannot mask the motor-speed loss event.
  vppHPFWPRunning = vppHPFWPMotorEnergized and vppHPFWPSpeedProven;
  vppIPFWPRunning = vppIPFWPMotorEnergized and vppIPFWPSpeedProven;
  connect(vppHPFWPHydraulicSpeedCommand, PompeAlimHP.rpm_or_mpower) annotation(
    Line(visible = false, points = {{650, -25}, {720, -25}, {720, -50}, {781, -50}}, color = {0, 0, 127}));
  connect(vppIPFWPHydraulicSpeedCommand, PompeAlimMP.rpm_or_mpower) annotation(
    Line(visible = false, points = {{650, 15}, {710, 15}, {710, -10}, {781, -10}}, color = {0, 0, 127}));
  vppSTTripLatched = vppSTTripLatch;
  // TRIPLENS_LP_BFP_OPERATOR_CHAIN_V1: observable protection chain
  vppLPFWPTripCommandNative =
    if vppLPFWPTripPushbuttonNative >= 0.5 then 1 else 0;
  vppLPFWPTripLatchNative = vppLPFWPTripLatchState;
  vppVCBA02TripCommandNative = vppLPFWPTripLatchState;
  when vppLPFWPResetPushbuttonNative >= 0.5 then
    vppLPFWPTripLatchState = 0;
  elsewhen vppLPFWPTripPushbuttonNative >= 0.5 then
    vppLPFWPTripLatchState = 1;
  end when;
  vppLPFWPMotorEnergized = vppECMSVCBA02Closed;
  vppLPFWPDrive.breakerClosed.signal = vppLPFWPMotorEnergized;
  vppLPFWPDrive.pumpPower.signal = PompeAlimBP.Wm;
  vppLPFWPHydraulicSpeedCommand.signal = noEvent(max(vppLPFWPHydraulicSpeedFloorRPM, vppLPFWPDrive.speedRpm));
  connect(vppLPFWPHydraulicSpeedCommand, PompeAlimBP.rpm_or_mpower) annotation(
    Line(visible = false, points = {{690, -485}, {719, -485}, {719, -446}}, color = {0, 0, 127}));
  connect(PompeAlimBP.C2, vppLPFWPCheckValve.C1) annotation(
    Line(visible = false, points = {{729, -436}, {739, -436}}, color = {0, 0, 255}));
  connect(vppLPFWPCheckValve.C2, vanne_extraction.C1) annotation(
    Line(visible = false, points = {{759, -436}, {769, -430}}, color = {0, 0, 255}));
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
  connect(PompeAlimHP.C2, vppHPFWPCheckValve.C1) annotation(
    Line(visible = false, points = {{781, -50}, {767, -72}}, color = {0, 0, 255}));
  connect(vppHPFWPCheckValve.C2, Vanne_alimentationMPHP1.C1) annotation(
    Line(visible = false, points = {{747, -72}, {709, -110}}, color = {0, 0, 255}));
  connect(PompeAlimMP.C2, vppIPFWPCheckValve.C1) annotation(
    Line(visible = false, points = {{781, -10}, {767, -112}}, color = {0, 0, 255}));
  connect(vppIPFWPCheckValve.C2, Vanne_alimentationMPHP2.C1) annotation(
    Line(visible = false, points = {{747, -112}, {771, -150}}, color = {0, 0, 255}));
  vppHPFWPCheckValveOpen = vppHPFWPCheckValve.ouvert;
  vppHPFWPCheckValveOpening = vppHPFWPCheckValve.opening;
  vppHPFWPCheckValveMassFlowTH = 3.6*vppHPFWPCheckValve.Q;
  vppHPFWPCheckValveDeltaPPa = vppHPFWPCheckValve.deltaP;
  vppHPFWPCheckValveInletPressurePa = vppHPFWPCheckValve.C1.P;
  vppHPFWPCheckValveOutletPressurePa = vppHPFWPCheckValve.C2.P;
  vppHPFWPCheckValveResistancePaSPerKg = vppHPFWPCheckValve.effectiveResistance;
  vppIPFWPCheckValveOpen = vppIPFWPCheckValve.ouvert;
  vppIPFWPCheckValveOpening = vppIPFWPCheckValve.opening;
  vppIPFWPCheckValveMassFlowTH = 3.6*vppIPFWPCheckValve.Q;
  vppIPFWPCheckValveDeltaPPa = vppIPFWPCheckValve.deltaP;
  vppIPFWPCheckValveInletPressurePa = vppIPFWPCheckValve.C1.P;
  vppIPFWPCheckValveOutletPressurePa = vppIPFWPCheckValve.C2.P;
  vppIPFWPCheckValveResistancePaSPerKg = vppIPFWPCheckValve.effectiveResistance;
  vppLPFWPCheckValveMassFlowTH = 3.6*vppLPFWPCheckValve.Q;
  vppLPFWPCheckValveDeltaPPa = vppLPFWPCheckValve.deltaP;
  vppLPFWPCheckValveInletPressurePa = vppLPFWPCheckValve.C1.P;
  vppLPFWPCheckValveOutletPressurePa = vppLPFWPCheckValve.C2.P;
  vppLPFWPCheckValveResistancePaSPerKg = vppLPFWPCheckValve.effectiveResistance;
// The native OPC UA server permits writes to continuous states. A negligible
// derivative keeps this command memory as a state without affecting physics.
  // Drum persistence timers capture each raw-condition rising edge.
  when vppHPDrumHHRaw then
    vppHPDrumHHAssertTime = time;
  end when;
  when vppIPDrumHHRaw then
    vppIPDrumHHAssertTime = time;
  end when;
  when vppLPDrumHHRaw then
    vppLPDrumHHAssertTime = time;
  end when;
  when vppHPDrumLLRaw then
    vppHPDrumLLAssertTime = time;
  end when;
  when vppIPDrumLLRaw then
    vppIPDrumLLAssertTime = time;
  end when;
  when vppLPDrumLLRaw then
    vppLPDrumLLAssertTime = time;
  end when;
  // Capture a manual/feedback-equivalent 52GT OPEN transition while the
  // GT is in service. It remains visible until the safe reset sequence.
  when vppGTTripResetNative >= 0.5 and
      not vppCauseDirectGTTrip and not vppCauseHPDrumLL and
      not vppCauseIPDrumLL and not vppCauseLPDrumLL and
      vppECMS52GTClosedCommandNative < 0.5 then
    vppGTBreakerOpenCauseState = false;
  // TRIPLENS_PROTECTION_MATRIX_V8_2_DISCRETE_LOOP_FIX: event condition is independent of the trip latch
  elsewhen vppECMS52GTClosedCommandNative < 0.5 then
    vppGTBreakerOpenCauseState = true;
  end when;
  when vppGTTripResetNative >= 0.5 and
      not vppCauseDirectGTTrip and not vppCauseHPDrumLL and
      not vppCauseIPDrumLL and not vppCauseLPDrumLL and
      vppECMS52GTClosedCommandNative < 0.5 then
    vppGTTripLatchInternal = false;
    vppGTTripAssertTime = time;
  elsewhen vppGTTripRequest and vppGTTripResetNative < 0.5 then
    vppGTTripLatchInternal = true;
    vppGTTripAssertTime = time;
  end when;
  when vppSTTripResetNative >= 0.5 and not vppCauseDirectSTTrip and
      not vppCauseHPDrumHH and not vppCauseIPDrumHH and
      not vppCauseLPDrumHH and not vppGTTripRequest and
      not vppGTTripLatchInternal and
      vppECMS52STClosedCommandNative < 0.5 then
    vppSTTripLatch = false;
    vppSTTripAssertTime = time;
  elsewhen (vppSTTripRequest or vppGTTripLatchInternal) and
      vppSTTripResetNative < 0.5 then
    vppSTTripLatch = true;
    vppSTTripAssertTime = time;
  end when;
  der(vppGTExhaustMassFlowState) = ((if vppGTTripLatchInternal then vppGTExhaustMassFlowTrip else vppGTExhaustMassFlowNormal) - vppGTExhaustMassFlowState)/vppGTExhaustResponseTau;
  der(vppGTExhaustTemperatureState) = ((if vppGTTripLatchInternal then vppGTExhaustTemperatureTrip else vppGTExhaustTemperatureNormal) - vppGTExhaustTemperatureState)/vppGTExhaustResponseTau;
  vppGTExhaustMassFlowCommand.signal = if vppUseExternalTripInput then vppGTExhaustMassFlowState else Debit.y.signal;
  vppGTExhaustTemperatureCommand.signal = if vppUseExternalTripInput then vppGTExhaustTemperatureState else Temperature.y.signal;
  vppHPBypassCmd = if vppSTTripLatch then 1 else vppValveLeak;
  vppLPBypassCmd = if vppSTTripLatch then 1 else vppValveLeak;
  der(vppHPAdmissionPos) = ((if vppSTTripLatch then vppAdmissionSeatLeak else 0.8) - vppHPAdmissionPos)/vppAdmissionTau;
  der(vppIPAdmissionPos) = ((if vppSTTripLatch then vppAdmissionSeatLeak else 0.8) - vppIPAdmissionPos)/vppAdmissionTau;
  der(vppLPDrumAdmissionMultiplier) = ((if vppSTTripLatch then vppAdmissionSeatLeak else 1) - vppLPDrumAdmissionMultiplier)/vppAdmissionTau;
  der(vppHPBypassPos) = (vppHPBypassCmd - vppHPBypassPos)/vppHPBypassTau;
  der(vppLPBypassPos) = (vppLPBypassCmd - vppLPBypassPos)/vppLPBypassTau;
  der(vppHPSprayPos) = ((if vppSTTripLatch then 1 else 0) - vppHPSprayPos)/vppSprayTau;
  der(vppLPSprayPos) = ((if vppSTTripLatch then 1 else 0) - vppLPSprayPos)/vppSprayTau;
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
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for vanne_entree_TurbineHP
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for vanne_entree_TurbineMP
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for vanne_vapeurBP
  vppHPBypassValve.Ouv.signal = vppHPBypassPos;
  vppLPBypassValve.Ouv.signal = vppLPBypassPos;
  vppHPSprayFlowCommand.signal = noEvent(max(vppSpraySeatLeak, max(0, vppHPBypassValve.Q)*vppHPSprayRatio*vppHPSprayPos));
  vppLPSprayFlowCommand.signal = noEvent(max(vppSpraySeatLeak, max(0, vppLPBypassValve.Q)*vppLPSprayRatio*vppLPSprayPos));
  connect(vppHPSprayFlowCommand, vppHPSpraySource.IMassFlow) annotation(
    Line(visible = false, points = {{-70, -260}, {-20, -260}}, color = {0, 0, 127}));
  connect(vppHPBypassValve.C2, vppHPColdReheatVolume.Ce2) annotation(
    Line(visible = false, points = {{-80, -200}, {30, -200}, {30, -216}}, color = {0, 127, 255}, thickness = 1));
  connect(vppHPSpraySource.C, vppHPSprayInjector.C1) annotation(
    Line(visible = false, points = {{20, -260}, {0, -260}}, color = {0, 127, 255}));
  connect(vppHPSprayInjector.C2, vppHPColdReheatVolume.Ce3) annotation(
    Line(visible = false, points = {{20, -260}, {30, -260}, {30, -216}}, color = {0, 127, 255}));
  connect(vppLPSprayFlowCommand, vppLPSpraySource.IMassFlow) annotation(
    Line(visible = false, points = {{480, -360}, {540, -360}}, color = {0, 0, 127}));
  connect(vppLPBypassValve.C2, vppCondenserSteamVolume.Ce2) annotation(
    Line(visible = false, points = {{360, -328}, {636, -328}, {636, -286}}, color = {0, 127, 255}, thickness = 1));
  connect(vppLPSpraySource.C, vppLPSprayInjector.C1) annotation(
    Line(visible = false, points = {{560, -360}, {570, -360}}, color = {0, 127, 255}));
  connect(vppLPSprayInjector.C2, vppCondenserSteamVolume.Ce3) annotation(
    Line(visible = false, points = {{590, -360}, {636, -360}, {636, -306}}, color = {0, 127, 255}));
  // TRIPLENS_DRUM_INVENTORY_FAULT_PATH_V1: Ce2 is the otherwise unused
  // liquid inlet on each physical DynamicDrum.  Positive source Q adds
  // liquid inventory; negative Q removes it through the same mass balance.
  connect(vppHPDrumInventoryFaultFlowCommand, vppHPDrumInventoryFaultSource.IMassFlow) annotation(
    Line(visible = false, points = {{-120, -400}, {-80, -400}}, color = {0, 0, 127}));
  connect(vppHPDrumInventoryFaultEnthalpyCommand, vppHPDrumInventoryFaultSource.ISpecificEnthalpy) annotation(
    Line(visible = false, points = {{-120, -430}, {-60, -430}, {-60, -410}}, color = {0, 0, 127}));
  connect(vppHPDrumInventoryFaultSource.C, vppHPDrumInventoryFaultInjector.C1) annotation(
    Line(visible = false, points = {{-40, -400}, {-30, -400}}, color = {0, 127, 255}));
  connect(vppHPDrumInventoryFaultInjector.C2, BallonHP.Ce2) annotation(
    Line(visible = false, points = {{-10, -400}, {-20, -400}, {-20, 10}, {-35, 10}}, color = {0, 127, 255}));
  connect(vppIPDrumInventoryFaultFlowCommand, vppIPDrumInventoryFaultSource.IMassFlow) annotation(
    Line(visible = false, points = {{40, -400}, {80, -400}}, color = {0, 0, 127}));
  connect(vppIPDrumInventoryFaultEnthalpyCommand, vppIPDrumInventoryFaultSource.ISpecificEnthalpy) annotation(
    Line(visible = false, points = {{40, -430}, {100, -430}, {100, -410}}, color = {0, 0, 127}));
  connect(vppIPDrumInventoryFaultSource.C, vppIPDrumInventoryFaultInjector.C1) annotation(
    Line(visible = false, points = {{120, -400}, {130, -400}}, color = {0, 127, 255}));
  connect(vppIPDrumInventoryFaultInjector.C2, BallonMP.Ce2) annotation(
    Line(visible = false, points = {{150, -400}, {300, -400}, {300, 10}, {287, 10}}, color = {0, 127, 255}));
  connect(vppLPDrumInventoryFaultFlowCommand, vppLPDrumInventoryFaultSource.IMassFlow) annotation(
    Line(visible = false, points = {{200, -400}, {240, -400}}, color = {0, 0, 127}));
  connect(vppLPDrumInventoryFaultEnthalpyCommand, vppLPDrumInventoryFaultSource.ISpecificEnthalpy) annotation(
    Line(visible = false, points = {{200, -430}, {260, -430}, {260, -410}}, color = {0, 0, 127}));
  connect(vppLPDrumInventoryFaultSource.C, vppLPDrumInventoryFaultInjector.C1) annotation(
    Line(visible = false, points = {{280, -400}, {290, -400}}, color = {0, 127, 255}));
  connect(vppLPDrumInventoryFaultInjector.C2, BallonBP.Ce2) annotation(
    Line(visible = false, points = {{310, -400}, {535, -400}, {535, 10}, {527, 10}}, color = {0, 127, 255}));
  connect(SurchauffeurHP3.Cws1, SurchauffeurHP2.Cws2) annotation(
    Line(visible = false, points = {{-327, -30}, {-327, -10}, {-207, -10}, {-207, -30}}, color = {255, 0, 0}));
  connect(SurchauffeurHP2.Cws1, SurchauffeurHP1.Cws2) annotation(
    Line(visible = false, points = {{-207, -70}, {-207, -90}, {-87, -90}, {-87, -70}}, color = {255, 0, 0}));
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for vanne_vapeurHP
  connect(vanne_vapeurHP.C1, BallonHP.Cv) annotation(
    Line(visible = false, points = {{-55, 50}, {-35, 50}}, color = {255, 0, 0}));
  connect(GainChargeHP.C1, BallonHP.Cd) annotation(
    Line(visible = false, points = {{5, -90}, {15, -90}, {15, 10}, {5, 10}}, color = {255, 128, 0}));
  connect(BallonHP.Cm, EvaporateurHP.Cws2) annotation(
    Line(visible = false, points = {{-35, 10}, {-47, 10}, {-47, -30}}));
  connect(VolumeEvapHP.Cs, EvaporateurHP.Cws1) annotation(
    Line(visible = false, points = {{-45, -90}, {-45, -70}, {-47, -70}}, color = {255, 128, 0}));
  connect(VolumeEvapHP.Ce1, GainChargeHP.C2) annotation(
    Line(visible = false, points = {{-25, -90}, {-15, -90}}, color = {255, 128, 0}));
  connect(EconomiseurHP4.Cws1, EconomiseurHP3.Cws2) annotation(
    Line(visible = false, points = {{53, -70}, {53, -82}, {173, -82}, {173, -70}}));
  connect(BallonMP.Cm, EvaporateurMP.Cws2) annotation(
    Line(visible = false, points = {{287, 10}, {273, 10}, {273, -30}}));
  connect(EvaporateurMP.Cws1, VolumeEvapMP.Cs) annotation(
    Line(visible = false, points = {{273, -70}, {273, -80}, {275, -80}, {275, -90}}, color = {255, 128, 0}));
  connect(VolumeEvapMP.Ce1, GainChargeMP.C2) annotation(
    Line(visible = false, points = {{295, -90}, {305, -90}}, color = {255, 128, 0}));
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for vanne_vapeurMP
  connect(SurchauffeurHP1.Cfg2, EvaporateurHP.Cfg1) annotation(
    Line(visible = false, points = {{-77, -50}, {-57, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(EvaporateurHP.Cfg2, EconomiseurHP4.Cfg1) annotation(
    Line(visible = false, points = {{-37, -50}, {63, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(EconomiseurHP4.Cfg2, SurchauffeurMP1.Cfg1) annotation(
    Line(visible = false, points = {{43, -50}, {103, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(SurchauffeurMP1.Cfg2, EconomiseurHP3.Cfg1) annotation(
    Line(visible = false, points = {{123, -50}, {163, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(EvaporateurMP.Cfg2, EconomiseurHP2.Cfg1) annotation(
    Line(visible = false, points = {{283, -50}, {363, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(EconomiseurHP2.Cfg2, EconomiseurMP.Cfg1) annotation(
    Line(visible = false, points = {{383, -50}, {423, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(EconomiseurMP.Cfg2, EconomiseurHP1.Cfg1) annotation(
    Line(visible = false, points = {{443, -50}, {483, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(GainChargeMP.C1, BallonMP.Cd) annotation(
    Line(visible = false, points = {{325, -90}, {335, -90}, {335, 10}, {325, 10}}, color = {255, 128, 0}));
  connect(SurchauffeurMP2.Cfg2, SurchauffeurHP1.Cfg1) annotation(
    Line(visible = false, points = {{-137, -50}, {-97, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(SurchauffeurMP2.Cfg1, SurchauffeurHP2.Cfg2) annotation(
    Line(visible = false, points = {{-157, -50}, {-197, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(SurchauffeurMP3.Cfg2, SurchauffeurHP2.Cfg1) annotation(
    Line(visible = false, points = {{-257, -50}, {-217, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(SurchauffeurHP3.Cfg2, SurchauffeurMP3.Cfg1) annotation(
    Line(visible = false, points = {{-317, -50}, {-277, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(SurchauffeurMP3.Cws1, SurchauffeurMP2.Cws2) annotation(
    Line(visible = false, points = {{-267, -30}, {-267, 10}, {-147, 10}, {-147, -30}}, color = {255, 0, 0}));
  connect(SurchauffeurMP1.Cws2, MelangeurHPMP.Ce2) annotation(
    Line(visible = false, points = {{113, -70}, {113, -85}, {115, -85}, {115, -100}}, color = {255, 0, 0}, pattern = LinePattern.None));
  connect(vanne_vapeurBP.C1, BallonBP.Cv) annotation(
    Line(visible = false, points = {{525, 50}, {545, 50}}, color = {255, 0, 0}));
  connect(EvaporateurBP.Cws1, VolumeEvapBP.Cs) annotation(
    Line(visible = false, points = {{533, -70}, {533, -90}, {539, -90}}, color = {255, 128, 0}));
  connect(VolumeEvapBP.Ce1, GainChargeBP.C2) annotation(
    Line(visible = false, points = {{559, -90}, {567, -90}}, color = {255, 128, 0}));
  connect(BallonBP.Cd, GainChargeBP.C1) annotation(
    Line(visible = false, points = {{585, 10}, {595, 10}, {595, -90}, {587, -90}}, color = {255, 128, 0}));
  connect(EconomiseurBP.Cfg2, PuitsFumees.C) annotation(
    Line(visible = false, points = {{657, -50}, {679.2, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(EconomiseurHP3.Cfg2, SurchauffeurBP.Cfg1) annotation(
    Line(visible = false, points = {{183, -50}, {223, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(SurchauffeurBP.Cfg2, EvaporateurMP.Cfg1) annotation(
    Line(visible = false, points = {{243, -50}, {263, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(EconomiseurHP1.Cfg2, EvaporateurBP.Cfg1) annotation(
    Line(visible = false, points = {{503, -50}, {523, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(EvaporateurBP.Cfg2, EconomiseurBP.Cfg1) annotation(
    Line(visible = false, points = {{543, -50}, {637, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(BallonBP.Cm, EvaporateurBP.Cws2) annotation(
    Line(visible = false, points = {{545, 10}, {533, 10}, {533, -30}}));
  connect(vanne_vapeurMP.C1, BallonMP.Cv) annotation(
    Line(visible = false, points = {{265, 50}, {287, 50}}, color = {255, 0, 0}));
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for Vanne_alimentationMPHP
  connect(SurchauffeurHP3.Cws2, DoubleDebitHP.Ce) annotation(
    Line(visible = false, points = {{-327, -70}, {-327, -80}, {-325, -80}, {-325, -90}}, color = {255, 0, 0}));
  connect(SurchauffeurMP3.Cws2, DoubleDebitMP.Ce) annotation(
    Line(visible = false, points = {{-267, -70}, {-267, -80}, {-265, -80}, {-265, -90}}, color = {255, 0, 0}));
  connect(VolumeCond1.Cs, perteChargeKCond1.C1) annotation(
    Line(visible = false, points = {{869, -308}, {869, -282}}, color = {0, 0, 255}));
  connect(Vanne_alimentationMPHP.C2, VolumeAlimMPHP.Ce1) annotation(
    Line(visible = false, points = {{697, -10}, {709, -10}}, color = {0, 0, 255}));
  connect(SurchauffeurBP.Cws2, DoubleDebitBP.Ce) annotation(
    Line(visible = false, points = {{233, -70}, {233, -80}, {235, -80}, {235, -90}}, color = {255, 0, 0}));
  connect(perteChargeK8.C2, PompeAlimMP.C1) annotation(
    Line(visible = false, points = {{757, -10}, {764, -10}, {771, -10}}, color = {0, 0, 255}));
  connect(VolumeAlimMPHP.Cs1, perteChargeK8.C1) annotation(
    Line(visible = false, points = {{729, -10}, {733, -10}, {737, -10}}, color = {0, 0, 255}));
  connect(VolumeAlimMPHP.Cs2, perteChargeK3.C1) annotation(
    Line(visible = false, points = {{719, -20}, {719, -50}, {737, -50}}, color = {0, 0, 255}));
  connect(perteChargeK3.C2, PompeAlimHP.C1) annotation(
    Line(visible = false, points = {{757, -50}, {771, -50}}, color = {0, 0, 255}));
  connect(MelangeurPostTMP1.Ce2, PerteChargeZero2.C2) annotation(
    Line(visible = false, points = {{385, -239}, {385, -278}, {321, -278}}, color = {255, 0, 0}));
  connect(perteChargeK.C2, PompeAlimBP.C1) annotation(
    Line(visible = false, points = {{689, -436}, {709, -436}}, color = {0, 0, 255}));
  connect(vanne_extraction.C2, perteChargeK2.C1) annotation(
    Line(visible = false, points = {{789, -436}, {807, -436}}, color = {0, 0, 255}));
  connect(vanne_alimentationHP.C1, CapteurDebitEauHP.C2) annotation(
    Line(visible = false, points = {{45, 50}, {53.3, 50}, {53.3, 38.12}}));
  connect(vanne_vapeurHP.C2, CapteurDebitVapHP.C1) annotation(
    Line(visible = false, points = {{-75, 50}, {-86.2, 50}, {-86.2, 14}}, color = {255, 0, 0}));
  connect(CapteurDebitVapHP.C2, SurchauffeurHP1.Cws1) annotation(
    Line(visible = false, points = {{-86.2, 1.88}, {-86.2, -3.06}, {-87, -3.06}, {-87, -30}}, color = {255, 0, 0}));
  connect(vanne_alimentationMP.C1, CapteurDebitEauMP.C2) annotation(
    Line(visible = false, points = {{365, 50}, {370.425, 50}, {370.425, 50.4}, {375.85, 50.4}}));
  connect(CapteurDebitVapMP.C1, vanne_vapeurMP.C2) annotation(
    Line(visible = false, points = {{211, 49.6}, {227, 49.6}, {227, 50}, {245, 50}}, color = {255, 0, 0}));
  connect(CapteurDebitVapMP.C2, SurchauffeurMP1.Cws1) annotation(
    Line(visible = false, points = {{194.84, 49.6}, {113, 49.6}, {113, -30}}, color = {255, 0, 0}));
  connect(CapteurDebitVapBP.C2, SurchauffeurBP.Cws1) annotation(
    Line(visible = false, points = {{472.84, 49.6}, {457, 49.6}, {457, -2}, {233, -2}, {233, -30}}, color = {255, 0, 0}));
  connect(CapteurDebitVapBP.C1, vanne_vapeurBP.C2) annotation(
    Line(visible = false, points = {{489, 49.6}, {497, 49.6}, {497, 50}, {505, 50}}, color = {255, 0, 0}));
  connect(CapteurDebitEauBP.C2, vanne_alimentationBP.C1) annotation(
    Line(visible = false, points = {{625.3, 40.12}, {625.3, 48}, {617, 48}}, color = {0, 0, 255}));
  connect(CapteurDebitEauBPsortie.C2, Vanne_alimentationMPHP.C1) annotation(
    Line(visible = false, points = {{667.13, -9.8}, {672.065, -9.8}, {672.065, -10}, {677, -10}}, color = {0, 0, 255}));
  connect(CapteurDebitEauCondenseur.C2, perteChargeK.C1) annotation(
    Line(visible = false, points = {{647.3, -422.2}, {647.3, -436}, {669, -436}}, color = {0, 0, 255}));
  connect(perteChargeK1.C2, vppCondenserSteamVolume.Ce1);
  connect(vppCondenserSteamVolume.Cs, CapteurDebitVapCondenseur.C1);
  connect(MelangeurHPMP.Ce1, MoitieDebitHP.Cs) annotation(
    Line(visible = false, points = {{115, -120}, {115, -170}, {101, -170}}, color = {255, 0, 0}));
  connect(perteChargeK2.C2, MoitieDebitBP.Ce) annotation(
    Line(visible = false, points = {{827, -436}, {829, -436}, {829, -318}, {839, -318}}, color = {0, 0, 255}));
  connect(MoitieDebitBP.Cs, VolumeCond1.Ce3) annotation(
    Line(visible = false, points = {{853, -318}, {859, -318}}, color = {0, 0, 255}));
  connect(SurchauffeurMP2.Cws1, lumpedStraightPipeK2.C2) annotation(
    Line(visible = false, points = {{-147, -70}, {-147, -110}, {61, -110}}, color = {255, 0, 0}));
  connect(lumpedStraightPipeK2.C1, MelangeurHPMP.Cs2) annotation(
    Line(visible = false, points = {{81, -110}, {105.2, -110}}, color = {255, 0, 0}));
  connect(DoubleDebitHP.Cs, vppHPSplitter.Ce) annotation(
    Line(visible = false, points = {{-325, -90}, {-180, -90}, {-180, -240}}, color = {0, 127, 255}));
  connect(vppHPSplitter.Cs1, vanne_entree_TurbineHP.C1) annotation(
    Line(visible = false, points = {{-170, -230}, {-145, -230}}, color = {0, 127, 255}));
  connect(vppHPSplitter.Cs2, vppHPBypassValve.C1) annotation(
    Line(visible = false, points = {{-180, -220}, {-180, -200}, {-120, -200}}, color = {0, 127, 255}, thickness = 1));
  connect(DoubleDebitBP.Cs, PerteChargeZero2.C1) annotation(
    Line(visible = false, points = {{235, -110}, {235, -278}, {301, -278}}, color = {255, 0, 0}));
// TRIPLENS_LP_FWP_OPCUA_ADAPTER_V1: adapter owns PompeAlimBP.C2, vanne_extraction.C1
  connect(BallonHP.yLevel, regulation_Niveau_HP.MesureNiveauEau) annotation(
    Line(visible = false, points = {{-37, 30}, {-101, 30}, {-101, 125}, {-73.5, 125}}));
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for vanne_alimentationHP
  connect(ConsigneNiveauEauMP.y, regulation_Niveau_MP.ConsigneNiveauEau) annotation(
    Line(visible = false, points = {{175.7, 122}, {201, 122}, {201, 110}, {228.5, 110}}));
  connect(BallonMP.yLevel, regulation_Niveau_MP.MesureNiveauEau) annotation(
    Line(visible = false, points = {{285.1, 30}, {219, 30}, {219, 125}, {228.5, 125}}));
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for vanne_alimentationMP
  connect(ConsigneNiveauEauBP.y, regulation_Niveau_BP.ConsigneNiveauEau) annotation(
    Line(visible = false, points = {{472.7, 135}, {496.85, 135}, {496.85, 112}, {534.5, 112}}));
  connect(BallonBP.yLevel, regulation_Niveau_BP.MesureNiveauEau) annotation(
    Line(visible = false, points = {{543, 30}, {485, 30}, {485, 127}, {534.5, 127}}));
  connect(ConsigneNiveauCondenseur1.y, regulation_Niveau_Condenseur.ConsigneNiveauEau) annotation(
    Line(visible = false, points = {{708.2, -238}, {719, -238}, {719, -269}, {724.5, -269}}));
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for vanne_extraction
  connect(CapteurDebitEauBP.C1, EconomiseurBP.Cws2) annotation(
    Line(visible = false, points = {{625.3, 28}, {627, 28}, {627, 6}, {647, 6}, {647, -30}}));
  connect(EconomiseurBP.Cws1, perteChargeKCond1.C2) annotation(
    Line(visible = false, points = {{647, -70}, {647, -186}, {869, -186}, {869, -258}}));
  connect(CapteurDebitVapCondenseur.Measure, regulation_Niveau_Condenseur.MesureDebitVapeur) annotation(
    Line(visible = false, points = {{658.13, -264}, {671, -264}, {671, -280.9}, {724.6, -280.9}}));
  connect(regulation_Niveau_Condenseur.MesureDebitEau, CapteurDebitEauCondenseur.Measure) annotation(
    Line(visible = false, points = {{724.45, -274.95}, {717, -274.95}, {717, -310}, {759, -310}, {759, -412}, {659.13, -412}}));
// VPP patch owns the HP admission-valve actuator equation.
// VPP patch multiplies LP drum level demand by the Trip isolation actuator.
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for vanne_alimentationBP
  connect(EconomiseurHP1.Cws2, VolumeECO_HP1_2.Ce1) annotation(
    Line(visible = false, points = {{493, -70}, {493, -88}, {423, -88}}, color = {0, 0, 255}));
  connect(VolumeECO_HP1_2.Cs, EconomiseurHP2.Cws1) annotation(
    Line(visible = false, points = {{403, -88}, {373, -88}, {373, -70}}, color = {0, 0, 255}));
  connect(EconomiseurHP2.Cws2, VolumeECO_HP2_3.Ce1) annotation(
    Line(visible = false, points = {{373, -30}, {373, -10}, {219, -10}}, color = {0, 0, 255}));
  connect(VolumeECO_HP2_3.Cs, EconomiseurHP3.Cws1) annotation(
    Line(visible = false, points = {{199, -10}, {173, -10}, {173, -30}}, color = {0, 0, 255}));
// TRIPLENS_ALL_FWP_CHECK_VALVES_OPCUA_V1: check valve owns Vanne_alimentationMPHP1.C1, PompeAlimHP.C2
// TRIPLENS_ALL_FWP_CHECK_VALVES_OPCUA_V1: check valve owns PompeAlimMP.C2, Vanne_alimentationMPHP2.C1
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for Vanne_alimentationMPHP1
  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2: adapter owns original drive for Vanne_alimentationMPHP2
  connect(Vanne_alimentationMPHP1.C2, EconomiseurHP1.Cws1) annotation(
    Line(visible = false, points = {{697, -102.8}, {603, -102.8}, {603, -106}, {515, -106}, {515, -6}, {493, -6}, {493, -30}}, color = {0, 0, 255}));
  connect(EconomiseurMP.Cws1, Vanne_alimentationMPHP2.C2) annotation(
    Line(visible = false, points = {{433, -70}, {433, -142.8}, {747, -142.8}}));
// VPP patch owns the IP admission-valve actuator equation.
  connect(vanne_entree_TurbineHP.C2, VolumePreTHP.Ce) annotation(
    Line(visible = false, points = {{-137, -230}, {-95, -230}}, color = {255, 0, 0}));
  connect(DoubleDebitMP.Cs, vppLPSplitter.Ce) annotation(
    Line(visible = false, points = {{-265, -90}, {-180, -90}, {-180, -324}}, color = {0, 127, 255}));
  connect(vppLPSplitter.Cs1, vanne_entree_TurbineMP.C1) annotation(
    Line(visible = false, points = {{-170, -314}, {-145, -314}}, color = {0, 127, 255}));
  connect(vppLPSplitter.Cs2, vppLPBypassValve.C1) annotation(
    Line(visible = false, points = {{-180, -324}, {-180, -328}, {320, -328}}, color = {0, 127, 255}, thickness = 1));
  connect(vanne_entree_TurbineMP.C2, MelangeurPreTMP.Ce1) annotation(
    Line(visible = false, points = {{-137, -314}, {-93, -314}}, color = {255, 0, 0}));
  connect(SourceCaloporteur.C, Condenseur.Cee) annotation(
    Line(visible = false, points = {{587, -353}, {605, -353}, {605, -352.8}, {604, -352.8}}, color = {0, 0, 255}));
  connect(Condenseur.Cse, PuitsCaloporteur.C) annotation(
    Line(visible = false, points = {{684, -352}, {703, -352}}, color = {0, 0, 255}));
  connect(CapteurDebitVapCondenseur.C2, Condenseur.Cv) annotation(
    Line(visible = false, points = {{646.3, -274.2}, {646.3, -288.1}, {644, -288.1}, {644, -304}}, color = {0, 0, 255}));
  connect(CapteurDebitEauCondenseur.C1, Condenseur.Cl) annotation(
    Line(visible = false, points = {{647.3, -402}, {644.8, -402}, {644.8, -384}}));
  connect(ConsigneNiveauEauHP.y, regulation_Niveau_HP.ConsigneNiveauEau) annotation(
    Line(visible = false, points = {{-155.3, 122}, {-133, 122}, {-133, 110}, {-73.5, 110}}));
  connect(Condenseur.yNiveau, regulation_Niveau_Condenseur.MesureNiveauEau) annotation(
    Line(visible = false, points = {{688, -372.8}, {747, -372.8}, {747, -326}, {699, -326}, {699, -263}, {724.5, -263}}));
  connect(BallonBP.Cs, CapteurDebitEauBPsortie.C1) annotation(
    Line(visible = false, points = {{545, 22}, {531, 22}, {531, 16}, {609, 16}, {609, -9.8}, {654, -9.8}}, color = {0, 0, 255}));
  connect(BallonBP.Ce1, vanne_alimentationBP.C2) annotation(
    Line(visible = false, points = {{585, 50}, {591, 50}, {591, 48}, {597, 48}}));
  connect(BallonMP.Ce1, vanne_alimentationMP.C2) annotation(
    Line(visible = false, points = {{325, 50}, {345, 50}}));
  connect(BallonHP.Ce1, vanne_alimentationHP.C2) annotation(
    Line(visible = false, points = {{5, 50}, {25, 50}}));
  connect(TurbineHP.Cs, vppHPColdReheatVolume.Ce1);
  connect(vppHPColdReheatVolume.Cs, MoitieDebitHP.Ce);
  connect(VolumePreTHP.Cs3, TurbineHP.Ce) annotation(
    Line(visible = false, points = {{-75, -230}, {-35.2, -230}}, color = {255, 0, 0}));
  connect(MelangeurPreTMP.Cs, TurbineMP.Ce) annotation(
    Line(visible = false, points = {{-73, -314}, {73, -314}, {73, -230}, {284.8, -230}}, color = {255, 0, 0}));
  connect(TurbineMP.Cs, MelangeurPostTMP1.Ce1) annotation(
    Line(visible = false, points = {{325.2, -230}, {375, -230}}, color = {255, 0, 0}));
  connect(MelangeurPostTMP1.Cs, TurbineBP.Ce) annotation(
    Line(visible = false, points = {{395, -230}, {542.8, -230}}, color = {255, 0, 0}));
  connect(TurbineBP.Cs, perteChargeK1.C1) annotation(
    Line(visible = false, points = {{583.2, -230}, {607, -230}}, color = {255, 0, 0}));
  connect(EconomiseurMP.Cws2, CapteurDebitEauMP.C1) annotation(
    Line(visible = false, points = {{433, -30}, {437, -30}, {437, 50.4}, {391, 50.4}}, color = {0, 0, 255}));
  connect(TurbineMP.MechPower, Alternateur.Wmec2) annotation(
    Line(visible = false, points = {{327, -248}, {335, -248}, {335, -378}, {369, -378}}));
  connect(TurbineBP.MechPower, Alternateur.Wmec1) annotation(
    Line(visible = false, points = {{585, -248}, {595, -248}, {595, -290}, {355, -290}, {355, -358}, {369, -358}}));
  connect(TurbineHP.MechPower, Alternateur.Wmec3) annotation(
    Line(visible = false, points = {{7, -248}, {15, -248}, {15, -398}, {369, -398}}));
  connect(heatSource.C[1], BallonHP.Cex) annotation(
    Line(visible = false, points = {{-15, 68.3}, {-15, 50}}, color = {191, 95, 0}));
  connect(heatSource1.C[1], BallonMP.Cex) annotation(
    Line(visible = false, points = {{306, 68.3}, {306, 50}}, color = {191, 95, 0}));
  connect(heatSource2.C[1], BallonBP.Cex) annotation(
    Line(visible = false, points = {{565, 64.3}, {565, 50}}, color = {191, 95, 0}));
  connect(CapteurDebitEauHP.C1, EconomiseurHP4.Cws2) annotation(
    Line(visible = false, points = {{53.3, 26}, {53, 26}, {53, -30}}, smooth = Smooth.None));
// TRIPLENS_HP_IP_FWP_INERTIAL_DRIVES_V8_6: the adapter owns the HP/IP
// pump-speed inputs; legacy fixed Ramp connections are intentionally removed.
// TRIPLENS_LP_FWP_OPCUA_ADAPTER_V1: adapter owns PompeAlimBP.rpm_or_mpower, arretPomesBP.y
  connect(SourceFumees.C, SurchauffeurHP3.Cfg1) annotation(
    Line(visible = false, points = {{-371, -49}, {-371, -50}, {-337, -50}}, color = {0, 0, 0}, thickness = 1));
  connect(vppGTExhaustTemperatureCommand, SourceFumees.ITemperature);
  connect(vppGTExhaustMassFlowCommand, SourceFumees.IMassFlow);
// TRIPLENS_NATIVE_OPCUA_BOUNDARY_INSERTION_POINT
  annotation(
    Diagram(coordinateSystem(preserveAspectRatio = false, extent = {{-240, -165}, {240, 140}}, initialScale = 0.035), graphics = {Rectangle(lineColor = {80, 95, 115}, fillColor = {250, 252, 255}, fillPattern = FillPattern.Solid, extent = {{-238, 138}, {238, -162}}, radius = 3), Text(textColor = {20, 45, 85}, extent = {{-230, 119}, {110, 136}}, textString = "TripLens CCPP Dynamic Process View v36", fontSize = 13, horizontalAlignment = TextAlignment.Left), Text(textColor = {30, 70, 110}, extent = {{116, 121}, {230, 135}}, textString = DynamicSelect("SIM TIME  0.00 s", "SIM TIME  " + String(time) + " s"), fontSize = 9), Rectangle(lineColor = {110, 120, 130}, fillColor = DynamicSelect({226, 240, 226}, if vppSTTripLatch then {255, 205, 205} else {220, 245, 225}), fillPattern = FillPattern.Solid, extent = {{-230, 104}, {230, 118}}, radius = 2), Text(textColor = DynamicSelect({0, 120, 45}, if vppSTTripLatch then {190, 0, 0} else {0, 120, 45}), extent = {{-225, 106}, {-80, 116}}, textString = DynamicSelect("PLANT STATUS : RUNNING", if vppSTTripLatch then "PLANT STATUS : ST TRIP LATCHED" else "PLANT STATUS : RUNNING"), fontSize = 8, horizontalAlignment = TextAlignment.Left), Text(textColor = {50, 55, 65}, extent = {{-70, 106}, {80, 116}}, textString = DynamicSelect("EXT TRIP CMD : 0", "EXT TRIP CMD : " + String(vppExternalTripCommandNative, significantDigits = 3)), fontSize = 8), Text(textColor = DynamicSelect({0, 115, 45}, if vppVCBA02ClosedNative >= 0.5 then {0, 115, 45} else {190, 0, 0}), extent = {{90, 106}, {225, 116}}, textString = DynamicSelect("VCB-A02 : CLOSED", if vppVCBA02ClosedNative >= 0.5 then "VCB-A02 : CLOSED" else "VCB-A02 : OPEN"), fontSize = 8), Text(textColor = {145, 0, 0}, extent = {{-230, 91}, {-180, 101}}, textString = "MAIN STEAM", fontSize = 8, horizontalAlignment = TextAlignment.Left), Line(points = {{-220, 74}, {218, 74}}, color = {190, 0, 0}, thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Rectangle(lineColor = {120, 0, 0}, fillColor = {255, 226, 226}, fillPattern = FillPattern.Solid, extent = {{-226, 62}, {-194, 86}}), Text(textColor = {115, 0, 0}, extent = {{-224, 65}, {-196, 83}}, textString = "HP DRUM
STEAM", fontSize = 7), Rectangle(lineColor = {120, 0, 0}, fillColor = {255, 232, 220}, fillPattern = FillPattern.Solid, extent = {{-188, 62}, {-156, 86}}), Text(textColor = {115, 0, 0}, extent = {{-186, 65}, {-158, 83}}, textString = "HP SUPER-
HEATER", fontSize = 7), Rectangle(lineColor = {120, 0, 0}, fillColor = {255, 232, 220}, fillPattern = FillPattern.Solid, extent = {{-150, 62}, {-120, 86}}), Text(textColor = {115, 0, 0}, extent = {{-148, 66}, {-122, 82}}, textString = "HP SPLIT", fontSize = 7), Polygon(lineColor = {80, 80, 80}, fillColor = DynamicSelect({130, 210, 145}, if vppHPAdmissionPos > 0.05 then {0, 190, 80} else {190, 190, 190}), fillPattern = FillPattern.Solid, points = {{-114, 62}, {-99, 74}, {-114, 86}, {-114, 62}}), Polygon(lineColor = {80, 80, 80}, fillColor = DynamicSelect({130, 210, 145}, if vppHPAdmissionPos > 0.05 then {0, 190, 80} else {190, 190, 190}), fillPattern = FillPattern.Solid, points = {{-84, 62}, {-99, 74}, {-84, 86}, {-84, 62}}), Text(textColor = {30, 60, 30}, extent = {{-116, 50}, {-82, 60}}, textString = DynamicSelect("HP ADM 80.0 %", "HP ADM " + String(100*vppHPAdmissionPos, significantDigits = 4) + " %"), fontSize = 7), Polygon(lineColor = {40, 40, 40}, fillColor = DynamicSelect({120, 220, 90}, if vppSTTripLatch then {190, 190, 190} else {100, 225, 70}), fillPattern = FillPattern.Solid, points = {{-76, 84}, {-76, 64}, {-44, 58}, {-44, 90}, {-76, 84}}), Text(textColor = {20, 60, 20}, extent = {{-74, 67}, {-46, 81}}, textString = "HP TURB", fontSize = 7), Rectangle(lineColor = {120, 0, 0}, fillColor = {255, 238, 210}, fillPattern = FillPattern.Solid, extent = {{-38, 62}, {-4, 86}}), Text(textColor = {115, 0, 0}, extent = {{-36, 65}, {-6, 83}}, textString = "COLD
REHEAT", fontSize = 7), Rectangle(lineColor = {120, 0, 0}, fillColor = {255, 238, 210}, fillPattern = FillPattern.Solid, extent = {{2, 62}, {36, 86}}), Text(textColor = {115, 0, 0}, extent = {{4, 65}, {34, 83}}, textString = "IP
REHEATER", fontSize = 7), Rectangle(lineColor = {120, 0, 0}, fillColor = {255, 232, 220}, fillPattern = FillPattern.Solid, extent = {{42, 62}, {72, 86}}), Text(textColor = {115, 0, 0}, extent = {{44, 66}, {70, 82}}, textString = "IP SPLIT", fontSize = 7), Polygon(lineColor = {80, 80, 80}, fillColor = DynamicSelect({130, 210, 145}, if vppIPAdmissionPos > 0.05 then {0, 190, 80} else {190, 190, 190}), fillPattern = FillPattern.Solid, points = {{78, 62}, {93, 74}, {78, 86}, {78, 62}}), Polygon(lineColor = {80, 80, 80}, fillColor = DynamicSelect({130, 210, 145}, if vppIPAdmissionPos > 0.05 then {0, 190, 80} else {190, 190, 190}), fillPattern = FillPattern.Solid, points = {{108, 62}, {93, 74}, {108, 86}, {108, 62}}), Text(textColor = {30, 60, 30}, extent = {{76, 50}, {110, 60}}, textString = DynamicSelect("IP ADM 80.0 %", "IP ADM " + String(100*vppIPAdmissionPos, significantDigits = 4) + " %"), fontSize = 7), Polygon(lineColor = {40, 40, 40}, fillColor = DynamicSelect({120, 220, 90}, if vppSTTripLatch then {190, 190, 190} else {100, 225, 70}), fillPattern = FillPattern.Solid, points = {{116, 84}, {116, 64}, {148, 58}, {148, 90}, {116, 84}}), Text(textColor = {20, 60, 20}, extent = {{118, 67}, {146, 81}}, textString = "IP TURB", fontSize = 7), Rectangle(lineColor = {120, 0, 0}, fillColor = {255, 232, 220}, fillPattern = FillPattern.Solid, extent = {{154, 62}, {180, 86}}), Text(textColor = {115, 0, 0}, extent = {{156, 66}, {178, 82}}, textString = "LP MIX", fontSize = 7), Polygon(lineColor = {40, 40, 40}, fillColor = DynamicSelect({120, 220, 90}, if vppSTTripLatch then {190, 190, 190} else {100, 225, 70}), fillPattern = FillPattern.Solid, points = {{186, 84}, {186, 64}, {218, 58}, {218, 90}, {186, 84}}), Text(textColor = {20, 60, 20}, extent = {{188, 67}, {216, 81}}, textString = "LP TURB", fontSize = 7), Line(points = {{-135, 62}, {-135, 34}, {-112, 34}}, color = DynamicSelect({150, 150, 150}, if vppHPBypassMassFlow > 0.01 then {0, 90, 220} else {150, 150, 150}), thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Polygon(lineColor = {0, 70, 160}, fillColor = DynamicSelect({205, 220, 240}, if vppHPBypassPos > 0.01 then {40, 145, 255} else {205, 220, 240}), fillPattern = FillPattern.Solid, points = {{-112, 22}, {-99, 32}, {-112, 42}, {-112, 22}}), Polygon(lineColor = {0, 70, 160}, fillColor = DynamicSelect({205, 220, 240}, if vppHPBypassPos > 0.01 then {40, 145, 255} else {205, 220, 240}), fillPattern = FillPattern.Solid, points = {{-86, 22}, {-99, 32}, {-86, 42}, {-86, 22}}), Text(textColor = {0, 60, 150}, extent = {{-122, 7}, {-76, 20}}, textString = DynamicSelect("HP BYPASS 0.0 %", "HP BYPASS " + String(100*vppHPBypassPos, significantDigits = 4) + " %"), fontSize = 7), Rectangle(lineColor = {0, 90, 180}, fillColor = DynamicSelect({225, 235, 245}, if vppHPSprayPos > 0.01 then {80, 190, 255} else {225, 235, 245}), fillPattern = FillPattern.Solid, extent = {{-74, 22}, {-48, 42}}), Text(textColor = {0, 65, 145}, extent = {{-72, 26}, {-50, 38}}, textString = DynamicSelect("HP SPRAY", "SPRAY " + String(100*vppHPSprayPos, significantDigits = 3) + "%"), fontSize = 6), Line(points = {{-86, 32}, {-74, 32}}, color = {0, 90, 220}, thickness = 2), Line(points = {{-48, 32}, {-21, 32}, {-21, 62}}, color = DynamicSelect({150, 150, 150}, if vppHPBypassMassFlow > 0.01 then {0, 90, 220} else {150, 150, 150}), thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Text(textColor = {0, 70, 160}, extent = {{-45, 18}, {12, 28}}, textString = DynamicSelect("HP BP FLOW 0.0 kg/s", "HP BP FLOW " + String(vppHPBypassMassFlow, significantDigits = 5) + " kg/s"), fontSize = 6), Line(points = {{57, 62}, {57, 34}, {76, 34}}, color = DynamicSelect({150, 150, 150}, if vppLPBypassMassFlow > 0.01 then {0, 90, 220} else {150, 150, 150}), thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Polygon(lineColor = {0, 70, 160}, fillColor = DynamicSelect({205, 220, 240}, if vppLPBypassPos > 0.01 then {40, 145, 255} else {205, 220, 240}), fillPattern = FillPattern.Solid, points = {{76, 22}, {89, 32}, {76, 42}, {76, 22}}), Polygon(lineColor = {0, 70, 160}, fillColor = DynamicSelect({205, 220, 240}, if vppLPBypassPos > 0.01 then {40, 145, 255} else {205, 220, 240}), fillPattern = FillPattern.Solid, points = {{102, 22}, {89, 32}, {102, 42}, {102, 22}}), Text(textColor = {0, 60, 150}, extent = {{66, 7}, {112, 20}}, textString = DynamicSelect("LP BYPASS 0.0 %", "LP BYPASS " + String(100*vppLPBypassPos, significantDigits = 4) + " %"), fontSize = 7), Rectangle(lineColor = {0, 90, 180}, fillColor = DynamicSelect({225, 235, 245}, if vppLPSprayPos > 0.01 then {80, 190, 255} else {225, 235, 245}), fillPattern = FillPattern.Solid, extent = {{114, 22}, {140, 42}}), Text(textColor = {0, 65, 145}, extent = {{116, 26}, {138, 38}}, textString = DynamicSelect("LP SPRAY", "SPRAY " + String(100*vppLPSprayPos, significantDigits = 3) + "%"), fontSize = 6), Line(points = {{102, 32}, {114, 32}}, color = {0, 90, 220}, thickness = 2), Line(points = {{140, 32}, {204, 32}, {204, -10}}, color = DynamicSelect({150, 150, 150}, if vppLPBypassMassFlow > 0.01 then {0, 90, 220} else {150, 150, 150}), thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Text(textColor = {0, 70, 160}, extent = {{139, 18}, {210, 28}}, textString = DynamicSelect("LP BP FLOW 0.0 kg/s", "LP BP FLOW " + String(vppLPBypassMassFlow, significantDigits = 5) + " kg/s"), fontSize = 6), Line(origin = {14, 0}, points = {{202, 58}, {202, -10}}, color = {190, 0, 0}, thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Rectangle(lineColor = {0, 75, 125}, fillColor = {220, 245, 255}, fillPattern = FillPattern.Solid, extent = {{180, -48}, {228, -10}}, radius = 4), Rectangle(lineColor = {0, 120, 200}, fillColor = {70, 175, 245}, fillPattern = FillPattern.Solid, extent = DynamicSelect({{184, -44}, {224, -42}}, {{184, -44}, {224, 22*min(1, max(0, vppCondenserLevel/3)) - 44}})), Text(textColor = {0, 55, 100}, extent = {{182, -22}, {226, -12}}, textString = "CONDENSER", fontSize = 8), Text(textColor = {0, 45, 90}, extent = {{181, -39}, {227, -27}}, textString = DynamicSelect("LEVEL 0.00 m", "LEVEL " + String(vppCondenserLevel, significantDigits = 5) + " m"), fontSize = 6), Text(textColor = {0, 55, 100}, extent = {{174, -59}, {234, -49}}, textString = DynamicSelect("P 0.000 bar(a)", "P " + String(vppCondenserPressure/100000, significantDigits = 5) + " bar(a)"), fontSize = 6), Text(textColor = {0, 55, 145}, extent = {{-230, -60}, {-155, -50}}, textString = "FEEDWATER / DRUMS", fontSize = 8, horizontalAlignment = TextAlignment.Left), Text(textColor = {0, 70, 160}, extent = {{-229, -82}, {-211, -70}}, textString = "FW", fontSize = 7), Line(points = {{-212, -76}, {-194, -76}}, color = {0, 90, 220}, thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Ellipse(lineColor = {0, 70, 160}, fillColor = DynamicSelect({190, 190, 190}, if vppHPFWPRunning then {0, 205, 95} else {190, 190, 190}), fillPattern = FillPattern.Solid, extent = {{-194, -88}, {-170, -64}}), Polygon(lineColor = {0, 70, 120}, fillColor = {235, 250, 255}, fillPattern = FillPattern.Solid, points = {{-188, -82}, {-175, -76}, {-188, -70}, {-188, -82}}), Text(textColor = {0, 60, 125}, extent = {{-202, -100}, {-162, -89}}, textString = DynamicSelect("HP FWP 0.0 t/h", "HP FWP " + String(vppHPFWPMassFlowTH, significantDigits = 5) + " t/h"), fontSize = 6), Line(points = {{-170, -76}, {-158, -76}}, color = {0, 90, 220}, thickness = 2), Polygon(lineColor = {0, 70, 160}, fillColor = DynamicSelect({210, 220, 230}, if vppHPFWPCheckValveOpen then {0, 205, 95} else {210, 220, 230}), fillPattern = FillPattern.Solid, points = {{-158, -84}, {-148, -76}, {-158, -68}, {-158, -84}}), Line(points = {{-146, -85}, {-146, -67}}, color = {0, 70, 160}, thickness = 1), Text(textColor = {0, 60, 125}, extent = {{-166, -100}, {-134, -89}}, textString = DynamicSelect("NRV 0.0 %", "NRV " + String(100*vppHPFWPCheckValveOpening, significantDigits = 4) + " %"), fontSize = 6), Line(points = {{-146, -76}, {-126, -76}}, color = {0, 90, 220}, thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Rectangle(lineColor = {0, 70, 160}, fillColor = {245, 250, 255}, fillPattern = FillPattern.Solid, extent = {{-126, -101}, {-94, -67}}), Rectangle(lineColor = {0, 120, 200}, fillColor = {70, 175, 245}, fillPattern = FillPattern.Solid, extent = DynamicSelect({{-122, -97}, {-98, -95}}, {{-122, -97}, {-98, 26*min(1, max(0, vppHPDrumLevelM/2)) - 97}})), Text(textColor = {0, 55, 120}, extent = {{-124, -76}, {-96, -68}}, textString = "HP DRUM", fontSize = 7), Text(textColor = {0, 55, 120}, extent = {{-129, -113}, {-91, -102}}, textString = DynamicSelect("L 0.00 m", "L " + String(vppHPDrumLevelM, significantDigits = 5) + " m"), fontSize = 6), Text(textColor = {0, 55, 120}, extent = {{-137, -124}, {-83, -114}}, textString = DynamicSelect("P 0.00 bar(a)", "P " + String(vppHPDrumPressurePa/100000, significantDigits = 5) + " bar(a)"), fontSize = 6), Line(points = {{-110, -67}, {-110, -56}, {-210, -56}, {-210, 62}}, color = {215, 115, 0}, thickness = 1, arrow = {Arrow.None, Arrow.Filled}), Text(textColor = {0, 70, 160}, extent = {{-76, -82}, {-58, -70}}, textString = "FW", fontSize = 7), Line(points = {{-59, -76}, {-41, -76}}, color = {0, 90, 220}, thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Ellipse(lineColor = {0, 70, 160}, fillColor = DynamicSelect({190, 190, 190}, if vppIPFWPRunning then {0, 205, 95} else {190, 190, 190}), fillPattern = FillPattern.Solid, extent = {{-41, -88}, {-17, -64}}), Polygon(lineColor = {0, 70, 120}, fillColor = {235, 250, 255}, fillPattern = FillPattern.Solid, points = {{-35, -82}, {-22, -76}, {-35, -70}, {-35, -82}}), Text(textColor = {0, 60, 125}, extent = {{-49, -100}, {-9, -89}}, textString = DynamicSelect("IP FWP 0.0 t/h", "IP FWP " + String(vppIPFWPMassFlowTH, significantDigits = 5) + " t/h"), fontSize = 6), Line(points = {{-17, -76}, {-5, -76}}, color = {0, 90, 220}, thickness = 2), Polygon(lineColor = {0, 70, 160}, fillColor = DynamicSelect({210, 220, 230}, if vppIPFWPCheckValveOpen then {0, 205, 95} else {210, 220, 230}), fillPattern = FillPattern.Solid, points = {{-5, -84}, {5, -76}, {-5, -68}, {-5, -84}}), Line(points = {{7, -85}, {7, -67}}, color = {0, 70, 160}, thickness = 1), Text(textColor = {0, 60, 125}, extent = {{-13, -100}, {19, -89}}, textString = DynamicSelect("NRV 0.0 %", "NRV " + String(100*vppIPFWPCheckValveOpening, significantDigits = 4) + " %"), fontSize = 6), Line(points = {{7, -76}, {27, -76}}, color = {0, 90, 220}, thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Rectangle(lineColor = {0, 70, 160}, fillColor = {245, 250, 255}, fillPattern = FillPattern.Solid, extent = {{27, -101}, {59, -67}}), Rectangle(lineColor = {0, 120, 200}, fillColor = {70, 175, 245}, fillPattern = FillPattern.Solid, extent = DynamicSelect({{31, -97}, {55, -95}}, {{31, -97}, {55, 26*min(1, max(0, vppIPDrumLevelM/2)) - 97}})), Text(textColor = {0, 55, 120}, extent = {{29, -76}, {57, -68}}, textString = "IP DRUM", fontSize = 7), Text(textColor = {0, 55, 120}, extent = {{24, -113}, {62, -102}}, textString = DynamicSelect("L 0.00 m", "L " + String(vppIPDrumLevelM, significantDigits = 5) + " m"), fontSize = 6), Text(textColor = {0, 55, 120}, extent = {{16, -124}, {70, -114}}, textString = DynamicSelect("P 0.00 bar(a)", "P " + String(vppIPDrumPressurePa/100000, significantDigits = 5) + " bar(a)"), fontSize = 6), Line(points = {{43, -67}, {43, -55}, {18, -55}, {18, 62}}, color = {215, 115, 0}, thickness = 1, arrow = {Arrow.None, Arrow.Filled}), Line(points = {{180, -38}, {152, -38}, {152, -76}}, color = {0, 90, 220}, thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Ellipse(lineColor = {0, 70, 160}, fillColor = DynamicSelect({190, 190, 190}, if vppLPFWPRunning then {0, 205, 95} else {190, 190, 190}), fillPattern = FillPattern.Solid, extent = {{140, -88}, {164, -64}}), Polygon(lineColor = {0, 70, 120}, fillColor = {235, 250, 255}, fillPattern = FillPattern.Solid, points = {{146, -82}, {159, -76}, {146, -70}, {146, -82}}), Text(textColor = {0, 60, 125}, extent = {{132, -100}, {172, -89}}, textString = DynamicSelect("LP FWP 0 rpm", "LP FWP " + String(vppLPFWPSpeedRPM, significantDigits = 5) + " rpm"), fontSize = 6), Text(textColor = {0, 60, 125}, extent = {{132, -111}, {172, -101}}, textString = DynamicSelect("FLOW 0.0 t/h", "FLOW " + String(vppLPFWPMassFlowTH, significantDigits = 5) + " t/h"), fontSize = 6), Line(points = {{164, -76}, {174, -76}}, color = {0, 90, 220}, thickness = 2), Polygon(lineColor = {0, 70, 160}, fillColor = DynamicSelect({210, 220, 230}, if vppLPFWPCheckValveOpen then {0, 205, 95} else {210, 220, 230}), fillPattern = FillPattern.Solid, points = {{174, -84}, {184, -76}, {174, -68}, {174, -84}}), Line(points = {{186, -85}, {186, -67}}, color = {0, 70, 160}, thickness = 1), Text(textColor = {0, 60, 125}, extent = {{166, -123}, {198, -112}}, textString = DynamicSelect("NRV 0.0 %", "NRV " + String(100*vppLPFWPCheckValveOpening, significantDigits = 4) + " %"), fontSize = 6), Line(points = {{186, -76}, {196, -76}}, color = {0, 90, 220}, thickness = 2, arrow = {Arrow.None, Arrow.Filled}), Rectangle(lineColor = {0, 70, 160}, fillColor = {245, 250, 255}, fillPattern = FillPattern.Solid, extent = {{196, -110}, {228, -67}}), Rectangle(lineColor = {0, 120, 200}, fillColor = {70, 175, 245}, fillPattern = FillPattern.Solid, extent = DynamicSelect({{200, -106}, {224, -104}}, {{200, -106}, {224, 34*min(1, max(0, vppLPDrumLevelM/3)) - 106}})), Text(textColor = {0, 55, 120}, extent = {{198, -76}, {226, -68}}, textString = "LP DRUM", fontSize = 7), Text(textColor = {0, 55, 120}, extent = {{193, -122}, {231, -111}}, textString = DynamicSelect("L 0.00 m", "L " + String(vppLPDrumLevelM, significantDigits = 5) + " m"), fontSize = 6), Text(textColor = {0, 55, 120}, extent = {{185, -133}, {239, -123}}, textString = DynamicSelect("P 0.00 bar(a)", "P " + String(vppLPDrumPressurePa/100000, significantDigits = 5) + " bar(a)"), fontSize = 6), Line(points = {{212, -67}, {212, -56}, {167, -56}, {167, 62}}, color = {215, 115, 0}, thickness = 1, arrow = {Arrow.None, Arrow.Filled}), Rectangle(lineColor = {175, 180, 190}, fillColor = {245, 247, 250}, fillPattern = FillPattern.Solid, extent = {{-230, -154}, {168, -137}}), Line(points = {{-222, -145}, {-198, -145}}, color = {190, 0, 0}, thickness = 2), Text(textColor = {100, 0, 0}, extent = {{-195, -150}, {-138, -141}}, textString = "steam / reheat", fontSize = 6), Line(points = {{-127, -145}, {-103, -145}}, color = {0, 90, 220}, thickness = 2), Text(textColor = {0, 60, 145}, extent = {{-100, -150}, {-45, -141}}, textString = "water / bypass", fontSize = 6), Line(points = {{-34, -145}, {-10, -145}}, color = {215, 115, 0}, thickness = 2), Text(textColor = {150, 70, 0}, extent = {{-7, -150}, {43, -141}}, textString = "drum steam", fontSize = 6), Ellipse(lineColor = {0, 90, 80}, fillColor = {0, 205, 95}, fillPattern = FillPattern.Solid, extent = {{55, -150}, {65, -140}}), Text(textColor = {0, 90, 55}, extent = {{68, -150}, {158, -141}}, textString = "green = running / open", fontSize = 6), Text(textColor = {70, 75, 85}, extent = {{172, -154}, {230, -137}}, textString = "Dynamic values
from the same solver", fontSize = 6)}),
    experiment(StartTime = 0, StopTime = 100, Interval = 0.04, Tolerance = 1e-5),
    experimentSetupOutput,
    __OpenModelica_simulationFlags(s = "dassl"));
end TripLens_CombinedCycle_TripTAC_ProcessView_v36;
