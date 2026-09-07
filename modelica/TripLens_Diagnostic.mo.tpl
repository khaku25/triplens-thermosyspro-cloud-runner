within ;
model TripLens_Diagnostic
  extends ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC(
    Debit(Table=@FLOW_TABLE@),
    Temperature(Table=@TEMPERATURE_TABLE@));
end TripLens_Diagnostic;

