within ;
model TripLens_CombinedCycle_TripTAC
  // Legacy wrapper/model name retained because it extends ThermoSysPro's
  // CombinedCycle_TripTAC example. The exhaust boundary itself is not the
  // canonical GT Trip definition used by TripLens.
  parameter Real eventTime(unit="s") = @TRIP_TIME@;
  parameter Real boundaryRampDuration(unit="s") = @TRIP_RAMP_DURATION@;
  parameter Real exhaustFlowNormalTH = 2184.984
    "Published normal GT exhaust mass flow in t/h";
  // Canonical semantics: 2184.984 -> 540 t/h and 893.75 -> 550 K is GT DERATE.
  // It must not be used as evidence of GT Trip success; GT Trip success is
  // electrical separation with 52GT.CLOSED=0 in the VPP/ECMS path.
  parameter Real exhaustFlowDeratedTH = 540.0
    "Published derated GT exhaust mass flow in t/h";
  parameter Real exhaustFlowTripTH = 180.0
    "Post-Trip purge/coastdown exhaust-flow boundary in t/h";
  parameter Real exhaustTemperatureNormal(unit="K") = 893.75;
  parameter Real exhaustTemperatureDerated(unit="K") = 550.0;
  parameter Real exhaustTemperatureTrip(unit="K") = 450.0;
  parameter Boolean enableGTTrip = @GT_TRIP_ENABLED@
    "Assert the canonical GT Trip command in the Modelica run";
  parameter Real vppGTTripCommandDelay(unit="s") = 0.055;
  parameter Real vppGTBreakerOpenDelay(unit="s") = 0.080;
  parameter Real vppSTBreakerOpenDelay(unit="s") = 0.100;
  parameter Real vppGTGPowerNormalMW(unit="MW") = 160.0;
  parameter Real vppGTGPowerDecayTau(unit="s") = 0.35;
  parameter Real vppGTGSpeedNormalRPM = 3600.0;
  parameter Real vppGTGCoastdownTau(unit="s") = 1.2;

  output Boolean vppGTTripCmd "GT Trip command observed by the physical model";
  output Boolean vppGTTripLatch "Modelica-produced GT Trip latch";
  output Boolean vpp52GTTripCmd "Modelica-produced 52GT Trip command";
  output Boolean vpp52GTClosed "Modelica-produced 52GT auxiliary contact";
  output Boolean vpp52STTripCmd "Modelica-produced 52ST Trip command";
  output Boolean vpp52STClosed "Modelica-produced 52ST auxiliary contact";
  output Boolean vppSTTripLatchPublished
    "Stable top-level FMU output for the physical ST Trip latch";
  output Real vppGTGPowerMW(unit="MW") "Reduced-order GT electrical output";
  output Real vppGTGSpeedRPM "Reduced-order GT shaft speed in rpm";
  discrete Real vppGTTripAssertTime(unit="s", start=eventTime, fixed=true)
    "Simulation time at the first physical GT Trip assertion";

  output Real vppGTExhaustMassFlowTH "Published GT exhaust mass flow in t/h";
  output Real vppGTExhaustTemperatureK(unit="K")
    "Published GT exhaust temperature at the physical source boundary";
  output Real vppHPTurbineSteamFlowTH "Published HP turbine steam flow in t/h";
  output Real vppIPTurbineSteamFlowTH "Published IP turbine steam flow in t/h";
  output Real vppLPTurbineSteamFlowTH "Published LP turbine steam flow in t/h";
  output Real vppHPBypassMassFlowTH "Published HP bypass steam flow in t/h";
  output Real vppLPBypassMassFlowTH "Published LP bypass steam flow in t/h";
  output Real vppHPSprayMassFlowTH "Published HP bypass spray flow in t/h";
  output Real vppLPSprayMassFlowTH "Published LP bypass spray flow in t/h";
  output Real vppHPDrumLevelM(unit="m") "Published HP drum liquid level";
  output Real vppIPDrumLevelM(unit="m") "Published IP drum liquid level";
  output Real vppLPDrumLevelM(unit="m") "Published LP drum liquid level";
  output Real vppHPDrumPressurePa(unit="Pa") "Published HP drum pressure";
  output Real vppIPDrumPressurePa(unit="Pa") "Published IP drum pressure";
  output Real vppLPDrumPressurePa(unit="Pa") "Published LP drum pressure";
  output Real vppHPAdmissionPositionPU "Applied HP turbine admission position";
  output Real vppIPAdmissionPositionPU "Applied IP turbine admission position";
  output Real vppLPAdmissionMultiplierPU "Applied LP admission multiplier";
  output Real vppHPBypassPositionPU "Applied HP bypass-valve position";
  output Real vppLPBypassPositionPU "Applied LP bypass-valve position";
  output Real vppCondenserPressurePa(unit="Pa") "Published condenser pressure";
  output Real vppCondenserLevelM(unit="m") "Published condenser level";

  extends ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC(
    vppTripTime=@VPP_TRIP_TIME@,
    vppUseExternalTripInput=@EXTERNAL_TRIP_ENABLED@,
    vppGTExhaustMassFlowNormal=exhaustFlowNormalTH/3.6,
    vppGTExhaustMassFlowTrip=exhaustFlowTripTH/3.6,
    vppGTExhaustTemperatureNormal=exhaustTemperatureNormal,
    vppGTExhaustTemperatureTrip=exhaustTemperatureTrip,
    vppGTExhaustResponseTau=boundaryRampDuration/(-log(0.05)),
    // Seed the routed steam path from the last verified normal operating
    // point. These are initialization guesses only; the fluid equations own
    // every value after initialization and throughout the transient.
    DoubleDebitHP(
      P(start=12681000, nominal=1.3e7),
      h(start=3450835, nominal=3.5e6),
      Ce(Q(start=75.88454959880416, nominal=100),
         h(start=3450835), h_vol(start=3450835)),
      Cs(Q(start=151.7690991976083, nominal=200),
         h(start=3450835), h_vol(start=3450835))),
    vanne_entree_TurbineHP(
      Q(start=151.7690991976083, nominal=200),
      C1(Q(start=151.7690991976083, nominal=200),
         h(start=3450835), h_vol(start=3450835)),
      C2(Q(start=151.7690991976083, nominal=200),
         h(start=3450835), h_vol(start=3450835))),
    TurbineHP(
      regularizePressureCrossover=true,
      Q(start=151.7690991976083, nominal=200),
      Ce(Q(start=151.7690991976083, nominal=200),
         h(start=3450835), h_vol(start=3450835)),
      Cs(Q(start=151.7690991976083, nominal=200),
         h(start=3046260), h_vol(start=3046260))),
    MoitieDebitHP(
      h(start=3046260, nominal=3.2e6),
      Ce(Q(start=151.7690991976083, nominal=200), h_vol(start=3046260)),
      Cs(Q(start=75.88454959880416, nominal=100),
         h(start=3046260), h_vol(start=3046260))),
    lumpedStraightPipeK2(
      Q(start=75.88454959880416, nominal=100),
      h(start=3046260, nominal=3.2e6),
      C2(Q(start=75.88454959880416, nominal=100),
         h(start=3046260), h_vol(start=3046260))),
    DoubleDebitMP(
      P(start=2548600, nominal=3e6),
      h(start=3523910, nominal=3.6e6),
      Ce(Q(start=88.39466916714395, nominal=100),
         h(start=3523910), h_vol(start=3523910)),
      Cs(Q(start=176.7893383342879, nominal=200),
         h(start=3523910), h_vol(start=3523910))),
    vanne_entree_TurbineMP(
      Q(start=176.7893383342879, nominal=200),
      C1(Q(start=176.7893383342879, nominal=200),
         h(start=3523910), h_vol(start=3523910)),
      C2(Q(start=176.7893383342879, nominal=200),
         h(start=3523910), h_vol(start=3523910))),
    TurbineMP(
      regularizePressureCrossover=true,
      Q(start=176.7893383342879, nominal=200),
      Ce(Q(start=176.7893383342879, nominal=200),
         h(start=3523910), h_vol(start=3523910)),
      Cs(Q(start=176.7893383342879, nominal=200),
         h(start=3029780), h_vol(start=3029780))),
    TurbineBP(
      regularizePressureCrossover=true,
      Q(start=196.6524916480812, nominal=200),
      Ce(Q(start=196.6524916480812, nominal=200),
         h(start=2997231.36734756), h_vol(start=2997231.36734756)),
      Cs(Q(start=196.6524916480812, nominal=200), h_vol(start=2401030))),
    perteChargeK1(
      Q(start=196.6524916480812, nominal=200),
      C2(Q(start=196.6524916480812, nominal=200),
         h(start=2401030), h_vol(start=2401030))),
    CapteurDebitVapCondenseur(
      Q(start=196.6524916480812, nominal=200),
      C1(Q(start=196.6524916480812, nominal=200),
         h(start=2401030), h_vol(start=2401030)),
      C2(Q(start=196.6524916480812, nominal=200))),
    Debit(Table=@EXHAUST_FLOW_TABLE@),
    Temperature(Table=@EXHAUST_TEMPERATURE_TABLE@));

