setCommandLineOptions("--std=3.4");
// CVODE is embedded in the Co-Simulation FMU so the network communication
// interval is not confused with an explicit Euler integration step.
setCommandLineOptions("--fmiFlags=s:cvode");
setCommandLineOptions("--fmuRuntimeDepends=modelica");
loadModel(Modelica, {"3.2.3"});
getErrorString();
loadFile("/workspace/vendor/ThermoSysPro/ThermoSysPro/package.mo");
getErrorString();
loadFile("/workspace/build/TripLens_CombinedCycle_TripTAC.mo");
getErrorString();
cd("/workspace/build");
buildModelFMU(
  TripLens_CombinedCycle_TripTAC,
  version="2.0",
  fmuType="cs",
  fileNamePrefix="TripLens_CCPP_Live",
  platforms={"static"});
getErrorString();
