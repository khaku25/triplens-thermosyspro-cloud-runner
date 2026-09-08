PRAGMA foreign_keys = ON;

CREATE TABLE schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE logic_rule (
    logic_id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    console_scope TEXT,
    console_csv TEXT,
    format_profile TEXT,
    system TEXT NOT NULL,
    subsystem TEXT,
    equipment TEXT,
    source_class TEXT NOT NULL,
    source_tag_ids TEXT,
    source_model_variables TEXT,
    derived_signal TEXT,
    alarm_type TEXT NOT NULL,
    alarm_text_ko TEXT NOT NULL,
    condition_expression TEXT NOT NULL,
    threshold_basis TEXT NOT NULL,
    threshold_value REAL,
    threshold_unit TEXT,
    threshold_direction TEXT,
    delay_s REAL NOT NULL,
    hysteresis_value REAL,
    hysteresis_unit TEXT,
    hysteresis_raw TEXT,
    priority_rank INTEGER,
    display_priority TEXT,
    display_color_ko TEXT,
    display_hex TEXT,
    latching INTEGER NOT NULL CHECK (latching IN (0,1)),
    ack_required INTEGER NOT NULL CHECK (ack_required IN (0,1)),
    shelvable INTEGER NOT NULL CHECK (shelvable IN (0,1)),
    trip_action TEXT,
    enabled_default INTEGER NOT NULL CHECK (enabled_default IN (0,1)),
    editable INTEGER NOT NULL CHECK (editable IN (0,1)),
    assumption_class TEXT,
    data_origin TEXT,
    validation_status TEXT,
    implementation_readiness TEXT,
    source_url TEXT,
    note_ko TEXT,
    source_platform TEXT,
    source_system TEXT,
    legacy_condition_expression TEXT,
    legacy_threshold_basis TEXT,
    legacy_threshold_value TEXT,
    legacy_threshold_unit TEXT,
    calibration_signal TEXT,
    calibration_nominal_value REAL,
    calibration_source_file TEXT,
    calibration_window_s TEXT,
    absolute_conversion_status TEXT NOT NULL,
    logic_enable_reason TEXT,
    CHECK (
        enabled_default = 0 OR
        threshold_basis NOT IN ('PRE_EVENT_BASELINE_RATIO','NORMALIZED_SPAN','ABSOLUTE_VALUE_PENDING')
    ),
    CHECK (
        enabled_default = 0 OR
        threshold_basis NOT LIKE 'ABSOLUTE_%' OR
        (threshold_value IS NOT NULL AND length(trim(coalesce(threshold_unit,''))) > 0)
    )
);

CREATE TABLE logic_source (
    logic_id TEXT NOT NULL REFERENCES logic_rule(logic_id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('TAG','MODEL_VARIABLE')),
    ordinal INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    PRIMARY KEY (logic_id, source_kind, ordinal)
);

CREATE TABLE tag_master (
    tag_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    platform TEXT NOT NULL,
    system TEXT,
    subsystem TEXT,
    equipment_id TEXT,
    equipment_type TEXT,
    signal_name TEXT,
    description_ko TEXT,
    io_type TEXT,
    data_type TEXT,
    unit TEXT,
    source_layer TEXT,
    tag_class TEXT,
    value_basis TEXT,
    limit_basis TEXT,
    model_mapping TEXT,
    canonical_signal TEXT,
    status TEXT NOT NULL,
    editable INTEGER NOT NULL CHECK (editable IN (0,1)),
    source_file TEXT NOT NULL,
    source_record_id TEXT,
    notes TEXT
);

CREATE TABLE tag_alias (
    alias TEXT NOT NULL,
    tag_id TEXT NOT NULL REFERENCES tag_master(tag_id) ON DELETE CASCADE,
    alias_type TEXT NOT NULL,
    canonical_signal TEXT,
    unit TEXT,
    status TEXT NOT NULL,
    source_file TEXT NOT NULL,
    PRIMARY KEY (alias, tag_id, alias_type)
);

CREATE TABLE logic_tag_link (
    logic_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_ordinal INTEGER NOT NULL,
    tag_id TEXT NOT NULL REFERENCES tag_master(tag_id),
    link_role TEXT NOT NULL,
    mapping_method TEXT NOT NULL,
    source_unit TEXT,
    target_unit TEXT,
    unit_transform TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (logic_id, source_kind, source_ordinal),
    FOREIGN KEY (logic_id, source_kind, source_ordinal)
        REFERENCES logic_source(logic_id, source_kind, ordinal) ON DELETE CASCADE
);

