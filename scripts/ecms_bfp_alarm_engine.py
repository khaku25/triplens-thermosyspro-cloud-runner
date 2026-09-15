#!/usr/bin/env python3
"""Plant-wide Dual Log recorder and live protection/historian publisher.

EVENT.csv remains a human Alarm/Event journal.  RAW.csv remains the complete
numeric VPP historian.  The JSON snapshot is a presentation surface only: it
mirrors the latest real OPC UA values and never manufactures model time or
process values.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import queue
import shutil
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MARKER = "TRIPLENS_PROTECTION_DASHBOARD_V8_COMPLETE"
logging.getLogger("opcua").setLevel(logging.ERROR)

OPENMODELICA_CONTROL_NODE_IDS = {
    "run": 10001,
    "real_time_factor": 10002,
    "enable_stop_time": 10003,
    "model_time": 10004,
}

# V8 Modelica publishes every cause used by the common GT/ST trip matrix.
# Keeping this list explicit makes a missing live binding fail early instead
# of drawing a plausible but incomplete protection diagram.
COMMON_TRIP_MATRIX = (
    ("GT+ST", "DIRECT_GT_TRIP", "vppCauseDirectGTTrip"),
    ("GT+ST", "GT_BREAKER_OPEN_WHILE_RUNNING", "vppCauseGTBreakerOpenWhileRunning"),
    ("ST", "DIRECT_ST_TRIP", "vppCauseDirectSTTrip"),
    ("ST", "HP_DRUM_HH", "vppCauseHPDrumHH"),
    ("ST", "IP_DRUM_HH", "vppCauseIPDrumHH"),
    ("ST", "LP_DRUM_HH", "vppCauseLPDrumHH"),
    ("GT+ST", "HP_DRUM_LL", "vppCauseHPDrumLL"),
    ("GT+ST", "IP_DRUM_LL", "vppCauseIPDrumLL"),
    ("GT+ST", "LP_DRUM_LL", "vppCauseLPDrumLL"),
)

PROTECTION_CHAIN_NODES = {
    "GT": {
        "request": "vppGTTripRequest",
        "latch": "vppGTTripLatch",
        "breaker_command": "vpp52GTTripCmd",
        "breaker_closed": "vpp52GTClosed",
    },
    "ST": {
        "request": "vppSTTripRequest",
        "latch": "vppSTTripLatchPublished",
        "breaker_command": "vpp52STTripCmd",
        "breaker_closed": "vpp52STClosed",
    },
    "HP FWP": {
        "request": "vppHPFWPTripCommandNative",
        "latch": "vppHPFWPTripLatchNative",
        "breaker_command": "vppVCBA01TripCommandNative",
        "breaker_closed": "vppECMSVCBA01Closed",
    },
    "IP FWP": {
        "request": "vppIPFWPTripCommandNative",
        "latch": "vppIPFWPTripLatchNative",
        "breaker_command": "vppVCBB01TripCommandNative",
        "breaker_closed": "vppECMSVCBB01Closed",
    },
}

PROTECTION_DETAIL_NODES = {
    "vppExternalTripCommandNative", "vppExternalSTTripCommandNative",
    "vppGTTripResetNative", "vppSTTripResetNative",
    "vppHPDrumHHRaw", "vppIPDrumHHRaw", "vppLPDrumHHRaw",
    "vppHPDrumLLRaw", "vppIPDrumLLRaw", "vppLPDrumLLRaw",
    "vppGTTripCmd", "vppSTTripLatched",
    "vppHPFWPTripPushbuttonNative", "vppHPFWPResetPushbuttonNative",
    "vppIPFWPTripPushbuttonNative", "vppIPFWPResetPushbuttonNative",
    "vppVCBA01ClosedNative", "vppVCBB01ClosedNative",
    "vppHPFWPMotorEnergized", "vppHPFWPSpeedRPM",
    "vppHPFWPSpeedProven", "vppHPFWPRunning",
    "vppIPFWPMotorEnergized", "vppIPFWPSpeedRPM",
    "vppIPFWPSpeedProven", "vppIPFWPRunning",
}
PROTECTION_REQUIRED_NODES = set(PROTECTION_DETAIL_NODES)
PROTECTION_REQUIRED_NODES.update(node for _, _, node in COMMON_TRIP_MATRIX)
for _chain in PROTECTION_CHAIN_NODES.values():
    PROTECTION_REQUIRED_NODES.update(_chain.values())

SIGNALS = {
    "TRIP_PB": "vppLPFWPTripPushbuttonNative",
    "RESET_PB": "vppLPFWPResetPushbuttonNative",
    "TRIP_CMD": "vppLPFWPTripCommandNative",
    "TRIP_LATCH": "vppLPFWPTripLatchNative",
    "VCB_TRIP_CMD": "vppVCBA02TripCommandNative",
    "BREAKER_COMMAND": "vppVCBA02ClosedNative",
    "BREAKER_CLOSED": "vppECMSVCBA02Closed",
    "MOTOR_ENERGIZED": "vppLPFWPMotorEnergized",
    "SPEED_PROVEN": "vppLPFWPSpeedProven",
    "RUNNING": "vppLPFWPRunning",
    "SPEED_RPM": "vppLPFWPSpeedRPM",
    "NRV_OPEN": "vppLPFWPCheckValveOpen",
    "NRV_POSITION": "vppLPFWPCheckValveOpening",
    "MASS_FLOW_TH": "vppLPFWPMassFlowTH",
    "DELTA_P_PA": "vppLPFWPDeltaPPa",
    "DRUM_LEVEL_M": "vppLPDrumLevelM",
    "DRUM_PRESSURE_PA": "vppLPDrumPressurePa",
}

PUMP_CONTROL_SIGNALS = {
    "HP": {
        "trip_pb": "vppHPFWPTripPushbuttonNative",
        "reset_pb": "vppHPFWPResetPushbuttonNative",
        "trip_cmd": "vppHPFWPTripCommandNative",
        "latch": "vppHPFWPTripLatchNative",
        "breaker_trip_cmd": "vppVCBA01TripCommandNative",
        "breaker_command": "vppVCBA01ClosedNative",
        "breaker_closed": "vppECMSVCBA01Closed",
    },
    "IP": {
        "trip_pb": "vppIPFWPTripPushbuttonNative",
        "reset_pb": "vppIPFWPResetPushbuttonNative",
        "trip_cmd": "vppIPFWPTripCommandNative",
        "latch": "vppIPFWPTripLatchNative",
        "breaker_trip_cmd": "vppVCBB01TripCommandNative",
        "breaker_command": "vppVCBB01ClosedNative",
        "breaker_closed": "vppECMSVCBB01Closed",
    },
    "LP": {
        "trip_pb": SIGNALS["TRIP_PB"],
        "reset_pb": SIGNALS["RESET_PB"],
        "trip_cmd": SIGNALS["TRIP_CMD"],
        "latch": SIGNALS["TRIP_LATCH"],
        "breaker_trip_cmd": SIGNALS["VCB_TRIP_CMD"],
        "breaker_command": SIGNALS["BREAKER_COMMAND"],
        "breaker_closed": SIGNALS["BREAKER_CLOSED"],
    },
}
for _pump_signals in PUMP_CONTROL_SIGNALS.values():
    PROTECTION_REQUIRED_NODES.update(_pump_signals.values())

EVENT_COLUMNS = (
    "event_id", "event_sequence", "session_id", "incident_id", "model_time_s",
    "wall_time_utc", "priority", "event_class", "equipment", "tag", "state",
    "value", "unit", "message", "source", "acknowledged",
)
RAW_META_COLUMNS = (
    "record_sequence", "session_id", "incident_id", "model_time_s",
    "wall_time_utc", "quality",
)
RAW_DERIVED_COLUMNS = (
    "LP_BFP_TRIP_PB", "LP_BFP_RESET_PB", "LP_BFP_TRIP_CMD",
    "LP_BFP_TRIP_LATCH", "VCB_A02_TRIP_CMD", "VCB_A02_OPEN_CMD",
    "VCB_A02_CLOSE_CMD", "VCB_A02_CLOSED", "LP_BFP_SPEED_RPM",
    "LP_FW_FLOW_TH",
)
FORBIDDEN_AI_COLUMNS = {"scenario_id", "root_cause", "fault_injection", "fault_preset"}
VISIBLE_EVENT_CLASSES = {"ALARM", "OPERATOR_ACTION", "PROTECTION", "ACK", "SYSTEM"}
AI_EXCLUDED_HISTORIAN_SUFFIXES = (
    "FaultEnableNative", "FaultValueNative", "FaultActive",
)
MATRIX_SCENARIOS = {
    "direct_gt", "gt_breaker", "direct_st",
    "hp_drum_hh", "ip_drum_hh", "lp_drum_hh",
    "hp_drum_ll", "ip_drum_ll", "lp_drum_ll",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo-root", type=Path, required=True)
    result.add_argument("--endpoint", required=True)
    result.add_argument("--snapshot-file", type=Path, required=True)
    result.add_argument("--control-file", type=Path, required=True)
    result.add_argument("--output-root", type=Path)
    result.add_argument("--period", type=float, default=0.25)
    result.add_argument("--raw-period", type=float, default=1.0)
    result.add_argument("--watchdog-stall-s", type=float, default=3.0)
    result.add_argument("--watchdog-cooldown-s", type=float, default=10.0)
    result.add_argument("--real-time-factor", type=float, default=1.0)
    result.add_argument("--no-auto-resume", action="store_true")
    result.add_argument(
        "--watchdog-keep-stop-time", action="store_true",
        help="Do not disable OpenModelica stopTime when recovering a frozen runtime",
    )
    return result


def json_primitive(value: Any) -> Any:
    """Recursively convert OPC UA/numpy-ish values to strict JSON primitives."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else ""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, deque)):
        return [json_primitive(item) for item in value]
    # numpy scalars and similar wrappers expose item().
    if hasattr(value, "item"):
        try:
            return json_primitive(value.item())
        except Exception:
            pass
    return str(value)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(json_primitive(value), ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.02)


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def neutral_incident_id() -> str:
    return datetime.now().strftime("INCIDENT_%Y%m%d_%H%M%S_%f")[:-3]


