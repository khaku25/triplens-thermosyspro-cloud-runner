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
  parameter Real exhaustTemperatureNormal(unit="K") = 893.75;
  parameter Real exhaustTemperatureDerated(unit="K") = 550.0;

  Real vppGTExhaustMassFlowTH "Published GT exhaust mass flow in t/h";
  Real vppHPTurbineSteamFlowTH "Published HP turbine steam flow in t/h";
  Real vppIPTurbineSteamFlowTH "Published IP turbine steam flow in t/h";
  Real vppLPTurbineSteamFlowTH "Published LP turbine steam flow in t/h";
  Real vppHPBypassMassFlowTH "Published HP bypass steam flow in t/h";
  Real vppLPBypassMassFlowTH "Published LP bypass steam flow in t/h";
  Real vppHPSprayMassFlowTH "Published HP bypass spray flow in t/h";
  Real vppLPSprayMassFlowTH "Published LP bypass spray flow in t/h";

  extends ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC(
    vppTripTime=@VPP_TRIP_TIME@,
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
  // ThermoSysPro connectors retain their native SI balance. Only the
  // published RAW boundary is converted to the plant-facing t/h contract.
  vppGTExhaustMassFlowTH = 3.6*Debit.y.signal;
  vppHPTurbineSteamFlowTH = 3.6*TurbineHP.Q;
  vppIPTurbineSteamFlowTH = 3.6*TurbineMP.Q;
  vppLPTurbineSteamFlowTH = 3.6*TurbineBP.Q;
  vppHPBypassMassFlowTH = 3.6*vppHPBypassMassFlow;
  vppLPBypassMassFlowTH = 3.6*vppLPBypassMassFlow;
  vppHPSprayMassFlowTH = 3.6*vppHPSprayMassFlow;
  vppLPSprayMassFlowTH = 3.6*vppLPSprayMassFlow;

  annotation(experiment(
    StartTime=0,
    StopTime=@STOP_TIME@,
    Tolerance=1e-3,
    Interval=@OUTPUT_INTERVAL@));
end TripLens_CombinedCycle_TripTAC;
