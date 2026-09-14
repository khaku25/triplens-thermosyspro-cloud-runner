# V8.5.3 RC1 validation boundary

This branch carries the locally proven V8.5.2 protection dashboard and Dual Log
implementation into GitHub Actions without changing the ThermoSysPro HP/IP
pump-speed wiring inherited from V7.

The acceptance job starts a fresh OpenModelica process, advances model time,
presses the real `vppLPFWPTripPushbuttonNative` input through OPC UA, and
requires all of the following before the candidate can be promoted:

- 66 generated, changeable Real command inputs;
- all 67 alarm sources bound in the running OPC UA address space;
- LP trip command, latch, VCB trip command, and breaker-open edges in RAW;
- decreasing LP BFP speed and feedwater flow;
- the seven operator/protection/alarm records in EVENT;
- no internal command or latch records leaked into EVENT;
- successful combined EVENT + RAW analysis;
- server-process and TCP 4841 cleanup after the scenario.

V8.5.3 RC1 is a short-run LP BFP validation candidate. It must not be labelled
as long-run stable: a separate local run previously reached model time
3789.626 s before a non-finite HP-bypass outlet pressure terminated the solver.
That long-duration issue is outside this LP BFP acceptance gate and remains
documented as an open limitation.
