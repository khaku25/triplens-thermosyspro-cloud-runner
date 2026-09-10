#!/usr/bin/env python3
"""Build and validate the TripLens SQLite logic master."""

from __future__ import annotations
import argparse, csv, hashlib, json, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path

ABSOLUTE_BASES = {"ABSOLUTE_MODEL_VALUE", "ABSOLUTE_MODEL_LEVEL", "ABSOLUTE_LIMIT"}

def rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def number(value, *, nullable=True):
    text = str(value or "").strip()
    if not text:
        if nullable: return None
        raise ValueError("Required numeric value is empty")
    return float(text)

def integer(value):
    return int(float(str(value).strip()))

def boolean(value):
    text = str(value).strip().upper()
    if text in {"TRUE", "Y", "YES", "1"}: return 1
    if text in {"FALSE", "N", "NO", "0"}: return 0
    raise ValueError(f"Invalid boolean: {value!r}")

def hysteresis(raw):
    text = str(raw or "").strip()
    m = re.match(r"^([-+]?[0-9]*\.?[0-9]+)\s*(.*)$", text)
    if not m: return None, None
    return float(m.group(1)), m.group(2).strip() or None

def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

TAG_COLUMNS = [
    "tag_id", "record_type", "platform", "system", "subsystem",
    "equipment_id", "equipment_type", "signal_name", "description_ko",
    "io_type", "data_type", "unit", "source_layer", "tag_class",
    "value_basis", "limit_basis", "model_mapping", "canonical_signal",
    "status", "editable", "source_file", "source_record_id", "notes",
]

def insert_tag(db, record):
    """Insert a canonical tag without overwriting a stronger existing source."""
    sql = f"""INSERT INTO tag_master ({','.join(TAG_COLUMNS)})
              VALUES ({','.join('?' for _ in TAG_COLUMNS)})
              ON CONFLICT(tag_id) DO NOTHING"""
    db.execute(sql, [record.get(c, "") for c in TAG_COLUMNS])
    db.execute("""INSERT OR IGNORE INTO tag_alias
                  (alias,tag_id,alias_type,canonical_signal,unit,status,source_file)
                  VALUES (?,?,?,?,?,?,?)""", (
        record["tag_id"], record["tag_id"], "TAG_ID",
        record.get("canonical_signal", ""), record.get("unit", ""),
        "EXACT", record.get("source_file", "")))

def insert_alias(db, alias, tag_id, alias_type, canonical_signal, unit, status, source_file):
    alias = str(alias or "").strip()
    if not alias:
        return
    db.execute("""INSERT OR IGNORE INTO tag_alias
                  (alias,tag_id,alias_type,canonical_signal,unit,status,source_file)
                  VALUES (?,?,?,?,?,?,?)""",
               (alias, tag_id, alias_type, canonical_signal, unit, status, source_file))

def split_refs(value):
    return [x.strip() for x in str(value or "").split(";") if x.strip()]

def signal_system(signal):
    prefix = str(signal or "").split("_", 1)[0].lower()
    return {
        "gt": "GT", "stg": "ST", "hp": "HRSG", "ip": "HRSG",
        "lp": "HRSG", "bfp": "BOP", "time": "SYS",
    }.get(prefix, "SYS")

def resolved_canonical_signal(rule):
    signal = str(rule.get("derived_signal", "")).strip()
    if "_" in signal and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", signal):
        return signal
    return ""

