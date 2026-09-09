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
    parameter Modelica.SIunits.Torque initialTorque = 5000
      "Initial motor-torque guess used to preload the speed controller";
    parameter Modelica.SIunits.Torque torqueLimit = 1e5;

    ThermoSysPro.InstrumentationAndControl.Connectors.InputLogical
      breakerClosed;
    ThermoSysPro.ElectroMechanics.Connectors.MechanichalTorque shaft;

    ThermoSysPro.Units.AngularVelocity_rpm speedRpm;
    Modelica.SIunits.Torque motorTorque;
    Real speedError(unit="rev/min");
    Real integralState(start=initialTorque/integralGain, fixed=false);

  initial equation
    // Start from an estimated normal-load torque, then let the PI controller
    // settle during the pre-trip warm-up. No post-trip residual RPM is imposed.
    integralState = initialTorque/integralGain;

  equation
    speedRpm = 30/Modelica.Constants.pi*shaft.w;
    speedError = nominalSpeedRpm - speedRpm;
    der(integralState) = if breakerClosed.signal then speedError else 0;

    motorTorque = if breakerClosed.signal then noEvent(max(0, min(
      torqueLimit,
      proportionalGain*speedError + integralGain*integralState))) else 0;
    shaft.Ctr = motorTorque;
  end BreakerTorqueDrive;

  model SpringLoadedIdealCheckValve
    "Ideal non-return valve with a spring-equivalent minimum closing flow"
    parameter Modelica.SIunits.MassFlowRate closeFlow = 1
      "Forward flow below which the spring closes the valve";
    parameter Modelica.SIunits.MassFlowRate closedFlow = 0.1
      "Small positive numerical leakage while closed";
    parameter ThermoSysPro.Units.DifferentialPressure reopenPressure = 1e5
      "Upstream pressure needed to reopen a closed valve";

    Boolean ouvert(start=true, fixed=true) "Valve state";
    discrete Boolean tOpen(start=false, fixed=true);
    discrete Boolean tClose(start=false, fixed=true);
    Modelica.SIunits.MassFlowRate Q "Mass flow rate";
    ThermoSysPro.Units.DifferentialPressure deltaP
      "Pressure difference between inlet and outlet";
    ThermoSysPro.WaterSteam.Connectors.FluidInlet C1;
    ThermoSysPro.WaterSteam.Connectors.FluidOutlet C2;

  equation
    assert(closedFlow >= 0 and closedFlow < closeFlow,
      "SpringLoadedIdealCheckValve requires 0 <= closedFlow < closeFlow");

    C1.Q = C2.Q;
    C1.h = C2.h;
    Q = C1.Q;
    deltaP = C1.P - C2.P;

    // Preserve ThermoSysPro's directional enthalpy transport without adding
    // a second IF97 property state to the large plant initialization system.
    0 = if Q > 0 then C1.h - C1.h_vol else C2.h - C2.h_vol;

    if ouvert then
      deltaP = 0;
    else
      Q = closedFlow;
    end if;

    tClose = not (Q > closeFlow);
    tOpen = deltaP > reopenPressure;

    // Match ThermoSysPro IdealCheckValve's pre-trigger formulation so the
    // nonlinear hydraulic relation stays outside the when-equation.
    when {pre(tClose), pre(tOpen)} then
      ouvert = pre(tOpen);
    end when;
  end SpringLoadedIdealCheckValve;

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