def normalize_event(row: dict[str, Any], sequence: int, incident_id: str = "") -> dict[str, Any]:
    event_id = str(row.get("event_id", ""))
    session_id = str(row.get("session_id", ""))
    if not session_id and "-" in event_id:
        session_id = event_id.rsplit("-", 1)[0]
    normalized = {column: row.get(column, "") for column in EVENT_COLUMNS}
    normalized["event_id"] = event_id
    normalized["event_sequence"] = sequence
    normalized["session_id"] = session_id
    normalized["incident_id"] = str(row.get("incident_id", "")) or incident_id
    if not normalized["event_class"]:
        tag = str(row.get("tag", ""))
        state = str(row.get("state", ""))
        source = str(row.get("source", ""))
        if tag == "TRIP_REQUEST":
            normalized["tag"] = "LP_BFP_TRIP_PB"
            normalized["message"] = "LP BFP TRIP PB PRESSED"
            normalized["source"] = "OPERATOR"
            normalized["state"] = "PRESSED"
            normalized["event_class"] = "OPERATOR_ACTION"
        elif source == "OPERATOR" or state == "ACK":
            normalized["event_class"] = "ACK" if state == "ACK" else "OPERATOR_ACTION"
        elif tag in {"FLOW_LOW", "LEVEL_LOW", "LEVEL_LOW_LOW"}:
            normalized["event_class"] = "ALARM"
        elif tag in {"52A_OPEN", "BREAKER_OPEN"}:
            normalized["event_class"] = "PROTECTION"
        else:
            normalized["event_class"] = "LEGACY_EVENT"
    normalized["acknowledged"] = parse_bool(row.get("acknowledged", False))
    return normalized


def visible_event(row: dict[str, Any]) -> bool:
    """Keep only records that belong on a human Alarm/Event display."""
    return str(row.get("event_class", "")) in VISIBLE_EVENT_CLASSES