CREATE TABLE runtime_alarm_rule (
    rule_id TEXT PRIMARY KEY,
    system TEXT NOT NULL CHECK (system IN ('DCS1','DCS2')),
    source_signal TEXT NOT NULL,
    alarm_tag TEXT NOT NULL UNIQUE,
    description_ko TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LOW','HIGH')),
    threshold_mode TEXT NOT NULL CHECK (threshold_mode IN ('ABSOLUTE','BOOLEAN')),
    threshold_value REAL NOT NULL,
    hysteresis_value REAL NOT NULL CHECK (hysteresis_value >= 0),
    delay_s REAL NOT NULL CHECK (delay_s >= 0),
    severity TEXT NOT NULL,
    unit TEXT NOT NULL,
    status TEXT NOT NULL,
    calibration_basis TEXT
);

CREATE TABLE runtime_tag_link (
    rule_id TEXT NOT NULL REFERENCES runtime_alarm_rule(rule_id) ON DELETE CASCADE,
    link_role TEXT NOT NULL CHECK (link_role IN ('SOURCE_SIGNAL','ALARM_OUTPUT')),
    tag_id TEXT NOT NULL REFERENCES tag_master(tag_id),
    PRIMARY KEY (rule_id, link_role)
);

CREATE TABLE ecms_setting (
    setting_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    status TEXT NOT NULL,
    source_reference TEXT,
    notes TEXT
);

CREATE TABLE ecms_signal (
    signal_name TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('IN','OUT')),
    data_type TEXT NOT NULL,
    source_layer TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    bound_tag TEXT,
    notes TEXT,
    PRIMARY KEY (signal_name, direction)
);

