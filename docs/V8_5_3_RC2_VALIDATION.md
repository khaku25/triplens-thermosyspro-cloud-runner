# V8.5.3 RC2 validation boundary

This candidate keeps the V7 ThermoSysPro plant topology and applies the
validated `BreakerInertialPumpDrive` boundary to HP, IP, and LP feedwater
pumps. A BFP trip must therefore remove motor torque, prove speed loss,
collapse feedwater flow, close the discharge check valve, and allow the
corresponding Drum LL cause to persist long enough for the GT+ST matrix trip.

The GitHub Action builds the model once and starts a fresh OPC UA server for
each of twelve scenarios. Every scenario is isolated, receives at least five
seconds of pre-fault RAW, and is cleaned up before the next one. The LP BFP
and all drum/matrix scenarios retain a 100-second post-fault window. HP/IP
BFP-only scenarios use a 45-second equipment-coastdown window; their separate
HP/IP Drum LL scenarios remain the 100-second matrix proof.

For the LP end-to-end BFP scenario, the acceptance gate requires:

- operator PB, breaker-open, motor-deenergized, running-lost, speed-lost,
  check-valve-closed, and feedwater-flow-low EVENT records;
- the corresponding physical speed, hydraulic-speed floor, flow, and
  check-valve trajectories in RAW;
- the corresponding Drum LL matrix cause and final GT/ST latch state;
- schema-safe `EVENT.csv` plus complete numeric `RAW.csv` output.

For HP/IP BFP-only scenarios, the gate stops at the equipment chain (operator
PB → breaker/motor → speed/flow loss → check-valve closure). HP/IP Drum LL
and GT/ST behavior is checked by their dedicated 100-second drum scenarios,
so a short HP/IP BFP run is not reported as a Drum LL proof.

The downloadable artifact also contains `LUNA_SUMMARY.csv/json`, so a later
review can start with the compact summary and open only failed scenarios.
RC2 is promoted only after the Action reports all twelve scenarios as PASS.
