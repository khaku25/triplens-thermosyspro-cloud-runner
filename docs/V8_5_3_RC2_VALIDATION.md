# V8.5.3 RC2 validation boundary

This candidate keeps the V7 ThermoSysPro plant topology and applies the
validated `BreakerInertialPumpDrive` boundary to HP, IP, and LP feedwater
pumps. A BFP trip must therefore remove motor torque, prove speed loss,
collapse feedwater flow, close the discharge check valve, and allow the
corresponding Drum LL cause to persist long enough for the GT+ST matrix trip.

The GitHub Action builds the model once and starts a fresh OPC UA server for
each of twelve scenarios. Every scenario is isolated, receives at least five
seconds of pre-fault RAW, and is allowed to run for 100 seconds after its
trigger. A failed scenario is recorded and cleaned up before the next one.

For each BFP scenario the acceptance gate requires:

- operator PB, breaker-open, motor-deenergized, running-lost, speed-lost,
  check-valve-closed, and feedwater-flow-low EVENT records;
- the corresponding physical speed, hydraulic-speed floor, flow, and
  check-valve trajectories in RAW;
- the corresponding Drum LL matrix cause and final GT/ST latch state;
- schema-safe `EVENT.csv` plus complete numeric `RAW.csv` output.

The downloadable artifact also contains `LUNA_SUMMARY.csv/json`, so a later
review can start with the compact summary and open only failed scenarios.
RC2 is promoted only after the Action reports all twelve scenarios as PASS.