def ensure_event_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or not path.stat().st_size:
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            csv.DictWriter(stream, fieldnames=EVENT_COLUMNS).writeheader()
        return
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    legacy_required = {
        "event_id", "model_time_s", "wall_time_utc", "priority", "equipment",
        "tag", "state", "value", "unit", "message", "source", "acknowledged",
    }
    if not legacy_required.issubset(fields):
        missing = sorted(legacy_required.difference(fields))
        raise ValueError(f"EVENT.csv unsupported schema; missing={','.join(missing)}")
    scenario_map: dict[str, str] = {}
    converted: list[dict[str, Any]] = []
    for row in rows:
        legacy_scenario = str(row.get("scenario_id", ""))
        if legacy_scenario and legacy_scenario not in scenario_map:
            scenario_map[legacy_scenario] = f"LEGACY_INCIDENT_{len(scenario_map)+1:04d}"
        normalized = normalize_event(
            row, len(converted) + 1, scenario_map.get(legacy_scenario, "")
        )
        if visible_event(normalized):
            converted.append(normalized)
    same_schema = fields == list(EVENT_COLUMNS) or fields == EVENT_COLUMNS
    same_rows = len(converted) == len(rows)
    if same_schema and same_rows:
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.before-dual-log-v7-{stamp}.bak"))
    temporary = path.with_name(f"{path.name}.{os.getpid()}.migrate.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        writer.writerows(converted)
    os.replace(temporary, path)


def load_events(path: Path, limit: int = 2000) -> tuple[list[dict[str, Any]], int]:
    ensure_event_csv(path)
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    events = [normalize_event(row, sequence) for sequence, row in enumerate(rows, start=1)]
    by_id = {str(item["event_id"]): item for item in events}
    for item in events:
        if item["event_class"] == "ACK":
            target = by_id.get(str(item.get("value", "")))
            if target is not None:
                target["acknowledged"] = True
    return events[-limit:], len(events)


def append_csv(path: Path, fields: Iterable[str], row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writerow({column: row.get(column, "") for column in fields})
        stream.flush()
        os.fsync(stream.fileno())


def ensure_raw_csv(path: Path, tag_columns: list[str]) -> list[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    requested = list(RAW_META_COLUMNS) + tag_columns
    if not path.exists() or not path.stat().st_size:
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            csv.DictWriter(stream, fieldnames=requested).writeheader()
        return requested
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        existing = list(reader.fieldnames or [])
        rows = list(reader)
    if any(name in FORBIDDEN_AI_COLUMNS for name in existing):
        raise ValueError("RAW.csv contains forbidden answer/fault metadata columns")
    union = list(RAW_META_COLUMNS)
    union.extend(name for name in existing if name not in RAW_META_COLUMNS)
    union.extend(name for name in tag_columns if name not in union)
    if existing == union:
        return union
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.before-dual-log-v7-{stamp}.bak"))
    temporary = path.with_name(f"{path.name}.{os.getpid()}.schema.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=union)
        writer.writeheader()
        writer.writerows({name: row.get(name, "") for name in union} for row in rows)
    os.replace(temporary, path)
    return union


def raw_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        next(reader, None)
        return sum(1 for _ in reader)


def read_numeric_values(client: Any, live: Any, nodes: dict[str, Any]) -> dict[str, float | str]:
    names = list(nodes)
    result: dict[str, float | str] = {}
    for start in range(0, len(names), 200):
        batch_names = names[start:start + 200]
        batch_nodes = [nodes[name] for name in batch_names]
        try:
            values = client.get_values(batch_nodes)
            if len(values) != len(batch_nodes):
                raise RuntimeError(
                    f"OPC UA batch length mismatch: expected={len(batch_nodes)} actual={len(values)}"
                )
        except Exception:
            values = []
            for node in batch_nodes:
                try:
                    values.append(node.get_value())
                except Exception:
                    values.append(None)
        for name, value in zip(batch_names, values):
            try:
                result[name] = live.scalar(value)
            except Exception:
                result[name] = ""
    return result


def historian_metadata(name: str, registry_units: dict[str, str] | None = None) -> tuple[str, str, str]:
    """Return stable ``(group, kind, unit)`` metadata for a published tag."""
    upper = name.upper()
    if name == "time":
        return "System", "Time", "s"
    state_tokens = ("LATCH", "CAUSE", "HHRAW", "LLRAW")
    command_tokens = ("COMMAND", "CMD", "PUSHBUTTON", "RESETNATIVE")
    digital_tokens = (
        "CLOSED", "AVAILABLE", "ENERGIZED", "RUNNING", "PROVEN",
        "FAULTACTIVE", "CHECKVALVEOPEN",
    )
    if any(token in upper for token in state_tokens):
        kind = "Digital"
    elif any(token in upper for token in command_tokens) or upper.endswith("NATIVE"):
        kind = "Command"
    elif any(token in upper for token in digital_tokens):
        kind = "Digital"
    else:
        kind = "Analog"

    if name in PROTECTION_REQUIRED_NODES or any(
        token in upper for token in ("TRIP", "LATCH", "PROTECTION", "HHRAW", "LLRAW")
    ):
        group = "Protection"
    elif any(token in upper for token in ("BREAKER", "VCB", "52GT", "52ST", "CBIN", "CBTIE")):
        group = "Breaker"
    elif any(token in upper for token in ("VLV", "VALVE", "OPENING", "CV")):
        group = "Valve"
    elif any(token in upper for token in ("FWP", "BFP", "PUMP", "MOTOR", "SPEEDRPM")):
        group = "Pump"
    elif any(token in upper for token in ("DRUM", "PRESSURE", "TEMPERATURE", "FLOW", "LEVEL")):
        group = "Process"
    elif kind == "Command":
        group = "Command"
    else:
        group = "Other"

    unit = (registry_units or {}).get(name, "")
    if not unit:
        if "PRESSUREPA" in upper or upper.endswith("DPPA"):
            unit = "Pa"
        elif "MASFLOWTH" in upper or "MASSFLOWTH" in upper:
            unit = "t/h"
        elif "SPEEDRPM" in upper:
            unit = "rpm"
        elif "TEMPERATUREK" in upper:
            unit = "K"
        elif "LEVELM" in upper:
            unit = "m"
        elif kind == "Digital":
            unit = "BOOL"
        elif kind == "Command" and any(token in upper for token in (
            "PUSHBUTTON", "TRIPCOMMAND", "TRIPCMD", "RESET", "CLOSEDNATIVE",
            "MODEAUTONATIVE", "FAULTENABLENATIVE",
        )):
            unit = "BOOL"
        elif "OPENING" in upper or upper.endswith("CMD"):
            unit = "pu"
    return group, kind, unit


def numeric_changed(previous: Any, current: Any) -> bool:
    """Compare historian samples without treating missing first samples as edges."""
    if previous is None:
        return False
    try:
        return not math.isclose(float(previous), float(current), rel_tol=0.0, abs_tol=1e-12)
    except (TypeError, ValueError):
        return previous != current


def load_alarm_registry(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Alarm registry is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {
        "rule_id", "event_class", "priority", "equipment", "tag",
        "source_node", "active_when", "active_threshold", "return_threshold",
        "delay_s", "unit", "active_message", "return_message", "enabled",
    }
    fields = set(rows[0]) if rows else set()
    if not rows or not required.issubset(fields):
        raise ValueError("Alarm registry is empty or has an unsupported schema")
    enabled: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for row in rows:
        if not parse_bool(row.get("enabled", False)):
            continue
        rule_id = str(row["rule_id"]).strip()
        if not rule_id or rule_id in identifiers:
            raise ValueError(f"Alarm registry duplicate/empty rule_id: {rule_id}")
        identifiers.add(rule_id)
        active_when = str(row["active_when"]).strip().upper()
        if active_when not in {"HIGH", "LOW", "BASELINE_RATIO_LOW", "BASELINE_DELTA_LOW"}:
            raise ValueError(f"Unsupported active_when for {rule_id}: {active_when}")
        item = dict(row)
        item["rule_id"] = rule_id
        item["active_when"] = active_when
        item["active_threshold"] = float(row["active_threshold"])
        item["return_threshold"] = float(row["return_threshold"])
        item["delay_s"] = float(row.get("delay_s", 0.0) or 0.0)
        if item["delay_s"] < 0.0:
            raise ValueError(f"Negative delay_s for {rule_id}: {item['delay_s']}")
        enabled.append(item)
    return enabled


def discover_historian_nodes(
    client: Any, live: Any, extra_required: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    required = set(SIGNALS.values()).union(extra_required).union({"time"})
    matches: dict[str, list[Any]] = {}
    for node in live.walk_nodes(client.get_objects_node()):
        try:
            name = str(node.get_browse_name().Name)
        except Exception:
            continue
        ai_excluded = name.endswith(AI_EXCLUDED_HISTORIAN_SUFFIXES)
        if name in required or (name.startswith("vpp") and not ai_excluded):
            matches.setdefault(name, []).append(node)
    missing = sorted(name for name in required if not matches.get(name))
    duplicate_required = sorted(name for name in required if len(matches.get(name, [])) > 1)
    if missing or duplicate_required:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if duplicate_required:
            details.append("duplicate=" + ",".join(duplicate_required))
        raise RuntimeError("Dual Log OPC UA binding failed: " + "; ".join(details))
    duplicates = sorted(name for name, found in matches.items() if len(found) > 1)
    nodes = {name: found[0] for name, found in sorted(matches.items()) if len(found) == 1}
    probe = read_numeric_values(client, live, nodes)
    numeric_names: set[str] = set()
    for name, value in probe.items():
        if value == "":
            continue
        try:
            float(value)
        except (TypeError, ValueError):
            continue
        numeric_names.add(name)
    nodes = {name: node for name, node in nodes.items() if name in numeric_names}
    still_missing = sorted(required.difference(nodes))
    if still_missing:
        raise RuntimeError("Required historian nodes are nonnumeric: " + ",".join(still_missing))
    return nodes, duplicates


class AlarmEngine:
    def __init__(self, args: argparse.Namespace, live: Any, ua: Any, analyzer: Any) -> None:
        self.args = args
        self.live = live
        self.ua = ua
        self.analyzer = analyzer
        self.client: Any = None
        self.nodes: dict[str, Any] = {}
        self.historian_nodes: dict[str, Any] = {}
        self.alarm_nodes: dict[str, Any] = {}
        self.historian_rows: list[dict[str, Any]] = []
        self.historian_groups: list[dict[str, Any]] = []
        self.last_historian_values: dict[str, float | str] = {}
        self.historian_updated_model_time_s: float | str = ""
        self.protection_chain: list[dict[str, Any]] = []
        self.protection_matrix: list[dict[str, Any]] = []
        self.operator_pump_trains = list(PUMP_CONTROL_SIGNALS)
        self.operator_controls: list[dict[str, Any]] = []
        self.raw_fields: list[str] = []
        self.model_time_node: Any = None
        self.runtime_control_nodes: dict[str, Any] = {}
        self.session_id = datetime.now().strftime("SESSION_%Y%m%d_%H%M%S")
        runtime_root = (args.output_root or (args.repo_root.resolve() / "runtime")).resolve()
        self.event_dir = runtime_root / "events"
        self.incident_root = runtime_root / "incidents"
        self.internal_dir = runtime_root / "internal"
        self.event_csv = self.event_dir / "EVENT.csv"
        self.raw_csv = self.event_dir / "RAW.csv"
        self.analysis_json = self.event_dir / "DUAL_ANALYSIS.json"
        self.session_event_csv = self.event_dir / f"EVENT_{self.session_id}.csv"
        self.session_raw_csv = self.event_dir / f"RAW_{self.session_id}.csv"
        ensure_event_csv(self.event_csv)
        ensure_event_csv(self.session_event_csv)
        self.events, self.total_event_count = load_events(self.event_csv)
        self.session_events: deque[dict[str, Any]] = deque(maxlen=2000)
        self.event_sequence = self.total_event_count
        self.session_event_count = 0
        self.raw_sequence = 0
        self.session_raw_count = 0
        self.raw_buffer: deque[dict[str, Any]] = deque(maxlen=65)
        self.last_raw_model_time = -math.inf
        self.last_raw_edge_values: dict[str, float] = {}
        self.force_raw = True
        self.current_incident_id = ""
        self.current_event_csv: Path | None = None
        self.current_raw_csv: Path | None = None
        self.current_analysis_json: Path | None = None
        self.analysis: dict[str, Any] = {"status": "WAITING", "message": "Dual Log 수집 대기"}
        self.baseline: dict[str, float] | None = None
        self.last_conditions: dict[str, bool] | None = None
        self.last_values: dict[str, float] = {}
        self.last_model_time = -1.0
        self.observed_model_time: float | None = None
        self.model_time_changed_wall = time.monotonic()
        self.model_time_stalled_s = 0.0
        self.watchdog_enabled = not bool(args.no_auto_resume)
        self.watchdog_supported = False
        self.watchdog_state = "INITIALIZING" if self.watchdog_enabled else "DISABLED"
        self.watchdog_last_result = "NEVER"
        self.watchdog_error = ""
        self.watchdog_attempt_count = 0
        self.watchdog_success_count = 0
        self.watchdog_last_attempt_monotonic = -math.inf
        self.watchdog_last_attempt_utc = ""
        self.watchdog_resume_reference_time: float | None = None
        self.armed_at: float | None = None
        self.trip_at: float | None = None
        self.command_results: queue.Queue[tuple[str, bool, str]] = queue.Queue()
        self.command_busy = False
        self.command_state = "IDLE"
        self.stop_requested = False
        self.connection_state = "CONNECTING"
        self.connection_error = ""
        self.duplicate_historian_names: list[str] = []
        self.registry_path = args.repo_root.resolve() / "config" / "alarm_registry_v1.csv"
        self.alarm_rules = load_alarm_registry(self.registry_path)
        self.rule_baselines: dict[str, float] = {}
        self.rule_conditions: dict[str, bool] = {}
        self.rule_pending_since: dict[str, float] = {}
        self.rule_reported_active: set[str] = set()
        self.alarm_coverage: list[dict[str, Any]] = []

    def connect(self) -> None:
        self.disconnect()
        self.client = self.live.connect(self.args.endpoint, 5.0)
        rule_nodes = {str(rule["source_node"]) for rule in self.alarm_rules}
        all_numeric_nodes, self.duplicate_historian_names = discover_historian_nodes(
            self.client, self.live, rule_nodes.union(PROTECTION_REQUIRED_NODES)
        )
        # Alarm rules must still observe internal valve-fault states, but those
        # test-orchestration signals are intentionally excluded from AI RAW.
        self.historian_nodes = {
            name: node for name, node in all_numeric_nodes.items()
            if not name.endswith(AI_EXCLUDED_HISTORIAN_SUFFIXES)
        }
        # Bind cards/control-chain readers from the same browsed and numeric-
        # validated node set as the historian. Some field variants of
        # local_ecms_opcua.find_nodes returned None placeholders, which later
        # surfaced only as an unhelpful NoneType.get_value reconnect loop.
        self.nodes = {
            role: all_numeric_nodes[name] for role, name in SIGNALS.items()
        }
        self.alarm_nodes = {
            name: all_numeric_nodes[name] for name in sorted(rule_nodes)
        }
        self.operator_controls = [
            {
                "train": train,
                "trip_action": "PUMP_TRIP",
                "reset_action": "PUMP_RESET",
                "available": all(name in all_numeric_nodes for name in signals.values()),
            }
            for train, signals in PUMP_CONTROL_SIGNALS.items()
        ]
        invalid_roles = sorted(role for role, node in self.nodes.items() if node is None)
        if invalid_roles:
            raise RuntimeError("OPC UA signal binding returned null: " + ",".join(invalid_roles))
        self.alarm_coverage = [
            {
                "rule_id": rule["rule_id"],
                "event_class": rule["event_class"],
                "priority": rule["priority"],
                "equipment": rule["equipment"],
                "tag": rule["tag"],
                "source_node": rule["source_node"],
                "delay_s": float(rule.get("delay_s", 0.0)),
                "bound": rule["source_node"] in all_numeric_nodes,
                "state": "BASELINING",
                "pending_s": 0.0,
            }
            for rule in self.alarm_rules
        ]
        tag_columns = list(self.historian_nodes) + list(RAW_DERIVED_COLUMNS)
        self.raw_fields = ensure_raw_csv(self.raw_csv, tag_columns)
        all_tag_columns = [name for name in self.raw_fields if name not in RAW_META_COLUMNS]
        ensure_raw_csv(self.session_raw_csv, all_tag_columns)
        self.raw_sequence = raw_row_count(self.raw_csv)
        self.model_time_node = self.historian_nodes["time"]
        self.bind_runtime_controls()
        self.connection_state = "PASS"
        self.connection_error = ""
        self.force_raw = True
        # A reconnect, particularly after a time-zero runtime restart, begins
        # a fresh liveness window.  Never carry the previous server's frozen
        # age into the newly connected process.
        self.observed_model_time = None
        self.model_time_changed_wall = time.monotonic()
        self.model_time_stalled_s = 0.0

    def bind_runtime_controls(self) -> None:
        """Bind OpenModelica interactive controls without making them fatal.

        Alarm collection remains useful on read-only OPC UA servers.  The
        snapshot therefore reports unsupported controls explicitly instead of
        turning a watchdog capability difference into a reconnect loop.
        """
        self.runtime_control_nodes = {}
        try:
            for role, identifier in OPENMODELICA_CONTROL_NODE_IDS.items():
                self.runtime_control_nodes[role] = self.client.get_node(
                    self.ua.NodeId(identifier, 0)
                )
            float(self.live.scalar(self.runtime_control_nodes["model_time"].get_value()))
            self.runtime_control_nodes["run"].get_value()
            self.watchdog_supported = True
            self.watchdog_error = ""
            self.watchdog_state = "MONITORING" if self.watchdog_enabled else "DISABLED"
        except Exception as exc:
            self.runtime_control_nodes = {}
            self.watchdog_supported = False
            self.watchdog_state = "UNSUPPORTED" if self.watchdog_enabled else "DISABLED"
            self.watchdog_error = f"{type(exc).__name__}: {exc}"

    def disconnect(self) -> None:
        if self.client is not None:
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.client = None
        self.nodes = {}
        self.historian_nodes = {}
        self.alarm_nodes = {}
        self.runtime_control_nodes = {}
        self.watchdog_supported = False

    def read_values(self) -> tuple[float, dict[str, float]]:
        values = {role: self.live.scalar(node.get_value()) for role, node in self.nodes.items()}
        model_time = self.live.scalar(self.model_time_node.get_value())
        return model_time, values

    def observe_model_time(self, current: float) -> None:
        """Track solver liveness independently from OPC UA connectivity."""
        now = time.monotonic()
        advancing = self.observed_model_time is None or not math.isclose(
            current, self.observed_model_time, abs_tol=1e-12
        )
        if advancing:
            self.model_time_changed_wall = now
            if (
                self.watchdog_resume_reference_time is not None
                and current > self.watchdog_resume_reference_time + 1e-12
            ):
                self.watchdog_success_count += 1
                self.watchdog_last_result = "RESUMED"
                self.watchdog_resume_reference_time = None
            if self.watchdog_enabled and self.watchdog_supported:
                self.watchdog_state = "RUNNING"
        self.observed_model_time = current
        self.model_time_stalled_s = max(0.0, now - self.model_time_changed_wall)

    def handle_model_time_rewind(self, previous: float, current: float) -> None:
        """Reset sampling/alarm baselines after a genuine runtime time reset."""
        if previous < 0.0 or current >= previous - 1e-9:
            return
        self.last_raw_model_time = -math.inf
        self.last_raw_edge_values.clear()
        self.last_historian_values.clear()
        self.rule_baselines.clear()
        self.rule_conditions.clear()
        self.rule_pending_since.clear()
        self.rule_reported_active.clear()
        self.force_raw = True
        self.internal_audit(
            "MODEL_TIME_REWIND_OBSERVED",
            {"previous_model_time": previous, "current_model_time": current},
        )

    def resume_runtime(self, force: bool = False) -> bool:
        """Request a real solver resume through OpenModelica control nodes.

        Node 10004 is intentionally read-only here.  The watchdog can disable
        the configured stopTime and set Run=true, but it never writes a fake
        time value or restarts the executable behind the user's back.
        """
        if not self.watchdog_enabled and not force:
            self.watchdog_state = "DISABLED"
            return False
        if not self.watchdog_supported or not self.runtime_control_nodes:
            self.watchdog_state = "UNSUPPORTED"
            return False
        now = time.monotonic()
        cooldown = max(0.25, float(self.args.watchdog_cooldown_s))
        if not force and now - self.watchdog_last_attempt_monotonic < cooldown:
            return False
        self.watchdog_last_attempt_monotonic = now
        self.watchdog_last_attempt_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        self.watchdog_attempt_count += 1
        before = float(self.live.scalar(self.runtime_control_nodes["model_time"].get_value()))
        try:
            self.runtime_control_nodes["real_time_factor"].set_value(
                self.ua.Variant(float(self.args.real_time_factor), self.ua.VariantType.Double)
            )
            if not bool(self.args.watchdog_keep_stop_time):
                self.runtime_control_nodes["enable_stop_time"].set_value(
                    self.ua.Variant(False, self.ua.VariantType.Boolean)
                )
            self.runtime_control_nodes["run"].set_value(
                self.ua.Variant(True, self.ua.VariantType.Boolean)
            )
            self.watchdog_resume_reference_time = before
            self.watchdog_state = "RESUME_SENT"
            self.watchdog_last_result = "PENDING"
            self.watchdog_error = ""
            self.internal_audit(
                "AUTO_RESUME_RUNTIME" if not force else "MANUAL_RESUME_RUNTIME",
                {
                    "model_time_before": before,
                    "stop_time_disabled": not bool(self.args.watchdog_keep_stop_time),
                    "real_time_factor": float(self.args.real_time_factor),
                },
            )
            return True
        except Exception as exc:
            self.watchdog_state = "RESUME_FAILED"
            self.watchdog_last_result = "FAILED"
            self.watchdog_error = f"{type(exc).__name__}: {exc}"
            return False

    def watchdog_tick(self) -> None:
        if not self.watchdog_enabled:
            self.watchdog_state = "DISABLED"
            return
        if not self.watchdog_supported:
            self.watchdog_state = "UNSUPPORTED"
            return
        if self.model_time_stalled_s < float(self.args.watchdog_stall_s):
            return
        if self.watchdog_state not in {"RESUME_SENT", "RESUME_FAILED"}:
            self.watchdog_state = "FROZEN"
        self.resume_runtime()

    def start_incident(self) -> None:
        self.current_incident_id = neutral_incident_id()
        incident_dir = self.incident_root / self.current_incident_id
        incident_dir.mkdir(parents=True, exist_ok=True)
        self.current_event_csv = incident_dir / "EVENT.csv"
        self.current_raw_csv = incident_dir / "RAW.csv"
        self.current_analysis_json = incident_dir / "DUAL_ANALYSIS.json"
        ensure_event_csv(self.current_event_csv)
        incident_fields = ensure_raw_csv(
            self.current_raw_csv,
            [name for name in self.raw_fields if name not in RAW_META_COLUMNS],
        )
        for buffered in self.raw_buffer:
            row = dict(buffered)
            row["incident_id"] = self.current_incident_id
            append_csv(self.current_raw_csv, incident_fields, row)
        self.analysis = {"status": "COLLECTING", "message": "EVENT+RAW Dual Log 수집 중"}

    def add_event(
        self, priority: str, event_class: str, equipment: str, tag: str,
        state: str, value: float | str, unit: str, message: str, source: str,
        acknowledged: bool = False,
    ) -> dict[str, Any]:
        self.event_sequence += 1
        self.total_event_count += 1
        self.session_event_count += 1
        event = {
            "event_id": f"{self.session_id}-{self.event_sequence:05d}",
            "event_sequence": self.event_sequence,
            "session_id": self.session_id,
            "incident_id": self.current_incident_id,
            "model_time_s": round(self.last_model_time, 6),
            "wall_time_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "priority": priority,
            "event_class": event_class,
            "equipment": equipment,
            "tag": tag,
            "state": state,
            "value": value,
            "unit": unit,
            "message": message,
            "source": source,
            "acknowledged": bool(acknowledged),
        }
        self.events.append(event)
        self.events = self.events[-2000:]
        self.session_events.append(event)
        append_csv(self.event_csv, EVENT_COLUMNS, event)
        append_csv(self.session_event_csv, EVENT_COLUMNS, event)
        if self.current_event_csv is not None:
            append_csv(self.current_event_csv, EVENT_COLUMNS, event)
        self.force_raw = True
        return event

    def rule_condition(self, rule: dict[str, Any], value: float, previous: bool) -> bool:
        kind = str(rule["active_when"])
        active = float(rule["active_threshold"])
        returning = float(rule["return_threshold"])
        baseline = self.rule_baselines[rule["rule_id"]]
        if kind == "HIGH":
            return value >= (returning if previous else active)
        if kind == "LOW":
            return value < (returning if previous else active)
        if kind == "BASELINE_RATIO_LOW":
            reference = max(abs(baseline), 1.0)
            return abs(value) < (returning if previous else active) * reference
        if kind == "BASELINE_DELTA_LOW":
            return value < baseline - (returning if previous else active)
        raise ValueError(f"Unsupported rule kind: {kind}")

    def evaluate_registry(self, raw: dict[str, float | str]) -> None:
        """Evaluate every registered rule without replaying pre-existing alarms."""
        has_model_clock = hasattr(self, "last_model_time")
        model_time = float(getattr(self, "last_model_time", 0.0))
        pending = getattr(self, "rule_pending_since", None)
        if pending is None:
            # Compatibility for focused tests that construct the engine with
            # object.__new__ instead of running the full constructor.
            self.rule_pending_since = {}
        for index, rule in enumerate(self.alarm_rules):
            rule_id = str(rule["rule_id"])
            source = str(rule["source_node"])
            value = float(raw[source])
            if rule_id not in self.rule_baselines:
                self.rule_baselines[rule_id] = value
                self.rule_conditions[rule_id] = self.rule_condition(rule, value, False)
                self.alarm_coverage[index]["state"] = "ACTIVE_AT_ATTACH" if self.rule_conditions[rule_id] else "NORMAL"
                continue
            previous = self.rule_conditions[rule_id]
            condition_now = self.rule_condition(rule, value, previous)
            active = previous
            if previous:
                if not condition_now:
                    active = False
                    self.rule_pending_since.pop(rule_id, None)
            elif condition_now:
                started = self.rule_pending_since.setdefault(rule_id, model_time)
                # Focused legacy rule tests construct AlarmEngine without its
                # runtime clock.  They still exercise the threshold/hysteresis
                # transition with zero delay; a real engine always owns
                # last_model_time and therefore always uses model-time delay.
                delay_s = max(0.0, float(rule.get("delay_s", 0.0))) if has_model_clock else 0.0
                active = model_time - started >= delay_s - 1e-12
                if not active:
                    self.alarm_coverage[index]["state"] = "PENDING"
                    self.alarm_coverage[index]["pending_s"] = round(
                        max(0.0, model_time - started), 6
                    )
            else:
                self.rule_pending_since.pop(rule_id, None)

            if active != previous:
                if active:
                    self.add_event(
                        str(rule["priority"]), str(rule["event_class"]),
                        str(rule["equipment"]), str(rule["tag"]), "ACTIVE",
                        round(value, 6), str(rule["unit"]),
                        str(rule["active_message"]), "OPENMODELICA_PHYSICS",
                    )
                    self.rule_reported_active.add(rule_id)
                    self.rule_pending_since.pop(rule_id, None)
                elif rule_id in self.rule_reported_active:
                    self.add_event(
                        "INFO", str(rule["event_class"]), str(rule["equipment"]),
                        str(rule["tag"]), "RETURN", round(value, 6),
                        str(rule["unit"]), str(rule["return_message"]),
                        "OPENMODELICA_PHYSICS",
                    )
                    self.rule_reported_active.discard(rule_id)
            self.rule_conditions[rule_id] = active
            if active:
                self.alarm_coverage[index]["state"] = "ACTIVE"
                self.alarm_coverage[index]["pending_s"] = 0.0
            elif not condition_now:
                self.alarm_coverage[index]["state"] = "NORMAL"
                self.alarm_coverage[index]["pending_s"] = 0.0

    def evaluate(self, values: dict[str, float]) -> None:
        """LP-BFP card values are read here; plant alarms use the RAW sample."""
        if self.baseline is None:
            self.baseline = dict(values)

    def evaluate_live_alarms(self) -> None:
        """Sample all plant alarm sources at UI cadence, independent of RAW CSV cadence."""
        raw = read_numeric_values(self.client, self.live, self.alarm_nodes)
        self.evaluate_registry(raw)

    def write_input(self, browse_name: str, value: float) -> float:
        client = self.live.connect(self.args.endpoint, 5.0)
        try:
            node = self.live.find_nodes(client, (browse_name,))[browse_name]
            # OpenModelica exposes top-level Real inputs as OPC UA Float.
            node.set_value(self.ua.Variant(float(value), self.ua.VariantType.Float))
            if hasattr(self.live, "wait_write_echo"):
                return float(self.live.wait_write_echo(node, value, 30.0))
            deadline = time.monotonic() + 30.0
            last = math.nan
            while time.monotonic() < deadline:
                last = self.live.scalar(node.get_value())
                if math.isclose(last, value, abs_tol=2e-6):
                    return last
                time.sleep(0.02)
            raise RuntimeError(f"write commit timeout: {browse_name} expected={value} actual={last}")
        finally:
            client.disconnect()

    def wait_chain(self, expected: dict[str, float], timeout_s: float = 30.0) -> None:
        client = self.live.connect(self.args.endpoint, 5.0)
        try:
            nodes = self.live.find_nodes(client, expected)
            deadline = time.monotonic() + timeout_s
            actual: dict[str, float] = {}
            while time.monotonic() < deadline:
                actual = {name: self.live.scalar(nodes[name].get_value()) for name in expected}
                if all(math.isclose(actual[name], target, abs_tol=2e-6) for name, target in expected.items()):
                    return
                time.sleep(0.05)
            raise RuntimeError(f"protection chain timeout: expected={expected} actual={actual}")
        finally:
            client.disconnect()

    def execute_pump_trip(self, train: str) -> None:
        signals = PUMP_CONTROL_SIGNALS[train]
        pressed = False
        try:
            self.write_input(signals["trip_pb"], 1.0)
            pressed = True
            self.wait_chain({
                signals["trip_cmd"]: 1.0,
                signals["latch"]: 1.0,
                signals["breaker_trip_cmd"]: 1.0,
                signals["breaker_closed"]: 0.0,
            })
        finally:
            # A momentary operator PB must never be left asserted after a
            # failed downstream proof.
            if pressed:
                self.write_input(signals["trip_pb"], 0.0)

    def execute_pump_reset(self, train: str) -> None:
        signals = PUMP_CONTROL_SIGNALS[train]
        # Fail safe: remove the trip stimulus and prove/open the breaker before
        # clearing the latch.  Reclose only after reset and trip-command clear
        # are both proven.
        self.write_input(signals["trip_pb"], 0.0)
        self.write_input(signals["breaker_command"], 0.0)
        self.wait_chain({signals["breaker_closed"]: 0.0})
        pressed = False
        try:
            self.write_input(signals["reset_pb"], 1.0)
            pressed = True
            self.wait_chain({
                signals["trip_cmd"]: 0.0,
                signals["latch"]: 0.0,
                signals["breaker_trip_cmd"]: 0.0,
            })
        finally:
            if pressed:
                self.write_input(signals["reset_pb"], 0.0)
        self.write_input(signals["breaker_command"], 1.0)
        self.wait_chain({signals["breaker_closed"]: 1.0})

    def start_control(self, action: str, train: str = "LP") -> None:
        train = train.upper()
        equipment = f"{train} BFP"
        if self.command_busy:
            self.add_event("MEDIUM", "SYSTEM", equipment, "CONTROL_BUSY", "REJECTED", action, "", "이전 제어 동작 처리 중", "ECMS_UI")
            return
        if action in {"PUMP_TRIP", "PUMP_RESET"} and train not in PUMP_CONTROL_SIGNALS:
            self.add_event("HIGH", "SYSTEM", equipment, "CONTROL_PATH_FAILURE", "REJECTED", action, "", f"지원하지 않는 펌프 계열: {train}", "ECMS_UI")
            return
        self.command_busy = True
        work_item = f"{action}:{train}" if action in {"PUMP_TRIP", "PUMP_RESET"} else action
        self.command_state = work_item + "_PENDING"

        def worker() -> None:
            try:
                if action == "PUMP_TRIP":
                    self.execute_pump_trip(train)
                elif action == "PUMP_RESET":
                    self.execute_pump_reset(train)
                elif action == "FAULT_OPEN":
                    breaker_map = self.live.load_breaker_map(
                        self.args.repo_root.resolve() / "config" / "local_ecms_breaker_nodes_v1.csv"
                    )
                    binding, value = self.live.resolve_breaker_operation(breaker_map, "VCB-A02", "OPEN")
                    result = self.live.write_breaker(self.args.endpoint, binding, "OPEN", value, 5.0)
                    if result.get("status") != "PASS":
                        raise RuntimeError(json.dumps(result, ensure_ascii=False))
                else:
                    raise RuntimeError(f"unknown control action: {action}")
                self.command_results.put((work_item, True, "PASS"))
            except Exception as exc:
                self.command_results.put((work_item, False, str(exc)))

        thread_name = work_item.lower().replace(":", "-")
        threading.Thread(target=worker, name=f"dual-log-{thread_name}", daemon=True).start()

    def drain_command_results(self) -> None:
        while True:
            try:
                action, passed, detail = self.command_results.get_nowait()
            except queue.Empty:
                return
            self.command_busy = False
            self.command_state = action + ("_PASS" if passed else "_FAIL")
            self.force_raw = True
            if not passed:
                train = action.rsplit(":", 1)[-1] if ":" in action else "LP"
                self.add_event("HIGH", "SYSTEM", f"{train} BFP", "CONTROL_PATH_FAILURE", "ACTIVE", action, "", f"제어 경로 실패 · {detail}", "ECMS_UI")

    def internal_audit(self, action: str, detail: dict[str, Any]) -> None:
        self.internal_dir.mkdir(parents=True, exist_ok=True)
        path = self.internal_dir / "FAULT_INJECTION_AUDIT.jsonl"
        record = {
            "wall_time_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "model_time_s": self.last_model_time,
            "model_time_advancing": self.model_time_stalled_s < float(self.args.watchdog_stall_s),
            "model_time_stalled_s": round(self.model_time_stalled_s, 3),
            "watchdog_enabled": self.watchdog_enabled,
            "watchdog_supported": self.watchdog_supported,
            "watchdog_stall_threshold_s": float(self.args.watchdog_stall_s),
            "watchdog_state": self.watchdog_state,
            "watchdog_last_result": self.watchdog_last_result,
            "watchdog_error": self.watchdog_error,
            "watchdog_attempt_count": self.watchdog_attempt_count,
            "watchdog_success_count": self.watchdog_success_count,
            "watchdog_last_attempt_utc": self.watchdog_last_attempt_utc,
            "action": action,
            "detail": detail,
            "excluded_from_ai_input": True,
        }
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def process_control(self) -> None:
        path = self.args.control_file
        if not path.exists():
            return
        try:
            command = json.loads(path.read_text(encoding="utf-8-sig"))
            path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            return
        action = str(command.get("action", "")).upper()
        if action == "STOP":
            self.stop_requested = True
        elif action == "RESUME_RUNTIME":
            sent = self.resume_runtime(force=True)
            self.command_state = "RESUME_RUNTIME_SENT" if sent else "RESUME_RUNTIME_FAIL"
        elif action == "ARM":
            delay = max(0.0, min(3600.0, float(command.get("delay_s", 10.0))))
            self.armed_at = self.last_model_time
            self.trip_at = self.last_model_time + delay
            self.internal_audit("ARM_FAULT_OPEN", {"delay_s": delay})
        elif action == "TRIP_NOW":
            self.armed_at = None
            self.trip_at = None
            self.start_incident()
            self.add_event("HIGH", "OPERATOR_ACTION", "LP BFP", "LP_BFP_TRIP_PB", "PRESSED", 1, "BOOL", "LP BFP TRIP PB PRESSED", "OPERATOR")
            self.start_control("PUMP_TRIP", "LP")
        elif action == "BEGIN_SCENARIO":
            scenario = str(command.get("scenario", "")).strip().lower()
            if scenario not in MATRIX_SCENARIOS:
                self.command_state = "BEGIN_SCENARIO_FAIL"
                self.internal_audit(
                    "BEGIN_MATRIX_SCENARIO_REJECTED", {"scenario": scenario}
                )
                return
            self.armed_at = None
            self.trip_at = None
            self.start_incident()
            self.command_state = f"SCENARIO:{scenario}_PASS"
            self.internal_audit(
                "BEGIN_MATRIX_SCENARIO", {"scenario": scenario}
            )
            self.force_raw = True
        elif action == "RESET":
            self.armed_at = None
            self.trip_at = None
            if not self.current_incident_id:
                self.start_incident()
            self.add_event("INFO", "OPERATOR_ACTION", "LP BFP", "LP_BFP_RESET_PB", "PRESSED", 1, "BOOL", "LP BFP RESET PB PRESSED", "OPERATOR")
            self.start_control("PUMP_RESET", "LP")
        elif action in {"PUMP_TRIP", "PUMP_RESET"}:
            train = str(command.get("train", "")).upper()
            if train not in PUMP_CONTROL_SIGNALS:
                self.add_event("HIGH", "SYSTEM", "PUMP CONTROL", "CONTROL_PATH_FAILURE", "REJECTED", train, "", f"지원하지 않는 펌프 계열: {train}", "ECMS_UI")
                return
            self.armed_at = None
            self.trip_at = None
            if action == "PUMP_TRIP":
                self.start_incident()
                priority, suffix, verb = "HIGH", "TRIP", "TRIP"
            else:
                if not self.current_incident_id:
                    self.start_incident()
                priority, suffix, verb = "INFO", "RESET", "RESET"
            self.add_event(
                priority, "OPERATOR_ACTION", f"{train} BFP",
                f"{train}_BFP_{suffix}_PB", "PRESSED", 1, "BOOL",
                f"{train} BFP {verb} PB PRESSED", "OPERATOR",
            )
            self.start_control(action, train)
        elif action == "ACK":
            event_id = str(command.get("event_id", ""))
            matched = next((item for item in self.events if item["event_id"] == event_id), None)
            if matched is not None:
                matched["acknowledged"] = True
                self.add_event("INFO", "ACK", matched["equipment"], matched["tag"], "ACK", event_id, "", f"알람 확인: {matched['message']}", "OPERATOR", True)

    def maybe_fire_scenario(self) -> None:
        if self.trip_at is None or self.last_model_time < self.trip_at:
            return
        self.trip_at = None
        self.start_incident()
        self.internal_audit("FIRE_FAULT_OPEN", {"incident_id": self.current_incident_id})
        self.start_control("FAULT_OPEN")

    def update_live_snapshot_rows(self, raw: dict[str, float | str]) -> None:
        """Build full historian and protection views from one real RAW sample."""
        registry_units = {
            str(rule["source_node"]): str(rule.get("unit", ""))
            for rule in self.alarm_rules
        }
        rows: list[dict[str, Any]] = []
        group_counts: dict[str, int] = {}
        for name in sorted(raw):
            value = json_primitive(raw[name])
            group, kind, unit = historian_metadata(name, registry_units)
            changed = numeric_changed(self.last_historian_values.get(name), value)
            rows.append({
                "name": name,
                "value": value,
                "group": group,
                "kind": kind,
                "unit": unit,
                "changed": changed,
                "quality": "GOOD",
            })
            group_counts[group] = group_counts.get(group, 0) + 1
        self.historian_rows = rows
        self.historian_groups = [
            {"name": name, "count": group_counts[name]}
            for name in sorted(group_counts)
        ]
        self.historian_updated_model_time_s = round(float(self.last_model_time), 9)

        matrix: list[dict[str, Any]] = []
        for domain, cause, source in COMMON_TRIP_MATRIX:
            value = json_primitive(raw.get(source, ""))
            matrix.append({
                "domain": domain,
                "cause": cause,
                "source": source,
                "value": value,
                "active": value != "" and float(value) >= 0.5,
            })
        self.protection_matrix = matrix

        chain: list[dict[str, Any]] = []
        for domain, names in PROTECTION_CHAIN_NODES.items():
            values = {key: json_primitive(raw.get(node, "")) for key, node in names.items()}
            closed = values["breaker_closed"]
            chain.append({
                "train": domain,
                "domain": domain,
                "request": values["request"],
                "latch": values["latch"],
                "breaker_command": values["breaker_command"],
                "breaker_closed": closed,
                "state": "OPEN" if closed != "" and float(closed) < 0.5 else "CLOSED",
            })
        self.protection_chain = chain
        self.last_historian_values = dict(raw)

    def raw_edge_changed(self, raw: dict[str, float | str]) -> bool:
        watched = (
            SIGNALS["TRIP_PB"], SIGNALS["RESET_PB"], SIGNALS["TRIP_CMD"],
            SIGNALS["TRIP_LATCH"], SIGNALS["VCB_TRIP_CMD"],
            SIGNALS["BREAKER_COMMAND"], SIGNALS["BREAKER_CLOSED"],
            SIGNALS["MOTOR_ENERGIZED"], SIGNALS["RUNNING"], SIGNALS["NRV_OPEN"],
        )
        changed = False
        for name in watched:
            value = raw.get(name, "")
            if value == "":
                continue
            number = float(value)
            previous = self.last_raw_edge_values.get(name)
            if previous is not None and not math.isclose(previous, number, abs_tol=1e-9):
                changed = True
            self.last_raw_edge_values[name] = number
        return changed

    def record_raw_if_due(self) -> None:
        due = self.last_model_time >= self.last_raw_model_time + self.args.raw_period - 1e-9
        if not due and not self.force_raw:
            return
        raw = read_numeric_values(self.client, self.live, self.historian_nodes)
        self.update_live_snapshot_rows(raw)
        if not due and not self.raw_edge_changed(raw):
            self.force_raw = False
            return
        self.raw_edge_changed(raw)
        self.raw_sequence += 1
        self.session_raw_count += 1
        row: dict[str, Any] = {
            "record_sequence": self.raw_sequence,
            "session_id": self.session_id,
            "incident_id": self.current_incident_id,
            "model_time_s": round(self.last_model_time, 9),
            "wall_time_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "quality": "GOOD",
        }
        row.update(raw)
        trip_command = float(raw[SIGNALS["VCB_TRIP_CMD"]])
        closed_command = float(raw[SIGNALS["BREAKER_COMMAND"]])
        row.update({
            "LP_BFP_TRIP_PB": raw[SIGNALS["TRIP_PB"]],
            "LP_BFP_RESET_PB": raw[SIGNALS["RESET_PB"]],
            "LP_BFP_TRIP_CMD": raw[SIGNALS["TRIP_CMD"]],
            "LP_BFP_TRIP_LATCH": raw[SIGNALS["TRIP_LATCH"]],
            "VCB_A02_TRIP_CMD": trip_command,
            "VCB_A02_OPEN_CMD": max(1.0 - closed_command, trip_command),
            "VCB_A02_CLOSE_CMD": closed_command * (1.0 - trip_command),
            "VCB_A02_CLOSED": raw[SIGNALS["BREAKER_CLOSED"]],
            "LP_BFP_SPEED_RPM": raw[SIGNALS["SPEED_RPM"]],
            "LP_FW_FLOW_TH": raw[SIGNALS["MASS_FLOW_TH"]],
        })
        append_csv(self.raw_csv, self.raw_fields, row)
        append_csv(self.session_raw_csv, self.raw_fields, row)
        self.raw_buffer.append(dict(row))
        if self.current_raw_csv is not None:
            append_csv(self.current_raw_csv, self.raw_fields, row)
        self.last_raw_model_time = self.last_model_time
        self.force_raw = False

    def refresh_analysis(self) -> None:
        event_path = self.current_event_csv or self.event_csv
        raw_path = self.current_raw_csv or self.raw_csv
        if not event_path.exists() or not raw_path.exists():
            return
        try:
            self.analysis = self.analyzer.analyze_dual_logs(event_path, raw_path)
            atomic_json(self.analysis_json, self.analysis)
            if self.current_analysis_json is not None:
                atomic_json(self.current_analysis_json, self.analysis)
        except Exception as exc:
            self.analysis = {"status": "FAIL", "message": f"Dual-input analysis failed: {exc}"}

    def publish(self) -> None:
        payload = {
            "status": self.connection_state,
            "error": self.connection_error,
            "endpoint": self.args.endpoint,
            "session_id": self.session_id,
            "incident_id": self.current_incident_id,
            "model_time_s": self.last_model_time,
            "model_time_advancing": self.model_time_stalled_s < float(self.args.watchdog_stall_s),
            "model_time_stalled_s": round(self.model_time_stalled_s, 3),
            "event_csv": str(self.current_event_csv or self.event_csv),
            "raw_csv": str(self.current_raw_csv or self.raw_csv),
            "analysis_json": str(self.current_analysis_json or self.analysis_json),
            "armed_at_s": self.armed_at,
            "trip_at_s": self.trip_at,
            "command_busy": self.command_busy,
            "command_state": self.command_state,
            "event_count_total": self.total_event_count,
            "event_count_session": self.session_event_count,
            "raw_count_session": self.session_raw_count,
            "historian_tag_count": len(self.historian_nodes),
            "duplicate_historian_names": self.duplicate_historian_names,
            "historian_updated_model_time_s": self.historian_updated_model_time_s,
            "historian_groups": self.historian_groups,
            "historian_rows": self.historian_rows,
            "protection_chain": self.protection_chain,
            "protection_matrix": self.protection_matrix,
            "pump_control_trains": self.operator_pump_trains,
            "operator_controls": self.operator_controls,
            "values": self.last_values,
            "events": self.events,
            "session_events": list(self.session_events),
            "alarm_rule_count": len(self.alarm_rules),
            "alarm_bound_count": sum(bool(item["bound"]) for item in self.alarm_coverage),
            "alarm_active_count": sum(item["state"] in {"ACTIVE", "ACTIVE_AT_ATTACH"} for item in self.alarm_coverage),
            "alarm_pending_count": sum(item["state"] == "PENDING" for item in self.alarm_coverage),
            "alarm_coverage": self.alarm_coverage,
            "analysis": self.analysis,
        }
        atomic_json(self.args.snapshot_file, payload)

    def run(self) -> int:
        last_analysis_time = 0.0
        while not self.stop_requested:
            self.process_control()
            self.drain_command_results()
            if self.client is None:
                try:
                    self.connect()
                except Exception as exc:
                    self.connection_state = "RECONNECTING"
                    self.connection_error = f"{type(exc).__name__}: {exc}"
                    self.publish()
                    time.sleep(2.0)
                    continue
            cycle = time.monotonic()
            try:
                previous_model_time = self.last_model_time
                current_model_time, current_values = self.read_values()
                self.handle_model_time_rewind(previous_model_time, current_model_time)
                self.last_model_time, self.last_values = current_model_time, current_values
                self.observe_model_time(self.last_model_time)
                self.watchdog_tick()
                self.connection_state = "PASS"
                self.connection_error = ""
                self.evaluate(self.last_values)
                self.evaluate_live_alarms()
                self.maybe_fire_scenario()
                self.record_raw_if_due()
                if time.monotonic() - last_analysis_time >= 1.0:
                    self.refresh_analysis()
                    last_analysis_time = time.monotonic()
                self.publish()
            except Exception as exc:
                self.connection_state = "RECONNECTING"
                self.connection_error = f"{type(exc).__name__}: {exc}"
                self.disconnect()
                self.publish()
            remaining = self.args.period - (time.monotonic() - cycle)
            if remaining > 0:
                time.sleep(remaining)
        self.disconnect()
        self.connection_state = "STOPPED"
        self.publish()
        return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not 0.10 <= args.period <= 5.0:
        raise ValueError("period must be within 0.10..5.0 seconds")
    if not 0.25 <= args.raw_period <= 60.0:
        raise ValueError("raw-period must be within 0.25..60.0 model seconds")
    if not 1.0 <= args.watchdog_stall_s <= 300.0:
        raise ValueError("watchdog-stall-s must be within 1..300 seconds")
    if not 0.25 <= args.watchdog_cooldown_s <= 300.0:
        raise ValueError("watchdog-cooldown-s must be within 0.25..300 seconds")
    if not 0.01 <= args.real_time_factor <= 100.0:
        raise ValueError("real-time-factor must be within 0.01..100")
    root = args.repo_root.resolve()
    sys.path.insert(0, str(root / "scripts"))
    import local_ecms_opcua as live  # pylint: disable=import-error,import-outside-toplevel
    import triplens_dual_log_analyzer as analyzer  # pylint: disable=import-error,import-outside-toplevel
    from opcua import ua  # pylint: disable=import-error,import-outside-toplevel
    return AlarmEngine(args, live, ua, analyzer).run()


if __name__ == "__main__":
    raise SystemExit(main())
