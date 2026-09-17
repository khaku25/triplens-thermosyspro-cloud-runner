#!/usr/bin/env python3
"""Augment a TripLens Logic DB with deterministic EVENT -> Tag Master links.

EVENT.csv uses short event tags such as TRIP_LATCH or FLOW_LOW_LOW.  Those
labels are only unique together with the event registry rule/equipment and must
not be fuzzy-matched.  This module imports the runtime EVENT registry and gives
every enabled event an auditable Tag Master target.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _safe(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").upper()).strip("_")
    return text or "UNKNOWN"


def _alarm_level(event_tag: str) -> str | None:
    tag = str(event_tag or "").upper()
    if tag.endswith("_LOW_LOW"):
        return "LL"
    if tag.endswith("_HIGH_HIGH"):
        return "HH"
    if tag.endswith("_LOW"):
        return "L"
    if tag.endswith("_HIGH"):
        return "H"
    return None


def _alias_index(signal_map: dict) -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, spec in signal_map.get("signals", {}).items():
        for alias in [canonical, *spec.get("aliases", [])]:
            alias = str(alias or "").strip()
            if alias:
                index[alias] = canonical
    return index


def _resolve_dcs_alarm(event: dict[str, str], dcs_rows: list[dict[str, str]], aliases: dict[str, str]) -> str | None:
    canonical = aliases.get(str(event.get("source_node", "")).strip())
    if not canonical:
        return None
    candidates = [row for row in dcs_rows if row.get("source_signal") == canonical]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["alarm_tag"]
    level = _alarm_level(event.get("tag", ""))
    if level:
        matches = [row for row in candidates if str(row.get("alarm_tag", "")).endswith(f".{level}")]
        if len(matches) == 1:
            return matches[0]["alarm_tag"]
    return None


def _special_tag(event: dict[str, str]) -> str | None:
    rule_id = event.get("rule_id", "")
    return {
        "GT_TRIP_LATCH": "GT.TRIP.LATCH",
        "ST_TRIP_LATCH": "ST.TRIP.LATCH",
    }.get(rule_id)


def _existing_alias_target(db: sqlite3.Connection, source_node: str) -> str | None:
    rows = db.execute(
        """SELECT DISTINCT t.tag_id
           FROM tag_alias a JOIN tag_master t ON t.tag_id=a.tag_id
           WHERE a.alias=?
           ORDER BY CASE t.record_type
               WHEN 'DCS_ALARM' THEN 0
               WHEN 'ACTIVE_LOGIC_SOURCE' THEN 1
               WHEN 'PROCESSBUS_SIGNAL' THEN 2
               ELSE 3 END, t.tag_id""",
        (source_node,),
    ).fetchall()
    if len(rows) == 1:
        return rows[0][0]
    return None


def _ensure_event_tag(db: sqlite3.Connection, event: dict[str, str], tag_id: str) -> None:
    if db.execute("SELECT 1 FROM tag_master WHERE tag_id=?", (tag_id,)).fetchone():
        return
    db.execute(
        """INSERT INTO tag_master (
             tag_id,record_type,platform,system,subsystem,equipment_id,equipment_type,
             signal_name,description_ko,io_type,data_type,unit,source_layer,tag_class,
             value_basis,limit_basis,model_mapping,canonical_signal,status,editable,
             source_file,source_record_id,notes
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            tag_id, "EVENT_RULE", "EVENT", "EVENT", "ALARM_EVENT",
            event.get("equipment", ""), "Event source", event.get("tag", ""),
            event.get("active_message", "") or event.get("rule_id", ""),
            "DI", "BOOL" if event.get("unit") == "BOOL" else "REAL",
            event.get("unit", ""), "EVENT_REGISTRY", "A", "A", "A",
            event.get("source_node", ""), "", "EVENT_REGISTRY_ENABLED", 0,
            "config/alarm_registry_v1.csv", event.get("rule_id", ""),
            "First-class EVENT Tag Master record; no fuzzy matching",
        ),
    )
    db.execute(
        """INSERT OR IGNORE INTO tag_alias
           (alias,tag_id,alias_type,canonical_signal,unit,status,source_file)
           VALUES (?,?,?,?,?,?,?)""",
        (tag_id, tag_id, "TAG_ID", "", event.get("unit", ""), "EXACT", "config/alarm_registry_v1.csv"),
    )


def _add_alias(db: sqlite3.Connection, alias: str, tag_id: str, alias_type: str, unit: str) -> None:
    alias = str(alias or "").strip()
    if not alias:
        return
    db.execute(
        """INSERT OR IGNORE INTO tag_alias
           (alias,tag_id,alias_type,canonical_signal,unit,status,source_file)
           VALUES (?,?,?,?,?,?,?)""",
        (alias, tag_id, alias_type, "", unit, "EVENT_EXACT", "config/alarm_registry_v1.csv"),
    )


