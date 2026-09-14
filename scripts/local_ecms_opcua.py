#!/usr/bin/env python3
"""Single-server TripLens ECMS client for 8 breakers and 12 native valves."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BREAKER_MAP = ROOT / "config" / "local_ecms_breaker_nodes_v1.csv"
DEFAULT_VALVE_MAP = ROOT / "config" / "ecms_valve_nodes_v1.csv"
BREAKER_COMMANDS = frozenset({"OPEN", "CLOSE"})
VALVE_COMMAND_ROLES = {
    "MODE_AUTO": "AUTO_MAN_SELECT",
    "MANUAL_POSITION": "MANUAL_COMMAND",
    "FAULT_ENABLE": "FAULT_ENABLE",
    "FAULT_POSITION": "FAULT_FORCED_VALUE",
}
BOOLEAN_VALVE_ROLES = frozenset({"AUTO_MAN_SELECT", "FAULT_ENABLE"})

# OpenModelica may negotiate a 600 s secure-channel lifetime instead of the
# 3600 s requested by python-opcua.  That is valid and not a binding failure.
logging.getLogger("opcua").setLevel(logging.ERROR)


class LocalControlError(RuntimeError):
    """The live local-control contract could not be satisfied."""


@dataclass(frozen=True)
class BreakerBinding:
    equipment_id: str
    label_ko: str
    write_browse_name: str
    feedback_browse_name: str
    open_value: float
    close_value: float
    owner: str


def load_breaker_map(path: Path = DEFAULT_BREAKER_MAP) -> dict[str, BreakerBinding]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {
        "equipment_id", "label_ko", "write_browse_name",
        "feedback_browse_name", "open_value", "close_value", "owner",
    }
    if not rows or not required.issubset(rows[0]):
        missing = sorted(required.difference(rows[0] if rows else ()))
        raise LocalControlError(f"invalid breaker map; missing columns: {missing}")
    result: dict[str, BreakerBinding] = {}
    for row in rows:
        equipment_id = row["equipment_id"].strip().upper()
        if not equipment_id or equipment_id in result:
            raise LocalControlError(f"duplicate or empty breaker id: {equipment_id!r}")
        owner = row["owner"].strip().upper()
        if owner != "ECMS":
            raise LocalControlError(f"breaker {equipment_id} has forbidden owner {owner!r}")
        result[equipment_id] = BreakerBinding(
            equipment_id=equipment_id,
            label_ko=row["label_ko"].strip(),
            write_browse_name=row["write_browse_name"].strip(),
            feedback_browse_name=row["feedback_browse_name"].strip(),
            open_value=float(row["open_value"]),
            close_value=float(row["close_value"]),
            owner=owner,
        )
    if len(result) != 8:
        raise LocalControlError(f"expected 8 breakers, got {len(result)}")
    return result


def load_valve_map(path: Path = DEFAULT_VALVE_MAP) -> dict[str, dict[str, dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {
        "owner", "direction", "opcua_browse_name", "unit",
        "control_point_id", "role", "writable",
    }
    if not rows or not required.issubset(rows[0]):
        missing = sorted(required.difference(rows[0] if rows else ()))
        raise LocalControlError(f"invalid valve map; missing columns: {missing}")
    if len(rows) != 144:
        raise LocalControlError(f"expected 144 valve nodes, got {len(rows)}")
    browse_names = [row["opcua_browse_name"].strip() for row in rows]
    if len(set(browse_names)) != 144:
        raise LocalControlError("valve BrowseNames are not unique")

    result: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        equipment_id = row["control_point_id"].strip().upper()
        role = row["role"].strip().upper()
        direction = row["direction"].strip().upper()
        writable = row["writable"].strip() == "1"
        if row["owner"].strip().upper() not in {"ECMS", "OPENMODELICA"}:
            raise LocalControlError(f"invalid valve owner for {equipment_id}/{role}")
        if (direction == "WRITE") != writable:
            raise LocalControlError(f"direction/writable mismatch for {equipment_id}/{role}")
        roles = result.setdefault(equipment_id, {})
        if role in roles:
            raise LocalControlError(f"duplicate valve role: {equipment_id}/{role}")
        roles[role] = row

    if len(result) != 12:
        raise LocalControlError(f"expected 12 valves, got {len(result)}")
    expected_write = set(VALVE_COMMAND_ROLES.values())
    for equipment_id, roles in result.items():
        write_roles = {
            role for role, row in roles.items() if row["direction"].strip().upper() == "WRITE"
        }
        read_count = sum(
            row["direction"].strip().upper() == "READ" for row in roles.values()
        )
        if write_roles != expected_write or read_count != 8 or len(roles) != 12:
            raise LocalControlError(
                f"invalid 4-write/8-read valve contract for {equipment_id}"
            )
    return result


def walk_nodes(root: Any) -> Iterable[Any]:
    pending = deque(root.get_children())
    visited: set[str] = set()
    while pending:
        node = pending.popleft()
        identity = str(getattr(node, "nodeid", node))
        if identity in visited:
            continue
        visited.add(identity)
        yield node
        try:
            pending.extend(node.get_children())
        except Exception:
            continue


def find_nodes(client: Any, browse_names: Iterable[str]) -> dict[str, Any]:
    requested = set(browse_names)
    matches: dict[str, list[Any]] = {name: [] for name in requested}
    for node in walk_nodes(client.get_objects_node()):
        try:
            name = str(node.get_browse_name().Name)
        except Exception:
            continue
        if name in matches:
            matches[name].append(node)
    missing = sorted(name for name, nodes in matches.items() if not nodes)
    duplicate = sorted(name for name, nodes in matches.items() if len(nodes) > 1)
    if missing or duplicate:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if duplicate:
            details.append("duplicate=" + ",".join(duplicate))
        raise LocalControlError("OPC UA node binding failed: " + "; ".join(details))
    return {name: nodes[0] for name, nodes in matches.items()}


def scalar(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    result = float(value)
    if not math.isfinite(result):
        raise LocalControlError(f"non-finite OPC UA value: {value!r}")
    return result


def connect(endpoint: str, timeout_s: float) -> Any:
    from opcua import Client

    deadline = time.monotonic() + timeout_s
    error: Exception | None = None
    while time.monotonic() < deadline:
        client = Client(endpoint, timeout=min(5.0, timeout_s))
        try:
            client.connect()
            return client
        except Exception as exc:
            error = exc
            try:
                client.disconnect()
            except Exception:
                pass
            time.sleep(0.2)
    raise LocalControlError(f"cannot connect to {endpoint}: {error}")


def resolve_breaker_operation(
    breaker_map: dict[str, BreakerBinding], equipment_id: str, command: str
) -> tuple[BreakerBinding, float]:
    equipment_id = equipment_id.strip().upper()
    command = command.strip().upper()
    if command not in BREAKER_COMMANDS:
        raise LocalControlError("ECMS breaker command must be OPEN or CLOSE")
    try:
        binding = breaker_map[equipment_id]
    except KeyError as exc:
        raise LocalControlError(f"{equipment_id!r} is not an ECMS-owned breaker") from exc
    return binding, binding.open_value if command == "OPEN" else binding.close_value


def resolve_valve_operation(
    valve_map: dict[str, dict[str, dict[str, str]]],
    equipment_id: str,
    command: str,
    value: float,
) -> tuple[dict[str, str], float]:
    equipment_id = equipment_id.strip().upper()
    command = command.strip().upper()
    if command not in VALVE_COMMAND_ROLES:
        raise LocalControlError("unknown valve command: " + command)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise LocalControlError("valve command value must be within 0..1")
    role = VALVE_COMMAND_ROLES[command]
    if role in BOOLEAN_VALVE_ROLES and value not in (0.0, 1.0):
        raise LocalControlError(f"{command} accepts only 0 or 1")
    try:
        row = valve_map[equipment_id][role]
    except KeyError as exc:
        raise LocalControlError(f"unknown valve or missing role: {equipment_id}/{role}") from exc
    if row["direction"].strip().upper() != "WRITE" or row["writable"].strip() != "1":
        raise LocalControlError(f"read-only valve node rejected: {equipment_id}/{role}")
    return row, value


def check_live(
    endpoint: str,
    breaker_map: dict[str, BreakerBinding],
    valve_map: dict[str, dict[str, dict[str, str]]],
) -> dict[str, Any]:
    client = connect(endpoint, 5.0)
    try:
        breaker_names = {
            name for binding in breaker_map.values()
            for name in (binding.write_browse_name, binding.feedback_browse_name)
        }
        valve_names = {
            row["opcua_browse_name"].strip()
            for roles in valve_map.values() for row in roles.values()
        }
        nodes = find_nodes(client, breaker_names | valve_names)
        feedback = {
            equipment_id: scalar(nodes[binding.feedback_browse_name].get_value())
            for equipment_id, binding in breaker_map.items()
        }
        return {
            "status": "PASS",
            "endpoint": endpoint,
            "owner": "ECMS",
            "allowed_commands": sorted(BREAKER_COMMANDS),
            "breaker_count": len(breaker_map),
            "valve_count": len(valve_map),
            "valve_node_count": len(valve_names),
            "writable_valve_node_count": 48,
            "readable_valve_node_count": 96,
            "feedback": feedback,
        }
    finally:
        client.disconnect()


def read_valve_values(
    client: Any,
    equipment_id: str,
    roles: dict[str, dict[str, str]],
    nodes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    names = [row["opcua_browse_name"].strip() for row in roles.values()]
    if nodes is None:
        nodes = find_nodes(client, names)
    values: dict[str, dict[str, Any]] = {}
    for role, row in roles.items():
        browse_name = row["opcua_browse_name"].strip()
        values[role] = {
            "value": scalar(nodes[browse_name].get_value()),
            "unit": row["unit"].strip(),
            "direction": row["direction"].strip().upper(),
            "browse_name": browse_name,
        }
    return {
        "status": "PASS",
        "equipment_id": equipment_id,
        "node_count": len(values),
        "values": values,
    }


def read_valve(
    endpoint: str,
    valve_map: dict[str, dict[str, dict[str, str]]],
    equipment_id: str,
) -> dict[str, Any]:
    equipment_id = equipment_id.strip().upper()
    try:
        roles = valve_map[equipment_id]
    except KeyError as exc:
        raise LocalControlError(f"unknown valve: {equipment_id}") from exc
    client = connect(endpoint, 5.0)
    try:
        result = read_valve_values(client, equipment_id, roles)
        result["endpoint"] = endpoint
        return result
    finally:
        client.disconnect()



def wait_write_echo(node, expected: float, timeout_s: float = 30.0) -> float:
    """Wait for OpenModelica to commit an OPC UA input at a solver boundary."""
    deadline = time.monotonic() + timeout_s
    last = float("nan")
    while time.monotonic() < deadline:
        last = scalar(node.get_value())
        if math.isclose(last, expected, rel_tol=0.0, abs_tol=2e-6):
            return last
        time.sleep(0.02)
    raise LocalControlError(
        f"delayed write commit timeout after {timeout_s:.0f}s: "
        f"expected={expected}, actual={last}"
    )


# TRIPLENS_OPCUA_RUN_DELAYED_ECHO_V2

def write_valve(
    endpoint: str,
    valve_map: dict[str, dict[str, dict[str, str]]],
    equipment_id: str,
    command: str,
    value: float,
) -> dict[str, Any]:
    from opcua import ua

    equipment_id = equipment_id.strip().upper()
    command = command.strip().upper()
    row, value = resolve_valve_operation(valve_map, equipment_id, command, value)
    roles = valve_map[equipment_id]
    client = connect(endpoint, 5.0)
    try:
        all_names = [item["opcua_browse_name"].strip() for item in roles.values()]
        nodes = find_nodes(client, all_names)
        browse_name = row["opcua_browse_name"].strip()
        nodes[browse_name].set_value(ua.Variant(float(value), ua.VariantType.Float))
        echo = wait_write_echo(nodes[browse_name], value)
        time.sleep(0.05)
        result = read_valve_values(client, equipment_id, roles, nodes)
        result.update({
            "endpoint": endpoint,
            "command": command,
            "command_node": browse_name,
            "command_echo": echo,
        })
        return result
    finally:
        client.disconnect()


def write_breaker(
    endpoint: str,
    binding: BreakerBinding,
    command: str,
    value: float,
    feedback_timeout_s: float,
) -> dict[str, Any]:
    from opcua import ua

    client = connect(endpoint, 5.0)
    try:
        nodes = find_nodes(client, (binding.write_browse_name, binding.feedback_browse_name))
        command_node = nodes[binding.write_browse_name]
        feedback_node = nodes[binding.feedback_browse_name]
        command_node.set_value(ua.Variant(float(value), ua.VariantType.Float))
        echo = wait_write_echo(command_node, value)
        deadline = time.monotonic() + feedback_timeout_s
        feedback = scalar(feedback_node.get_value())
        while not math.isclose(feedback, value, abs_tol=1e-9) and time.monotonic() < deadline:
            time.sleep(0.05)
            feedback = scalar(feedback_node.get_value())
        matched = math.isclose(feedback, value, abs_tol=1e-9)
        return {
            "status": "PASS" if matched else "INTERLOCKED",
            "endpoint": endpoint,
            "owner": binding.owner,
            "equipment_id": binding.equipment_id,
            "label_ko": binding.label_ko,
            "command": command,
            "command_node": binding.write_browse_name,
            "command_echo": echo,
            "feedback_node": binding.feedback_browse_name,
            "feedback": feedback,
        }
    finally:
        client.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="opc.tcp://127.0.0.1:4841")
    parser.add_argument("--breaker-map", type=Path, default=DEFAULT_BREAKER_MAP)
    parser.add_argument("--valve-map", type=Path, default=DEFAULT_VALVE_MAP)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("check")
    writer = actions.add_parser("write")
    writer.add_argument("--equipment", required=True)
    writer.add_argument("--command", required=True)
    writer.add_argument("--feedback-timeout", type=float, default=2.0)
    reader = actions.add_parser("valve-read")
    reader.add_argument("--equipment", required=True)
    valve_writer = actions.add_parser("valve-write")
    valve_writer.add_argument("--equipment", required=True)
    valve_writer.add_argument("--command", required=True)
    valve_writer.add_argument("--value", required=True, type=float)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        breaker_map = load_breaker_map(args.breaker_map)
        valve_map = load_valve_map(args.valve_map)
        if args.action == "check":
            result = check_live(args.endpoint, breaker_map, valve_map)
        elif args.action == "write":
            binding, value = resolve_breaker_operation(
                breaker_map, args.equipment, args.command
            )
            result = write_breaker(
                args.endpoint, binding, args.command.strip().upper(),
                value, args.feedback_timeout,
            )
        elif args.action == "valve-read":
            result = read_valve(args.endpoint, valve_map, args.equipment)
        else:
            result = write_valve(
                args.endpoint, valve_map, args.equipment, args.command, args.value
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "PASS" else 3
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
