within ;
model TripLens_CombinedCycle_VPPEvent
  "Validated BFP process adapter with Modelica-owned VPP alarm logic"
  parameter Real bfpEventTime(unit="s") = @BFP_EVENT_TIME@;
  parameter Real bfpCoastdownDuration(unit="s") = @BFP_COASTDOWN_DURATION@;
  parameter Real bfpNormalSpeed(unit="rev/min") = 1400.0;
  parameter Real bfpResidualSpeed(unit="rev/min") = @BFP_FINAL_RPM@;
  parameter Real exhaustFlowNormal(unit="kg/s") = 606.94;
  parameter Real exhaustTemperatureNormal(unit="K") = 893.75;

  extends ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC(
    Debit(Table=[0,exhaustFlowNormal;
                 @STOP_TIME@,exhaustFlowNormal]),
    Temperature(Table=[0,exhaustTemperatureNormal;
                       @STOP_TIME@,exhaustTemperatureNormal]),
    arretPomesHP(
      Initialvalue=bfpNormalSpeed,
      Starttime=bfpEventTime,
      Duration=bfpCoastdownDuration,
      Finalvalue=bfpResidualSpeed));

  TripLens_VPPAlarmRuntime.VPPAlarmRuntime alarmRuntime;
  Boolean bfpHPBreakerClosed;
  Boolean gtTripRequest;
  Boolean stTripRequest;
  Boolean gtTripLatched;
  Boolean stTripLatched;
  Boolean relay86GTTripReceived;
  Boolean relay86GTOperated;
  Boolean gt52GClosed;
  Boolean st52GClosed;
  Modelica.SIunits.Power gtGridElectricalPower;
  Modelica.SIunits.Power stGridElectricalPower;

equation
  // This event command is part of the Modelica run and is exported as an
  // operation state. ECMS protection/SOE remains an independent data source.
  bfpHPBreakerClosed = not (time >= bfpEventTime);

  alarmRuntime.gt_trip_cmd = false;
  alarmRuntime.st_trip_cmd = false;
  alarmRuntime.gt_exhaust_mass_flow_kg_s = Debit.y.signal;
  alarmRuntime.gt_exhaust_temperature_k = Temperature.y.signal;
  alarmRuntime.stg_power_w = Alternateur.Welec;
  alarmRuntime.hp_drum_level_m = BallonHP.yLevel.signal;
  alarmRuntime.ip_drum_level_m = BallonMP.yLevel.signal;
  alarmRuntime.lp_drum_level_m = BallonBP.yLevel.signal;
  alarmRuntime.hp_drum_pressure_pa = BallonHP.P;
  alarmRuntime.ip_drum_pressure_pa = BallonMP.P;
  alarmRuntime.lp_drum_pressure_pa = BallonBP.P;
  alarmRuntime.hp_steam_flow_kg_s = TurbineHP.Q;
  alarmRuntime.ip_steam_flow_kg_s = TurbineMP.Q;
  alarmRuntime.lp_steam_flow_kg_s = TurbineBP.Q;

  gtTripRequest = alarmRuntime.gtTripRequest;
  stTripRequest = alarmRuntime.stTripRequest;
  gtTripLatched = alarmRuntime.gtTripLatched;
  stTripLatched = alarmRuntime.stTripLatched;
  relay86GTTripReceived = alarmRuntime.relay86GTTripReceived;
  relay86GTOperated = alarmRuntime.relay86GTOperated;
  gt52GClosed = alarmRuntime.breaker52GTClosed;
  st52GClosed = alarmRuntime.breaker52STClosed;
  gtGridElectricalPower = if gt52GClosed then 160e6 else 0;
  stGridElectricalPower = if st52GClosed then Alternateur.Welec else 0;

  annotation(experiment(
    StartTime=0,
    StopTime=@STOP_TIME@,
    Tolerance=1e-3,
    Interval=@OUTPUT_INTERVAL@));
end TripLens_CombinedCycle_VPPEvent;
