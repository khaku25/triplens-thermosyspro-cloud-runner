# TripLens Active Logic DB v2

SQLite is the canonical query layer for TripLens logic and Tag Master data. Operational queries and validation
use **active logic only** by default. The full 903-row catalog remains available solely for
traceability and later restoration; it is not an implemented-logic count.

The database imports the Thermo VPP tag catalog, ECMS tag catalog, ProcessBus signal map,
DCS runtime alarm tags, and ECMS Simulink ports. Active A-L source tags and their declared
Modelica variables are joined with foreign keys. Similar-looking names are never fuzzy-matched.

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
python3 logic_db/query_logic_db.py outputs/triplens_logic_master_v2.sqlite --tag-id TSP.DRUM.HP.LEVEL
python3 logic_db/query_logic_db.py outputs/triplens_logic_master_v2.sqlite --scope disabled --limit 20
python3 logic_db/query_logic_db.py outputs/triplens_logic_master_v2.sqlite --scope all --limit 20
```

## Tables

- `logic_rule`: complete candidate catalog; default queries exclude disabled rows
- `v_active_logic`: operational and verification scope
- `v_excluded_unlinked_analog`: restorable H/HH/L/LL candidates with no bound model input
- `logic_source`: normalized tag and Modelica-variable links
- `tag_master`: unified Thermo, ECMS, ProcessBus, DCS-alarm, and Simulink-port tags
- `tag_alias`: exact raw aliases, canonical ProcessBus names, and declared Modelica variables
- `logic_tag_link`: active Logic DB source to Tag Master foreign-key mapping
- `runtime_tag_link`: runtime rule source/output to Tag Master foreign-key mapping
- `v_active_logic_tag_map`, `v_active_analog_tag_map`: active mapping views
- `v_unlinked_active_logic_source`: must remain empty
- `runtime_alarm_rule`: 32 DCS runtime rules
- `ecms_setting`: ECMS thresholds/timing
- `ecms_signal`: Simulink input/output contract
- `drawing_reference`, `tag_drawing_map`: primary future P&ID/SLD cross-reference
- `logic_drawing_map`: exceptional direct override only
- `validation_result`: build-time integrity checks

Enabled rules cannot use baseline ratios, normalized spans, or pending absolute values.
Unlinked H/HH/L/LL candidates stay stored with `enabled_default=0` and do not participate
in normal queries, P&ID mapping views, or active validation.
P&ID mapping follows `active logic -> Tag Master -> drawing tag`; it does not attach a
drawing directly to an alarm unless an explicit override is required.
Values are virtual-model engineering settings and are not approved plant protection settings.
