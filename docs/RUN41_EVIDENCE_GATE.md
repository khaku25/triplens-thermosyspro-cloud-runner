# Run #41 evidence gate

This document freezes what GitHub Actions **Run #41** (run id `34984251101`) actually proved and what it did not prove.

## Provenance

- Workflow: `Verify V8.5.3 all-trip matrix (100 s full, 45 s HP/IP BFP)`
- Artifact: `v8-all-trip-matrix-mixed-horizon-41`
- Overall result: **10 PASS / 2 FAIL**
- Failed scenarios: `hp_bfp`, `lp_bfp`
- The uploaded `RAW(2).csv` and `EVENT(3).csv` used for the current Tag Master were byte-identical to the Run #41 `direct_gt/RAW.csv` and `direct_gt/EVENT.csv` artifact files.

Do not describe Run #41 as an all-pass validation.

## RAW / OPC UA provenance

The Dual Log collector browses the OpenModelica OPC UA Objects tree and retains unique numeric BrowseNames matching required nodes or the `vpp*` namespace. Numeric values are read from OPC UA and written to RAW.

The Run #41 direct-GT RAW schema was:

- 6 collector metadata columns,
- 684 directly read numeric OPC UA historian nodes (`time` + 683 `vpp*` names),
- 10 deterministic readability aliases/derived fields.

The 10 readability fields are not native OPC UA BrowseNames. They must remain explicitly classified as CSV aliases/derived fields.

## Quality semantics

Historical Run #41 used:

`quality=GOOD`

That value was set by the collector and means **the RAW row was recorded successfully**. It is **not** an OPC UA per-node StatusCode.

The current contract uses:

`collector_quality`

Legacy `quality` is accepted only for backward compatibility.

## Clock semantics

Use `model_time_s` for:

- causal ordering,
- alarm/protection timing,
- trip/latch/breaker delay comparison,
- evidence windows.

Use `wall_time_utc` only for audit/transport traceability. GitHub runners can miss real-time deadlines, so wall-clock differences must not be interpreted as plant/model protection delays.

## Primary-cause timing gate

A cause cannot be promoted to initiating Primary Cause when its model time is later than the first Direct Trigger / Trip Request / Trip Latch.

Example from Run #41 direct GT:

- GT/ST trip latch: about 48.44 s
- IP Drum HH: about 131.925 s

IP Drum HH is therefore a secondary/post-trip cause, not the initiating cause of the GT trip.

## Validation classes

The canonical machine-readable status is in `config/run41_logic_validation.csv`.

- `RC_CONFIRMED`: Run #41 directly supports the logic behavior.
- `RC_BOUND_ONLY`: rule/source bound, but threshold/event was not triggered in Run #41.
- `RC_PARTIAL`: part of the chain was observed, but full downstream acceptance failed.
- `RC_NOT_CONFIRMED`: Run #41 explicitly failed to prove the required behavior.
- `SOURCE_DEFINED_NOT_RUN41`: source-defined but not exercised in Run #41.

Specific caveats:

- IP Drum Pressure LL: bound, not triggered.
- LP Drum Pressure L / LL: bound, not triggered.
- IP BFP trip: proven.
- LP BFP trip: electrical chain observed, downstream NRV/drum/common-trip path not proven before stall.
- HP BFP trip: not proven in Run #41.
- HP/IP/LP BFP reset paths: not exercised.

## Scenario Lab boundary

Scenario Lab may write real control/fault inputs, but these fields must never be passed to the analyzer:

- scenario id/name,
- fault preset,
- fault-injection label,
- expected/root cause,
- ground truth,
- answer label,
- TEST_AUDIT metadata.

Only the resulting EVENT + RAW evidence is admissible to the Hybrid Agent.

Current GitHub valve `FaultEnableNative` / `FaultValueNative` nodes are source-confirmed writable controls but are **not Run #41 live-proven**. They require a separate live write/echo/effect validation.
