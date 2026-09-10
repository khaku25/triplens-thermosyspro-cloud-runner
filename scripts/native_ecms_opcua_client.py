#!/usr/bin/env python3
"""Drive the native OpenModelica process and archive only OPC-UA-received data."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

PROTOCOL = "TRIPLENS-NATIVE-OPCUA/1"


@dataclass(frozen=True)
class Signal:
    field: str
    node_name: str
    unit: str
    owner: str


SIGNALS = (
    Signal("gt_trip_latch", "vppSTTripLatch", "BOOL", "DCS1"),
    Signal("gt_exhaust_flow_th", "vppGTExhaustMassFlowTH", "t/h", "DCS1"),
    Signal("hp_turbine_flow_th", "vppHPTurbineSteamFlowTH", "t/h", "DCS1"),
    Signal("ip_turbine_flow_th", "vppIPTurbineSteamFlowTH", "t/h", "DCS1"),
    Signal("lp_turbine_flow_th", "vppLPTurbineSteamFlowTH", "t/h", "DCS1"),
    Signal("hp_admission_position_pu", "vppHPAdmissionPos", "pu", "DCS1"),
    Signal("ip_admission_position_pu", "vppIPAdmissionPos", "pu", "DCS1"),
    Signal("lp_admission_position_pu", "vppLPDrumAdmissionMultiplier", "pu", "DCS1"),
    Signal("hp_bypass_position_pu", "vppHPBypassPos", "pu", "DCS2"),
    Signal("lp_bypass_position_pu", "vppLPBypassPos", "pu", "DCS2"),
    Signal("hp_bypass_flow_th", "vppHPBypassMassFlowTH", "t/h", "DCS2"),
    Signal("lp_bypass_flow_th", "vppLPBypassMassFlowTH", "t/h", "DCS2"),
    Signal("hp_spray_position_pu", "vppHPSprayPos", "pu", "DCS2"),
    Signal("lp_spray_position_pu", "vppLPSprayPos", "pu", "DCS2"),
    Signal("hp_spray_flow_th", "vppHPSprayMassFlowTH", "t/h", "DCS2"),
    Signal("lp_spray_flow_th", "vppLPSprayMassFlowTH", "t/h", "DCS2"),
    Signal("hp_drum_level_m", "BallonHP.yLevel.signal", "m", "DCS2"),
    Signal("ip_drum_level_m", "BallonMP.yLevel.signal", "m", "DCS2"),
    Signal("lp_drum_level_m", "BallonBP.yLevel.signal", "m", "DCS2"),
    Signal("hp_drum_pressure_pa", "BallonHP.P", "Pa", "DCS2"),
    Signal("ip_drum_pressure_pa", "BallonMP.P", "Pa", "DCS2"),
    Signal("lp_drum_pressure_pa", "BallonBP.P", "Pa", "DCS2"),
    Signal("condenser_pressure_pa", "vppCondenserPressure", "Pa", "DCS2"),
    Signal("condenser_level_m", "vppCondenserLevel", "m", "DCS2"),
)


def connect(endpoint: str, timeout_s: float):
    from opcua import Client

    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        client = Client(endpoint, timeout=5)
        try:
            client.connect()
            return client
        except Exception as exc:  # server starts only after native initialization
            last_error = exc
            try:
                client.disconnect()
            except Exception:
                pass
            time.sleep(0.25)
    raise TimeoutError(f"native OPC UA server was not ready: {last_error}")


def browse_nodes(client: Client) -> dict[str, object]:
    nodes: dict[str, object] = {}
    for node in client.get_objects_node().get_children():
        try:
            name = node.get_browse_name().Name
        except Exception:
            continue
        if name in nodes:
            raise ValueError(f"duplicate OPC UA browse name: {name}")
        nodes[name] = node
    return nodes


def wait_for_model_nodes(client, required: set[str], timeout_s: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    nodes: dict[str, object] = {}
    while time.monotonic() < deadline:
        nodes = browse_nodes(client)
        if required <= nodes.keys():
            return nodes
        time.sleep(0.10)
    missing = sorted(required - nodes.keys())
    available_vpp = sorted(name for name in nodes if name.startswith("vpp"))
    raise ValueError(
        "native OPC UA model nodes missing after registration wait: "
        + ", ".join(missing)
        + f"; available vpp nodes={available_vpp}"
    )


def request_step(step_node: object, time_node: object, previous: float, ua, timeout_s: float) -> float:
    """Request one native step, tolerating the server's initial registration race."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        step_node.set_value(ua.Variant(True, ua.VariantType.Boolean))
        retry_at = min(deadline, time.monotonic() + 0.25)
        while time.monotonic() < retry_at:
            current = float(time_node.get_value())
            if current > previous + 1e-12:
                return current
            time.sleep(0.002)
    raise TimeoutError(f"native solver did not advance beyond {previous:.9f} s")


def as_number(value: object) -> float | int:
    if isinstance(value, bool):
        return int(value)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("OPC UA returned a non-finite physical value")
    return number


