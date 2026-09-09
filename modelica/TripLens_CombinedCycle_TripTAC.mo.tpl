within ;
model TripLens_CombinedCycle_TripTAC
  "Compatibility wrapper name retained; this model performs GT DERATE, not GT Trip"
  parameter Real derateTime(unit="s") = @DERATE_TIME@;
  parameter Real derateRampDuration(unit="s") = @DERATE_RAMP_DURATION@;
  parameter Real exhaustFlowNormal(unit="kg/s") = 606.94;
  // This validated process-boundary experiment is DERATING only.
  // It must never be interpreted as GT Trip because the associated generator
  // breaker remains CLOSED in the canonical TripLens semantics.
  // 150 kg/s is the lowest severe derating point verified to reach 1000 s in
  // OpenModelica 1.27 with the paired 550 K temperature boundary.
  parameter Real exhaustFlowDerated(unit="kg/s") = 150.0;
  parameter Real exhaustTemperatureNormal(unit="K") = 893.75;
  parameter Real exhaustTemperatureDerated(unit="K") = 550.0;

  extends ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC(
    Debit(Table=[0,exhaustFlowNormal;
                 derateTime,exhaustFlowNormal;
                 derateTime + derateRampDuration,exhaustFlowDerated;
                 @STOP_TIME@,exhaustFlowDerated]),
    Temperature(Table=[0,exhaustTemperatureNormal;
                       derateTime,exhaustTemperatureNormal;
                       derateTime + derateRampDuration,exhaustTemperatureDerated;
                       @STOP_TIME@,exhaustTemperatureDerated]));

  annotation(experiment(
    StartTime=0,
    StopTime=@STOP_TIME@,
    Tolerance=1e-3,
    Interval=@OUTPUT_INTERVAL@));
end TripLens_CombinedCycle_TripTAC;
