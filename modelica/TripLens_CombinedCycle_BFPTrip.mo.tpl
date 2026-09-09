within ;
model TripLens_CombinedCycle_BFPTrip
  parameter Real bfpTripTime(unit="s") = @BFP_TRIP_TIME@;
  parameter Real bfpCoastdownDuration(unit="s") = @BFP_COASTDOWN_DURATION@;
  parameter Real bfpNormalSpeed(unit="rev/min") = 1400.0;
  // The legacy pump model is numerically robust at this residual speed. The
  // electrical breaker is still represented as open in the blind ECMS data;
  // this value is the hydraulic adapter floor, not a claim that the motor runs.
  parameter Real bfpResidualSpeed(unit="rev/min") = @BFP_FINAL_RPM@;
  parameter Real exhaustFlowNormalTH = 2184.984
    "Published normal GT exhaust mass flow in t/h";
  parameter Real exhaustTemperatureNormal(unit="K") = 893.75;

  Real vppGTExhaustMassFlowTH "Published GT exhaust mass flow in t/h";
  Real vppHPTurbineSteamFlowTH "Published HP turbine steam flow in t/h";
  Real vppIPTurbineSteamFlowTH "Published IP turbine steam flow in t/h";
  Real vppLPTurbineSteamFlowTH "Published LP turbine steam flow in t/h";
  Real vppFWPHPMassFlowTH "Published HP feedwater-pump mass flow in t/h";

  extends ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC(
    // Keep the GT boundary normal: this is not a GT trip scenario.
    Debit(Table=[0,exhaustFlowNormalTH/3.6;
                 @STOP_TIME@,exhaustFlowNormalTH/3.6]),
    Temperature(Table=[0,exhaustTemperatureNormal;
                       @STOP_TIME@,exhaustTemperatureNormal]),
    // PompeAlimHP is the HP boiler-feed pump in the upstream model. Its
    // connected speed source is overridden to create the physical disturbance.
    arretPomesHP(
      Initialvalue=bfpNormalSpeed,
      Starttime=bfpTripTime,
      Duration=bfpCoastdownDuration,
      Finalvalue=bfpResidualSpeed));

equation
  // ThermoSysPro retains its native SI connector balance; GitHub RAW exports
  // only these plant-facing t/h aliases for mass-flow quantities.
  vppGTExhaustMassFlowTH = 3.6*Debit.y.signal;
  vppHPTurbineSteamFlowTH = 3.6*TurbineHP.Q;
  vppIPTurbineSteamFlowTH = 3.6*TurbineMP.Q;
  vppLPTurbineSteamFlowTH = 3.6*TurbineBP.Q;
  vppFWPHPMassFlowTH = 3.6*CapteurDebitEauHP.Measure.signal;

  annotation(experiment(
    StartTime=0,
    StopTime=@STOP_TIME@,
    Tolerance=1e-3,
    Interval=@OUTPUT_INTERVAL@));
end TripLens_CombinedCycle_BFPTrip;
