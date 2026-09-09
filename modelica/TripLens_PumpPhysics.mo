within ;
package TripLens_PumpPhysics
  "Reusable motor-breaker dynamics used by the TripLens ThermoSysPro adapters"

  model BreakerTorqueDrive
    "Ideal regulated motor while closed; zero electromagnetic torque when open"
    parameter Real nominalSpeedRpm(unit="rev/min") = 1400;
    parameter Real proportionalGain = 250
      "Speed controller gain in N.m/(rev/min)";
    parameter Real integralGain = 25
      "Speed controller integral gain in N.m/(rev/min.s)";
    parameter Modelica.SIunits.Torque torqueLimit = 1e5;

    ThermoSysPro.InstrumentationAndControl.Connectors.InputLogical
      breakerClosed;
    ThermoSysPro.ElectroMechanics.Connectors.MechanichalTorque shaft;

    ThermoSysPro.Units.AngularVelocity_rpm speedRpm;
    Modelica.SIunits.Torque motorTorque;
    Real speedError(unit="rev/min");
    Real integralState(start=0, fixed=false);

  initial equation
    // Solve the integrator preload from the connected pump load. This keeps
    // the original steady-state operating point without prescribing a fake
    // residual RPM after a trip.
    der(integralState) = 0;

  equation
    speedRpm = 30/Modelica.Constants.pi*shaft.w;
    speedError = nominalSpeedRpm - speedRpm;
    der(integralState) = if breakerClosed.signal then speedError else 0;

    motorTorque = if breakerClosed.signal then noEvent(max(0, min(
      torqueLimit,
      proportionalGain*speedError + integralGain*integralState))) else 0;
    shaft.Ctr = motorTorque;
  end BreakerTorqueDrive;

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

end TripLens_PumpPhysics;
