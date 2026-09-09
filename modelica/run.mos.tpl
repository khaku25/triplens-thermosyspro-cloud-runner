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
  // The routed steam path is seeded from a previously verified normal state.
  // Skip only the separate symbolic initialization solve, whose exploratory
  // Newton iterates leave the valid IF97 domain; the complete DAE remains
  // active from t=0 and throughout the Trip transient.
  simflags="-noEventEmit -iim=none -lv=LOG_INIT,LOG_NLS",
  fileNamePrefix="thermosyspro_trip_tac",
  variableFilter="^(time|Debit\\.y\\.signal|Temperature\\.y\\.signal|Alternateur\\.Welec|Ballon(HP|MP|BP)\\.(yLevel\\.signal|zl|P)|Turbine(HP|MP|BP)\\.Q|vanne_alimentation(HP|MP|BP)\\.Ouv\\.signal|vpp(STTripLatch|HPAdmissionPos|IPAdmissionPos|LPDrumAdmissionMultiplier|HPBypassCmd|LPBypassCmd|HPBypassPos|LPBypassPos|HPSprayPos|LPSprayPos|HPBypassOpenLS|HPBypassCloseLS|LPBypassOpenLS|LPBypassCloseLS|HPBypassMassFlow|LPBypassMassFlow|HPSprayMassFlow|LPSprayMassFlow|HPBypassInletPressure|LPBypassInletPressure|HPBypassOutletPressure|LPBypassOutletPressure|HPBypassInletTemperature|LPBypassInletTemperature|HPBypassOutletTemperature|LPBypassOutletTemperature|CondenserPressure|CondenserLevel))$");
getErrorString();
