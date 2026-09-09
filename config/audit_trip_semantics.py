#!/usr/bin/env python3
"""Fail closed on Trip causality, naming, ownership, and retired equipment drift."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ROOT / "config" / "ecms_command_catalog.csv"
ALARMS = ROOT / "config" / "dcs_alarm_rules.csv"
COMMON_TRIP = ROOT / "config" / "common_trip_matrix.csv"
ALIASES = ROOT / "config" / "tag_alias_contract.csv"
EQUIPMENT = ROOT / "config" / "ecms_a_equipment.csv"
M_LINKS = ROOT / "data" / "ecms_m_links.csv"
TAG_CATALOG = ROOT / "data" / "ecms_tag_catalog.csv"
TOPOLOGY = ROOT / "topology" / "triplens_ecms_6p9kv.svg"
OUT = ROOT / "outputs" / "trip_semantics_audit.json"

RETIRED = {"CW-PUMP", "COND-PUMP", "RECIRC-HP", "RECIRC-IP", "RECIRC-LP", "SST"}
FWP_TO_VCB = {"FWP-HP": "VCB-A01", "FWP-IP": "VCB-B01", "FWP-LP": "VCB-A02"}
EXPECTED_COMMON_TRIP = {
    "DIRECT_GT_TRIP": (1, 1),
    "DIRECT_ST_TRIP": (0, 1),
    "HP_DRUM_HH": (0, 1),
    "IP_DRUM_HH": (0, 1),
    "LP_DRUM_HH": (0, 1),
    "HP_DRUM_LL": (1, 1),
    "IP_DRUM_LL": (1, 1),
    "LP_DRUM_LL": (1, 1),
}
REQUIRED_RAW_ALIASES = {
    "SIM.FWP_HP_TRIP": ("CMD.FWP-HP.TRIP", "COMMANDBUS", "fwp_hp_trip_input"),
    "FWP_HP.RUN_ENABLE": ("DCS.FWP-HP.RUN_ENABLE", "DCS_MCC", "fwp_hp_run_enable"),
    "VCB_A01_TRIP_CMD": ("ECMS.VCB-A01.TRIP_CMD", "ECMS", "fwp_hp_vcb_trip_cmd"),
    "VCB-A01.CLOSED": ("ECMS.VCB-A01.CLOSED", "ECMS", "fwp_hp_vcb_closed"),
    "FWP_HP.TRIP_LATCH": ("CTRL.FWP-HP.TRIP_LATCH", "PROTECTION", "fwp_hp_trip_latch"),
    "FWP_HP.RUN_FB": ("DCS.FWP-HP.RUN_CMD_FB", "DCS_MCC", "fwp_hp_run_cmd_feedback"),
    "FWP_HP.SPEED_RPM": ("PROCESS.FWP-HP.SPEED_RPM", "PROCESSBUS", "fwp_hp_speed_rpm"),
    "FWP_HP.SPEED_PROVEN": ("DCS.FWP-HP.SPEED_PROVEN", "DCS_MCC", "fwp_hp_speed_proven"),
    "FWP_HP.STATE_CODE": ("TWIN.FWP-HP.STATE_CODE", "TWIN_INTERNAL", "fwp_hp_state_code"),
    "FWP_HP.TRIPPED": ("CTRL.FWP-HP.TRIPPED", "PROTECTION", "fwp_hp_tripped"),
    "ECMS.BUS-A.VOLTAGE": ("ECMS.BUS-A.VOLTAGE", "ECMS", "ecms_bus_a_voltage_kv"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def one(rows: list[dict[str, str]], **values: str) -> dict[str, str] | None:
    matches = [
        row for row in rows
        if all(row.get(field, "").strip().upper() == value.upper() for field, value in values.items())
    ]
    return matches[0] if len(matches) == 1 else None


def main() -> None:
    commands = read_csv(COMMANDS)
    alarms = read_csv(ALARMS)
    common_trip = read_csv(COMMON_TRIP)
    aliases = read_csv(ALIASES)
    equipment = read_csv(EQUIPMENT)
    m_links = read_csv(M_LINKS)
    tags = read_csv(TAG_CATALOG)
    errors: list[str] = []

    trip_rows = [row for row in commands if row["command"].strip().upper() == "TRIP"]
    derate_rows = [row for row in commands if row["command"].strip().upper() == "DERATE"]
    for row in trip_rows:
        equipment_type = row["equipment_type"].strip().upper()
        feedback = row["feedback_tag"].strip().upper()
        if equipment_type in {"GENERATOR", "MOTOR", "BREAKER"} and "CLOSED" not in feedback:
            errors.append(
                f"{row['equipment_id']} TRIP has non-breaker feedback_tag={row['feedback_tag']}"
            )
        if row["default_value"].strip() != "1":
            errors.append(f"{row['equipment_id']} TRIP is not active-high")
    for row in derate_rows:
        if "CLOSED" in row["feedback_tag"].strip().upper():
            errors.append(f"{row['equipment_id']} DERATE incorrectly uses breaker CLOSED feedback")

    analog_trip_alarms: list[str] = []
    for row in alarms:
        if row["severity"].strip().upper() != "TRIP":
            continue
        boolean_command = (
            row["threshold_mode"].strip().upper() == "BOOLEAN"
            and "TRIP.CMD" in row["alarm_tag"].strip().upper()
        )
        if not boolean_command:
            analog_trip_alarms.append(row["rule_id"])
    if analog_trip_alarms:
        errors.append("Analog/non-command alarms still labeled TRIP: " + ",".join(analog_trip_alarms))

    common_by_id = {row["cause_id"].strip().upper(): row for row in common_trip}
    if set(common_by_id) != set(EXPECTED_COMMON_TRIP):
        errors.append("Common Trip cause set differs from the approved executable matrix")
    for cause, expected in EXPECTED_COMMON_TRIP.items():
        row = common_by_id.get(cause)
        if row is None:
            continue
        actual = (int(row["gt_trip_request"]), int(row["st_trip_request"]))
        if actual != expected:
            errors.append(f"{cause} common Trip outputs are {actual}, expected {expected}")
        if not row["source_event_tag"].strip():
            errors.append(f"{cause} has no canonical source_event_tag")
        if "POWER" in row["source_signal"].upper():
            errors.append(f"{cause} illegally uses power/output as a Trip cause")

    for equipment_id, feeder_id in FWP_TO_VCB.items():
        stop = one(commands, equipment_id=equipment_id, command="STOP")
        trip = one(commands, equipment_id=equipment_id, command="TRIP")
        reset = one(commands, equipment_id=equipment_id, command="RESET")
        close = one(commands, equipment_id=feeder_id, command="CLOSE")
        if stop is None or feeder_id not in stop["notes"] or "CLOSED" not in stop["notes"].upper():
            errors.append(f"{equipment_id} STOP does not explicitly preserve {feeder_id} CLOSED")
        if trip is None or trip["feedback_tag"].strip().upper() != f"ECMS.{feeder_id}.CLOSED":
            errors.append(f"{equipment_id} TRIP is not tied to {feeder_id} CLOSED feedback")
        if reset is None or "RECLOSE" not in reset["notes"].upper():
            errors.append(f"{equipment_id} RESET does not explicitly forbid automatic reclose")
        if close is None:
            errors.append(f"{feeder_id} has no explicit CLOSE command")

    alias_index = {row["alias"].strip(): row for row in aliases}
    term = one(aliases, kind="TERM", canonical_name="VPP", alias="VVP")
    if term is None:
        errors.append("VPP canonical / VVP legacy alias contract is missing")
    for canonical, legacy in (("IP", "MP"), ("LP", "BP")):
        row = one(aliases, kind="PRESSURE_LEVEL", canonical_name=canonical, alias=legacy)
        if row is None or row["status"].strip().upper() != "BOUNDARY_ALIAS":
            errors.append(f"ThermoSysPro {legacy}->{canonical} boundary alias is missing")
    for alias, expected in REQUIRED_RAW_ALIASES.items():
        row = alias_index.get(alias)
        actual = None if row is None else (
            row["canonical_name"].strip(), row["owner"].strip(), row["processbus_field"].strip()
        )
        if actual != expected:
            errors.append(f"RAW alias {alias} resolves to {actual}, expected {expected}")

    executable_equipment = {
        row["equipment_id"].strip().upper() for row in equipment
    } | {
        row["equipment_id"].strip().upper() for row in commands
    } | {
        row["ecms_equipment_id"].strip().upper() for row in m_links
    }
    topology_text = TOPOLOGY.read_text(encoding="utf-8").upper()
    for retired in RETIRED:
        if retired in executable_equipment:
            errors.append(f"retired equipment remains executable: {retired}")
        if retired in topology_text:
            errors.append(f"retired equipment remains in topology: {retired}")

    mixed_physical_tags = [
        row["ecms_tag_id"] for row in tags
        if row["ecms_tag_id"].startswith("ECMS.FWP-") and row["layer"].strip().upper() == "M"
    ]
    if mixed_physical_tags:
        errors.append("Process physical quantities remain mis-owned by ECMS: " + ",".join(mixed_physical_tags))

    d2_speed = one(alarms, rule_id="D2-001")
    if d2_speed is None or d2_speed["source_signal"].strip() != "fwp_hp_speed_proven":
        errors.append("DCS2 FWP-HP speed-proven loss rule is missing")

    report = {
        "pass": not errors,
        "canonical_trip_result": "associated breaker CLOSED feedback = 0",
        "st_output_policy": "active power is a measurement only; no H/HH/L/LL or low-state output",
        "canonical_naming": "VPP / FWP-HP-IP-LP / IP-LP; VVP-BFP-MP-BP are aliases only",
        "raw_aliases_checked": len(REQUIRED_RAW_ALIASES),
        "common_trip_causes_checked": len(EXPECTED_COMMON_TRIP),
        "trip_command_rows": len(trip_rows),
        "derate_command_rows": len(derate_rows),
        "retired_equipment_checked": sorted(RETIRED),
        "analog_trip_alarm_rows": analog_trip_alarms,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)
    print("TRIPLENS_TRIP_SEMANTICS_AUDIT_PASS")


if __name__ == "__main__":
    main()
