# Current V8 Live SOT

This directory separates the preserved live OPC UA census from later searchable/source-mapped runtime evidence.

- Preserved live census: GitHub Actions #54 / run `35309650110`
- Live OPC UA `vpp*` BrowseNames: **603**
- Live Logic Master rows: **53**
- Searchable master after the 2026-09-26 ST breaker-open update: **606 tags / 55 rules / 37 input groups / 102 drawing pages**
- Search-only/source-mapped additions: `vppSTGeneratorPowerMW`, `vppSTGridPowerMW`, and `vppCauseSTBreakerOpenWhileRunning`
- Verified local runtime build: `TripLens_PlantControlV2_20260926-104046`
- Verified manual 52ST OPEN path: `vppECMS52STClosedCommandNative=0` → `vppCauseSTBreakerOpenWhileRunning=1` → `vppSTTripRequest=1` → `vppSTTripLatchPublished=1` → 52ST trip, turbine admission closure, HP/LP bypass and spray opening, and ST grid output 0 MW
- Writable current inputs in the preserved live baseline: 66
- Valve/breaker persistence proof from the preserved baseline: 56/56

`live_tag_allowlist.csv`, `live_tag_master.csv`, and `live_logic_runtime.csv` remain the frozen Run #54 live-runtime baseline. Do not silently inflate them with later source-mapped observations.

`st_power_evidence_20260924.json` preserves the earlier closed-breaker ST power observation.  
`st_breaker_open_evidence_20260926.csv` records the later build-104046 breaker-open runtime proof used to promote the searchable ST breaker-open and grid-power behavior to `RUNTIME_VERIFIED`.

TripLens-local derived alarm IDs are valid rule outputs but are not OPC UA source nodes.
