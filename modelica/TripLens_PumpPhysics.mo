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

  model BoundaryMotorPump
    "Motor-pump coastdown for an existing mass-flow boundary such as CW"
    parameter Real nominalSpeedRpm(unit="rev/min") = 600;
    parameter Modelica.SIunits.MassFlowRate nominalMassFlow = 29804.5;
    parameter Real equivalentInertia = 1
      "Equivalent normalized rotating inertia";
    parameter Real coastdownTime(unit="s") = 8;
    parameter Real restartTime(unit="s") = 2;
    parameter Real valveCloseSpeedRatio = 0.08;
    parameter Real valveTimeConstant(unit="s") = 0.25;

    ThermoSysPro.InstrumentationAndControl.Connectors.InputLogical
      breakerClosed;
    ThermoSysPro.InstrumentationAndControl.Connectors.OutputReal massFlow;

    Real speedRatio(start=1, fixed=true);
    Real checkValvePosition(start=1, fixed=true);
    Real valveTarget;
    Modelica.SIunits.Torque motorTorque;
    Modelica.SIunits.Torque hydraulicTorque;
    ThermoSysPro.Units.AngularVelocity_rpm speedRpm;

  equation
    speedRpm = nominalSpeedRpm*max(speedRatio, 0);
    hydraulicTorque = equivalentInertia*max(speedRatio, 0)/coastdownTime;
    motorTorque = if breakerClosed.signal then hydraulicTorque
      + equivalentInertia*(1 - speedRatio)/restartTime else 0;
    equivalentInertia*der(speedRatio) = motorTorque - hydraulicTorque;

    valveTarget = if speedRatio > valveCloseSpeedRatio then 1 else 0;
    der(checkValvePosition) = (valveTarget - checkValvePosition)/valveTimeConstant;
    massFlow.signal = nominalMassFlow*max(speedRatio, 0)
      *max(0, min(1, checkValvePosition));
  end BoundaryMotorPump;

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

  model BackpressureTurbineTrip
    "Condenser-pressure protection with latched turbine and generator trip"
    parameter Modelica.SIunits.AbsolutePressure nominalPressurePa=10000;
    parameter Real highRatio=1.10;
    parameter Real tripRatio=1.15;
    parameter Real tripDelay(unit="s")=2;
    parameter Real referenceTrackingTime(unit="s")=30;
    parameter Real timerResetTime(unit="s")=0.1;

    ThermoSysPro.InstrumentationAndControl.Connectors.InputReal
      condenserPressure;
    ThermoSysPro.InstrumentationAndControl.Connectors.InputLogical armed;
    ThermoSysPro.InstrumentationAndControl.Connectors.OutputLogical
      highAlarm;
    ThermoSysPro.InstrumentationAndControl.Connectors.OutputLogical
      tripPickup;
    ThermoSysPro.InstrumentationAndControl.Connectors.OutputLogical
      tripLatched;
    ThermoSysPro.InstrumentationAndControl.Connectors.OutputLogical
      generatorBreakerClosed;

    Modelica.SIunits.AbsolutePressure referencePressure(
      start=nominalPressurePa, fixed=true);
    Modelica.SIunits.AbsolutePressure highSetpoint;
    Modelica.SIunits.AbsolutePressure tripSetpoint;
    Real persistenceTimer(unit="s", start=0, fixed=true);
    discrete Boolean latched(start=false, fixed=true);

  equation
    assert(highRatio > 1 and tripRatio > highRatio and tripDelay > 0,
      "Backpressure trip requires 1 < highRatio < tripRatio and delay > 0");

    der(referencePressure) = if armed.signal then 0 else
      (max(condenserPressure.signal, 1000) - referencePressure)/
      referenceTrackingTime;
    highSetpoint = highRatio*referencePressure;
    tripSetpoint = tripRatio*referencePressure;
    highAlarm.signal = armed.signal and condenserPressure.signal >=
      highSetpoint;
    tripPickup.signal = armed.signal and condenserPressure.signal >=
      tripSetpoint;

    der(persistenceTimer) = if tripPickup.signal and not latched then 1
      else if not tripPickup.signal then -persistenceTimer/timerResetTime
      else 0;

    when persistenceTimer >= tripDelay then
      latched = true;
    end when;

    tripLatched.signal = latched;
    generatorBreakerClosed.signal = not latched;
  end BackpressureTurbineTrip;

end TripLens_PumpPhysics;
