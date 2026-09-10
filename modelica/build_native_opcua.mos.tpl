// OpenModelica's native OPC UA server exposes inputs and continuous states,
// but the default alias-elimination pass may remove their public names before
// code generation.  Keep simple equations so the ECMS command endpoint
// remains addressable without changing the plant equations.
setCommandLineOptions("--std=3.4 --removeSimpleEquations=none");
loadModel(Modelica, {"3.2.3"});
getErrorString();
loadFile("/workspace/vendor/ThermoSysPro/ThermoSysPro/package.mo");
getErrorString();
loadFile("/workspace/build/TripLens_CombinedCycle_TripTAC.mo");
getErrorString();
cd("/workspace/build");
buildModel(
  TripLens_CombinedCycle_TripTAC,
  startTime=0,
  stopTime=@STOP_TIME@,
  numberOfIntervals=@NUMBER_OF_INTERVALS@,
  tolerance=1e-3,
  method="dassl",
  outputFormat="csv",
  fileNamePrefix="TripLens_Native_OPCUA");
getErrorString();