def add_validation(db, check_id, passed, actual, expected, detail):
    db.execute("INSERT INTO validation_result VALUES (?,?,?,?,?)",
               (check_id, int(bool(passed)), str(actual), str(expected), detail))
    if not passed:
        raise ValueError(f"{check_id} failed: actual={actual}, expected={expected}")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--schema", type=Path)
    p.add_argument("--logic", type=Path)
    p.add_argument("--dcs", type=Path)
    p.add_argument("--thermo-tags", type=Path)
    p.add_argument("--ecms-tags", type=Path)
    p.add_argument("--signal-map", type=Path)
    p.add_argument("--ecms-settings", type=Path)
    p.add_argument("--ecms-interface", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--source-commit", default="")
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    a.schema=a.schema or root/"logic_db/schema.sql"
    a.logic=a.logic or root/"data/triplens_A-L_alarm_logic_master_absolute_v2.csv"
    a.dcs=a.dcs or root/"config/dcs_alarm_rules.csv"
    a.thermo_tags=a.thermo_tags or root/"data/thermo_vpp_full_tag_list.csv"
    a.ecms_tags=a.ecms_tags or root/"data/ecms_tag_catalog.csv"
    a.signal_map=a.signal_map or root/"config/signal_map.json"
    a.ecms_settings=a.ecms_settings or root/"logic_db/sources/a_logic_settings_v1.csv"
    a.ecms_interface=a.ecms_interface or root/"logic_db/sources/a_logic_interface_v1.csv"
    a.output=a.output or root/"outputs/triplens_logic_master_v2.sqlite"
    a.manifest=a.manifest or root/"outputs/logic_db_manifest.json"
    inputs=[a.schema,a.logic,a.dcs,a.thermo_tags,a.ecms_tags,a.signal_map,
            a.ecms_settings,a.ecms_interface]
    for item in inputs:
        if not item.is_file(): raise FileNotFoundError(item)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.manifest.parent.mkdir(parents=True,exist_ok=True)
    if a.output.exists(): a.output.unlink()

    logic_rows, dcs_rows = rows(a.logic), rows(a.dcs)
    thermo_tag_rows, ecms_tag_rows = rows(a.thermo_tags), rows(a.ecms_tags)
    signal_map = json.loads(a.signal_map.read_text(encoding="utf-8-sig"))
    signal_rows = signal_map.get("signals", {})
    setting_rows, interface_rows = rows(a.ecms_settings), rows(a.ecms_interface)
    db=sqlite3.connect(a.output)
    try:
        db.executescript(a.schema.read_text(encoding="utf-8"))
        meta={
            "schema_version":"2.1",
            "dataset":"TripLens Absolute Logic Master",
            "generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "source_commit":a.source_commit,
            "plant_use":"NOT APPROVED FOR REAL PLANT PROTECTION",
            "unit_policy":"Enabled numeric logic uses absolute engineering units",
            "reporting_scope":"ACTIVE_LOGIC_ONLY",
        }
        meta.update({f"sha256:{x.name}":digest(x) for x in inputs[1:]})
        db.executemany("INSERT INTO schema_metadata(key,value) VALUES (?,?)",meta.items())

        cols=[
          "logic_id","platform","console_scope","console_csv","format_profile","system",
          "subsystem","equipment","source_class","source_tag_ids","source_model_variables",
          "derived_signal","alarm_type","alarm_text_ko","condition_expression",
          "threshold_basis","threshold_value","threshold_unit","threshold_direction",
          "delay_s","hysteresis_value","hysteresis_unit","hysteresis_raw","priority_rank",
          "display_priority","display_color_ko","display_hex","latching","ack_required",
          "shelvable","trip_action","enabled_default","editable","assumption_class",
          "data_origin","validation_status","implementation_readiness","source_url",
          "note_ko","source_platform","source_system","legacy_condition_expression",
          "legacy_threshold_basis","legacy_threshold_value","legacy_threshold_unit",
          "calibration_signal","calibration_nominal_value","calibration_source_file",
          "calibration_window_s","absolute_conversion_status","logic_enable_reason"
        ]
        sql=f"INSERT INTO logic_rule ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
        for r in logic_rows:
            hv,hu=hysteresis(r["hysteresis"])
            record=dict(r)
            record.update({
                "threshold_value":number(r["threshold_value"]),
                "delay_s":number(r["delay_s"],nullable=False),
                "hysteresis_value":hv,"hysteresis_unit":hu,"hysteresis_raw":r["hysteresis"],
                "priority_rank":integer(r["priority_rank"]),
                "latching":boolean(r["latching"]),"ack_required":boolean(r["ack_required"]),
                "shelvable":boolean(r["shelvable"]),
                "enabled_default":boolean(r["enabled_default"]),"editable":boolean(r["editable"]),
                "calibration_nominal_value":number(r["calibration_nominal_value"]),
            })
            db.execute(sql,[record.get(c) for c in cols])
            for kind,field in (("TAG","source_tag_ids"),("MODEL_VARIABLE","source_model_variables")):
                for n,value in enumerate((x.strip() for x in r[field].split(";") if x.strip()),1):
                    db.execute("INSERT INTO logic_source VALUES (?,?,?,?)",
                               (r["logic_id"],kind,n,value))

        for r in thermo_tag_rows:
            insert_tag(db, {
                "tag_id": r["tag_id"], "record_type": "THERMO_TAG",
                "platform": r["platform"], "system": r["system"],
                "subsystem": r["subsystem"], "equipment_id": r["equipment_id"],
                "equipment_type": r["equipment_type"], "signal_name": r["signal_name"],
                "description_ko": r["description_ko"], "io_type": r["io_type"],
                "data_type": r["data_type"], "unit": r["unit"],
                "source_layer": r["tag_class"], "tag_class": r["tag_class"],
                "value_basis": r["value_basis"], "limit_basis": r["limit_basis"],
                "model_mapping": r["model_mapping"], "canonical_signal": "",
                "status": "CATALOGUED", "editable": boolean(r["editable"]),
                "source_file": "data/thermo_vpp_full_tag_list.csv",
                "source_record_id": r["tag_id"], "notes": r["notes"],
            })
            insert_alias(db, r["model_mapping"], r["tag_id"], "MODEL_MAPPING", "",
                         r["unit"], "DECLARED", "data/thermo_vpp_full_tag_list.csv")

        for r in ecms_tag_rows:
            tag_id = r["ecms_tag_id"]
            insert_tag(db, {
                "tag_id": tag_id, "record_type": "ECMS_TAG", "platform": "ECMS",
                "system": tag_id.split(".")[1] if "." in tag_id else "ECMS",
                "subsystem": "", "equipment_id": r["equipment_id"],
                "equipment_type": "", "signal_name": tag_id.rsplit(".",1)[-1],
                "description_ko": r["description_ko"], "io_type": "",
                "data_type": r["data_type"], "unit": r["unit"],
                "source_layer": r["layer"], "tag_class": r["layer"],
                "value_basis": r["layer"], "limit_basis": "",
                "model_mapping": r["source_or_basis"], "canonical_signal": "",
                "status": r["status"], "editable": boolean(r["editable"]),
                "source_file": "data/ecms_tag_catalog.csv",
                "source_record_id": tag_id, "notes": r["value_rule"],
            })

        for canonical, spec in signal_rows.items():
            tag_id = f"PB.{canonical}"
            unit = str(spec.get("unit", ""))
            insert_tag(db, {
                "tag_id": tag_id, "record_type": "PROCESSBUS_SIGNAL",
                "platform": "ProcessBus", "system": signal_system(canonical),
                "subsystem": "CANONICAL", "equipment_id": "",
                "equipment_type": "ProcessBus Signal", "signal_name": canonical,
                "description_ko": canonical, "io_type": "AI",
                "data_type": "BOOL" if canonical.endswith("_cmd") else "REAL",
                "unit": unit, "source_layer": "PROCESS_BUS", "tag_class": "T",
                "value_basis": "T", "limit_basis": "A", "model_mapping": " | ".join(spec.get("aliases", [])),
                "canonical_signal": canonical,
                "status": "REQUIRED" if spec.get("required") else "OPTIONAL_PASSTHROUGH",
                "editable": 0, "source_file": "config/signal_map.json",
                "source_record_id": canonical, "notes": "Canonical ProcessBus signal",
            })
            insert_alias(db, canonical, tag_id, "CANONICAL_SIGNAL", canonical, unit,
                         "CANONICAL", "config/signal_map.json")
            for alias in spec.get("aliases", []):
                insert_alias(db, alias, tag_id, "RAW_ALIAS", canonical, unit,
                             "DECLARED", "config/signal_map.json")

        for r in dcs_rows:
            db.execute("INSERT INTO runtime_alarm_rule VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                r["rule_id"],r["system"],r["source_signal"],r["alarm_tag"],
                r["description_ko"],r["direction"],r["threshold_mode"],
                number(r["threshold_value"],nullable=False),
                number(r["hysteresis_value"],nullable=False),
                number(r["delay_s"],nullable=False),r["severity"],r["unit"],
                r["status"],r["calibration_basis"]))
            insert_tag(db, {
                "tag_id": r["alarm_tag"], "record_type": "DCS_ALARM",
                "platform": r["system"], "system": r["system"],
                "subsystem": "ALARM", "equipment_id": "",
                "equipment_type": "Alarm Rule", "signal_name": r["alarm_tag"].rsplit(".",1)[-1],
                "description_ko": r["description_ko"], "io_type": "DI",
                "data_type": "BOOL", "unit": "BOOL", "source_layer": "LOGIC",
                "tag_class": "A", "value_basis": "A", "limit_basis": "A",
                "model_mapping": r["source_signal"], "canonical_signal": r["source_signal"],
                "status": r["status"], "editable": 1,
                "source_file": "config/dcs_alarm_rules.csv",
                "source_record_id": r["rule_id"], "notes": r["calibration_basis"],
            })

        for r in setting_rows:
            db.execute("INSERT INTO ecms_setting VALUES (?,?,?,?,?,?,?)",(
                r["setting_id"],r["category"],number(r["value"],nullable=False),
                r["unit"],r["status"],r["source_reference"],r["notes"]))
        for r in interface_rows:
            db.execute("INSERT INTO ecms_signal VALUES (?,?,?,?,?,?,?,?)",(
                r["signal_name"],r["direction"],r["data_type"],r["source_layer"],
                r["role"],r["status"],r["bound_tag"],r["notes"]))
            tag_id = f"ECMS.SIMULINK.{r['direction']}.{r['signal_name']}"
            insert_tag(db, {
                "tag_id": tag_id, "record_type": "ECMS_INTERFACE",
                "platform": "ECMS", "system": "ECMS", "subsystem": "SIMULINK_INTERFACE",
                "equipment_id": "", "equipment_type": "Simulink Port",
                "signal_name": r["signal_name"], "description_ko": r["role"],
                "io_type": r["direction"], "data_type": r["data_type"], "unit": "",
                "source_layer": r["source_layer"], "tag_class": "A",
                "value_basis": r["source_layer"], "limit_basis": "A",
                "model_mapping": r["bound_tag"], "canonical_signal": r["signal_name"],
                "status": r["status"], "editable": 0,
                "source_file": "logic_db/sources/a_logic_interface_v1.csv",
                "source_record_id": f"{r['signal_name']}:{r['direction']}", "notes": r["notes"],
            })

        # The A-L master explicitly declares each active physical tag and its paired
        # Modelica variable. Those declared pairs are the authoritative join; no fuzzy
        # name matching is used.
        for r in logic_rows:
            if not boolean(r["enabled_default"]):
                continue
            tag_refs = split_refs(r["source_tag_ids"])
            model_refs = split_refs(r["source_model_variables"])
            canonical_signal = resolved_canonical_signal(r)
            conversion = r["absolute_conversion_status"]
            if conversion == "CALIBRATED_MODEL_LEVEL_MM":
                model_source_unit, unit_transform = "m", "x*1000"
            elif conversion == "CALIBRATED_MODEL_MASS_FLOW_T_H":
                # ThermoSysPro's connector balance remains SI internally;
                # Tag Master and every deployed logic threshold use t/h.
                model_source_unit, unit_transform = "kg/s", "x*3.6"
            else:
                model_source_unit, unit_transform = r["threshold_unit"], "IDENTITY"
            if len(tag_refs) != len(model_refs):
                raise ValueError(f"{r['logic_id']} source tag/model reference count mismatch")
            for ordinal, (tag_id, model_ref) in enumerate(zip(tag_refs, model_refs), 1):
                insert_tag(db, {
                    "tag_id": tag_id, "record_type": "ACTIVE_LOGIC_SOURCE",
                    "platform": "Thermo VPP", "system": r["system"],
                    "subsystem": r["subsystem"], "equipment_id": r["equipment"],
                    "equipment_type": "Model Signal", "signal_name": tag_id.rsplit(".",1)[-1],
                    "description_ko": f"{r['equipment']} 모델 입력",
                    "io_type": "AI", "data_type": "REAL", "unit": r["threshold_unit"],
                    "source_layer": "MODEL", "tag_class": "M", "value_basis": "M",
                    "limit_basis": "A", "model_mapping": model_ref,
                    "canonical_signal": canonical_signal,
                    "status": "ACTIVE_MODEL_BACKED", "editable": 0,
                    "source_file": "data/triplens_A-L_alarm_logic_master_absolute_v2.csv",
                    "source_record_id": r["logic_id"],
                    "notes": "Active A-L source pair; not a plant-approved field tag",
                })
                # Active calibrated logic is newer and more specific than provisional
                # catalog units/mappings, so it becomes the resolved Tag Master record.
                db.execute("""UPDATE tag_master
                              SET unit=?, model_mapping=?, canonical_signal=?,
                                  status='ACTIVE_MODEL_BACKED', editable=0,
                                  source_file='data/triplens_A-L_alarm_logic_master_absolute_v2.csv',
                                  source_record_id=?, notes=?
                              WHERE tag_id=?""", (
                    r["threshold_unit"], model_ref, canonical_signal, r["logic_id"],
                    f"Active A-L source; model input uses {unit_transform} into {r['threshold_unit']}",
                    tag_id))
                db.execute("""UPDATE tag_alias
                              SET canonical_signal=?, unit=?, status='ACTIVE_RESOLVED',
                                  source_file='data/triplens_A-L_alarm_logic_master_absolute_v2.csv'
                              WHERE tag_id=? AND alias_type='TAG_ID'""",
                           (canonical_signal, r["threshold_unit"], tag_id))
                insert_alias(db, model_ref, tag_id, "MODEL_VARIABLE",
                             canonical_signal, model_source_unit,
                             "ACTIVE_DECLARED_PAIR",
                             "data/triplens_A-L_alarm_logic_master_absolute_v2.csv")
                if r["calibration_signal"]:
                    insert_alias(db, r["calibration_signal"], tag_id, "CALIBRATION_SIGNAL",
                                 canonical_signal, model_source_unit,
                                 "ACTIVE_DECLARED_PAIR",
                                 "data/triplens_A-L_alarm_logic_master_absolute_v2.csv")
                db.execute("INSERT INTO logic_tag_link VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                    r["logic_id"], "TAG", ordinal, tag_id, "SOURCE_INPUT",
                    "EXACT_DECLARED_TAG_ID", r["threshold_unit"], r["threshold_unit"],
                    "IDENTITY", "MODEL_BACKED_NOT_PLANT_VERIFIED", ""))
                db.execute("INSERT INTO logic_tag_link VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                    r["logic_id"], "MODEL_VARIABLE", ordinal, tag_id, "SOURCE_INPUT",
                    "AL_MASTER_DECLARED_PAIR", model_source_unit, r["threshold_unit"],
                    unit_transform, "MODEL_BACKED_NOT_PLANT_VERIFIED", ""))

        for r in dcs_rows:
            source_tag = f"PB.{r['source_signal']}"
            if db.execute("SELECT 1 FROM tag_master WHERE tag_id=?", (source_tag,)).fetchone() is None:
                # Commands are intentionally outside the physical ProcessBus contract.
                source_tag = f"ACTION.{r['source_signal']}"
                insert_tag(db, {
                    "tag_id": source_tag, "record_type": "COMMAND_SIGNAL",
                    "platform": "ACTION", "system": r["system"], "subsystem": "COMMAND",
                    "equipment_id": "", "equipment_type": "Operator/Scenario Command",
                    "signal_name": r["source_signal"], "description_ko": r["description_ko"],
                    "io_type": "DI", "data_type": "BOOL", "unit": r["unit"],
                    "source_layer": "ACTION", "tag_class": "A", "value_basis": "A",
                    "limit_basis": "A", "model_mapping": r["source_signal"],
                    "canonical_signal": r["source_signal"], "status": "COMMAND_INPUT",
                    "editable": 1, "source_file": "config/dcs_alarm_rules.csv",
                    "source_record_id": r["rule_id"],
                    "notes": "Command path; intentionally not a physical ProcessBus measurement",
                })
                insert_alias(db, r["source_signal"], source_tag, "COMMAND_SIGNAL",
                             r["source_signal"], r["unit"], "COMMAND_INPUT",
                             "config/dcs_alarm_rules.csv")
            db.execute("INSERT INTO runtime_tag_link VALUES (?,?,?)",
                       (r["rule_id"], "SOURCE_SIGNAL", source_tag))
            db.execute("INSERT INTO runtime_tag_link VALUES (?,?,?)",
                       (r["rule_id"], "ALARM_OUTPUT", r["alarm_tag"]))

        total=db.execute("SELECT count(*) FROM logic_rule").fetchone()[0]
        active=db.execute("SELECT count(*) FROM logic_rule WHERE enabled_default=1").fetchone()[0]
        excluded_unlinked_analog=db.execute("""SELECT count(*) FROM logic_rule
            WHERE enabled_default=0
              AND alarm_type IN ('H','HH','L','LL')
              AND absolute_conversion_status='UNLINKED_OPTIONAL_SIGNAL'""").fetchone()[0]
        active_unlinked_analog=db.execute("""SELECT count(*) FROM logic_rule
            WHERE enabled_default=1
              AND alarm_type IN ('H','HH','L','LL')
              AND absolute_conversion_status='UNLINKED_OPTIONAL_SIGNAL'""").fetchone()[0]
        legacy=db.execute("""SELECT count(*) FROM logic_rule WHERE enabled_default=1 AND
            (threshold_basis IN ('PRE_EVENT_BASELINE_RATIO','NORMALIZED_SPAN','ABSOLUTE_VALUE_PENDING')
             OR lower(coalesce(hysteresis_raw,'')) LIKE '%ratio%')""").fetchone()[0]
        invalid_abs=db.execute("""SELECT count(*) FROM logic_rule WHERE enabled_default=1
            AND threshold_basis LIKE 'ABSOLUTE_%'
            AND (threshold_value IS NULL OR trim(coalesce(threshold_unit,''))='')""").fetchone()[0]
        active_source_refs=db.execute("""SELECT count(*) FROM logic_source s
            JOIN logic_rule l ON l.logic_id=s.logic_id WHERE l.enabled_default=1""").fetchone()[0]
        linked_active_source_refs=db.execute("SELECT count(*) FROM logic_tag_link").fetchone()[0]
        unlinked_active_source_refs=db.execute("SELECT count(*) FROM v_unlinked_active_logic_source").fetchone()[0]
        active_analog=db.execute("""SELECT count(*) FROM logic_rule
            WHERE enabled_default=1 AND alarm_type IN ('H','HH','L','LL')""").fetchone()[0]
        linked_active_analog=db.execute("""SELECT count(DISTINCT l.logic_id)
            FROM logic_rule l JOIN logic_tag_link x ON x.logic_id=l.logic_id
            WHERE l.enabled_default=1 AND l.alarm_type IN ('H','HH','L','LL')
              AND x.source_kind='TAG'""").fetchone()[0]
        runtime_tag_links=db.execute("SELECT count(*) FROM runtime_tag_link").fetchone()[0]
        invalid_unit_transforms=db.execute("""SELECT count(*) FROM logic_tag_link
            WHERE trim(coalesce(unit_transform,''))=''
               OR (coalesce(source_unit,'')<>coalesce(target_unit,'') AND unit_transform='IDENTITY')""").fetchone()[0]
        converted_model_sources=db.execute("""SELECT count(*) FROM logic_tag_link
            WHERE source_kind='MODEL_VARIABLE' AND unit_transform<>'IDENTITY'""").fetchone()[0]
        add_validation(db,"active_logic_count",active==538,active,538,"Enabled absolute/discrete logic")
        add_validation(db,"active_unlinked_analog_count",active_unlinked_analog==0,
                       active_unlinked_analog,0,
                       "Unlinked H/HH/L/LL candidates are excluded from active validation")
        add_validation(db,"active_legacy_ratio_count",legacy==0,legacy,0,"No enabled ratio/span logic")
        add_validation(db,"invalid_active_absolute_count",invalid_abs==0,invalid_abs,0,"Absolute value and unit required")
        add_validation(db,"active_source_tag_link_coverage",
                       linked_active_source_refs==active_source_refs,
                       linked_active_source_refs,active_source_refs,
                       "Every declared active TAG/MODEL_VARIABLE source is linked to Tag Master")
        add_validation(db,"unlinked_active_source_count",unlinked_active_source_refs==0,
                       unlinked_active_source_refs,0,"No active declared source is missing a Tag Master link")
        add_validation(db,"active_analog_tag_coverage",linked_active_analog==active_analog,
                       linked_active_analog,active_analog,"Every active H/HH/L/LL rule has a source tag")
        add_validation(db,"runtime_tag_link_count",runtime_tag_links==len(dcs_rows)*2,
                       runtime_tag_links,len(dcs_rows)*2,"Runtime source and alarm output tags are linked")
        add_validation(db,"logic_tag_unit_transform_valid",invalid_unit_transforms==0,
                       invalid_unit_transforms,0,"Every active source has an explicit valid engineering-unit transform")
        add_validation(db,"runtime_rule_count",len(dcs_rows)==30,len(dcs_rows),30,"DCS deployment rules")
        add_validation(db,"ecms_setting_count",len(setting_rows)==10,len(setting_rows),10,"ECMS settings")
        add_validation(db,"ecms_signal_count",len(interface_rows)==31,len(interface_rows),31,"ECMS ports")
        integrity=db.execute("PRAGMA integrity_check").fetchone()[0]
        add_validation(db,"sqlite_integrity",integrity=="ok",integrity,"ok","SQLite integrity check")
        db.commit()
        stats={
          "active_logic_rules":active,
          "runtime_alarm_rules":len(dcs_rows),
          "excluded_unlinked_analog_rules":excluded_unlinked_analog,
          "disabled_backlog_rules":total-active,
          "catalogued_logic_rows":total,
          "tag_master_rows":db.execute("SELECT count(*) FROM tag_master").fetchone()[0],
          "tag_alias_rows":db.execute("SELECT count(*) FROM tag_alias").fetchone()[0],
          "linked_active_source_refs":linked_active_source_refs,
          "unlinked_active_source_refs":unlinked_active_source_refs,
          "active_analog_rules_with_source_tag":linked_active_analog,
          "runtime_tag_links":runtime_tag_links,
          "converted_active_model_sources":converted_model_sources,
          "logic_sources":db.execute("SELECT count(*) FROM logic_source").fetchone()[0],
          "ecms_settings":len(setting_rows),
          "ecms_signals":len(interface_rows),"active_legacy_ratio":legacy,
          "validation_passed":db.execute("SELECT count(*) FROM validation_result WHERE passed=1").fetchone()[0],
        }
        manifest={"schema_version":"2.1","database":a.output.name,"sha256":digest(a.output),
                  "source_commit":a.source_commit,"stats":stats,
                  "reporting_scope":"ACTIVE_LOGIC_ONLY",
                  "plant_use":"NOT APPROVED FOR REAL PLANT PROTECTION"}
        a.manifest.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(manifest,ensure_ascii=False,indent=2))
    finally:
        db.close()

if __name__=="__main__":
    main()
