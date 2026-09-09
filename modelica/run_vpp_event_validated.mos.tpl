setCommandLineOptions("--std=3.4");
loadModel(Modelica, {"3.2.3"});
getErrorString();
loadFile("/workspace/vendor/ThermoSysPro/ThermoSysPro/package.mo");
getErrorString();
loadFile("/workspace/modelica/TripLens_VPPLogicBlocks.mo");
getErrorString();
loadFile("/workspace/build/TripLens_VPPAlarmRuntime.mo");
getErrorString();
loadFile("/workspace/build/TripLens_CombinedCycle_VPPEvent.mo");
getErrorString();
checkModel(TripLens_CombinedCycle_VPPEvent);
getErrorString();
cd("/workspace/build");
simulate(
  TripLens_CombinedCycle_VPPEvent,
  startTime=0,
  stopTime=@STOP_TIME@,
  numberOfIntervals=@NUMBER_OF_INTERVALS@,
  tolerance=1e-3,
  method="dassl",
  outputFormat="csv",
  fileNamePrefix="triplens_vpp_event",
  // Keep native event points so false/true transitions at one timestamp are
  // available to the transition-only serializer.
  variableFilter="^(time|alarmRuntime\\..*|bfpHPBreakerClosed|gtTrip(Request|Latched)|stTrip(Request|Latched)|relay86GT(TripReceived|Operated)|gt52GClosed|st52GClosed|gtGridElectricalPower|stGridElectricalPower|PompeAlimHP\\.(Vr|Q|Qv|Wm|R|deltaP)|arretPomesHP\\.y\\.signal|CapteurDebitEau(HP|MP|BP)\\.(Q|Measure\\.signal)|Alternateur\\.Welec|Ballon(HP|MP|BP)\\.(yLevel\\.signal|zl|P)|Turbine(HP|MP|BP)\\.Q|vanne_alimentation(HP|MP|BP)\\.Ouv\\.signal|Debit\\.y\\.signal|Temperature\\.y\\.signal)$");
getErrorString();
