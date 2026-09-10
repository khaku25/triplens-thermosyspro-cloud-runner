within ;
model TripLens_FMU_Valve_Export
  extends TripLens_CombinedCycle_TripTAC;
  annotation(__OpenModelica_commandLineOptions=
    "--indexReductionMethod=dummyDerivatives");
end TripLens_FMU_Valve_Export;
