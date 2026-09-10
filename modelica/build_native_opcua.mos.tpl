setCommandLineOptions("--std=3.4");
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
