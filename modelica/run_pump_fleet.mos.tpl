setCommandLineOptions("--std=3.4");
loadModel(Modelica, {"3.2.3"});
getErrorString();
loadFile("/workspace/vendor/ThermoSysPro/ThermoSysPro/package.mo");
getErrorString();
loadFile("/workspace/modelica/TripLens_PumpPhysics.mo");
getErrorString();
loadFile("/workspace/build/TripLens_CombinedCycle_AllPumps.mo");
getErrorString();
cd("/workspace/build");
simulate(
  @MODEL_NAME@,
  startTime=0,
  stopTime=@STOP_TIME@,
  numberOfIntervals=@NUMBER_OF_INTERVALS@,
  tolerance=1e-3,
  method="dassl",
  outputFormat="csv",
  // The translated legacy plant has no usable sparse Jacobian pattern.
  // Use OpenModelica's dense MINPACK hybrid nonlinear solver explicitly.
  simflags="-noEventEmit -nls=hybrid -nlsLS=lapack -nlssMaxDensity=0",
  fileNamePrefix="@OUTPUT_PREFIX@",
  variableFilter="^(time|breaker(HP|IP|LP|CW)Closed|drive(HP|IP|LP)\\.(speedRpm|motorTorque|speedError)|cwPumpDrive\\.(speedRpm|speedRatio|motorTorque|hydraulicTorque|checkValvePosition|massFlow\\.signal)|PompeAlim(HP|MP|BP)\\.(VRot|Q|Qv|Wm|Wh|R|deltaP)|checkValve(HP|IP|LP)\\.(ouvert|Q|deltaP)|CapteurDebitEau(HP|MP|BP|Condenseur)\\.(Q|Measure\\.signal)|Alternateur\\.Welec|Condenseur\\.(P|yNiveau\\.signal)|Ballon(HP|MP|BP)\\.(yLevel\\.signal|zl|P)|Turbine(HP|MP|BP)\\.Q|vanne_alimentation(HP|MP|BP)\\.Ouv\\.signal|Debit\\.y\\.signal|Temperature\\.y\\.signal)$");
getErrorString();