equation
  // The thermal plant and the reduced-order electrical boundary are solved in
  // one Modelica result file. Downstream ECMS code must observe these outputs;
  // it is not allowed to recreate them from Python timing constants.
  vppGTTripCmd = if vppUseExternalTripInput then
    (vppExternalTripCommand or vppExternalTripCommandNative >= 0.5)
    else enableGTTrip and time >= eventTime;
  vppGTTripLatch = vppSTTripLatch;
  vppSTTripLatchPublished = vppSTTripLatch;
  when edge(vppGTTripLatch) then
    vppGTTripAssertTime = time;
  end when;
  vpp52GTTripCmd = vppGTTripLatch and
    time >= vppGTTripAssertTime + vppGTTripCommandDelay;
  vpp52GTClosed = not (vppGTTripLatch and
    time >= vppGTTripAssertTime + vppGTBreakerOpenDelay);
  vpp52STTripCmd = vppSTTripLatch;
  vpp52STClosed = not (vppSTTripLatch and
    time >= vppGTTripAssertTime + vppSTBreakerOpenDelay);
  vppGTGPowerMW = if not vppGTTripLatch then vppGTGPowerNormalMW
    else if vpp52GTClosed then
      vppGTGPowerNormalMW*exp(
        -(time - vppGTTripAssertTime)/vppGTGPowerDecayTau)
    else 0;
  vppGTGSpeedRPM = if vpp52GTClosed then vppGTGSpeedNormalRPM
    else vppGTGSpeedNormalRPM*exp(
      -(time - vppGTTripAssertTime - vppGTBreakerOpenDelay)
      /vppGTGCoastdownTau);

  // ThermoSysPro connectors retain their native SI balance. Only the
  // published RAW boundary is converted to the plant-facing t/h contract.
  vppGTExhaustMassFlowTH = 3.6*vppGTExhaustMassFlowCommand.signal;
  vppGTExhaustTemperatureK = vppGTExhaustTemperatureCommand.signal;
  vppHPTurbineSteamFlowTH = 3.6*TurbineHP.Q;
  vppIPTurbineSteamFlowTH = 3.6*TurbineMP.Q;
  vppLPTurbineSteamFlowTH = 3.6*TurbineBP.Q;
  vppHPBypassMassFlowTH = 3.6*vppHPBypassMassFlow;
  vppLPBypassMassFlowTH = 3.6*vppLPBypassMassFlow;
  vppHPSprayMassFlowTH = 3.6*vppHPSprayMassFlow;
  vppLPSprayMassFlowTH = 3.6*vppLPSprayMassFlow;
  vppHPDrumLevelM = BallonHP.yLevel.signal;
  vppIPDrumLevelM = BallonMP.yLevel.signal;
  vppLPDrumLevelM = BallonBP.yLevel.signal;
  vppHPDrumPressurePa = BallonHP.P;
  vppIPDrumPressurePa = BallonMP.P;
  vppLPDrumPressurePa = BallonBP.P;
  vppHPAdmissionPositionPU = vppHPAdmissionPos;
  vppIPAdmissionPositionPU = vppIPAdmissionPos;
  vppLPAdmissionMultiplierPU = vppLPDrumAdmissionMultiplier;
  vppHPBypassPositionPU = vppHPBypassPos;
  vppLPBypassPositionPU = vppLPBypassPos;
  vppCondenserPressurePa = vppCondenserPressure;
  vppCondenserLevelM = vppCondenserLevel;

  annotation(experiment(
    StartTime=0,
    StopTime=@STOP_TIME@,
    Tolerance=1e-3,
    Interval=@OUTPUT_INTERVAL@));
end TripLens_CombinedCycle_TripTAC;
