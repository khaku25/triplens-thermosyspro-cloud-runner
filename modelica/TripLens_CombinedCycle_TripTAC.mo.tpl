within ;
model TripLens_CombinedCycle_TripTAC
  // Legacy wrapper/model name retained because it extends ThermoSysPro's
  // CombinedCycle_TripTAC example. The exhaust boundary itself is not the
  // canonical GT Trip definition used by TripLens.
  parameter Real eventTime(unit="s") = @TRIP_TIME@;
  parameter Real boundaryRampDuration(unit="s") = @TRIP_RAMP_DURATION@;
  parameter Real exhaustFlowNormal(unit="kg/s") = 606.94;
  // Canonical semantics: 606.94 -> 150 kg/s and 893.75 -> 550 K is GT DERATE.
  // It must not be used as evidence of GT Trip success; GT Trip success is
  // electrical separation with 52GT.CLOSED=0 in the VPP/ECMS path.
  parameter Real exhaustFlowDerated(unit="kg/s") = 150.0;
  parameter Real exhaustTemperatureNormal(unit="K") = 893.75;
  parameter Real exhaustTemperatureDerated(unit="K") = 550.0;

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

  annotation(experiment(
    StartTime=0,
    StopTime=@STOP_TIME@,
    Tolerance=1e-3,
    Interval=@OUTPUT_INTERVAL@));
end TripLens_CombinedCycle_TripTAC;
