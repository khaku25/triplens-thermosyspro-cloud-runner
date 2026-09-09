within ;
package TripLens_VPPLogicBlocks
  "Reusable alarm and protection blocks for the TripLens VPP event runtime"

  block AnalogAlarm
    "Absolute threshold alarm with hysteresis and pickup-only delay"
    parameter Integer direction = 1 "1: high alarm, -1: low alarm";
    parameter Real setpoint;
    parameter Real hysteresis(min=0) = 0;
    parameter Real pickupDelay(unit="s", min=0) = 0;

    input Real u;
    output Boolean active;
    output Real pickupElapsed(unit="s");

  protected
    Modelica.Blocks.Logical.Hysteresis deadband(
      uLow=if direction > 0 then setpoint - hysteresis
        else -(setpoint + hysteresis),
      uHigh=if direction > 0 then setpoint else -setpoint,
      pre_y_start=false);
    Modelica.Blocks.Logical.Timer onDelay;

  equation
    assert(direction == 1 or direction == -1,
      "AnalogAlarm direction must be 1 (HIGH) or -1 (LOW)");
    assert(hysteresis >= 0 and pickupDelay >= 0,
      "AnalogAlarm hysteresis and pickup delay must be non-negative");
    deadband.u = direction*u;
    onDelay.u = deadband.y;
    pickupElapsed = onDelay.y;
    // Guarding with deadband.y is essential when pickupDelay=0 because the
    // Timer output is also zero while its input is false.
    active = deadband.y and onDelay.y >= pickupDelay;
  end AnalogAlarm;

  block BooleanAlarm
    "Boolean state alarm with pickup-only delay"
    parameter Boolean activeWhen = true;
    parameter Real pickupDelay(unit="s", min=0) = 0;

    input Boolean u;
    output Boolean active;
    output Real pickupElapsed(unit="s");

  protected
    Boolean asserted;
    Modelica.Blocks.Logical.Timer onDelay;

  equation
    assert(pickupDelay >= 0,
      "BooleanAlarm pickup delay must be non-negative");
    asserted = if activeWhen then u else not u;
    onDelay.u = asserted;
    pickupElapsed = onDelay.y;
    active = asserted and onDelay.y >= pickupDelay;
  end BooleanAlarm;

  block GTTripSequence
    "Latched GT Trip relay and breaker sequence"
    parameter Real receiveDelay(unit="s", min=0) = 0.020;
    parameter Real lockoutDelay(unit="s", min=0) = 0.035;
    parameter Real breakerDelay(unit="s", min=0) = 0.080;

    input Boolean request;
    output Boolean latched(start=false, fixed=true);
    output Boolean relayTripReceived;
    output Boolean relay86Operated;
    output Boolean breakerClosed;
    output Real elapsed(unit="s");

  protected
    discrete Real tripTime(unit="s", start=-1, fixed=true);

  initial equation
    latched = false;
    tripTime = -1;

  equation
    assert(receiveDelay >= 0 and lockoutDelay >= 0 and breakerDelay >= 0,
      "GT Trip sequence delays must be non-negative");
    when request then
      latched = true;
      tripTime = time;
    end when;
    elapsed = if latched then time - tripTime else 0;
    relayTripReceived = latched and elapsed >= receiveDelay;
    relay86Operated = latched and elapsed >= receiveDelay + lockoutDelay;
    breakerClosed = not (latched and elapsed >= receiveDelay +
      lockoutDelay + breakerDelay);
  end GTTripSequence;

  block STTripSequence
    "Latched ST Trip breaker sequence"
    parameter Real breakerDelay(unit="s", min=0) = 0.100;

    input Boolean request;
    output Boolean latched(start=false, fixed=true);
    output Boolean breakerClosed;
    output Real elapsed(unit="s");

  protected
    discrete Real tripTime(unit="s", start=-1, fixed=true);

  initial equation
    latched = false;
    tripTime = -1;

  equation
    assert(breakerDelay >= 0,
      "ST Trip breaker delay must be non-negative");
    when request then
      latched = true;
      tripTime = time;
    end when;
    elapsed = if latched then time - tripTime else 0;
    breakerClosed = not (latched and elapsed >= breakerDelay);
  end STTripSequence;

end TripLens_VPPLogicBlocks;
