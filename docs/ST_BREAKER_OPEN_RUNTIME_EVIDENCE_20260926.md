# ST Breaker Open Runtime Evidence · PlantControlV2 104046

## Scope

This note records the post-Run-#54 runtime proof for the independent 52ST manual-open protection cause.

- Build: `TripLens_PlantControlV2_20260926-104046`
- Patch: `TRIPLENS_ST_BREAKER_OPEN_TRIP_V1`
- Patched Modelica source SHA-256: `9392B702487A891046B4F9E7E0466198F72D5ED087125D2E0BE9958E52E8F07E`
- Derived evidence ledger: `data/current_v8/st_breaker_open_evidence_20260926.csv`
- Status: `RUNTIME_VERIFIED`

This proof is later than the frozen Run #54 OPC UA census. It does not invent historical NodeIds or retroactively change the Run #54 live count.

## Verified causal path

```text
manual 52ST OPEN
  -> vppSTBreakerOpenCauseState = 1
  -> vppCauseSTBreakerOpenWhileRunning = 1
  -> vppSTTripRequest = 1
  -> vppSTTripLatchPublished = 1
  -> vpp52STTripCmd = 1
  -> HP/IP/LP admission closes to seat-leak position
  -> HP/LP bypass opens
  -> HP/LP spray opens
  -> vppSTGridPowerMW = 0 MW
```

`PROT-ST-BRK-OPEN` is the initiating protection cause. `SEQ-52ST-OPEN` remains a separate post-trip breaker-opening sequence.

## Current ST Trip Request representation

The current master does not use a fixed cause count. It represents the registered upstream OR relationship:

```text
vppGTTripRequest
OR vppCauseDirectSTTrip
OR vppCauseSTBreakerOpenWhileRunning
OR vppCauseHPDrumHH
OR vppCauseIPDrumHH
OR vppCauseLPDrumHH
 -> vppSTTripRequest
```

## Current production master counts

| Scope | Tags | Rules | Input groups |
| --- | ---: | ---: | ---: |
| Frozen Run #54 live census | 603 | 53 | 35 |
| Current production searchable projection | 606 | 55 | 37 |

The current generated draw.io contains 102 pages and the Drawing Master index contains 1,609 cells/objects, 55 linked logic IDs, and 89 linked tag IDs.

## Evidence boundary

The CSV is a **derived runtime validation ledger**, not the original `RAW.csv`. Approximate model times are retained as approximate. The older `st_power_evidence_20260924.json` remains the closed-only 282-row provenance record; its limitations are not overwritten. A fresh OPC UA census is still required before the three later search-only tags are promoted into the frozen live-census identity set.