def augment_event_tags(
    db_path: Path,
    event_registry: Path,
    dcs_rules: Path,
    signal_map_path: Path,
) -> dict[str, int]:
    events = [row for row in _rows(event_registry) if _enabled(row.get("enabled"))]
    dcs = _rows(dcs_rules)
    signal_map = json.loads(signal_map_path.read_text(encoding="utf-8-sig"))
    aliases = _alias_index(signal_map)

    db = sqlite3.connect(db_path)
    try:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS event_alarm_rule (
                rule_id TEXT PRIMARY KEY,
                event_class TEXT NOT NULL,
                priority TEXT NOT NULL,
                equipment TEXT NOT NULL,
                event_tag TEXT NOT NULL,
                source_node TEXT NOT NULL,
                unit TEXT,
                active_message TEXT,
                enabled INTEGER NOT NULL CHECK (enabled IN (0,1))
            );
            CREATE TABLE IF NOT EXISTS event_tag_link (
                rule_id TEXT PRIMARY KEY REFERENCES event_alarm_rule(rule_id) ON DELETE CASCADE,
                tag_id TEXT NOT NULL REFERENCES tag_master(tag_id),
                mapping_method TEXT NOT NULL,
                event_lookup_key TEXT NOT NULL,
                source_node TEXT NOT NULL,
                verification_status TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_event_tag_link_tag_id ON event_tag_link(tag_id);
            CREATE INDEX IF NOT EXISTS idx_event_alarm_lookup ON event_alarm_rule(equipment,event_tag);
            CREATE VIEW IF NOT EXISTS v_event_tag_map AS
            SELECT e.rule_id,e.event_class,e.priority,e.equipment,e.event_tag,e.source_node,
                   x.tag_id,x.mapping_method,x.event_lookup_key,x.verification_status,
                   t.description_ko,t.unit,t.model_mapping,t.canonical_signal,t.status AS tag_status
              FROM event_alarm_rule e
              JOIN event_tag_link x ON x.rule_id=e.rule_id
              JOIN tag_master t ON t.tag_id=x.tag_id;
            """
        )

        db.execute("DELETE FROM event_tag_link")
        db.execute("DELETE FROM event_alarm_rule")

        for event in events:
            db.execute(
                "INSERT INTO event_alarm_rule VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    event["rule_id"], event["event_class"], event["priority"],
                    event["equipment"], event["tag"], event["source_node"],
                    event.get("unit", ""), event.get("active_message", ""), 1,
                ),
            )

            tag_id = _special_tag(event)
            method = "SPECIAL_CANONICAL"
            if not tag_id:
                tag_id = _resolve_dcs_alarm(event, dcs, aliases)
                method = "SOURCE_ALIAS_PLUS_EVENT_SEMANTIC"
            if not tag_id:
                tag_id = _existing_alias_target(db, event.get("source_node", ""))
                method = "EXACT_SOURCE_NODE_ALIAS"
            if not tag_id:
                tag_id = f"EVENT.{_safe(event['equipment'])}.{_safe(event['tag'])}"
                method = "EVENT_REGISTRY_CANONICAL"

            _ensure_event_tag(db, event, tag_id)
            lookup_key = f"{event['equipment']}::{event['tag']}"
            _add_alias(db, event["rule_id"], tag_id, "EVENT_RULE_ID", event.get("unit", ""))
            _add_alias(db, lookup_key, tag_id, "EVENT_EQUIPMENT_TAG", event.get("unit", ""))
            _add_alias(db, event.get("source_node", ""), tag_id, "EVENT_SOURCE_NODE", event.get("unit", ""))
            db.execute(
                "INSERT INTO event_tag_link VALUES (?,?,?,?,?,?)",
                (
                    event["rule_id"], tag_id, method, lookup_key,
                    event.get("source_node", ""), "EVENT_REGISTRY_BOUND",
                ),
            )

        linked = db.execute("SELECT count(*) FROM event_tag_link").fetchone()[0]
        if linked != len(events):
            raise ValueError(f"EVENT Tag Master coverage failed: {linked}/{len(events)}")
        db.commit()
        return {"enabled_event_rules": len(events), "linked_event_rules": linked}
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db", type=Path)
    parser.add_argument("--event-registry", type=Path)
    parser.add_argument("--dcs-rules", type=Path)
    parser.add_argument("--signal-map", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stats = augment_event_tags(
        args.db,
        args.event_registry or root / "config" / "alarm_registry_v1.csv",
        args.dcs_rules or root / "config" / "dcs_alarm_rules.csv",
        args.signal_map or root / "config" / "signal_map.json",
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
