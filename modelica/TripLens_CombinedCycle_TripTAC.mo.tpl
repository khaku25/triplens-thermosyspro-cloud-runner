within ;
model TripLens_CombinedCycle_TripTAC
  parameter Real tripTime(unit="s") = @TRIP_TIME@;
  parameter Real tripRampDuration(unit="s") = @TRIP_RAMP_DURATION@;
  parameter Real exhaustFlowNormal(unit="kg/s") = 606.94;
  parameter Real exhaustFlowTripped(unit="kg/s") = 50.0;
  parameter Real exhaustTemperatureNormal(unit="K") = 893.75;
  parameter Real exhaustTemperatureTripped(unit="K") = 423.0;

  extends ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC(
    Debit(Table=[0,exhaustFlowNormal;
                 tripTime,exhaustFlowNormal;
                 tripTime + tripRampDuration,exhaustFlowTripped]),
    Temperature(Table=[0,exhaustTemperatureNormal;
                       tripTime,exhaustTemperatureNormal;
                       tripTime + tripRampDuration,exhaustTemperatureTripped]));

  annotation(experiment(
    StartTime=0,
    StopTime=@STOP_TIME@,
    Tolerance=1e-3,
    Interval=@OUTPUT_INTERVAL@));
end TripLens_CombinedCycle_TripTAC;

