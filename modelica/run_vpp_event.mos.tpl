setCommandLineOptions("--std=3.4");
loadModel(Modelica, {"3.2.3"});
getErrorString();
loadFile("/workspace/vendor/ThermoSysPro/ThermoSysPro/package.mo");
getErrorString();
loadFile("/workspace/modelica/TripLens_PumpPhysics.mo");
getErrorString();
loadFile("/workspace/modelica/TripLens_VPPLogicBlocks.mo");
getErrorString();
loadFile("/workspace/build/TripLens_VPPAlarmRuntime.mo");
getErrorString();
loadFile("/workspace/build/TripLens_CombinedCycle_AllPumps.mo");
getErrorString();
checkModel(@MODEL_NAME@);
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
  fileNamePrefix="@OUTPUT_PREFIX@",
  // Event emission remains enabled. Duplicate native time rows preserve the
  // exact pre/post state change needed by the VPP_EVENT serializer.
  variableFilter="^(time|alarmRuntime\\..*|breaker(HP|IP|LP)Closed|drive(HP|IP|LP)\\.(speedRpm|motorTorque|hydraulicTorque|frictionTorque|speedError)|PompeAlim(HP|MP|BP)\\.(Vr|Q|Qv|Wm|Wh|R|deltaP)|checkValve(HP|IP|LP)\\.(ouvert|opening|valveTarget|effectiveResistance|Q|deltaP)|CapteurDebitEau(HP|MP|BP|Condenseur)\\.(Q|Measure\\.signal)|Alternateur\\.Welec|hpDrumLevel(HH|LL)Pickup|ipDrumLevel(HH|LL)Pickup|lpDrumLevel(HH|LL)Pickup|gtTrip(Request|Latched)|stTrip(Request|Latched)|relay86GT(TripReceived|Operated)|gt52GClosed|st52GClosed|gtGridElectricalPower|stGridElectricalPower|Condenseur\\.(P|yNiveau\\.signal|Wout)|Ballon(HP|MP|BP)\\.(yLevel\\.signal|zl|P)|Turbine(HP|MP|BP)\\.Q|vanne_alimentation(HP|MP|BP)\\.Ouv\\.signal|Debit\\.y\\.signal|Temperature\\.y\\.signal)$");
getErrorString();
