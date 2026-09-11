#!/usr/bin/env python3
"""Drive native OpenModelica and prove the LP FWP Trip OPC UA closed loop."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

from generate_ecms import motor_feeder_state

PROTOCOL = "TRIPLENS-NATIVE-OPCUA/1"
ROOT = Path(__file__).resolve().parents[1]
ALARM_RULES = ROOT / "config" / "dcs_alarm_rules.csv"
TRIP_MATRIX = ROOT / "config" / "common_trip_matrix.csv"


@dataclass(frozen=True)
class Signal:
    field: str
    node_name: str
    unit: str
    owner: str


@dataclass
class DelayedLowAlarm:
    threshold: float
    hysteresis: float
    delay_s: float
    pending_since: float | None = None
    active: bool = False

    def update(self, now_s: float, value: float) -> bool:
        if self.active:
            if value >= self.threshold + self.hysteresis:
                self.active = False
                self.pending_since = None
            return self.active
        if value <= self.threshold:
            if self.pending_since is None:
                self.pending_since = now_s
            if now_s - self.pending_since >= self.delay_s - 1e-12:
                self.active = True
        else:
            self.pending_since = None
        return self.active


SIGNALS = (
    Signal("gt_trip_command", "vppGTTripCmd", "BOOL", "DCS1"),
    Signal("gt_trip_latch", "vppGTTripLatch", "BOOL", "DCS1"),
    Signal("gt_breaker_trip_command", "vpp52GTTripCmd", "BOOL", "DCS1"),
    Signal("gt_breaker_closed", "vpp52GTClosed", "BOOL", "DCS1"),
    Signal("st_trip_latch", "vppSTTripLatchPublished", "BOOL", "DCS1"),
    Signal("st_breaker_trip_command", "vpp52STTripCmd", "BOOL", "DCS1"),
    Signal("st_breaker_closed", "vpp52STClosed", "BOOL", "DCS1"),
    Signal("lp_fwp_motor_energized", "vppLPFWPMotorEnergized", "BOOL", "DCS1"),
    Signal("lp_fwp_speed_proven", "vppLPFWPSpeedProven", "BOOL", "DCS1"),
    Signal("lp_fwp_running", "vppLPFWPRunning", "BOOL", "DCS1"),
    Signal("lp_fwp_speed_rpm", "vppLPFWPSpeedRPM", "rpm", "DCS1"),
    Signal(
        "lp_fwp_hydraulic_speed_rpm", "vppLPFWPHydraulicSpeedRPM", "rpm", "DCS1"
    ),
    Signal("lp_fwp_mass_flow_th", "vppLPFWPMassFlowTH", "t/h", "DCS2"),
    Signal("lp_fwp_volume_flow_m3_s", "vppLPFWPVolumeFlowM3S", "m3/s", "DCS2"),
    Signal("lp_fwp_delta_p_pa", "vppLPFWPDeltaPPa", "Pa", "DCS2"),
    Signal("lp_fwp_mechanical_power_w", "vppLPFWPMechanicalPowerW", "W", "DCS2"),
    Signal("lp_fwp_check_valve_open", "vppLPFWPCheckValveOpen", "BOOL", "DCS2"),
    Signal("lp_fwp_check_valve_opening", "vppLPFWPCheckValveOpening", "pu", "DCS2"),
    Signal("stg_power_w", "Alternateur.Welec", "W", "DCS1"),
    Signal("gt_exhaust_flow_th", "vppGTExhaustMassFlowTH", "t/h", "DCS1"),
    Signal("gt_exhaust_temperature_k", "vppGTExhaustTemperatureK", "K", "DCS1"),
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

COMMAND_NODES = {
    "gt_trip_command_readback": "vppExternalTripCommandNative",
    "lp_fwp_trip_command_readback": "vppLPFWPTripCommandNative",
    "lp_fwp_trip_latch_readback": "vppLPFWPTripLatchNative",
    "vcb_a02_trip_command_readback": "vppVCBA02TripCommandNative",
    "vcb_a02_closed_readback": "vppVCBA02ClosedNative",
}


def load_lp_rules() -> tuple[DelayedLowAlarm, DelayedLowAlarm, bool, bool]:
    with ALARM_RULES.open(encoding="utf-8-sig", newline="") as stream:
        by_tag = {row["alarm_tag"]: row for row in csv.DictReader(stream)}
    alarms = []
    for tag in ("HRSG.LP.DRUM.LEVEL.L", "HRSG.LP.DRUM.LEVEL.LL"):
        row = by_tag[tag]
        alarms.append(DelayedLowAlarm(
            float(row["threshold_value"]),
            float(row["hysteresis_value"]),
            float(row["delay_s"]),
        ))
    with TRIP_MATRIX.open(encoding="utf-8-sig", newline="") as stream:
        matrix = {row["cause_id"]: row for row in csv.DictReader(stream)}
    ll = matrix["LP_DRUM_LL"]
    return (
        alarms[0], alarms[1],
        bool(int(ll["gt_trip_request"])),
        bool(int(ll["st_trip_request"])),
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
        except Exception as exc:
            last_error = exc
            try:
                client.disconnect()
            except Exception:
                pass
            time.sleep(0.25)
    raise TimeoutError(f"native OPC UA server was not ready: {last_error}")


def browse_nodes(client) -> dict[str, object]:
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
    nodes = {}
    while time.monotonic() < deadline:
        nodes = browse_nodes(client)
        if required <= nodes.keys():
            return nodes
        time.sleep(0.1)
    raise ValueError("native OPC UA nodes missing: " + ", ".join(sorted(required - nodes.keys())))


def request_step(step_node, time_node, previous: float, ua, timeout_s: float) -> float:
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


def number(value: object) -> float | int:
    if isinstance(value, bool):
        return int(value)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("OPC UA returned a non-finite value")
    return result


def set_real_once(node, value: float, written: dict[str, float], field: str, ua) -> None:
    if written.get(field) != value:
        node.set_value(ua.Variant(value, ua.VariantType.Double))
        written[field] = value


def validate_lp_bfp(rows: list[dict[str, float | int]], command_time: float) -> dict[str, object]:
    before = [row for row in rows if row["time_s"] < command_time]
    after = [row for row in rows if row["time_s"] >= command_time + 0.2]
    errors: list[str] = []
    changed = 0
    if not before or not after:
        errors.append("capture lacks pre-Trip or post-breaker-open frames")
    else:
        pre, post = before[-1], after[-1]
        for field in (
            "lp_fwp_trip_command_readback",
            "lp_fwp_trip_latch_readback",
            "vcb_a02_trip_command_readback",
        ):
            if not any(int(row[field]) == 1 for row in after):
                errors.append(f"missing OPC UA assertion: {field}")
        for field in ("vcb_a02_closed_readback", "lp_fwp_motor_energized"):
            if not any(int(row[field]) == 0 for row in after):
                errors.append(f"state did not clear: {field}")
        if not any(int(row["lp_fwp_check_valve_open"]) == 0 for row in after):
            errors.append("LP FWP discharge check valve did not close")
        if float(post["lp_fwp_check_valve_opening"]) >= 0.1:
            errors.append("LP FWP discharge check valve remained materially open")
        if float(post["lp_fwp_speed_rpm"]) >= float(pre["lp_fwp_speed_rpm"]) - 50:
            errors.append("PompeAlimBP did not coast down")
        if float(post["lp_fwp_speed_rpm"]) >= (
            float(post["lp_fwp_hydraulic_speed_rpm"]) - 50
        ):
            errors.append("physical shaft did not decay below the numerical pump floor")
        if float(post["lp_fwp_mass_flow_th"]) >= float(pre["lp_fwp_mass_flow_th"]):
            errors.append("PompeAlimBP mass flow did not decrease")
        if float(post["lp_drum_level_m"]) >= float(pre["lp_drum_level_m"]) - 0.02:
            errors.append("LP drum level did not decrease materially")
        for field in (
            "lp_drum_level_l_alarm", "lp_drum_level_ll_alarm",
            "gt_trip_command_readback", "gt_trip_latch", "st_trip_latch",
        ):
            if not any(int(row[field]) == 1 for row in after):
                errors.append(f"closed-loop state did not assert: {field}")
        for field in ("gt_breaker_closed", "st_breaker_closed"):
            if not any(int(row[field]) == 0 for row in after):
                errors.append(f"breaker did not open: {field}")
        changed = sum(
            not math.isclose(float(pre[s.field]), float(post[s.field]), abs_tol=1e-10)
            for s in SIGNALS if s.unit != "BOOL"
        )
    return {
        "status": "PASS" if not errors else "FAIL",
        "scenario": "lp-bfp-trip",
        "proof_type": "NATIVE_OPENMODELICA_OPCUA_CLOSED_LOOP",
        "protocol": PROTOCOL,
        "frames_received": len(rows),
        "values_received": len(rows) * (len(SIGNALS) + len(COMMAND_NODES)),
        "changed_physical_fields": changed,
        "command_time_s": command_time,
        "closed_loop": "FWP-LP Trip -> VCB-A02 open -> PompeAlimBP -> LP Drum LL -> GT/ST Trip",
        "errors": errors,
    }


def validate(rows: list[dict[str, float | int]], command_time: float) -> dict[str, object]:
    return validate_lp_bfp(rows, command_time)


def main() -> int:
    from opcua import ua

    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="opc.tcp://127.0.0.1:4841")
    parser.add_argument("--scenario", choices=("lp-bfp-trip",), default="lp-bfp-trip")
    parser.add_argument("--stop-time", type=float, default=80.0)
    parser.add_argument("--step-size", type=float, default=0.05)
    parser.add_argument("--command-time", type=float, default=20.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.step_size <= 0 or not math.isclose(
        args.stop_time / args.step_size, round(args.stop_time / args.step_size), abs_tol=1e-9
    ):
        parser.error("stop time must be an integer multiple of step size")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    l_alarm, ll_alarm, ll_trips_gt, ll_trips_st = load_lp_rules()
    client = connect(args.endpoint, 180.0)
    rows: list[dict[str, float | int]] = []
    try:
        required = {*COMMAND_NODES.values(), *(signal.node_name for signal in SIGNALS)}
        nodes = wait_for_model_nodes(client, required, 60.0)
        time_node = client.get_node(ua.NodeId(10004, 0))
        step_node = client.get_node(ua.NodeId(10000, 0))
        command_nodes = {field: nodes[name] for field, name in COMMAND_NODES.items()}
        signal_nodes = [nodes[signal.node_name] for signal in SIGNALS]
        current = float(time_node.get_value())
        written = {
            "gt_trip_command_readback": 0.0,
            "lp_fwp_trip_command_readback": 0.0,
            "lp_fwp_trip_latch_readback": 0.0,
            "vcb_a02_trip_command_readback": 0.0,
            "vcb_a02_closed_readback": 1.0,
        }
        gt_trip_requested = False
        command_rows = [{
            "time_s": str(args.command_time), "equipment_id": "FWP-LP",
            "command": "TRIP", "sequence": "1",
        }]
        while current < args.stop_time - args.step_size / 2:
            command = current >= args.command_time - 1e-12
            electrical = motor_feeder_state(
                initial_breaker_closed=True,
                initial_running=True,
                time_ms=round(current * 1000),
                commands=command_rows,
                equipment_id="FWP-LP",
                feeder_id="VCB-A02",
                breaker_open_delay_ms=80,
            )
            updates = {
                "lp_fwp_trip_command_readback": float(command),
                "lp_fwp_trip_latch_readback": float(electrical.trip_latched),
                "vcb_a02_trip_command_readback": float(electrical.trip_commanded),
                "vcb_a02_closed_readback": float(electrical.breaker_closed),
            }
            if gt_trip_requested:
                updates["gt_trip_command_readback"] = 1.0
            for field, value in updates.items():
                set_real_once(command_nodes[field], value, written, field, ua)
            sent_ns = time.time_ns()
            next_time = request_step(step_node, time_node, current, ua, 30.0)
            row: dict[str, float | int] = {
                "sequence": len(rows), "time_s": next_time,
                "ecms_command_sent": int(command),
                "round_trip_ms": (time.time_ns() - sent_ns) / 1e6,
            }
            for field, value in zip(command_nodes, client.get_values(list(command_nodes.values()))):
                row[field] = int(float(value) >= 0.5)
            for signal, value in zip(SIGNALS, client.get_values(signal_nodes)):
                row[signal.field] = number(value)
            level = float(row["lp_drum_level_m"])
            row["lp_drum_level_l_alarm"] = int(l_alarm.update(next_time, level))
            row["lp_drum_level_ll_alarm"] = int(ll_alarm.update(next_time, level))
            ll_active = bool(row["lp_drum_level_ll_alarm"])
            gt_trip_requested = ll_active and ll_trips_gt
            row["common_gt_trip_request"] = int(gt_trip_requested)
            row["common_st_trip_request"] = int(ll_active and ll_trips_st)
            rows.append(row)
            current = next_time
        step_node.set_value(ua.Variant(True, ua.VariantType.Boolean))
    finally:
        try:
            client.disconnect()
        except (BrokenPipeError, ConnectionError, TimeoutError):
            pass
    if not rows:
        raise SystemExit("NATIVE_OPCUA_FAIL: no frames received")
    with (args.output_dir / "ECMS-native-physical.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = validate_lp_bfp(rows, args.command_time)
    (args.output_dir / "native-opcua-proof.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    if report["status"] != "PASS":
        raise SystemExit("NATIVE_OPCUA_FAIL: " + "; ".join(report["errors"]))
    print(
        "NATIVE_OPENMODELICA_OPCUA_PASS "
        f"scenario=lp-bfp-trip frames={report['frames_received']} "
        f"values={report['values_received']} changed_physical={report['changed_physical_fields']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
