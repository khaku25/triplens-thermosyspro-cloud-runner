# TripLens Active Logic DB v2

SQLite is the canonical query layer for TripLens logic. Operational queries and validation
use **active logic only** by default. The full 903-row catalog remains available solely for
traceability and later restoration; it is not an implemented-logic count.

## Build

```bash
python3 logic_db/build_logic_db.py
```

Outputs:

- `outputs/triplens_logic_master_v2.sqlite`
- `outputs/logic_db_manifest.json`

## Query

```bash
python3 logic_db/query_logic_db.py outputs/triplens_logic_master_v2.sqlite --platform ECMS
python3 logic_db/query_logic_db.py outputs/triplens_logic_master_v2.sqlite --search "드럼" --limit 20
python3 logic_db/query_logic_db.py outputs/triplens_logic_master_v2.sqlite --scope disabled --limit 20
python3 logic_db/query_logic_db.py outputs/triplens_logic_master_v2.sqlite --scope all --limit 20
```

## Tables

- `logic_rule`: complete candidate catalog; default queries exclude disabled rows
- `v_active_logic`: operational and verification scope
- `v_excluded_unlinked_analog`: restorable H/HH/L/LL candidates with no bound model input
- `logic_source`: normalized tag and Modelica-variable links
- `runtime_alarm_rule`: 32 DCS runtime rules
- `ecms_setting`: ECMS thresholds/timing
- `ecms_signal`: Simulink input/output contract
- `drawing_reference`, `logic_drawing_map`: future P&ID/SLD cross-reference
- `validation_result`: build-time integrity checks

Enabled rules cannot use baseline ratios, normalized spans, or pending absolute values.
Unlinked H/HH/L/LL candidates stay stored with `enabled_default=0` and do not participate
in normal queries, P&ID mapping views, or active validation.
Values are virtual-model engineering settings and are not approved plant protection settings.
