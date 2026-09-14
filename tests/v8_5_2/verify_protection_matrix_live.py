#!/usr/bin/env python3
"""Live OPC UA proof for the independent GT/ST protection boundary.

The six drum trips are structurally covered by the Modelica self-test.  This
live proof exercises the writable trip/reset and breaker command inputs and
proves three matrix branches against a running solver:

* direct ST trip -> ST only
* 52GT open while running -> GT and ST
* direct GT trip -> GT and ST
* HP/IP BFP operator PB -> independent BFP latch and logical VCB open

Each case can be executed in a fresh solver process.  The verifier never
requires HP/IP hydraulic speed to become zero: V8.5 intentionally preserves
the proven V7 ThermoSysPro pump boundary.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from collections import deque
from pathlib import Path


INPUTS = {
    "gt_trip": "vppExternalTripCommandNative",
    "st_trip": "vppExternalSTTripCommandNative",
    "gt_reset": "vppGTTripResetNative",
    "st_reset": "vppSTTripResetNative",
    "gt_closed_command": "vppECMS52GTClosedCommandNative",
    "st_closed_command": "vppECMS52STClosedCommandNative",
}

OUTPUTS = {
    "gt_request": "vppGTTripRequest",
    "st_request": "vppSTTripRequest",
    "gt_latch": "vppGTTripLatch",
    "st_latch": "vppSTTripLatchPublished",
    "gt_trip_cmd": "vpp52GTTripCmd",
    "st_trip_cmd": "vpp52STTripCmd",
    "gt_closed": "vpp52GTClosed",
    "st_closed": "vpp52STClosed",
    "direct_gt_cause": "vppCauseDirectGTTrip",
    "direct_st_cause": "vppCauseDirectSTTrip",
    "gt_breaker_cause": "vppCauseGTBreakerOpenWhileRunning",
}

PUMPS = {
    "hp": {
        "trip": "vppHPFWPTripPushbuttonNative",
        "reset": "vppHPFWPResetPushbuttonNative",
        "closed_command": "vppVCBA01ClosedNative",
        "trip_command": "vppHPFWPTripCommandNative",
        "latch": "vppHPFWPTripLatchNative",
        "vcb_trip": "vppVCBA01TripCommandNative",
        "closed": "vppECMSVCBA01Closed",
        "motor": "vppHPFWPMotorEnergized",
        "speed_rpm": "vppHPFWPSpeedRPM",
        "speed_proven": "vppHPFWPSpeedProven",
        "running": "vppHPFWPRunning",
    },
    "ip": {
        "trip": "vppIPFWPTripPushbuttonNative",
        "reset": "vppIPFWPResetPushbuttonNative",
        "closed_command": "vppVCBB01ClosedNative",
        "trip_command": "vppIPFWPTripCommandNative",
        "latch": "vppIPFWPTripLatchNative",
        "vcb_trip": "vppVCBB01TripCommandNative",
        "closed": "vppECMSVCBB01Closed",
        "motor": "vppIPFWPMotorEnergized",
        "speed_rpm": "vppIPFWPSpeedRPM",
        "speed_proven": "vppIPFWPSpeedProven",
        "running": "vppIPFWPRunning",
    },
}


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def find_nodes(client, required: set[str]) -> dict[str, object]:
    found: dict[str, object] = {}
    duplicate: set[str] = set()
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
                    duplicate.add(name)
                found[name] = node
            pending.extend(node.get_children())
        except Exception:
            continue
    missing = sorted(required.difference(found))
    if missing or duplicate:
        raise RuntimeError(
            "protection binding failed: missing="
            + ",".join(missing)
            + "; duplicate="
            + ",".join(sorted(duplicate))
        )
    return found


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=0.0, abs_tol=2e-5)


def wait_values(
    nodes: dict[str, object], expected: dict[str, float], timeout: float, label: str
) -> dict[str, float]:
    deadline = time.monotonic() + timeout
    actual: dict[str, float] = {}
    while time.monotonic() < deadline:
        actual = {name: float(nodes[name].get_value()) for name in expected}
        if all(close(actual[name], value) for name, value in expected.items()):
            return actual
        time.sleep(0.02)
    raise RuntimeError(f"{label} timeout: expected={expected}, actual={actual}")


def set_real(node, value: float) -> None:
    from opcua import ua

    node.set_value(ua.Variant(float(value), ua.VariantType.Float))


def safe_reset(
    nodes: dict[str, object], timeout: float, reset_gt: bool, reset_st: bool
) -> None:
    """Reset latch memories without allowing an automatic breaker reclose."""
    if reset_gt:
        set_real(nodes[INPUTS["gt_trip"]], 0.0)
        set_real(nodes[INPUTS["gt_closed_command"]], 0.0)
    if reset_st:
        set_real(nodes[INPUTS["st_trip"]], 0.0)
        set_real(nodes[INPUTS["st_closed_command"]], 0.0)
    deasserted = {}
    if reset_gt:
        deasserted[INPUTS["gt_trip"]] = 0.0
        deasserted[INPUTS["gt_closed_command"]] = 0.0
    if reset_st:
        deasserted[INPUTS["st_trip"]] = 0.0
        deasserted[INPUTS["st_closed_command"]] = 0.0
    wait_values(nodes, deasserted, timeout, "safe reset precondition")
    # GT must be cleared before ST because ST reset is interlocked by the GT
    # request/latch.  Simultaneous reset pulses would be order-dependent.
    if reset_gt:
        set_real(nodes[INPUTS["gt_reset"]], 1.0)
        wait_values(
            nodes,
            {
                INPUTS["gt_reset"]: 1.0,
                OUTPUTS["gt_latch"]: 0.0,
                OUTPUTS["gt_request"]: 0.0,
                OUTPUTS["gt_breaker_cause"]: 0.0,
            },
            timeout,
            "safe GT latch reset",
        )
        set_real(nodes[INPUTS["gt_reset"]], 0.0)
        wait_values(nodes, {INPUTS["gt_reset"]: 0.0}, timeout, "GT reset release")
    if reset_st:
        set_real(nodes[INPUTS["st_reset"]], 1.0)
        wait_values(
            nodes,
            {INPUTS["st_reset"]: 1.0, OUTPUTS["st_latch"]: 0.0},
            timeout,
            "safe ST latch reset",
        )
        set_real(nodes[INPUTS["st_reset"]], 0.0)
        wait_values(nodes, {INPUTS["st_reset"]: 0.0}, timeout, "ST reset release")
    if reset_gt:
        set_real(nodes[INPUTS["gt_closed_command"]], 1.0)
    if reset_st:
        set_real(nodes[INPUTS["st_closed_command"]], 1.0)
    closed = {}
    if reset_gt:
        closed[OUTPUTS["gt_closed"]] = 1.0
    if reset_st:
        closed[OUTPUTS["st_closed"]] = 1.0
    wait_values(nodes, closed, timeout, "breaker reclose after released reset")


def proof_pump_chain(
    nodes: dict[str, object], timeout: float, label: str, contract: dict[str, str]
) -> dict[str, float]:
    # Begin with the PB released and breaker close command asserted.
    set_real(nodes[contract["trip"]], 0.0)
    set_real(nodes[contract["reset"]], 0.0)
    set_real(nodes[contract["closed_command"]], 1.0)
    wait_values(
        nodes,
        {
            contract["trip"]: 0.0,
            contract["reset"]: 0.0,
            contract["closed_command"]: 1.0,
            contract["closed"]: 1.0,
        },
        timeout,
        f"{label} initial state",
    )
    set_real(nodes[contract["trip"]], 1.0)
    actual = wait_values(
        nodes,
        {
            contract["trip_command"]: 1.0,
            contract["latch"]: 1.0,
            contract["vcb_trip"]: 1.0,
            contract["closed"]: 0.0,
            contract["motor"]: 0.0,
            contract["running"]: 0.0,
        },
        timeout,
        f"{label} trip chain",
    )
    # These two values intentionally remain on the preserved V7 hydraulic
    # boundary, but they must still be published and readable because the
    # plant-wide alarm/RAW engine binds them.
    actual[contract["speed_rpm"]] = float(nodes[contract["speed_rpm"]].get_value())
    actual[contract["speed_proven"]] = float(nodes[contract["speed_proven"]].get_value())

    # Safe reset: release Trip, command the breaker open, pulse Reset, then
    # restore the close command only after the latch is proven clear.
    set_real(nodes[contract["trip"]], 0.0)
    set_real(nodes[contract["closed_command"]], 0.0)
    wait_values(
        nodes,
        {contract["trip"]: 0.0, contract["closed_command"]: 0.0},
        timeout,
        f"{label} reset precondition",
    )
    set_real(nodes[contract["reset"]], 1.0)
    wait_values(
        nodes,
        {contract["reset"]: 1.0, contract["latch"]: 0.0},
        timeout,
        f"{label} latch reset",
    )
    set_real(nodes[contract["reset"]], 0.0)
    wait_values(nodes, {contract["reset"]: 0.0}, timeout, f"{label} reset release")
    set_real(nodes[contract["closed_command"]], 1.0)
    wait_values(
        nodes,
        {contract["closed_command"]: 1.0, contract["closed"]: 1.0},
        timeout,
        f"{label} reclose",
    )
    return actual


def main() -> int:
    logging.getLogger("opcua").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--case",
        choices=("hp", "ip", "st", "gt_breaker", "gt"),
        required=True,
        help="Run exactly one isolated proof trajectory.",
    )
    args = parser.parse_args()

    from opcua import Client, ua

    required = set(INPUTS.values()) | set(OUTPUTS.values())
    for contract in PUMPS.values():
        required.update(contract.values())
    client = Client(args.endpoint, timeout=10)
    client.connect()
    result: dict[str, object] = {"status": "FAIL", "endpoint": args.endpoint}
    nodes: dict[str, object] = {}
    try:
        nodes = find_nodes(client, required)
        run_node = client.get_node(ua.NodeId(10001, 0))
        time_node = client.get_node(ua.NodeId(10004, 0))
        run_node.set_value(ua.Variant(True, ua.VariantType.Boolean))

        actual: dict[str, float]
        if args.case in PUMPS:
            label = "HP BFP" if args.case == "hp" else "IP BFP"
            actual = proof_pump_chain(nodes, args.timeout, label, PUMPS[args.case])
        else:
            # Each non-pump case starts from a new, untripped solver.  Prove
            # that precondition without issuing any reset/open trajectory.
            set_real(nodes[INPUTS["gt_trip"]], 0.0)
            set_real(nodes[INPUTS["st_trip"]], 0.0)
            set_real(nodes[INPUTS["gt_closed_command"]], 1.0)
            set_real(nodes[INPUTS["st_closed_command"]], 1.0)
            wait_values(nodes, {
                OUTPUTS["gt_latch"]: 0.0,
                OUTPUTS["st_latch"]: 0.0,
                OUTPUTS["gt_closed"]: 1.0,
                OUTPUTS["st_closed"]: 1.0,
            }, args.timeout, "fresh untripped precondition")
            if args.case == "st":
                set_real(nodes[INPUTS["st_trip"]], 1.0)
                actual = wait_values(nodes, {
                    OUTPUTS["direct_st_cause"]: 1.0,
                    OUTPUTS["st_request"]: 1.0,
                    OUTPUTS["st_latch"]: 1.0,
                    OUTPUTS["st_trip_cmd"]: 1.0,
                    OUTPUTS["st_closed"]: 0.0,
                    OUTPUTS["gt_latch"]: 0.0,
                    OUTPUTS["gt_trip_cmd"]: 0.0,
                }, args.timeout, "direct ST isolation")
            elif args.case == "gt_breaker":
                set_real(nodes[INPUTS["gt_closed_command"]], 0.0)
                actual = wait_values(nodes, {
                    OUTPUTS["gt_breaker_cause"]: 1.0,
                    OUTPUTS["gt_latch"]: 1.0,
                    OUTPUTS["st_latch"]: 1.0,
                    OUTPUTS["gt_trip_cmd"]: 1.0,
                    OUTPUTS["st_trip_cmd"]: 1.0,
                    OUTPUTS["gt_closed"]: 0.0,
                    OUTPUTS["st_closed"]: 0.0,
                }, args.timeout, "52GT-open common trip")
            else:
                set_real(nodes[INPUTS["gt_trip"]], 1.0)
                actual = wait_values(nodes, {
                    OUTPUTS["direct_gt_cause"]: 1.0,
                    OUTPUTS["gt_request"]: 1.0,
                    OUTPUTS["st_request"]: 1.0,
                    OUTPUTS["gt_latch"]: 1.0,
                    OUTPUTS["st_latch"]: 1.0,
                    OUTPUTS["gt_trip_cmd"]: 1.0,
                    OUTPUTS["st_trip_cmd"]: 1.0,
                    OUTPUTS["gt_closed"]: 0.0,
                    OUTPUTS["st_closed"]: 0.0,
                }, args.timeout, "direct GT common trip")

        result = {
            "status": "PASS",
            "endpoint": args.endpoint,
            "model_time_s": float(time_node.get_value()),
            "bound_nodes": len(required),
            "case": args.case,
            "values": actual,
            "hp_ip_physics": "V7_HYDRAULIC_BOUNDARY_PRESERVED",
        }
        atomic_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        return 0
    finally:
        # Every case runs against a disposable solver process.  Do not inject
        # additional reset/open commands during cleanup.
        try:
            client.disconnect()
        except (ConnectionError, OSError):
            # The installer owns the disposable proof server; a failed Secure
            # Close must not hide the real proof result.
            pass


if __name__ == "__main__":
    raise SystemExit(main())
