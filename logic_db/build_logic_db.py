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
    if text == "TRUE": return 1
    if text == "FALSE": return 0
    raise ValueError(f"Invalid boolean: {value!r}")

def hysteresis(raw):
    text = str(raw or "").strip()
    m = re.match(r"^([-+]?[0-9]*\.?[0-9]+)\s*(.*)$", text)
    if not m: return None, None
    return float(m.group(1)), m.group(2).strip() or None

def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

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
    a.ecms_settings=a.ecms_settings or root/"logic_db/sources/a_logic_settings_v1.csv"
    a.ecms_interface=a.ecms_interface or root/"logic_db/sources/a_logic_interface_v1.csv"
    a.output=a.output or root/"outputs/triplens_logic_master_v2.sqlite"
    a.manifest=a.manifest or root/"outputs/logic_db_manifest.json"
    inputs=[a.schema,a.logic,a.dcs,a.ecms_settings,a.ecms_interface]
    for item in inputs:
        if not item.is_file(): raise FileNotFoundError(item)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.manifest.parent.mkdir(parents=True,exist_ok=True)
    if a.output.exists(): a.output.unlink()

    logic_rows, dcs_rows = rows(a.logic), rows(a.dcs)
    setting_rows, interface_rows = rows(a.ecms_settings), rows(a.ecms_interface)
    db=sqlite3.connect(a.output)
    try:
        db.executescript(a.schema.read_text(encoding="utf-8"))
        meta={
            "schema_version":"2.0",
            "dataset":"TripLens Absolute Logic Master",
            "generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "source_commit":a.source_commit,
            "plant_use":"NOT APPROVED FOR REAL PLANT PROTECTION",
            "unit_policy":"Enabled numeric logic uses absolute engineering units",
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

        for r in dcs_rows:
            db.execute("INSERT INTO runtime_alarm_rule VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                r["rule_id"],r["system"],r["source_signal"],r["alarm_tag"],
                r["description_ko"],r["direction"],r["threshold_mode"],
                number(r["threshold_value"],nullable=False),
                number(r["hysteresis_value"],nullable=False),
                number(r["delay_s"],nullable=False),r["severity"],r["unit"],
                r["status"],r["calibration_basis"]))

        for r in setting_rows:
            db.execute("INSERT INTO ecms_setting VALUES (?,?,?,?,?,?,?)",(
                r["setting_id"],r["category"],number(r["value"],nullable=False),
                r["unit"],r["status"],r["source_reference"],r["notes"]))
        for r in interface_rows:
            db.execute("INSERT INTO ecms_signal VALUES (?,?,?,?,?,?,?,?)",(
                r["signal_name"],r["direction"],r["data_type"],r["source_layer"],
                r["role"],r["status"],r["bound_tag"],r["notes"]))

        total=db.execute("SELECT count(*) FROM logic_rule").fetchone()[0]
        active=db.execute("SELECT count(*) FROM logic_rule WHERE enabled_default=1").fetchone()[0]
        legacy=db.execute("""SELECT count(*) FROM logic_rule WHERE enabled_default=1 AND
            (threshold_basis IN ('PRE_EVENT_BASELINE_RATIO','NORMALIZED_SPAN','ABSOLUTE_VALUE_PENDING')
             OR lower(coalesce(hysteresis_raw,'')) LIKE '%ratio%')""").fetchone()[0]
        invalid_abs=db.execute("""SELECT count(*) FROM logic_rule WHERE enabled_default=1
            AND threshold_basis LIKE 'ABSOLUTE_%'
            AND (threshold_value IS NULL OR trim(coalesce(threshold_unit,''))='')""").fetchone()[0]
        add_validation(db,"logic_row_count",total==903,total,903,"Complete v2 logic master")
        add_validation(db,"active_logic_count",active==538,active,538,"Enabled absolute/discrete logic")
        add_validation(db,"active_legacy_ratio_count",legacy==0,legacy,0,"No enabled ratio/span logic")
        add_validation(db,"invalid_active_absolute_count",invalid_abs==0,invalid_abs,0,"Absolute value and unit required")
        add_validation(db,"runtime_rule_count",len(dcs_rows)==32,len(dcs_rows),32,"DCS deployment rules")
        add_validation(db,"ecms_setting_count",len(setting_rows)==10,len(setting_rows),10,"ECMS settings")
        add_validation(db,"ecms_signal_count",len(interface_rows)==20,len(interface_rows),20,"ECMS ports")
        integrity=db.execute("PRAGMA integrity_check").fetchone()[0]
        add_validation(db,"sqlite_integrity",integrity=="ok",integrity,"ok","SQLite integrity check")
        db.commit()
        stats={
          "logic_rules":total,"active_logic":active,"deferred_logic":total-active,
          "logic_sources":db.execute("SELECT count(*) FROM logic_source").fetchone()[0],
          "runtime_alarm_rules":len(dcs_rows),"ecms_settings":len(setting_rows),
          "ecms_signals":len(interface_rows),"active_legacy_ratio":legacy,
          "validation_passed":db.execute("SELECT count(*) FROM validation_result WHERE passed=1").fetchone()[0],
        }
        manifest={"schema_version":"2.0","database":a.output.name,"sha256":digest(a.output),
                  "source_commit":a.source_commit,"stats":stats,
                  "plant_use":"NOT APPROVED FOR REAL PLANT PROTECTION"}
        a.manifest.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(manifest,ensure_ascii=False,indent=2))
    finally:
        db.close()

if __name__=="__main__":
    main()

