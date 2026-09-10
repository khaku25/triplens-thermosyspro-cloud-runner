// Preserve only named top-level interface aliases. OpenModelica enables the
// same targeted module for FMI 2.0 output contracts; unlike disabling alias
// elimination globally, it leaves the ThermoSysPro equation system intact.
setCommandLineOptions("--std=3.4 --preOptModules+=introduceOutputAliases");
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
