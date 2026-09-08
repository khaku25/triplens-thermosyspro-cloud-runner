# TripLens Logic DB v2

SQLite is the canonical query layer for the 903-row absolute engineering-unit logic master.
The source CSV files remain reviewable deployment inputs.

## Build

```bash
python3 logic_db/build_logic_db.py
```

Outputs:

- `outputs/triplens_logic_master_v2.sqlite`
- `outputs/logic_db_manifest.json`

## Query

```bash
python3 logic_db/query_logic_db.py outputs/triplens_logic_master_v2.sqlite --platform ECMS --enabled true
python3 logic_db/query_logic_db.py outputs/triplens_logic_master_v2.sqlite --search "드럼" --limit 20
```

## Tables

- `logic_rule`: 903 master logic records
- `logic_source`: normalized tag and Modelica-variable links
- `runtime_alarm_rule`: 32 DCS runtime rules
- `ecms_setting`: ECMS thresholds/timing
- `ecms_signal`: Simulink input/output contract
- `drawing_reference`, `logic_drawing_map`: future P&ID/SLD cross-reference
- `validation_result`: build-time integrity checks

Enabled rules cannot use baseline ratios, normalized spans, or pending absolute values.
Values are virtual-model engineering settings and are not approved plant protection settings.