CREATE TABLE drawing_reference (
    drawing_id TEXT PRIMARY KEY,
    drawing_type TEXT NOT NULL CHECK (drawing_type IN ('P&ID','SLD','LOGIC','OTHER')),
    title TEXT,
    revision TEXT,
    source_file TEXT,
    verification_status TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE logic_drawing_map (
    logic_id TEXT NOT NULL REFERENCES logic_rule(logic_id) ON DELETE CASCADE,
    drawing_id TEXT NOT NULL REFERENCES drawing_reference(drawing_id) ON DELETE CASCADE,
    drawing_tag_id TEXT,
    equipment_reference TEXT,
    mapping_confidence TEXT CHECK (mapping_confidence IN ('HIGH','MEDIUM','LOW','PENDING')),
    verification_status TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (logic_id, drawing_id, drawing_tag_id)
);

CREATE TABLE tag_drawing_map (
    tag_id TEXT NOT NULL REFERENCES tag_master(tag_id) ON DELETE CASCADE,
    drawing_id TEXT NOT NULL REFERENCES drawing_reference(drawing_id) ON DELETE CASCADE,
    drawing_tag_id TEXT,
    equipment_reference TEXT,
    mapping_confidence TEXT CHECK (mapping_confidence IN ('HIGH','MEDIUM','LOW','PENDING')),
    verification_status TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (tag_id, drawing_id, drawing_tag_id)
);

CREATE TABLE validation_result (
    check_id TEXT PRIMARY KEY,
    passed INTEGER NOT NULL CHECK (passed IN (0,1)),
    actual_value TEXT NOT NULL,
    expected_value TEXT NOT NULL,
    detail TEXT
);

CREATE INDEX idx_logic_platform_system ON logic_rule(platform, system, subsystem);
CREATE INDEX idx_logic_equipment ON logic_rule(equipment);
CREATE INDEX idx_logic_enabled ON logic_rule(enabled_default, threshold_basis);
CREATE INDEX idx_logic_signal ON logic_rule(derived_signal);
CREATE INDEX idx_logic_status ON logic_rule(absolute_conversion_status);
CREATE INDEX idx_source_name ON logic_source(source_name);
CREATE INDEX idx_tag_platform_system ON tag_master(platform, system, subsystem);
CREATE INDEX idx_tag_equipment ON tag_master(equipment_id);
CREATE INDEX idx_tag_canonical ON tag_master(canonical_signal);
CREATE INDEX idx_tag_model_mapping ON tag_master(model_mapping);
CREATE INDEX idx_tag_alias ON tag_alias(alias);
CREATE INDEX idx_logic_tag_id ON logic_tag_link(tag_id);
CREATE INDEX idx_runtime_source ON runtime_alarm_rule(source_signal);
CREATE INDEX idx_runtime_tag_id ON runtime_tag_link(tag_id);
CREATE INDEX idx_ecms_direction ON ecms_signal(direction);
CREATE INDEX idx_drawing_tag ON logic_drawing_map(drawing_tag_id);
CREATE INDEX idx_tag_drawing_tag ON tag_drawing_map(drawing_tag_id);

CREATE VIEW v_active_logic AS
SELECT * FROM logic_rule WHERE enabled_default = 1;

CREATE VIEW v_deferred_logic AS
SELECT * FROM logic_rule WHERE enabled_default = 0;

CREATE VIEW v_excluded_unlinked_analog AS
SELECT * FROM logic_rule
WHERE enabled_default = 0
  AND alarm_type IN ('H','HH','L','LL')
  AND absolute_conversion_status = 'UNLINKED_OPTIONAL_SIGNAL';

CREATE VIEW v_active_logic_tag_map AS
SELECT l.logic_id, l.platform AS logic_platform, l.system AS logic_system,
       l.subsystem AS logic_subsystem, l.equipment AS logic_equipment,
       l.alarm_type, l.alarm_text_ko,
       s.source_kind, s.ordinal AS source_ordinal, s.source_name,
       x.tag_id, x.link_role, x.mapping_method,
       x.source_unit, x.target_unit, x.unit_transform, x.verification_status,
       t.record_type, t.platform AS tag_platform, t.system AS tag_system,
       t.subsystem AS tag_subsystem, t.equipment_id, t.signal_name,
       t.description_ko AS tag_description_ko, t.unit, t.model_mapping,
       t.canonical_signal, t.status AS tag_status
FROM v_active_logic l
JOIN logic_source s ON s.logic_id = l.logic_id
JOIN logic_tag_link x
  ON x.logic_id = s.logic_id
 AND x.source_kind = s.source_kind
 AND x.source_ordinal = s.ordinal
JOIN tag_master t ON t.tag_id = x.tag_id;

CREATE VIEW v_active_analog_tag_map AS
SELECT * FROM v_active_logic_tag_map
WHERE alarm_type IN ('H','HH','L','LL');

CREATE VIEW v_unlinked_active_logic_source AS
SELECT l.logic_id, l.platform, l.system, l.alarm_type,
       s.source_kind, s.ordinal AS source_ordinal, s.source_name
FROM v_active_logic l
JOIN logic_source s ON s.logic_id = l.logic_id
LEFT JOIN logic_tag_link x
  ON x.logic_id = s.logic_id
 AND x.source_kind = s.source_kind
 AND x.source_ordinal = s.ordinal
WHERE x.logic_id IS NULL;

CREATE VIEW v_runtime_tag_map AS
SELECT r.rule_id, r.system, r.source_signal, r.alarm_tag,
       x.link_role, t.tag_id, t.record_type, t.platform,
       t.description_ko, t.unit, t.canonical_signal, t.status
FROM runtime_alarm_rule r
JOIN runtime_tag_link x ON x.rule_id = r.rule_id
JOIN tag_master t ON t.tag_id = x.tag_id;

CREATE VIEW v_absolute_thresholds AS
SELECT logic_id, platform, system, subsystem, equipment, derived_signal,
       alarm_type, alarm_text_ko, threshold_value, threshold_unit,
       threshold_direction, delay_s, hysteresis_value, hysteresis_unit,
       calibration_signal, calibration_nominal_value, calibration_source_file
FROM logic_rule
WHERE enabled_default = 1 AND threshold_basis LIKE 'ABSOLUTE_%';

CREATE VIEW v_ecms_ports AS
SELECT signal_name, direction, data_type, source_layer, role, status, bound_tag
FROM ecms_signal
ORDER BY CASE direction WHEN 'IN' THEN 0 ELSE 1 END, signal_name;

CREATE VIEW v_logic_pid_mapping AS
SELECT l.logic_id, l.platform, l.system, l.equipment, l.alarm_text_ko,
       m.drawing_id, d.drawing_type, d.revision, m.drawing_tag_id,
       m.equipment_reference, m.mapping_confidence, m.verification_status,
       x.tag_id, 'TAG_MASTER' AS mapping_route
FROM v_active_logic l
JOIN logic_tag_link x ON x.logic_id = l.logic_id AND x.source_kind = 'TAG'
JOIN tag_drawing_map m ON m.tag_id = x.tag_id
JOIN drawing_reference d ON d.drawing_id = m.drawing_id
UNION ALL
SELECT l.logic_id, l.platform, l.system, l.equipment, l.alarm_text_ko,
       m.drawing_id, d.drawing_type, d.revision, m.drawing_tag_id,
       m.equipment_reference, m.mapping_confidence, m.verification_status,
       NULL AS tag_id, 'DIRECT_OVERRIDE' AS mapping_route
FROM v_active_logic l
JOIN logic_drawing_map m ON m.logic_id = l.logic_id
JOIN drawing_reference d ON d.drawing_id = m.drawing_id;
