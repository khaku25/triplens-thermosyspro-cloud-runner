setCommandLineOptions("--std=3.4");
loadModel(Modelica, {"3.2.3"});
getErrorString();
loadFile("/workspace/vendor/ThermoSysPro/ThermoSysPro/package.mo");
getErrorString();
loadFile("/workspace/build/TripLens_CombinedCycle_TripTAC.mo");
getErrorString();
cd("/workspace/build");
simulate(
  TripLens_CombinedCycle_TripTAC,
  startTime=0,
  stopTime=@STOP_TIME@,
  numberOfIntervals=@NUMBER_OF_INTERVALS@,
  tolerance=1e-3,
  method="dassl",
  outputFormat="csv",
  // Retain the complete plant steady-state initialization. Closed VPP bypass
  // valves are isolated from pressure-property evaluation until they start
  // opening; the default sparse/dense solver selection remains enabled.
  // Verbose nonlinear-solver tracing is deliberately disabled for the
  // production RAW run because it does not change the solution and can
  // dominate runtime during the post-Trip transient.
  simflags="-noEventEmit",
  fileNamePrefix="thermosyspro_trip_tac",
  variableFilter="^(time|Debit\\.y\\.signal|Temperature\\.y\\.signal|Alternateur\\.Welec|Ballon(HP|MP|BP)\\.(yLevel\\.signal|zl|P)|Turbine(HP|MP|BP)\\.Q|vanne_alimentation(HP|MP|BP)\\.Ouv\\.signal|vpp(STTripLatch|HPAdmissionPos|IPAdmissionPos|LPDrumAdmissionMultiplier|HPBypassCmd|LPBypassCmd|HPBypassPos|LPBypassPos|HPSprayPos|LPSprayPos|HPBypassOpenLS|HPBypassCloseLS|LPBypassOpenLS|LPBypassCloseLS|HPBypassMassFlow|LPBypassMassFlow|HPSprayMassFlow|LPSprayMassFlow|HPBypassInletPressure|LPBypassInletPressure|HPBypassOutletPressure|LPBypassOutletPressure|HPBypassInletTemperature|LPBypassInletTemperature|HPBypassOutletTemperature|LPBypassOutletTemperature|CondenserPressure|CondenserLevel))$");
getErrorString();
