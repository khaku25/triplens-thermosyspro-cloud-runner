# TripLens ProcessBus Contract v2

## Purpose

ProcessBus is a derived, reproducible working layer between immutable source CSV data and TripLens analysis/alarm generation. It is not a replacement for RAW data and it must never be labelled as RAW.

```text
source RAW CSV (immutable)
        |
        v
normalize_processbus.py
        |
        +-- canonical known signals
        +-- every additional finite numeric source signal
        v
processbus.csv
        |
        +-- incident/change extraction
        +-- configured DCS alarm rules
        +-- ECMS derivation
        v
TripLens
```

## Contract rules

1. `time_s` is the only universally required process source.
2. Known source aliases are mapped to stable canonical names from `config/signal_map.json`.
3. Canonical signals that are absent from a source remain blank; their absence does not prevent ProcessBus creation.
4. Every unmapped source column whose non-empty values are finite numeric values is preserved automatically as a dynamic ProcessBus signal.
5. Dynamic signal names use the deterministic `raw__...` namespace. The exact original source header is recorded in `signal-mapping-review.json`.
6. Non-numeric source columns are not silently converted into process values. They are listed in the mapping review as skipped non-numeric columns.
7. The source CSV is read-only. Duplicate OpenModelica event timestamps may be collapsed in ProcessBus using the final post-event state, while the original RAW file remains unchanged.
8. Accident type is not part of the core ProcessBus schema. A generic `event_marker` may be added when a reference event time is supplied.
9. `gt_trip_cmd` is a legacy compatibility field only. It is generated automatically only when the legacy `--trip-time` path is used or when explicitly requested.
10. Dynamic ProcessBus signals are automatically included in persistent-deviation analysis by `extract_incident_window.py`.

## Alarm policy

ProcessBus discovery and DCS alarm creation are intentionally separate.

A newly discovered numeric process signal is preserved and analyzed automatically, but it is **not automatically declared to be a real plant DCS alarm**. DCS alarms still require an explicit rule in `config/dcs_alarm_rules.csv`. This prevents TripLens from fabricating plant alarm tags or thresholds merely because a new process column appeared.

## Scenario independence

GT Trip, BFP Trip and future incidents use the same normalization engine. The historical `normalize_bfp_processbus.py` entry point is retained only as a compatibility adapter and delegates to `normalize_processbus.py`.

This allows a future raw CSV to add previously unseen process variables without changing the parser first. If the input CSV contains a new numeric column, ProcessBus retains it, records its exact source header, and makes it available to TripLens change detection.
