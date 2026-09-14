#!/usr/bin/env python3
"""Verify delayed OpenModelica OPC UA input commits and persistence."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import time
from collections import deque
from pathlib import Path


BREAKER_COMMANDS = (
    "vppECMS52GTClosedCommandNative",
    "vppECMS52STClosedCommandNative",
    "vppECMSCBInAClosedCommandNative",
    "vppECMSCBInBClosedCommandNative",
    "vppECMSCBTieClosedCommandNative",
    "vppVCBA01ClosedNative",
    "vppVCBA02ClosedNative",
    "vppVCBB01ClosedNative",
)


def find_nodes(client, required: set[str]) -> dict[str, object]:
    found: dict[str, object] = {}
    duplicates: set[str] = set()
    pending = deque(client.get_objects_node().get_children())
    visited: set[str] = set()
    while pending:
        node = pending.popleft()
        identity = str(node.nodeid)
        if identity in visited:
            continue
        visited.add(identity)
        try:
            name = str(node.get_browse_name().Name)
            if name in required:
                if name in found:
                    duplicates.add(name)
                found[name] = node
            pending.extend(node.get_children())
        except Exception:
            continue
    missing = sorted(required.difference(found))
    if missing or duplicates:
        raise RuntimeError(
            "live binding failed: "
            + ("missing=" + ",".join(missing) if missing else "")
            + ("; " if missing and duplicates else "")
            + ("duplicate=" + ",".join(sorted(duplicates)) if duplicates else "")
        )
    return found


def different_value(name: str, before: float) -> float:
    is_discrete = (
        name.endswith("ModeAutoNative")
        or name.endswith("FaultEnableNative")
        or name in BREAKER_COMMANDS
    )
    if is_discrete:
        return 0.99 if before >= 0.5 else 0.01
    return 0.271 if before >= 0.5 else 0.729


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=0.0, abs_tol=2e-6)


def wait_delayed_commit(
    node,
    expected: float,
    time_node,
    minimum_advance: float,
    timeout_s: float,
) -> tuple[float, float]:
    """Allow the old echo until a solver boundary, then require persistence."""
    deadline = time.monotonic() + timeout_s
    accepted_at: float | None = None
    last = float("nan")
    while time.monotonic() < deadline:
        last = float(node.get_value())
        model_time = float(time_node.get_value())
        if accepted_at is None:
            if close(last, expected):
                accepted_at = model_time
        else:
            if not close(last, expected):
                raise RuntimeError(
                    f"value changed after commit: expected={expected}, actual={last}"
                )
            if model_time >= accepted_at + minimum_advance - 1e-9:
                return accepted_at, model_time
        time.sleep(0.02)
    if accepted_at is None:
        raise RuntimeError(f"delayed commit timeout: expected={expected}, actual={last}")
    raise RuntimeError(
        f"model time did not advance after commit: accepted={accepted_at}, "
        f"current={float(time_node.get_value())}"
    )


def wait_value(node, expected: float, timeout_s: float) -> float:
    deadline = time.monotonic() + timeout_s
    last = float("nan")
    while time.monotonic() < deadline:
        last = float(node.get_value())
        if close(last, expected):
            return last
        time.sleep(0.02)
    raise RuntimeError(f"restore timeout: expected={expected}, actual={last}")


def load_contract(path: Path) -> tuple[list[str], list[str], set[str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 144:
        raise RuntimeError(f"expected 144 valve contract rows, got {len(rows)}")
    required = {row["opcua_browse_name"] for row in rows}
    if len(required) != 144:
        raise RuntimeError("valve BrowseNames are not unique")
    writes = [row["opcua_browse_name"] for row in rows if row["direction"] == "WRITE"]
    reads = [row["opcua_browse_name"] for row in rows if row["direction"] == "READ"]
    commands = writes + list(BREAKER_COMMANDS)
    if len(commands) != 56 or len(reads) != 96:
        raise RuntimeError("expected 56 commands and 96 reads")
    return commands, reads, required | set(BREAKER_COMMANDS)


def main() -> int:
    logging.getLogger("opcua").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--mode", choices=("live", "read"), required=True)
    parser.add_argument("--step-size", type=float, default=0.04)
    parser.add_argument("--commit-timeout", type=float, default=180.0)
    args = parser.parse_args()

    from opcua import Client, ua

    commands, reads, required = load_contract(args.map)
    client = Client(args.endpoint, timeout=10)
    client.connect()
    try:
        nodes = find_nodes(client, required)
        time_node = client.get_node(ua.NodeId(10004, 0))
        run_node = client.get_node(ua.NodeId(10001, 0))
        run_node.set_value(ua.Variant(True, ua.VariantType.Boolean))

        if args.mode == "read":
            values = [float(nodes[name].get_value()) for name in reads]
            if not all(math.isfinite(value) for value in values):
                raise RuntimeError("non-finite valve physics value")
            print(json.dumps({
                "status": "PASS", "mode": "read", "total_nodes": 144,
                "commands": 56, "reads": 96,
                "model_time": float(time_node.get_value()),
            }, sort_keys=True))
            return 0

        tested = 0
        for name in commands:
            node = nodes[name]
            original = float(node.get_value())
            probe = different_value(name, original)
            node.set_value(ua.Variant(float(probe), ua.VariantType.Float))
            try:
                wait_delayed_commit(
                    node,
                    probe,
                    time_node,
                    minimum_advance=max(3.0 * args.step_size, 0.12),
                    timeout_s=args.commit_timeout,
                )
            finally:
                node.set_value(ua.Variant(float(original), ua.VariantType.Float))
                wait_value(node, original, args.commit_timeout)
            tested += 1
            if tested % 8 == 0 or tested == len(commands):
                print(
                    f"WRITE_PROGRESS {tested}/{len(commands)} "
                    f"model_time={float(time_node.get_value())}",
                    flush=True,
                )

        values = [float(nodes[name].get_value()) for name in reads]
        if not all(math.isfinite(value) for value in values):
            raise RuntimeError("non-finite valve physics value")
        print(json.dumps({
            "status": "PASS", "mode": "run-delayed-commit",
            "changed_write_pass": tested, "restore_pass": tested,
            "read_pass": len(reads), "total_nodes": 144,
            "model_time": float(time_node.get_value()),
        }, sort_keys=True))
        return 0
    finally:
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