def validate(rows: list[dict[str, float | int]], command_time_s: float) -> dict[str, object]:
    before = [row for row in rows if row["time_s"] < command_time_s]
    after = [row for row in rows if row["time_s"] >= command_time_s + 0.20]
    errors: list[str] = []
    if not before or not after:
        errors.append("capture lacks pre-command or post-command frames")
    else:
        pre, post = before[-1], after[-1]
        if pre["gt_trip_command_readback"] != 0:
            errors.append("GT Trip input was already true before the ECMS command")
        if not any(row["gt_trip_command_readback"] == 1 for row in after):
            errors.append("ECMS GT Trip command was not read back from OpenModelica")
        if not any(row["gt_trip_latch"] == 1 for row in after):
            errors.append("native Modelica GT Trip latch did not assert")
        if float(post["hp_admission_position_pu"]) >= float(pre["hp_admission_position_pu"]):
            errors.append("HP turbine admission valve did not close physically")
        if float(post["hp_bypass_position_pu"]) <= float(pre["hp_bypass_position_pu"]):
            errors.append("HP bypass valve did not open physically")
        physical_fields = [signal.field for signal in SIGNALS if signal.unit != "BOOL"]
        changed = sum(
            not math.isclose(float(pre[field]), float(post[field]), rel_tol=1e-10, abs_tol=1e-10)
            for field in physical_fields
        )
        if changed < 8:
            errors.append("too few native physical values changed after GT Trip")
    return {
        "status": "PASS" if not errors else "FAIL",
        "proof_type": "NATIVE_OPENMODELICA_OPCUA_CLOSED_LOOP",
        "protocol": PROTOCOL,
        "command_path": "ECMS_OPCUA_WRITE_TO_NATIVE_OPENMODELICA_INPUT",
        "feedback_path": "NATIVE_OPENMODELICA_SOLVED_VALUES_TO_ECMS_OPCUA_READ",
        "csv_role": "POST_RECEIVE_AUDIT_ONLY",
        "frames_received": len(rows),
        "values_received": len(rows) * len(SIGNALS),
        "command_time_s": command_time_s,
        "changed_physical_fields": changed if before and after else 0,
        "drum_level_delta_m": {
            field: float(after[-1][field]) - float(before[-1][field])
            for field in ("hp_drum_level_m", "ip_drum_level_m", "lp_drum_level_m")
        } if before and after else {},
        "errors": errors,
    }


def main() -> int:
    from opcua import ua

    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="opc.tcp://127.0.0.1:4841")
    parser.add_argument("--stop-time", type=float, default=2.0)
    parser.add_argument("--step-size", type=float, default=0.01)
    parser.add_argument("--command-time", type=float, default=0.25)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    count = args.stop_time / args.step_size
    if args.step_size <= 0 or not math.isclose(count, round(count), abs_tol=1e-9):
        parser.error("stop time must be an integer multiple of step size")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = connect(args.endpoint, 180.0)
    rows: list[dict[str, float | int]] = []
    try:
        command_name = "vppExternalTripCommandNative"
        required = {command_name, *(s.node_name for s in SIGNALS)}
        nodes = wait_for_model_nodes(client, required, 60.0)
        # OpenModelica 1.27 defines control nodes in namespace 0 with stable
        # numeric IDs. Their BrowseNames are OpenModelica.step/time, unlike
        # model variables whose BrowseNames are the Modelica names.
        time_node = client.get_node(ua.NodeId(10004, 0))
        step_node = client.get_node(ua.NodeId(10000, 0))
        command_node = nodes[command_name]
        signal_nodes = [nodes[signal.node_name] for signal in SIGNALS]
        current = float(time_node.get_value())
        initial_readback = float(command_node.get_value()) >= 0.5
        if current > args.step_size / 2:
            # If attachment happens after the first pause, retain that already
            # solved frame. At the normal t=0 pause the loop below produces
            # exactly 200 frames from 0.01 through 2.00 seconds.
            initial_values = client.get_values(signal_nodes)
            initial_row: dict[str, float | int] = {
                "sequence": 0,
                "time_s": current,
                "ecms_command_sent": 0,
                "gt_trip_command_readback": int(initial_readback),
                "round_trip_ms": 0.0,
            }
            initial_row.update(
                {
                    signal.field: as_number(value)
                    for signal, value in zip(SIGNALS, initial_values)
                }
            )
            rows.append(initial_row)

        command_written = initial_readback
        while current < args.stop_time - args.step_size / 2:
            command = current >= args.command_time - args.step_size / 2
            # A write to a native OpenModelica state intentionally restarts
            # the solver.  Write only on the command edge; repeating the same
            # value every scan would force an event restart every scan.
            if command and not command_written:
                command_node.set_value(ua.Variant(1.0, ua.VariantType.Double))
                command_written = True
            sent_ns = time.time_ns()
            next_time = request_step(step_node, time_node, current, ua, 30.0)
            readback = float(command_node.get_value()) >= 0.5
            values = client.get_values(signal_nodes)
            row: dict[str, float | int] = {
                "sequence": len(rows),
                "time_s": next_time,
                "ecms_command_sent": int(command),
                "gt_trip_command_readback": int(readback),
                "round_trip_ms": (time.time_ns() - sent_ns) / 1e6,
            }
            row.update({signal.field: as_number(value) for signal, value in zip(SIGNALS, values)})
            rows.append(row)
            current = next_time
        # Release the server from its final stop-time pause so the native
        # executable can terminate normally after the final frame is read.
        step_node.set_value(ua.Variant(True, ua.VariantType.Boolean))
    finally:
        try:
            client.disconnect()
        except (BrokenPipeError, ConnectionError, TimeoutError):
            # The server is allowed to close immediately after the final
            # release; all required physical values have already been read.
            pass

    csv_path = args.output_dir / "ECMS-native-physical.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = validate(rows, args.command_time)
    (args.output_dir / "native-opcua-proof.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    if report["status"] != "PASS":
        raise SystemExit("NATIVE_OPCUA_FAIL: " + "; ".join(report["errors"]))
    print(
        "NATIVE_OPENMODELICA_OPCUA_PASS "
        f"frames={report['frames_received']} values={report['values_received']} "
        f"changed_physical={report['changed_physical_fields']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
