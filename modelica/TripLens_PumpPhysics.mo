within ;
package TripLens_PumpPhysics
  "Reusable motor-breaker dynamics used by the TripLens ThermoSysPro adapters"

  model BreakerInertialPumpDrive
    "Breaker motor and rotating inertia driving a native pump-speed input"
    parameter Real nominalSpeedRpm(unit="rev/min") = 1400;
    parameter Modelica.SIunits.MomentOfInertia J = 100
      "Combined motor and pump rotating inertia";
    parameter Modelica.SIunits.Torque frictionTorqueNominal = 10
      "Nominal positive-speed bearing and windage torque";
    parameter Real proportionalGain = 250
      "Speed controller gain in N.m/(rev/min)";
    parameter Real integralGain = 25
      "Speed controller integral gain in N.m/(rev/min.s)";
    parameter Modelica.SIunits.Torque initialTorque = 5000
      "Initial motor-torque guess used to preload the speed controller";
    parameter Modelica.SIunits.Torque torqueLimit = 1e5;
    parameter Real torqueRegularizationSpeedRpm(unit="rev/min") = 30
      "Low-speed regularization used to recover load torque from pump power";

    ThermoSysPro.InstrumentationAndControl.Connectors.InputLogical
      breakerClosed;
    ThermoSysPro.InstrumentationAndControl.Connectors.InputReal pumpPower;
    ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal speedCommand;

    Modelica.SIunits.AngularVelocity angularSpeed(
      start=nominalSpeedRpm*Modelica.Constants.pi/30,
      fixed=true);
    ThermoSysPro.Units.AngularVelocity_rpm speedRpm;
    Modelica.SIunits.Torque motorTorque;
    Modelica.SIunits.Torque hydraulicTorque;
    Modelica.SIunits.Torque frictionTorque;
    Modelica.SIunits.Torque netTorque;
    Real speedError(unit="rev/min");
    Real integralState(start=initialTorque/integralGain, fixed=false);

  initial equation
    // Start from an estimated normal-load torque, then let the PI controller
    // settle during the pre-trip warm-up. No post-trip residual RPM is imposed.
    integralState = initialTorque/integralGain;

  equation
    speedRpm = 30/Modelica.Constants.pi*max(angularSpeed, 0);
    speedCommand.signal = speedRpm;
    speedError = nominalSpeedRpm - speedRpm;
    der(integralState) = if breakerClosed.signal then speedError else 0;

    motorTorque = if breakerClosed.signal then noEvent(max(0, min(
      torqueLimit,
      proportionalGain*speedError + integralGain*integralState))) else 0;

    // StaticCentrifugalPump exposes its mechanical load as Wm. Recover the
    // opposing shaft torque smoothly so the expression remains finite at
    // standstill, where a direct Wm/angularSpeed division would be singular.
    hydraulicTorque = noEvent(max(pumpPower.signal, 0)*max(angularSpeed, 0)/(
      angularSpeed^2 + (torqueRegularizationSpeedRpm*
      Modelica.Constants.pi/30)^2));
    frictionTorque = noEvent(if angularSpeed > 0 then
      frictionTorqueNominal*min(1, angularSpeed/(
      nominalSpeedRpm*Modelica.Constants.pi/30)) else 0);
    netTorque = motorTorque - hydraulicTorque - frictionTorque;
    der(angularSpeed) = if angularSpeed > 0 or netTorque > 0 then
      netTorque/J else 0;
  end BreakerInertialPumpDrive;

  model SpringLoadedCheckValve
    "Continuously moving non-return valve with spring-equivalent closing flow"
    parameter Modelica.SIunits.MassFlowRate closeFlow = 1
      "Forward flow below which the spring closes the valve";
    parameter Modelica.SIunits.MassFlowRate flowTransition = max(0.1,
      0.05*closeFlow) "Width of the smooth closing-flow transition";
    parameter Real openResistance(unit="Pa.s/kg") = 1e-3
      "Hydraulic resistance while open";
    parameter Real closedResistance(unit="Pa.s/kg") = 1e6
      "Large finite hydraulic resistance while closed";
    parameter Real closeTime(unit="s") = 0.25
      "Flap closing time constant";
    parameter Real reopenTime(unit="s") = 0.5
      "Flap reopening time constant";
    parameter Real closedPosition = 0.05
      "Position below which the valve reports closed";

    Boolean ouvert "Valve state";
    Real opening(start=1, fixed=true, min=0, max=1) "Continuous flap position";
    Real valveTarget(min=0, max=1);
    Real effectiveResistance(unit="Pa.s/kg");
    Modelica.SIunits.MassFlowRate Q "Mass flow rate";
    ThermoSysPro.Units.DifferentialPressure deltaP
      "Pressure difference between inlet and outlet";
    ThermoSysPro.WaterSteam.Connectors.FluidInlet C1;
    ThermoSysPro.WaterSteam.Connectors.FluidOutlet C2;

  equation
    assert(openResistance > 0 and closedResistance > openResistance and
      flowTransition > 0 and closeTime > 0 and reopenTime > 0 and
      closedPosition > 0 and closedPosition < 1,
      "SpringLoadedCheckValve requires 0 < openResistance < closedResistance");

    C1.Q = C2.Q;
    C1.h = C2.h;
    Q = C1.Q;
    deltaP = C1.P - C2.P;

    // Preserve ThermoSysPro's directional enthalpy transport without adding
    // a second IF97 property state to the large plant initialization system.
    0 = if Q > 0 then C1.h - C1.h_vol else C2.h - C2.h_vol;

    // The spring target falls continuously as forward flow approaches the
    // closing threshold. Keeping flap position and resistance continuous
    // avoids an ill-conditioned hydraulic jump in the full plant equations.
    valveTarget = noEvent(0.5 + 0.5*Modelica.Math.tanh((Q - closeFlow)/
      flowTransition));
    der(opening) = (valveTarget - opening)/noEvent(if valveTarget < opening
      then closeTime else reopenTime);
    effectiveResistance = openResistance + (closedResistance -
      openResistance)*(1 - opening)^2;
    deltaP = effectiveResistance*Q;
    ouvert = opening > closedPosition;
  end SpringLoadedCheckValve;


  model FastSteamTripValve
    "Finite-stroke steam trip valve; 52G opening remains instantaneous"
    parameter Real closeTime(unit="s")=0.15
      "Fast hydraulic actuator closing time";
    parameter Real reopenTime(unit="s")=1
      "Reset/reopening time used outside a latched trip";
    parameter Real minimumOpening=0.005
      "Small internal steam-flow floor for Stodola/IF97 regularization";

    ThermoSysPro.InstrumentationAndControl.Connectors.InputReal
      normalOpening;
    ThermoSysPro.InstrumentationAndControl.Connectors.InputLogical trip;
    ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal
      effectiveOpening;

    Real position(start=1, fixed=false, min=minimumOpening, max=1);
    Real target(min=minimumOpening, max=1);

  initial equation
    position = max(minimumOpening, min(1, normalOpening.signal));

  equation
    assert(closeTime > 0 and reopenTime > 0 and minimumOpening > 0 and
      minimumOpening < 1,
      "FastSteamTripValve requires positive time constants and 0 < minimumOpening < 1");
    // The electrical trip remains instantaneous at 52G. This small hydraulic
    // floor applies only to the internal turbine steam path: the simplified
    // Stodola/IF97 equations are singular at exactly zero mass flow.
    target = if trip.signal then minimumOpening else
      max(minimumOpening, min(1, normalOpening.signal));
    der(position) = (target - position)/noEvent(if target < position then
      closeTime else reopenTime);
    effectiveOpening.signal = position;
  end FastSteamTripValve;

  model ProtectedExhaustGasBoundary
    "GT exhaust boundary controlled only by a resolved common trip request"
    parameter Modelica.SIunits.MassFlowRate minimumMassFlow=50;
    parameter Modelica.SIunits.Temperature minimumTemperature=423;
    parameter Real rundownTime(unit="s")=5;

    ThermoSysPro.InstrumentationAndControl.Connectors.InputReal normalMassFlow;
    ThermoSysPro.InstrumentationAndControl.Connectors.InputReal normalTemperature;
    ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal effectiveMassFlow;
    ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal effectiveTemperature;
    input Boolean gtTripLatched;
    input Real gtTripElapsed(unit="s");
    Real rundownFraction(min=0, max=1);

  equation
    assert(minimumMassFlow >= 0 and minimumTemperature > 0 and rundownTime > 0,
      "ProtectedExhaustGasBoundary parameters must be physical and positive");
    rundownFraction = if gtTripLatched then
      1 - exp(-max(gtTripElapsed, 0)/rundownTime) else 0;
    effectiveMassFlow.signal = minimumMassFlow +
      (max(minimumMassFlow, normalMassFlow.signal) - minimumMassFlow)*
      (1 - rundownFraction);
    effectiveTemperature.signal = minimumTemperature +
      (max(minimumTemperature, normalTemperature.signal) - minimumTemperature)*
      (1 - rundownFraction);
  end ProtectedExhaustGasBoundary;

  model CommonDrumTripProtection
    "Layer 1 drum alarms, Layer 2 common matrix and Layer 3 breaker timing"
    parameter Modelica.SIunits.Length hpHHThreshold=1.25;
    parameter Modelica.SIunits.Length hpLLThreshold=0.85;
    parameter Modelica.SIunits.Length ipHHThreshold=1.25;
    parameter Modelica.SIunits.Length ipLLThreshold=0.85;
    parameter Modelica.SIunits.Length lpHHThreshold=1.95;
    parameter Modelica.SIunits.Length lpLLThreshold=1.55;
    parameter Real alarmDelay(unit="s")=0.5;
    parameter Real gtReceiveDelay(unit="s")=0.020;
    parameter Real gtLockoutDelay(unit="s")=0.035;
    parameter Real gtBreakerDelay(unit="s")=0.080;
    parameter Real stBreakerDelay(unit="s")=0.100;

    input Modelica.SIunits.Length hpDrumLevel;
    input Modelica.SIunits.Length ipDrumLevel;
    input Modelica.SIunits.Length lpDrumLevel;

    output Boolean hpDrumHH;
    output Boolean hpDrumLL;
    output Boolean ipDrumHH;
    output Boolean ipDrumLL;
    output Boolean lpDrumHH;
    output Boolean lpDrumLL;
    output Boolean hpDrumHHPickup;
    output Boolean hpDrumLLPickup;
    output Boolean ipDrumHHPickup;
    output Boolean ipDrumLLPickup;
    output Boolean lpDrumHHPickup;
    output Boolean lpDrumLLPickup;
    output Boolean gtTripRequest;
    output Boolean stTripRequest;
    output Boolean gtTripLatched(start=false);
    output Boolean stTripLatched(start=false);
    output Boolean relay86GTTripReceived;
    output Boolean relay86GTOperated;
    output Boolean breaker52GTClosed;
    output Boolean breaker52STClosed;

    output Real hpHHTimer(unit="s");
    output Real hpLLTimer(unit="s");
    output Real ipHHTimer(unit="s");
    output Real ipLLTimer(unit="s");
    output Real lpHHTimer(unit="s");
    output Real lpLLTimer(unit="s");
    output Real gtSequenceTimer(unit="s");
    output Real stSequenceTimer(unit="s");

    discrete Real hpHHSince(start=-1);
    discrete Real hpLLSince(start=-1);
    discrete Real ipHHSince(start=-1);
    discrete Real ipLLSince(start=-1);
    discrete Real lpHHSince(start=-1);
    discrete Real lpLLSince(start=-1);
    discrete Real gtTripTime(start=-1);
    discrete Real stTripTime(start=-1);

  initial equation
    hpHHSince = if hpDrumLevel >= hpHHThreshold then 0 else -1;
    hpLLSince = if hpDrumLevel <= hpLLThreshold then 0 else -1;
    ipHHSince = if ipDrumLevel >= ipHHThreshold then 0 else -1;
    ipLLSince = if ipDrumLevel <= ipLLThreshold then 0 else -1;
    lpHHSince = if lpDrumLevel >= lpHHThreshold then 0 else -1;
    lpLLSince = if lpDrumLevel <= lpLLThreshold then 0 else -1;
    gtTripLatched = false;
    stTripLatched = false;
    gtTripTime = -1;
    stTripTime = -1;

  equation
    assert(alarmDelay > 0 and gtReceiveDelay >= 0 and
      gtLockoutDelay >= 0 and gtBreakerDelay >= 0 and stBreakerDelay >= 0,
      "CommonDrumTripProtection delays must be non-negative");
    assert(hpLLThreshold < hpHHThreshold and ipLLThreshold < ipHHThreshold and
      lpLLThreshold < lpHHThreshold,
      "Drum LL thresholds must be below HH thresholds");

    hpDrumHH = hpDrumLevel >= hpHHThreshold;
    hpDrumLL = hpDrumLevel <= hpLLThreshold;
    ipDrumHH = ipDrumLevel >= ipHHThreshold;
    ipDrumLL = ipDrumLevel <= ipLLThreshold;
    lpDrumHH = lpDrumLevel >= lpHHThreshold;
    lpDrumLL = lpDrumLevel <= lpLLThreshold;

    when change(hpDrumHH) then
      hpHHSince = if hpDrumHH then time else -1;
    end when;
    when change(hpDrumLL) then
      hpLLSince = if hpDrumLL then time else -1;
    end when;
    when change(ipDrumHH) then
      ipHHSince = if ipDrumHH then time else -1;
    end when;
    when change(ipDrumLL) then
      ipLLSince = if ipDrumLL then time else -1;
    end when;
    when change(lpDrumHH) then
      lpHHSince = if lpDrumHH then time else -1;
    end when;
    when change(lpDrumLL) then
      lpLLSince = if lpDrumLL then time else -1;
    end when;

    hpHHTimer = if hpDrumHH and hpHHSince >= 0 then time - hpHHSince else 0;
    hpLLTimer = if hpDrumLL and hpLLSince >= 0 then time - hpLLSince else 0;
    ipHHTimer = if ipDrumHH and ipHHSince >= 0 then time - ipHHSince else 0;
    ipLLTimer = if ipDrumLL and ipLLSince >= 0 then time - ipLLSince else 0;
    lpHHTimer = if lpDrumHH and lpHHSince >= 0 then time - lpHHSince else 0;
    lpLLTimer = if lpDrumLL and lpLLSince >= 0 then time - lpLLSince else 0;

    hpDrumHHPickup = hpHHTimer >= alarmDelay;
    hpDrumLLPickup = hpLLTimer >= alarmDelay;
    ipDrumHHPickup = ipHHTimer >= alarmDelay;
    ipDrumLLPickup = ipLLTimer >= alarmDelay;
    lpDrumHHPickup = lpHHTimer >= alarmDelay;
    lpDrumLLPickup = lpLLTimer >= alarmDelay;

    // common_trip_matrix.csv: any drum LL trips GT and ST; any HH trips ST.
    gtTripRequest = hpDrumLLPickup or ipDrumLLPickup or lpDrumLLPickup;
    stTripRequest = gtTripRequest or hpDrumHHPickup or ipDrumHHPickup or
      lpDrumHHPickup;

    when gtTripRequest then
      gtTripLatched = true;
      gtTripTime = time;
    end when;
    when stTripRequest then
      stTripLatched = true;
      stTripTime = time;
    end when;

    gtSequenceTimer = if gtTripLatched then time - gtTripTime else 0;
    stSequenceTimer = if stTripLatched then time - stTripTime else 0;
    relay86GTTripReceived = gtTripLatched and
      gtSequenceTimer >= gtReceiveDelay;
    relay86GTOperated = gtTripLatched and
      gtSequenceTimer >= gtReceiveDelay + gtLockoutDelay;
    breaker52GTClosed = not (gtTripLatched and gtSequenceTimer >=
      gtReceiveDelay + gtLockoutDelay + gtBreakerDelay);
    breaker52STClosed = not (stTripLatched and
      stSequenceTimer >= stBreakerDelay);
  end CommonDrumTripProtection;


end TripLens_PumpPhysics;
