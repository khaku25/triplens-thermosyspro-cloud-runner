# Current V8 Live SOT

This directory is the machine-readable runtime baseline for TripLens.

- Validation evidence: GitHub Actions #54 / run `35309650110`, plus a private local `RAW_SESSION_20260924_191347.csv` supplemental ST grid-power readback. The raw session is not published because it contains plant telemetry; only its hash and bounded `PARTIAL` scope are recorded in provenance.
- Registered OPC UA `vpp*` BrowseNames: 604
- Current Logic Master: 54 rules
- Unique registered logic inputs: 45
- Unique registered `vpp*` logic outputs: 29
- Writable current inputs: 66
- Valve/breaker persistence proof: 56/56

`live_tag_allowlist.csv` contains source identities observed in the running OpenModelica OPC UA server. The supplemental `vppSTGridPowerMW` identity is supported by the current RAW-session readback; its numeric NodeId and 52ST-open response remain pending a matching live census/trip capture.
`live_logic_runtime.csv` contains only Current Logic rows whose source inputs and `vpp*` outputs resolve against that live set.
TripLens-local derived alarm IDs are valid rule outputs but are not OPC UA source nodes.
