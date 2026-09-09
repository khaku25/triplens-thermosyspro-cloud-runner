#!/usr/bin/env python3
"""Serialize Modelica-owned alarm state transitions into VPP_EVENT CSV.

This program deliberately does not evaluate thresholds, hysteresis, delay or
Trip matrices.  Those decisions have already happened inside the generated
Modelica runtime.  The configured setpoints are copied only as display/audit
metadata beside the actual physical value at each Boolean state transition.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EVENT_FIELDS = [
    "schema_version",
    "event_sequence",
    "event_id",
    "event_time_ms",
    "time_s",
    "system",
    "tag",
    "event_state",
    "event_class",
    "severity",
    "priority",
    "display_color",
    "source_signal",
    "actual_value",
    "setpoint",
    "return_setpoint",
    "direction",
    "delay_s",
    "unit",
    "quality",
    "decision_owner",
    "state_variable",
    "value_variable",
    "logic_version",
    "logic_status",
    "description",
]

REQUIRED_RULE_FIELDS = {
    "logic_version",
    "rule_id",
    "enabled",
    "system",
    "logic_kind",
    "source_signal",
    "model_state_candidates",
    "model_value_candidates",
    "active_when",
    "alarm_tag",
    "description_ko",
    "direction",
    "threshold_value",
    "hysteresis_value",
    "delay_s",
    "event_class",
    "severity",
    "priority",
    "display_color",
    "unit",
    "status",
}


@dataclass(frozen=True)
class EventRule:
    order: int
    rule_id: str
    logic_version: str
    system: str
    kind: str
    source_signal: str
    state_candidates: tuple[str, ...]
    value_candidates: tuple[str, ...]
    active_when: bool
    tag: str
    description: str
    direction: str
    threshold: float
    threshold_text: str
    hysteresis: float
    delay_text: str
    event_class: str
    severity: str
    priority: str
    display_color: str
    unit: str
    status: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_flag(value: str, *, label: str) -> bool:
    normalized = value.strip().upper()
    if normalized in {"1", "TRUE", "YES"}:
        return True
    if normalized in {"0", "FALSE", "NO"}:
        return False
    raise ValueError(f"{label} must be 0/1 or false/true")


def finite_number(value: str, *, label: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def split_candidates(value: str, *, label: str) -> tuple[str, ...]:
    candidates = tuple(item.strip() for item in value.split("|") if item.strip())
    if not candidates:
        raise ValueError(f"{label} needs at least one Modelica CSV column candidate")
    return candidates


def load_rules(path: Path) -> list[EventRule]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        missing = REQUIRED_RULE_FIELDS.difference(fields)
        if missing:
            raise ValueError("VPP event logic is missing: " + ", ".join(sorted(missing)))
        rows = list(reader)

    rules: list[EventRule] = []
    seen_ids: set[str] = set()
    seen_tags: set[str] = set()
    versions: set[str] = set()
    for order, row in enumerate(rows):
        row_number = order + 2
        if not parse_flag(row["enabled"], label=f"row {row_number} enabled"):
            continue
        rule_id = row["rule_id"].strip()
        tag = row["alarm_tag"].strip()
        if not rule_id or rule_id in seen_ids:
            raise ValueError(f"row {row_number} has an empty or duplicate rule_id")
        if not tag or tag in seen_tags:
            raise ValueError(f"row {row_number} has an empty or duplicate alarm_tag")
        seen_ids.add(rule_id)
        seen_tags.add(tag)
        system = row["system"].strip().upper()
        if system not in {"DCS1", "DCS2"}:
            raise ValueError(f"{rule_id}: system must be DCS1 or DCS2")
        version = row["logic_version"].strip()
        versions.add(version)
        threshold_text = row["threshold_value"].strip()
        hysteresis = finite_number(
            row["hysteresis_value"], label=f"{rule_id} hysteresis"
        )
        if hysteresis < 0:
            raise ValueError(f"{rule_id}: hysteresis must be non-negative")
        delay_text = row["delay_s"].strip()
        if finite_number(delay_text, label=f"{rule_id} delay") < 0:
            raise ValueError(f"{rule_id}: delay must be non-negative")
        direction = row["direction"].strip().upper()
        if direction not in {"HIGH", "LOW"}:
            raise ValueError(f"{rule_id}: direction must be HIGH or LOW")
        rules.append(
            EventRule(
                order=order,
                rule_id=rule_id,
                logic_version=version,
                system=system,
                kind=row["logic_kind"].strip().upper(),
                source_signal=row["source_signal"].strip(),
                state_candidates=split_candidates(
                    row["model_state_candidates"], label=f"{rule_id} state"
                ),
                value_candidates=split_candidates(
                    row["model_value_candidates"], label=f"{rule_id} value"
                ),
                active_when=parse_flag(
                    row["active_when"], label=f"{rule_id} active_when"
                ),
                tag=tag,
                description=row["description_ko"].strip(),
                direction=direction,
                threshold=finite_number(
                    threshold_text, label=f"{rule_id} threshold"
                ),
                threshold_text=threshold_text,
                hysteresis=hysteresis,
                delay_text=delay_text,
                event_class=row["event_class"].strip().upper(),
                severity=row["severity"].strip().upper(),
                priority=row["priority"].strip().upper(),
                display_color=row["display_color"].strip().upper(),
                unit=row["unit"].strip(),
                status=row["status"].strip(),
            )
        )
    if not rules:
        raise ValueError("VPP event logic has no enabled rules")
    if versions == {""} or len(versions) != 1:
        raise ValueError("enabled rules must have one non-empty logic_version")
    return rules


def resolve_column(
    fieldnames: list[str], candidates: tuple[str, ...], *, label: str
) -> str:
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
    for candidate in candidates:
        suffix_matches = [
            field for field in fieldnames
            if field.endswith("." + candidate) or field.endswith(candidate)
        ]
        if len(suffix_matches) == 1:
            return suffix_matches[0]
        if len(suffix_matches) > 1:
            raise ValueError(
                f"{label}: candidate {candidate} is ambiguous: "
                + ", ".join(suffix_matches)
            )
    raise ValueError(
        f"{label}: none of the Modelica columns exist: " + ", ".join(candidates)
    )


def parse_boolean(value: str, *, label: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "1.0"}:
        return True
    if normalized in {"false", "0", "0.0"}:
        return False
    try:
        number = float(normalized)
    except ValueError as exc:
        raise ValueError(f"{label} is not a Modelica Boolean") from exc
    if not math.isfinite(number) or number not in {0.0, 1.0}:
        raise ValueError(f"{label} is not a Modelica Boolean")
    return bool(number)


def display_number(value: str, *, label: str) -> str:
    number = finite_number(value.strip(), label=label)
    return f"{number:.12g}"


def return_setpoint(rule: EventRule) -> str:
    if rule.kind != "ANALOG":
        return f"{rule.threshold:.12g}"
    value = (
        rule.threshold - rule.hysteresis
        if rule.direction == "HIGH"
        else rule.threshold + rule.hysteresis
    )
    return f"{value:.12g}"


def write_events(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def file_metadata(path: Path) -> dict[str, object]:
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def export_events(
    *,
    raw_path: Path,
    rules_path: Path,
    event_path: Path,
    dcs1_path: Path,
    dcs2_path: Path,
    snapshot_path: Path,
    manifest_path: Path,
) -> list[dict[str, str]]:
    rules = load_rules(rules_path)
    with raw_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if "time" not in fieldnames:
        raise ValueError("VPP RAW is missing the native time column")
    if len(rows) < 2:
        raise ValueError("VPP RAW needs at least two data rows")

    resolved: dict[str, tuple[str, str]] = {}
    for rule in rules:
        resolved[rule.rule_id] = (
            resolve_column(
                fieldnames, rule.state_candidates,
                label=f"{rule.rule_id} state variable"
            ),
            resolve_column(
                fieldnames, rule.value_candidates,
                label=f"{rule.rule_id} value variable"
            ),
        )

    previous_time: float | None = None
    previous_states: dict[str, bool] = {}
    events_with_order: list[tuple[float, int, int, dict[str, str]]] = []
    for raw_order, row in enumerate(rows):
        time_s = finite_number(row["time"], label=f"RAW row {raw_order + 2} time")
        if previous_time is not None and time_s < previous_time:
            raise ValueError("VPP RAW native time reverses")
        previous_time = time_s
        for rule in rules:
            state_column, value_column = resolved[rule.rule_id]
            model_state = parse_boolean(
                row.get(state_column, ""),
                label=f"RAW row {raw_order + 2} {state_column}",
            )
            active = model_state if rule.active_when else not model_state
            previous = previous_states.get(rule.rule_id)
            previous_states[rule.rule_id] = active
            if previous is None:
                if not active:
                    continue
                event_state = "ACTIVE"
            elif active == previous:
                continue
            else:
                event_state = "ACTIVE" if active else "RETURN"

            value = display_number(
                row.get(value_column, ""),
                label=f"RAW row {raw_order + 2} {value_column}",
            )
            event = {
                "schema_version": "1.0",
                "event_sequence": "",
                "event_id": "",
                "event_time_ms": str(int(math.floor(time_s * 1000 + 0.5))),
                "time_s": f"{time_s:.9f}",
                "system": rule.system,
                "tag": rule.tag,
                "event_state": event_state,
                "event_class": rule.event_class,
                "severity": rule.severity,
                "priority": rule.priority,
                "display_color": rule.display_color,
                "source_signal": rule.source_signal,
                "actual_value": value,
                "setpoint": f"{rule.threshold:.12g}",
                "return_setpoint": return_setpoint(rule),
                "direction": rule.direction,
                "delay_s": display_number(
                    rule.delay_text, label=f"{rule.rule_id} delay"
                ),
                "unit": rule.unit,
                "quality": "GOOD",
                "decision_owner": "MODELICA_VPP_LOGIC_RUNTIME",
                "state_variable": state_column,
                "value_variable": value_column,
                "logic_version": rule.logic_version,
                "logic_status": rule.status,
                "description": rule.description,
            }
            events_with_order.append((time_s, raw_order, rule.order, event))

    events_with_order.sort(key=lambda item: (item[0], item[1], item[2]))
    events: list[dict[str, str]] = []
    for sequence, (_, _, _, event) in enumerate(events_with_order, start=1):
        event["event_sequence"] = str(sequence)
        event["event_id"] = f"VPP-E{sequence:06d}"
        events.append(event)

    dcs1 = [event for event in events if event["system"] == "DCS1"]
    dcs2 = [event for event in events if event["system"] == "DCS2"]
    write_events(event_path, events)
    write_events(dcs1_path, dcs1)
    write_events(dcs2_path, dcs2)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(rules_path, snapshot_path)

    raw_times = [finite_number(row["time"], label="RAW time") for row in rows]
    manifest = {
        "schema_version": "1.0",
        "artifact_type": "VPP_MODELICA_EVENT_BUNDLE",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "logic": {
            "version": rules[0].logic_version,
            "status": sorted({rule.status for rule in rules}),
            "enabled_event_rules": len(rules),
            "modelica_alarm_rules": sum(rule.kind != "STATE" for rule in rules),
            "configuration": file_metadata(snapshot_path),
        },
        "raw": {
            **file_metadata(raw_path),
            "row_count": len(rows),
            "first_time_s": raw_times[0],
            "last_time_s": raw_times[-1],
            "duplicate_native_time_rows": sum(
                right == left for left, right in zip(raw_times, raw_times[1:])
            ),
            "copy_policy": "BYTE_FOR_BYTE_FROM_OPENMODELICA_RESULT",
        },
        "events": {
            "combined": {**file_metadata(event_path), "row_count": len(events)},
            "dcs1": {**file_metadata(dcs1_path), "row_count": len(dcs1)},
            "dcs2": {**file_metadata(dcs2_path), "row_count": len(dcs2)},
            "ordering": "NATIVE_TIME_THEN_RAW_EVENT_ROW_THEN_RULE_ORDER",
            "initial_active_policy": "EMIT_ACTIVE_AT_FIRST_NATIVE_ROW",
        },
        "boundary": {
            "alarm_decision_owner": "MODELICA_VPP_LOGIC_RUNTIME",
            "serializer_role": "BOOLEAN_STATE_TRANSITIONS_ONLY",
            "serializer_recalculates_thresholds": False,
            "monitor_recalculates_thresholds": False,
            "system_routing_embedded": True,
            "scenario_label_included": False,
            "root_cause_label_included": False,
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument(
        "--rules", type=Path,
        default=ROOT / "config" / "vpp_event_logic_provisional.csv"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dcs1-output", type=Path, required=True)
    parser.add_argument("--dcs2-output", type=Path, required=True)
    parser.add_argument("--logic-snapshot", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if not args.raw.is_file() or args.raw.stat().st_size == 0:
        parser.error("--raw must be a non-empty OpenModelica CSV")
    events = export_events(
        raw_path=args.raw,
        rules_path=args.rules,
        event_path=args.output,
        dcs1_path=args.dcs1_output,
        dcs2_path=args.dcs2_output,
        snapshot_path=args.logic_snapshot,
        manifest_path=args.manifest,
    )
    print(f"VPP_EVENT_COUNT={len(events)}")
    print(f"VPP_EVENT_OUTPUT={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
