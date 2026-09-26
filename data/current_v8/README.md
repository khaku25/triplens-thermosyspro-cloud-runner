# Current V8 Live / Searchable SOT

This directory separates the frozen live census from later source/runtime-verified search evidence.

## Frozen live census

- Validation evidence: GitHub Actions #54 / run `35309650110`.
- Live OPC UA `vpp*` BrowseNames in the frozen census: **603**.
- Live Logic Master rows: **53**.
- Live input groups: **35**.
- Writable current inputs: **66**.
- Valve/breaker persistence proof: **56/56**.

`live_tag_allowlist.csv`, `live_tag_master.csv`, and `live_logic_runtime.csv` are the Run #54 live-census runtime package. They are not silently expanded with later source observations.

## Current production searchable projection

The generated web Logic/Tag/Drawing projection additionally includes later source/runtime evidence:

- Searchable tags: **606**.
- Searchable rules: **55**.
- Searchable input groups: **37**.
- Searchable native inputs: **47**.
- Searchable native outputs: **30**.
- draw.io pages: **102**.
- Drawing Master indexed cells/objects: **1,609**.
- Linked logic IDs: **55**.
- Linked tag IDs: **89**.

The three search-only/source-observed tags are:

1. `vppSTGeneratorPowerMW`
2. `vppSTGridPowerMW`
3. `vppCauseSTBreakerOpenWhileRunning`

These entries are searchable evidence but are **not retroactively promoted into the frozen Run #54 census** until a matching fresh OPC UA census captures their NodeId/VariantType identity.

## 52ST breaker-open runtime proof

PlantControlV2 build `TripLens_PlantControlV2_20260926-104046` with patch
`TRIPLENS_ST_BREAKER_OPEN_TRIP_V1` was runtime-verified for:

`manual 52ST OPEN -> ST breaker-open cause -> ST Trip Request -> ST Trip Latch -> 52ST Trip -> HP/LP Bypass OPEN -> HP/IP/LP Admission CLOSE -> ST grid output 0 MW`.

The derived validation ledger is `st_breaker_open_evidence_20260926.csv`. The older
`st_power_evidence_20260924.json` remains preserved as a separate closed-only provenance record.

TripLens-local derived alarm IDs are valid rule outputs but are not OPC UA source nodes.
