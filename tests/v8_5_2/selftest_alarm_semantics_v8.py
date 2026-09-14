#!/usr/bin/env python3
"""Audit the 67-rule plant registry against the DCS alarm contract.

The registry is the runtime source of truth.  The DCS CSV is the engineering
contract for absolute analogue thresholds, hysteresis, and assertion delay.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


EXPECTED_RULE_COUNT = 67

# DCS rule -> runtime registry rule.  These are the 28 absolute analogue
# points whose threshold, hysteresis and delay must match exactly.
DCS_TO_REGISTRY = {
    "D1-010": "GT_EXHAUST_FLOW_LOW",
    "D1-011": "GT_EXHAUST_FLOW_LOW_LOW",
    "D1-020": "GT_EXHAUST_TEMP_LOW",
    "D1-021": "GT_EXHAUST_TEMP_LOW_LOW",
    "D2-101": "HP_DRUM_LEVEL_HIGH",
    "D2-102": "HP_DRUM_LEVEL_HIGH_HIGH",
    "D2-103": "HP_DRUM_LEVEL_LOW",
    "D2-104": "HP_DRUM_LEVEL_LOW_LOW",
    "D2-111": "IP_DRUM_LEVEL_HIGH",
    "D2-112": "IP_DRUM_LEVEL_HIGH_HIGH",
    "D2-113": "IP_DRUM_LEVEL_LOW",
    "D2-114": "IP_DRUM_LEVEL_LOW_LOW",
    "D2-121": "LP_DRUM_LEVEL_HIGH",
    "D2-122": "LP_DRUM_LEVEL_HIGH_HIGH",
    "D2-123": "LP_DRUM_LEVEL_LOW",
    "D2-124": "LP_DRUM_LEVEL_LOW_LOW",
    "D2-201": "HP_DRUM_PRESSURE_LOW",
    "D2-202": "HP_DRUM_PRESSURE_LOW_LOW",
    "D2-211": "IP_DRUM_PRESSURE_LOW",
    "D2-212": "IP_DRUM_PRESSURE_LOW_LOW",
    "D2-221": "LP_DRUM_PRESSURE_LOW",
    "D2-222": "LP_DRUM_PRESSURE_LOW_LOW",
    "D2-301": "HP_STEAM_FLOW_LOW",
    "D2-302": "HP_STEAM_FLOW_LOW_LOW",
    "D2-311": "IP_STEAM_FLOW_LOW",
    "D2-312": "IP_STEAM_FLOW_LOW_LOW",
    "D2-321": "LP_STEAM_FLOW_LOW",
    "D2-322": "LP_STEAM_FLOW_LOW_LOW",
}

BOOLEAN_DCS_TO_REGISTRY = {
    "D1-001": "GT_TRIP_LATCH",
    "D2-001": "HP_FWP_SPEED_LOST",
}

SEVERITY_TO_PRIORITY = {
    "WARNING": "MEDIUM",
    "CRITICAL": "CRITICAL",
    "TRIP": "CRITICAL",
}


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise AssertionError(f"empty CSV: {path}")
    return rows


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-9)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--dcs-rules", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rows = load_csv(args.registry)
    dcs_rows = load_csv(args.dcs_rules)
    required = {
        "rule_id", "event_class", "priority", "equipment", "tag",
        "source_node", "active_when", "active_threshold",
        "return_threshold", "unit", "active_message", "return_message",
        "enabled", "delay_s",
    }
    missing_fields = sorted(required.difference(rows[0]))
    if missing_fields:
        raise AssertionError("registry fields missing: " + ",".join(missing_fields))
    if len(rows) != EXPECTED_RULE_COUNT:
        raise AssertionError(f"expected {EXPECTED_RULE_COUNT} registry rows, got {len(rows)}")
    if any(str(row["enabled"]).strip().lower() not in {"1", "true", "yes", "y"} for row in rows):
        raise AssertionError("all 67 plant alarm rules must remain enabled")

    by_id = {row["rule_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise AssertionError("duplicate rule_id in alarm registry")
    if any(not row["source_node"].startswith("vpp") for row in rows):
        raise AssertionError("every runtime alarm source must be a published vpp node")

    # A plant-wide registry must span turbine, electrical, HP/IP/LP process,
    # pumps, valves and buses.  This blocks accidental LP-only regressions.
    plant_wide_required = {
        "GT_TRIP_LATCH", "ST_TRIP_LATCH", "BUS_A_UNAVAILABLE",
        "HP_FWP_RUNNING_LOST", "IP_FWP_RUNNING_LOST", "LP_FWP_RUNNING_LOST",
        "HP_DRUM_LEVEL_LOW_LOW", "IP_DRUM_LEVEL_LOW_LOW", "LP_DRUM_LEVEL_LOW_LOW",
        "VLV_HP_FWCV_FAULT", "VLV_IP_FWCV_FAULT", "VLV_LP_FW_FAULT",
    }
    missing_coverage = sorted(plant_wide_required.difference(by_id))
    if missing_coverage:
        raise AssertionError("plant-wide alarm coverage missing: " + ",".join(missing_coverage))

    source_contract = {
        "HP_FWP_MOTOR_OFF": "vppHPFWPMotorEnergized",
        "HP_FWP_SPEED_LOST": "vppHPFWPSpeedProven",
        "IP_FWP_MOTOR_OFF": "vppIPFWPMotorEnergized",
        "IP_FWP_SPEED_LOST": "vppIPFWPSpeedProven",
        "LP_FWP_MOTOR_OFF": "vppLPFWPMotorEnergized",
        "LP_FWP_SPEED_LOST": "vppLPFWPSpeedProven",
    }
    for rule_id, source_node in source_contract.items():
        actual = by_id[rule_id]["source_node"]
        if actual != source_node:
            raise AssertionError(f"{rule_id} source expected {source_node}, got {actual}")

    dcs_by_id = {row["rule_id"]: row for row in dcs_rows}
    accounted_dcs = set(DCS_TO_REGISTRY).union(BOOLEAN_DCS_TO_REGISTRY)
    if set(dcs_by_id) != accounted_dcs:
        missing = sorted(set(dcs_by_id).difference(accounted_dcs))
        unexpected = sorted(accounted_dcs.difference(dcs_by_id))
        raise AssertionError(
            "DCS rule accounting mismatch: "
            f"unmapped={','.join(missing)}; missing={','.join(unexpected)}"
        )

    checks = 0
    for dcs_id, registry_id in DCS_TO_REGISTRY.items():
        dcs = dcs_by_id[dcs_id]
        rule = by_id[registry_id]
        if dcs["threshold_mode"] != "ABSOLUTE":
            raise AssertionError(f"{dcs_id} must remain ABSOLUTE")
        direction = dcs["direction"].upper()
        if rule["active_when"].upper() != direction:
            raise AssertionError(f"{registry_id} direction differs from {dcs_id}")
        threshold = float(dcs["threshold_value"])
        hysteresis = float(dcs["hysteresis_value"])
        expected_return = threshold - hysteresis if direction == "HIGH" else threshold + hysteresis
        expected = {
            "active_threshold": threshold,
            "return_threshold": expected_return,
            "delay_s": float(dcs["delay_s"]),
        }
        for field, value in expected.items():
            if not close(float(rule[field]), value):
                raise AssertionError(
                    f"{registry_id}.{field}: expected {value} from {dcs_id}, got {rule[field]}"
                )
            checks += 1
        if rule["unit"] != dcs["unit"]:
            raise AssertionError(f"{registry_id} unit differs from {dcs_id}")
        checks += 1

        expected_priority = SEVERITY_TO_PRIORITY[dcs["severity"]]
        if rule["priority"] != expected_priority:
            raise AssertionError(
                f"{registry_id}.priority: expected {expected_priority} from {dcs_id}, "
                f"got {rule['priority']}"
            )
        checks += 1

    # Boolean alarms use the OPC UA numeric boundary 0/1, with 0.5 as the
    # transition threshold.  Their DCS contract has no assertion delay.
    for dcs_id, rule_id in BOOLEAN_DCS_TO_REGISTRY.items():
        dcs = dcs_by_id[dcs_id]
        if dcs["threshold_mode"] != "BOOLEAN" or float(dcs["delay_s"]) != 0.0:
            raise AssertionError(f"{dcs_id} boolean DCS contract changed")
        expected = (dcs["direction"].upper(), 0.5, 0.5, 0.0)
        rule = by_id[rule_id]
        actual = (
            rule["active_when"].upper(), float(rule["active_threshold"]),
            float(rule["return_threshold"]), float(rule["delay_s"]),
        )
        if actual != expected:
            raise AssertionError(f"{rule_id} boolean boundary mismatch: {actual!r}")
        checks += 4
        expected_priority = SEVERITY_TO_PRIORITY[dcs["severity"]]
        if rule["priority"] != expected_priority:
            raise AssertionError(
                f"{rule_id}.priority: expected {expected_priority} from {dcs_id}, "
                f"got {rule['priority']}"
            )
        checks += 1

    for rule in rows:
        active_when = rule["active_when"].upper()
        active = float(rule["active_threshold"])
        returning = float(rule["return_threshold"])
        delay = float(rule["delay_s"])
        if delay < 0:
            raise AssertionError(f"negative delay_s: {rule['rule_id']}")
        if active_when in {"LOW", "BASELINE_RATIO_LOW"} and returning < active:
            raise AssertionError(f"invalid LOW hysteresis: {rule['rule_id']}")
        if active_when in {"HIGH", "BASELINE_DELTA_LOW"} and returning > active:
            raise AssertionError(f"invalid HIGH/delta hysteresis: {rule['rule_id']}")

    result = {
        "status": "PASS",
        "registry_rules": len(rows),
        "enabled_rules": len(rows),
        "dcs_absolute_rules_checked": len(DCS_TO_REGISTRY),
        "dcs_boolean_rules_checked": len(BOOLEAN_DCS_TO_REGISTRY),
        "dcs_rules_accounted": len(DCS_TO_REGISTRY) + len(BOOLEAN_DCS_TO_REGISTRY),
        "semantic_checks": checks,
        "startup_scope": "PLANT_WIDE",
        "lp_only_filter": False,
        "drum_low_mode": "ABSOLUTE",
        "delayed_rules": sum(float(row["delay_s"]) > 0 for row in rows),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
