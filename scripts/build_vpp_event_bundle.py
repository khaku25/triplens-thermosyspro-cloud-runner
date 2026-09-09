#!/usr/bin/env python3
"""Build the one-file TripLens VPP external event interface.

The builder is inside the VPP boundary. It may read simulator RAW and
deterministic DCS/ECMS event outputs, but it publishes only public/EVENT.csv.
It never evaluates a root cause and never copies a scenario answer into the
public file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
NANOSECONDS_PER_SECOND = 1_000_000_000
NANOSECONDS_PER_MILLISECOND = 1_000_000

RULE_COLUMNS = {
    "order",
    "rule_id",
    "enabled",
    "source_signal",
    "edge",
    "tag",
    "event_type",
    "state",
    "severity",
    "priority",
    "message_ko",
    "logic_status",
}


@dataclass(frozen=True)
class EdgeRule:
    order: int
    rule_id: str
    source_signal: str
    edge: str
    tag: str
    event_type: str
    state: str
    severity: str
    priority: str
    message: str
    logic_status: str


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        if not fields:
            raise ValueError(f"{path.name} has no CSV header")
        if len(fields) != len(set(fields)):
            raise ValueError(f"{path.name} contains duplicate CSV columns")
        return fields, list(reader)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_contract(path: Path) -> dict[str, object]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "official_output",
        "columns",
        "allowed_systems",
        "system_order",
        "allowed_event_types",
        "allowed_severities",
        "allowed_priorities",
        "allowed_quality",
        "forbidden_columns",
        "forbidden_column_prefixes",
        "timestamp_contract",
        "boundary",
    }
    missing = required.difference(contract)
    if missing:
        raise ValueError("event contract is missing: " + ", ".join(sorted(missing)))
    columns = contract["columns"]
    if not isinstance(columns, list) or len(columns) != len(set(columns)):
        raise ValueError("event contract columns must be a unique ordered list")
    boundary = contract["boundary"]
    if not isinstance(boundary, dict):
        raise ValueError("event contract boundary must be an object")
    if boundary.get("public_directory_exact_files") != ["EVENT.csv"]:
        raise ValueError("the public VPP boundary must contain only EVENT.csv")
    if boundary.get("alarm_console_inputs") != ["EVENT.csv"]:
        raise ValueError("Alarm Console must consume only EVENT.csv")
    if boundary.get("triplens_ai_inputs") != ["EVENT.csv"]:
        raise ValueError("TripLens AI must consume only EVENT.csv")
    if boundary.get("alarm_console_raw_access") is not False:
        raise ValueError("Alarm Console RAW access must remain disabled")
    if boundary.get("triplens_ai_raw_access") is not False:
        raise ValueError("TripLens AI RAW access must remain disabled")
    return contract


def normalized_name(value: str) -> str:
    with_word_boundaries = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value.strip())
    return re.sub(r"[^a-z0-9]+", "_", with_word_boundaries.lower()).strip("_")


def reject_forbidden_columns(
    fields: Iterable[str], contract: dict[str, object], label: str
) -> None:
    forbidden = {normalized_name(str(item)) for item in contract["forbidden_columns"]}
    forbidden_prefixes = {
        normalized_name(str(item))
        for item in contract["forbidden_column_prefixes"]
    }
    present = {normalized_name(field) for field in fields}
    blocked = sorted(
        field
        for field in present
        if field in forbidden
        or any(
            field == prefix or field.startswith(prefix + "_")
            for prefix in forbidden_prefixes
        )
    )
    if blocked:
        raise ValueError(f"{label} contains forbidden answer/RAW columns: {', '.join(blocked)}")


def parse_enabled(raw: str, label: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{label} must be a Boolean enable value")


def normalize_boolean(raw: str, label: str) -> str:
    value = raw.strip().lower()
    if value in {"1", "1.0", "true", "yes", "on"}:
        return "1"
    if value in {"0", "0.0", "false", "no", "off"}:
        return "0"
    raise ValueError(f"{label} must be a Boolean state, got {raw!r}")


def seconds_to_ns(raw: str, label: str) -> int:
    try:
        seconds = Decimal(raw.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{label} is not a decimal time: {raw!r}") from exc
    if not seconds.is_finite() or seconds < 0:
        raise ValueError(f"{label} must be a non-negative finite time")
    nanoseconds = seconds * NANOSECONDS_PER_SECOND
    integral = nanoseconds.to_integral_value()
    if nanoseconds != integral:
        raise ValueError(f"{label} has finer than nanosecond precision")
    return int(integral)


def milliseconds_to_ns(raw: str, label: str) -> int:
    try:
        milliseconds = Decimal(raw.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{label} is not a decimal millisecond time: {raw!r}") from exc
    if not milliseconds.is_finite() or milliseconds < 0:
        raise ValueError(f"{label} must be a non-negative finite time")
    nanoseconds = milliseconds * NANOSECONDS_PER_MILLISECOND
    integral = nanoseconds.to_integral_value()
    if nanoseconds != integral:
        raise ValueError(f"{label} has finer than nanosecond precision")
    return int(integral)


def format_ns(nanoseconds: int) -> str:
    seconds, remainder = divmod(nanoseconds, NANOSECONDS_PER_SECOND)
    return f"{seconds}.{remainder:09d}"


def load_edge_rules(
    path: Path, contract: dict[str, object]
) -> list[EdgeRule]:
    fields, rows = read_csv(path)
    missing = RULE_COLUMNS.difference(fields)
    if missing:
        raise ValueError("ECMS event map is missing: " + ", ".join(sorted(missing)))
    reject_forbidden_columns(fields, contract, path.name)
    event_types = set(contract["allowed_event_types"])
    severities = set(contract["allowed_severities"])
    priorities = set(contract["allowed_priorities"])
    rules: list[EdgeRule] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str]] = set()
    for row_number, row in enumerate(rows, start=2):
        if not parse_enabled(row["enabled"], f"{path.name} row {row_number} enabled"):
            continue
        rule_id = row["rule_id"].strip()
        signal = row["source_signal"].strip()
        edge = row["edge"].strip().upper()
        event_type = row["event_type"].strip().upper()
        severity = row["severity"].strip().upper()
        priority = row["priority"].strip().upper()
        if not rule_id or rule_id in seen_ids:
            raise ValueError(f"{path.name} row {row_number} has an empty or duplicate rule_id")
        if not signal:
            raise ValueError(f"{rule_id}: source_signal is empty")
        if edge not in {"RISING", "FALLING"}:
            raise ValueError(f"{rule_id}: edge must be RISING or FALLING")
        if (signal, edge) in seen_edges:
            raise ValueError(f"{rule_id}: duplicate {edge} mapping for {signal}")
        if event_type not in event_types:
            raise ValueError(f"{rule_id}: unsupported event_type {event_type}")
        if severity not in severities:
            raise ValueError(f"{rule_id}: unsupported severity {severity}")
        if priority not in priorities:
            raise ValueError(f"{rule_id}: unsupported priority {priority}")
        try:
            order = int(row["order"])
        except ValueError as exc:
            raise ValueError(f"{rule_id}: order must be an integer") from exc
        values = {
            "tag": row["tag"].strip(),
            "state": row["state"].strip().upper(),
            "message": row["message_ko"].strip(),
            "logic_status": row["logic_status"].strip().upper(),
        }
        if any(not item for item in values.values()):
            raise ValueError(f"{rule_id}: tag, state, message and logic_status are required")
        rules.append(EdgeRule(
            order=order,
            rule_id=rule_id,
            source_signal=signal,
            edge=edge,
            tag=values["tag"],
            event_type=event_type,
            state=values["state"],
            severity=severity,
            priority=priority,
            message=values["message"],
            logic_status=values["logic_status"],
        ))
        seen_ids.add(rule_id)
        seen_edges.add((signal, edge))
    return sorted(rules, key=lambda item: (item.order, item.rule_id))


def make_event(
    *,
    contract: dict[str, object],
    run_id: str,
    event_ns: int,
    source_ns: int,
    platform_ns: int,
    system: str,
    source: str,
    tag: str,
    event_type: str,
    state: str,
    old_value: str,
    new_value: str,
    severity: str,
    priority: str,
    message: str,
    quality: str,
    logic_status: str,
    provenance: str,
    source_order: int,
    row_order: int,
    rule_order: int,
) -> dict[str, str | int]:
    return {
        "schema_version": str(contract["schema_version"]),
        "run_id": run_id,
        "sequence": "",
        "same_time_order": "",
        "event_time_s": format_ns(event_ns),
        "event_time_ns": str(event_ns),
        "source_time_s": format_ns(source_ns),
        "platform_time_s": format_ns(platform_ns),
        "system": system,
        "source": source,
        "tag": tag,
        "event_type": event_type,
        "state": state,
        "old_value": old_value,
        "new_value": new_value,
        "severity": severity,
        "priority": priority,
        "message": message,
        "quality": quality,
        "logic_status": logic_status,
        "provenance": provenance,
        "_source_order": source_order,
        "_row_order": row_order,
        "_rule_order": rule_order,
    }


def eventize_ecms_raw(
    *,
    raw_path: Path,
    rules_path: Path,
    contract: dict[str, object],
    run_id: str,
    source_order: int,
) -> tuple[list[dict[str, str | int]], int]:
    fields, rows = read_csv(raw_path)
    if len(rows) < 2:
        raise ValueError(f"{raw_path.name} must contain at least two RAW rows")
    reject_forbidden_columns(fields, contract, raw_path.name)
    time_column = "time_s" if "time_s" in fields else "time"
    if time_column not in fields:
        raise ValueError(f"{raw_path.name} is missing time_s/time")
    rules = load_edge_rules(rules_path, contract)
    missing = sorted({rule.source_signal for rule in rules}.difference(fields))
    if missing:
        raise ValueError(
            f"{raw_path.name} is missing enabled ECMS event signals: {', '.join(missing)}"
        )

    previous = {
        signal: normalize_boolean(rows[0][signal], f"row 2 {signal}")
        for signal in {rule.source_signal for rule in rules}
    }
    previous_time_ns = seconds_to_ns(rows[0][time_column], f"row 2 {time_column}")
    events: list[dict[str, str | int]] = []
    for row_number, row in enumerate(rows[1:], start=3):
        current_time_ns = seconds_to_ns(row[time_column], f"row {row_number} {time_column}")
        if current_time_ns < previous_time_ns:
            raise ValueError(f"{raw_path.name} time moves backwards at row {row_number}")
        current = {
            signal: normalize_boolean(row[signal], f"row {row_number} {signal}")
            for signal in previous
        }
        for rule in rules:
            old_value = previous[rule.source_signal]
            new_value = current[rule.source_signal]
            if old_value == new_value:
                continue
            edge = "RISING" if old_value == "0" and new_value == "1" else "FALLING"
            if edge != rule.edge:
                continue
            events.append(make_event(
                contract=contract,
                run_id=run_id,
                event_ns=current_time_ns,
                source_ns=current_time_ns,
                platform_ns=current_time_ns,
                system="ECMS",
                source=rule.source_signal,
                tag=rule.tag,
                event_type=rule.event_type,
                state=rule.state,
                old_value=old_value,
                new_value=new_value,
                severity=rule.severity,
                priority=rule.priority,
                message=rule.message,
                quality="GOOD",
                logic_status=rule.logic_status,
                provenance=f"ECMS_SIMULINK_STATE_TRANSITION:{rule.rule_id}",
                source_order=source_order,
                row_order=row_number,
                rule_order=rule.order,
            ))
        previous = current
        previous_time_ns = current_time_ns
    return events, len(rows)


def infer_event_type(event_class: str, tag: str) -> str:
    value = event_class.strip().upper()
    if value in {"TRIP"}:
        return "TRIP"
    if value in {"POSITION"} and (tag.endswith(".CLOSED") or "52" in tag):
        return "BREAKER"
    if value in {"PICKUP", "OPERATE"}:
        return "PROTECTION"
    if value in {"ALARM", "FAULT"}:
        return "PROCESS_ALARM"
    if value in {"RETURN", "CLEAR"}:
        return "RETURN"
    if value in {"COMMAND"}:
        return "COMMAND"
    if value in {"QUALITY"}:
        return "QUALITY"
    if value in {"STATE", "POSITION"}:
        return "STATE"
    return "PROCESS_ALARM"


def infer_state(
    *, event_type: str, alarm_state: str, tag: str, new_value: str
) -> str:
    if alarm_state.strip():
        return alarm_state.strip().upper()
    normalized = new_value.strip().upper()
    if event_type == "BREAKER":
        if normalized in {"0", "FALSE", "OPEN"}:
            return "OPEN"
        if normalized in {"1", "TRUE", "CLOSED"}:
            return "CLOSED"
    if event_type in {"TRIP", "PROTECTION", "PROCESS_ALARM"}:
        return "ACTIVE" if normalized not in {"0", "FALSE", "OFF", "CLEAR"} else "INACTIVE"
    if event_type == "RETURN":
        return "CLEARED"
    return normalized or "CHANGED"


def infer_severity(event_type: str, supplied: str) -> str:
    if supplied.strip():
        return supplied.strip().upper()
    if event_type == "TRIP":
        return "TRIP"
    if event_type == "PROCESS_ALARM":
        return "CRITICAL"
    if event_type == "PROTECTION":
        return "WARNING"
    return "INFO"


def priority_for(severity: str) -> str:
    return {
        "TRIP": "P1",
        "CRITICAL": "P2",
        "WARNING": "P3",
        "INFO": "P4",
    }[severity]


def adapt_event_file(
    *,
    path: Path,
    contract: dict[str, object],
    run_id: str,
    source_order: int,
) -> tuple[list[dict[str, str | int]], int]:
    fields, rows = read_csv(path)
    reject_forbidden_columns(fields, contract, path.name)
    required = {"system", "tag"}
    missing = required.difference(fields)
    if missing:
        raise ValueError(f"{path.name} is missing event columns: {', '.join(sorted(missing))}")
    if not rows:
        return [], 0
    allowed_systems = set(contract["allowed_systems"])
    allowed_event_types = set(contract["allowed_event_types"])
    allowed_severities = set(contract["allowed_severities"])
    allowed_quality = set(contract["allowed_quality"])
    events: list[dict[str, str | int]] = []
    for row_number, row in enumerate(rows, start=2):
        system = row["system"].strip().upper()
        tag = row["tag"].strip()
        if system not in allowed_systems:
            raise ValueError(f"{path.name} row {row_number}: unsupported system {system}")
        if not tag:
            raise ValueError(f"{path.name} row {row_number}: tag is empty")
        if row.get("source_time_ms", "").strip():
            source_ns = milliseconds_to_ns(
                row["source_time_ms"], f"{path.name} row {row_number} source_time_ms"
            )
        elif row.get("time_s", "").strip():
            source_ns = seconds_to_ns(
                row["time_s"], f"{path.name} row {row_number} time_s"
            )
        else:
            raise ValueError(f"{path.name} row {row_number}: source time is missing")
        if row.get("event_time_ms", "").strip():
            platform_ns = milliseconds_to_ns(
                row["event_time_ms"], f"{path.name} row {row_number} event_time_ms"
            )
        else:
            platform_ns = source_ns
        event_type = infer_event_type(row.get("event_class", ""), tag)
        if event_type not in allowed_event_types:
            raise ValueError(f"{path.name} row {row_number}: unsupported event type")
        old_value = row.get("old_value", "")
        new_value = row.get("new_value", "")
        alarm_state = row.get("alarm_state", "")
        if alarm_state and not old_value and not new_value:
            if alarm_state.strip().upper() == "ACTIVE":
                old_value, new_value = "0", "1"
            else:
                old_value, new_value = "1", "0"
        severity = infer_severity(event_type, row.get("severity", ""))
        if severity not in allowed_severities:
            raise ValueError(f"{path.name} row {row_number}: unsupported severity {severity}")
        quality = row.get("quality", "GOOD").strip().upper() or "GOOD"
        if quality not in allowed_quality:
            raise ValueError(f"{path.name} row {row_number}: unsupported quality {quality}")
        state = infer_state(
            event_type=event_type,
            alarm_state=alarm_state,
            tag=tag,
            new_value=new_value,
        )
        events.append(make_event(
            contract=contract,
            run_id=run_id,
            event_ns=source_ns,
            source_ns=source_ns,
            platform_ns=platform_ns,
            system=system,
            source=row.get("source_signal", "").strip() or path.stem,
            tag=tag,
            event_type=event_type,
            state=state,
            old_value=old_value,
            new_value=new_value,
            severity=severity,
            priority=priority_for(severity),
            message=row.get("description", "").strip() or tag,
            quality=quality,
            logic_status=(
                row.get("rule_status", "").strip().upper()
                or "SIMULATION_DERIVED_NOT_PLANT_APPROVED"
            ),
            provenance=row.get("provenance", "").strip() or "VPP_INTERNAL_EVENT",
            source_order=source_order,
            row_order=row_number,
            rule_order=0,
        ))
    return events, len(rows)


def finalize_events(
    events: list[dict[str, str | int]], contract: dict[str, object]
) -> list[dict[str, str]]:
    system_rank = {
        name: index for index, name in enumerate(contract["system_order"])
    }
    events.sort(key=lambda item: (
        int(item["event_time_ns"]),
        system_rank[str(item["system"])],
        int(item["_source_order"]),
        int(item["_row_order"]),
        int(item["_rule_order"]),
        str(item["tag"]),
    ))
    same_time_counts: dict[int, int] = {}
    columns = list(contract["columns"])
    result: list[dict[str, str]] = []
    for sequence, item in enumerate(events, start=1):
        time_ns = int(item["event_time_ns"])
        same_time_counts[time_ns] = same_time_counts.get(time_ns, 0) + 1
        item["sequence"] = str(sequence)
        item["same_time_order"] = str(same_time_counts[time_ns])
        result.append({column: str(item[column]) for column in columns})
    return result


def validate_events(
    fields: list[str], rows: list[dict[str, str]], contract: dict[str, object]
) -> None:
    expected_fields = list(contract["columns"])
    if fields != expected_fields:
        raise ValueError("EVENT.csv header does not exactly match TRIPLENS_EVENT_V1")
    reject_forbidden_columns(fields, contract, "EVENT.csv")
    allowed_systems = set(contract["allowed_systems"])
    allowed_event_types = set(contract["allowed_event_types"])
    allowed_severities = set(contract["allowed_severities"])
    allowed_priorities = set(contract["allowed_priorities"])
    allowed_quality = set(contract["allowed_quality"])
    previous_ns = -1
    same_time_expected = 0
    previous_same_time_ns: int | None = None
    unique_transitions: set[tuple[str, str, str, str]] = set()
    for index, row in enumerate(rows, start=1):
        if row["schema_version"] != contract["schema_version"]:
            raise ValueError(f"EVENT.csv row {index}: schema version mismatch")
        if int(row["sequence"]) != index:
            raise ValueError(f"EVENT.csv row {index}: sequence is not contiguous")
        event_ns = int(row["event_time_ns"])
        if event_ns < previous_ns:
            raise ValueError(f"EVENT.csv row {index}: event time moves backwards")
        if seconds_to_ns(row["event_time_s"], f"EVENT.csv row {index} event_time_s") != event_ns:
            raise ValueError(f"EVENT.csv row {index}: event_time_s/ns mismatch")
        seconds_to_ns(row["source_time_s"], f"EVENT.csv row {index} source_time_s")
        seconds_to_ns(row["platform_time_s"], f"EVENT.csv row {index} platform_time_s")
        if event_ns != previous_same_time_ns:
            same_time_expected = 1
            previous_same_time_ns = event_ns
        else:
            same_time_expected += 1
        if int(row["same_time_order"]) != same_time_expected:
            raise ValueError(f"EVENT.csv row {index}: same_time_order is invalid")
        if row["system"] not in allowed_systems:
            raise ValueError(f"EVENT.csv row {index}: unsupported system")
        if row["event_type"] not in allowed_event_types:
            raise ValueError(f"EVENT.csv row {index}: unsupported event_type")
        if row["severity"] not in allowed_severities:
            raise ValueError(f"EVENT.csv row {index}: unsupported severity")
        if row["priority"] not in allowed_priorities:
            raise ValueError(f"EVENT.csv row {index}: unsupported priority")
        if row["quality"] not in allowed_quality:
            raise ValueError(f"EVENT.csv row {index}: unsupported quality")
        for required in ("run_id", "source", "tag", "state", "message", "logic_status", "provenance"):
            if not row[required].strip():
                raise ValueError(f"EVENT.csv row {index}: {required} is empty")
        transition = (row["system"], row["tag"], row["state"], row["event_time_ns"])
        if transition in unique_transitions:
            raise ValueError(f"EVENT.csv row {index}: duplicate semantic transition")
        unique_transitions.add(transition)
        previous_ns = event_ns


def write_event_csv(
    path: Path, rows: list[dict[str, str]], contract: dict[str, object]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(contract["columns"]))
        writer.writeheader()
        writer.writerows(rows)


def build_bundle(
    *,
    bundle_dir: Path,
    run_id: str,
    contract_path: Path,
    ecms_raw: Path | None = None,
    ecms_rules: Path | None = None,
    source_events: Iterable[Path] = (),
    copy_internal_evidence: bool = True,
) -> list[dict[str, str]]:
    if not run_id.strip():
        raise ValueError("run_id is required")
    contract = load_contract(contract_path)
    source_event_paths = list(source_events)
    if ecms_raw is None and not source_event_paths:
        raise ValueError("at least one simulator RAW or deterministic event source is required")
    if ecms_raw is not None and ecms_rules is None:
        raise ValueError("--ecms-rules is required with --ecms-raw")

    resolved_bundle = bundle_dir.resolve()
    forbidden_targets = {Path("/").resolve(), Path.home().resolve(), ROOT.resolve()}
    if resolved_bundle in forbidden_targets or len(resolved_bundle.parts) < 3:
        raise ValueError(f"unsafe VPP bundle target: {resolved_bundle}")
    public_dir = resolved_bundle / "public"
    internal_dir = resolved_bundle / "internal"
    for owned_directory in (public_dir, internal_dir):
        if owned_directory.exists():
            shutil.rmtree(owned_directory)
    public_dir.mkdir(parents=True)
    internal_dir.mkdir(parents=True)

    events: list[dict[str, str | int]] = []
    sources: list[dict[str, object]] = []
    source_order = 0
    if ecms_raw is not None:
        source_order += 1
        ecms_events, row_count = eventize_ecms_raw(
            raw_path=ecms_raw,
            rules_path=ecms_rules,
            contract=contract,
            run_id=run_id,
            source_order=source_order,
        )
        events.extend(ecms_events)
        sources.append({
            "kind": "ECMS_RAW_INTERNAL",
            "file": ecms_raw.name,
            "sha256": sha256(ecms_raw),
            "row_count": row_count,
            "published_to_consumers": False,
        })
        if copy_internal_evidence:
            evidence = internal_dir / "evidence"
            evidence.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ecms_raw, evidence / ecms_raw.name)
            shutil.copy2(ecms_rules, evidence / ecms_rules.name)

    for path in source_event_paths:
        source_order += 1
        adapted, row_count = adapt_event_file(
            path=path,
            contract=contract,
            run_id=run_id,
            source_order=source_order,
        )
        events.extend(adapted)
        sources.append({
            "kind": "DETERMINISTIC_EVENT_INTERNAL",
            "file": path.name,
            "sha256": sha256(path),
            "row_count": row_count,
            "published_to_consumers": False,
        })
        if copy_internal_evidence:
            evidence = internal_dir / "evidence"
            evidence.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, evidence / path.name)

    final_events = finalize_events(events, contract)
    event_path = public_dir / "EVENT.csv"
    write_event_csv(event_path, final_events, contract)
    fields, reread = read_csv(event_path)
    validate_events(fields, reread, contract)

    system_counts = {
        system: sum(row["system"] == system for row in final_events)
        for system in contract["allowed_systems"]
    }
    manifest = {
        "schema_version": contract["schema_version"],
        "run_id": run_id,
        "architecture": "VPP_INTERNAL_RAW_TO_SINGLE_EVENT_EXTERNAL_V1",
        "public_output": {
            "file": "public/EVENT.csv",
            "sha256": sha256(event_path),
            "row_count": len(final_events),
            "system_counts": system_counts,
        },
        "internal_sources": sources,
        "consumer_boundary": {
            "alarm_console_inputs": ["EVENT.csv"],
            "triplens_ai_inputs": ["EVENT.csv"],
            "raw_published_to_alarm_console": False,
            "raw_published_to_triplens_ai": False,
        },
        "timestamp_policy": contract["timestamp_contract"],
        "scenario_answer_labels_present": False,
    }
    (internal_dir / "event-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return final_events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "config" / "event_contract_v1.json",
    )
    parser.add_argument("--ecms-raw", type=Path)
    parser.add_argument(
        "--ecms-rules",
        type=Path,
        default=ROOT / "config" / "ecms_event_map_v1.csv",
    )
    parser.add_argument("--source-event", action="append", type=Path, default=[])
    parser.add_argument("--no-copy-internal-evidence", action="store_true")
    args = parser.parse_args()

    events = build_bundle(
        bundle_dir=args.bundle_dir,
        run_id=args.run_id,
        contract_path=args.contract,
        ecms_raw=args.ecms_raw,
        ecms_rules=args.ecms_rules if args.ecms_raw else None,
        source_events=args.source_event,
        copy_internal_evidence=not args.no_copy_internal_evidence,
    )
    print("VPP_EVENT_BUNDLE_PASS")
    print(f"EVENT_ROWS={len(events)}")
    print(f"PUBLIC_OUTPUT={args.bundle_dir / 'public' / 'EVENT.csv'}")
    print("ALARM_CONSOLE_INPUTS=EVENT.csv")
    print("TRIPLENS_AI_INPUTS=EVENT.csv")
    print("RAW_PUBLISHED_TO_CONSUMERS=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
