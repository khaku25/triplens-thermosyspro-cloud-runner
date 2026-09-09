within ;
model TripLens_CombinedCycle_TripTAC
  parameter Real tripTime(unit="s") = @TRIP_TIME@;
  parameter Real tripRampDuration(unit="s") = @TRIP_RAMP_DURATION@;
  parameter Real exhaustFlowNormal(unit="kg/s") = 606.94;
  // The legacy ThermoSysPro CCPP becomes singular when flue-gas flow is
  // forced to 50 kg/s while its steam-side pumps and valves remain online.
  // 150 kg/s is the lowest severe-trip point verified to reach 1000 s in
  // OpenModelica 1.27 with the paired temperature floor below.
  parameter Real exhaustFlowTripped(unit="kg/s") = 150.0;
  parameter Real exhaustTemperatureNormal(unit="K") = 893.75;
  parameter Real exhaustTemperatureTripped(unit="K") = 550.0;

  extends ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC(
    vppTripTime=tripTime,
    // Seed the routed steam path from the last verified normal operating
    // point. These are initialization guesses only; the fluid equations own
    // every value after initialization and throughout the Trip transient.
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
      Q(start=176.7893383342879, nominal=200),
      Ce(Q(start=176.7893383342879, nominal=200),
         h(start=3523910), h_vol(start=3523910)),
      Cs(Q(start=176.7893383342879, nominal=200),
         h(start=3029780), h_vol(start=3029780))),
    TurbineBP(
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
    Debit(Table=[0,exhaustFlowNormal;
                 tripTime,exhaustFlowNormal;
                 tripTime + tripRampDuration,exhaustFlowTripped;
                 @STOP_TIME@,exhaustFlowTripped]),
    Temperature(Table=[0,exhaustTemperatureNormal;
                       tripTime,exhaustTemperatureNormal;
                       tripTime + tripRampDuration,exhaustTemperatureTripped;
                       @STOP_TIME@,exhaustTemperatureTripped]));

  annotation(experiment(
    StartTime=0,
    StopTime=@STOP_TIME@,
    Tolerance=1e-3,
    Interval=@OUTPUT_INTERVAL@));
end TripLens_CombinedCycle_TripTAC;
