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
- at least one additional second of advancing model time with finite LP physical
  values after the final required event;
- successful combined EVENT + RAW analysis;
- server-process and TCP 4841 cleanup after the scenario.

V8.5.3 RC1 is a short-run LP BFP validation candidate. It must not be labelled
as long-run stable: a separate local run previously reached model time
3789.626 s before a non-finite HP-bypass outlet pressure terminated the solver.
That long-duration issue is outside this LP BFP acceptance gate and remains
documented as an open limitation.

## Complete 100-second trip matrix

`verify-v8-all-trip-matrix.yml` builds V8 once and then starts a fresh
OpenModelica/OPC UA process for each of twelve isolated scenarios: nine GT/ST
protection causes plus the three independent HP/IP/LP BFP trips. Each incident
contains at least 5 seconds of pre-fault RAW and 100 seconds of post-fault RAW.
One failed scenario is recorded and cleaned up without preventing the remaining
scenarios from running. The downloadable artifact contains a separate
`EVENT.csv`, `RAW.csv`, and `SCENARIO_RESULT.json` for every scenario, plus
`LUNA_SUMMARY.csv` and `LUNA_SUMMARY.json` for low-token follow-up review.

Drum HH cases use the existing writable feedwater-open and steam-close fault
inputs and must produce an ST-only trip. Drum LL cases use feedwater-close and
steam-open inputs and must produce the model's GT+ST common trip. These are
physical input trajectories; the Modelica protection equations and drum states
are not overwritten by the workflow.

GitHub Actions run 34910093160 passed the first live acceptance execution. It
produced the seven expected EVENT records and a finite 620-column RAW historian;
speed fell from 1399.9166 to 723.7632 rpm and feedwater flow fell from 708.9525
to 16.3569 t/h. The run also showed a recoverable nonlinear-system warning near
model time 40.86 s and real-time deadline misses on the shared CI runner. These
are recorded as warnings, not evidence of long-run stability. The post-roll
gate above was added before promotion to ensure the server remains alive and
the selected physical outputs stay finite after the final required event.
