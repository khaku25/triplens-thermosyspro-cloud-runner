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


@dataclass(frozen=True)
class EventSpec:
    field: str
    tag: str
    system: str
    event_class: str
    severity: str
    edge: str
    threshold: float
    unit: str
    description: str


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
    Signal("hp_fwp_check_valve_open", "vppHPFWPCheckValveOpen", "BOOL", "DCS2"),
    Signal("hp_fwp_check_valve_opening", "vppHPFWPCheckValveOpening", "pu", "DCS2"),
    Signal("hp_fwp_check_valve_mass_flow_th", "vppHPFWPCheckValveMassFlowTH", "t/h", "DCS2"),
    Signal("hp_fwp_check_valve_delta_p_pa", "vppHPFWPCheckValveDeltaPPa", "Pa", "DCS2"),
    Signal("hp_fwp_check_valve_inlet_p_pa", "vppHPFWPCheckValveInletPressurePa", "Pa", "DCS2"),
    Signal("hp_fwp_check_valve_outlet_p_pa", "vppHPFWPCheckValveOutletPressurePa", "Pa", "DCS2"),
    Signal("hp_fwp_check_valve_resistance", "vppHPFWPCheckValveResistancePaSPerKg", "Pa.s/kg", "DCS2"),
    Signal("ip_fwp_check_valve_open", "vppIPFWPCheckValveOpen", "BOOL", "DCS2"),
    Signal("ip_fwp_check_valve_opening", "vppIPFWPCheckValveOpening", "pu", "DCS2"),
    Signal("ip_fwp_check_valve_mass_flow_th", "vppIPFWPCheckValveMassFlowTH", "t/h", "DCS2"),
    Signal("ip_fwp_check_valve_delta_p_pa", "vppIPFWPCheckValveDeltaPPa", "Pa", "DCS2"),
    Signal("ip_fwp_check_valve_inlet_p_pa", "vppIPFWPCheckValveInletPressurePa", "Pa", "DCS2"),
    Signal("ip_fwp_check_valve_outlet_p_pa", "vppIPFWPCheckValveOutletPressurePa", "Pa", "DCS2"),
    Signal("ip_fwp_check_valve_resistance", "vppIPFWPCheckValveResistancePaSPerKg", "Pa.s/kg", "DCS2"),
    Signal("lp_fwp_check_valve_mass_flow_th", "vppLPFWPCheckValveMassFlowTH", "t/h", "DCS2"),
    Signal("lp_fwp_check_valve_delta_p_pa", "vppLPFWPCheckValveDeltaPPa", "Pa", "DCS2"),
    Signal("lp_fwp_check_valve_inlet_p_pa", "vppLPFWPCheckValveInletPressurePa", "Pa", "DCS2"),
    Signal("lp_fwp_check_valve_outlet_p_pa", "vppLPFWPCheckValveOutletPressurePa", "Pa", "DCS2"),
    Signal("lp_fwp_check_valve_resistance", "vppLPFWPCheckValveResistancePaSPerKg", "Pa.s/kg", "DCS2"),
    Signal("stg_power_w", "Alternateur.Welec", "W", "DCS1"),
    Signal("gtg_power_mw", "vppGTGPowerMW", "MW", "DCS1"),
    Signal("gtg_speed_rpm", "vppGTGSpeedRPM", "rpm", "DCS1"),
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

EVENT_FIELDS = (
    "event_sequence", "event_time_ms", "source_time_ms", "time_s",
    "relative_to_event_s", "phase", "source_system", "source_file", "tag",
    "canonical_tag", "event_state", "event_class", "severity", "source_signal",
    "old_value", "new_value", "value", "threshold", "unit", "quality",
    "provenance", "rule_status", "description",
)

EVENT_SPECS = (
    EventSpec("lp_fwp_trip_command_readback", "CMD.FWP-LP.TRIP", "ECMS", "COMMAND", "INFO", "RISE", 0.5, "BOOL", "LP feedwater pump Trip command"),
    EventSpec("lp_fwp_trip_latch_readback", "CTRL.FWP-LP.TRIP_LATCH", "ECMS", "TRIP", "CRITICAL", "RISE", 0.5, "BOOL", "LP feedwater pump Trip latch"),
    EventSpec("vcb_a02_trip_command_readback", "ECMS.VCB-A02.TRIP_CMD", "ECMS", "COMMAND", "CRITICAL", "RISE", 0.5, "BOOL", "VCB-A02 Trip command"),
    EventSpec("vcb_a02_closed_readback", "ECMS.VCB-A02.CLOSED", "ECMS", "STATUS", "CRITICAL", "FALL", 0.5, "BOOL", "VCB-A02 auxiliary contact opened"),
    EventSpec("lp_fwp_motor_energized", "FWP-LP.MOTOR_ENERGIZED", "DCS1", "STATUS", "CRITICAL", "FALL", 0.5, "BOOL", "LP feedwater pump motor de-energized"),
    EventSpec("lp_fwp_speed_proven", "DCS.FWP-LP.SPEED_PROVEN", "DCS1", "STATUS", "WARNING", "FALL", 0.5, "BOOL", "LP feedwater pump speed no longer proven"),
    EventSpec("lp_fwp_running", "DCS.FWP-LP.RUN_FB", "DCS1", "STATUS", "WARNING", "FALL", 0.5, "BOOL", "LP feedwater pump run feedback cleared"),
    EventSpec("lp_fwp_check_valve_open", "TSP.FWP-LP.DISCHARGE_CHECK_VALVE.OPEN", "DCS2", "STATUS", "INFO", "FALL", 0.5, "BOOL", "LP feedwater pump discharge check valve closed"),
    EventSpec("lp_drum_level_l_alarm", "HRSG.LP.DRUM.LEVEL.L", "DCS2", "ALARM", "WARNING", "RISE", 0.5, "BOOL", "LP drum level low alarm after configured delay"),
    EventSpec("lp_drum_level_ll_alarm", "HRSG.LP.DRUM.LEVEL.LL", "DCS2", "ALARM", "CRITICAL", "RISE", 0.5, "BOOL", "LP drum level low-low alarm after configured delay"),
    EventSpec("common_gt_trip_request", "COMMON.GT_TRIP.REQUEST", "ECMS", "PROTECTION", "CRITICAL", "RISE", 0.5, "BOOL", "LP drum LL requested GT Trip"),
    EventSpec("common_st_trip_request", "COMMON.ST_TRIP.REQUEST", "ECMS", "PROTECTION", "CRITICAL", "RISE", 0.5, "BOOL", "LP drum LL requested ST Trip"),
    EventSpec("gt_trip_command_readback", "GT.TRIP.CMD", "DCS1", "COMMAND", "CRITICAL", "RISE", 0.5, "BOOL", "GT Trip command returned from OpenModelica"),
    EventSpec("gt_trip_latch", "GT.TRIP.LATCH", "DCS1", "TRIP", "CRITICAL", "RISE", 0.5, "BOOL", "GT Trip latch asserted"),
    EventSpec("st_trip_latch", "ST.TRIP.LATCH", "DCS1", "TRIP", "CRITICAL", "RISE", 0.5, "BOOL", "ST Trip latch asserted"),
    EventSpec("gt_breaker_trip_command", "ECMS.52GT.TRIP_CMD", "ECMS", "COMMAND", "CRITICAL", "RISE", 0.5, "BOOL", "52GT Trip command asserted"),
    EventSpec("gt_breaker_closed", "ECMS.52GT.CLOSED", "ECMS", "STATUS", "CRITICAL", "FALL", 0.5, "BOOL", "52GT opened"),
    EventSpec("st_breaker_trip_command", "ECMS.52ST.TRIP_CMD", "ECMS", "COMMAND", "CRITICAL", "RISE", 0.5, "BOOL", "52ST Trip command asserted"),
    EventSpec("st_breaker_closed", "ECMS.52ST.CLOSED", "ECMS", "STATUS", "CRITICAL", "FALL", 0.5, "BOOL", "52ST opened"),
    EventSpec("hp_admission_position_pu", "TSP.TURBINE.HP.ADMISSION.CLOSE_LS", "DCS1", "STATUS", "INFO", "LOW", 0.05, "pu", "HP turbine admission valve reached closed limit"),
    EventSpec("ip_admission_position_pu", "TSP.TURBINE.IP.ADMISSION.CLOSE_LS", "DCS1", "STATUS", "INFO", "LOW", 0.05, "pu", "IP turbine admission valve reached closed limit"),
    EventSpec("lp_admission_position_pu", "TSP.TURBINE.LP.ADMISSION.CLOSE_LS", "DCS1", "STATUS", "INFO", "LOW", 0.05, "pu", "LP turbine admission valve reached closed limit"),
    EventSpec("hp_bypass_position_pu", "TSP.BYPASS.HP.OPEN_LS", "DCS2", "STATUS", "INFO", "HIGH", 0.95, "pu", "HP bypass valve reached open limit"),
    EventSpec("lp_bypass_position_pu", "TSP.BYPASS.LP.OPEN_LS", "DCS2", "STATUS", "INFO", "HIGH", 0.95, "pu", "LP bypass valve reached open limit"),
    EventSpec("hp_spray_position_pu", "TSP.BYPASS.HP.SPRAY.OPEN_LS", "DCS2", "STATUS", "INFO", "HIGH", 0.95, "pu", "HP bypass spray reached open limit"),
    EventSpec("lp_spray_position_pu", "TSP.BYPASS.LP.SPRAY.OPEN_LS", "DCS2", "STATUS", "INFO", "HIGH", 0.95, "pu", "LP bypass spray reached open limit"),
    EventSpec("gtg_power_mw", "GTG.ACTIVE_POWER.ZERO", "DCS1", "STATUS", "CRITICAL", "LOW", 1.0, "MW", "GT generator active power fell below 1 MW"),
    EventSpec("gtg_speed_rpm", "GTG.SPEED.COASTDOWN", "DCS1", "STATUS", "WARNING", "LOW", 3564.0, "rpm", "GT generator speed fell below 99 percent"),
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


def lp_bfp_closed_loop_complete(row: dict[str, float | int]) -> bool:
    """Return true only after the commanded protection loop is physically visible."""
    asserted = (
        "lp_drum_level_ll_alarm",
        "gt_trip_command_readback",
        "gt_trip_latch",
        "st_trip_latch",
    )
    return all(int(row[field]) == 1 for field in asserted) and all(
        int(row[field]) == 0 for field in ("gt_breaker_closed", "st_breaker_closed")
    )


def event_crossed(spec: EventSpec, previous: float, current: float) -> bool:
    if spec.edge == "RISE":
        return previous < spec.threshold <= current
    if spec.edge == "FALL":
        return previous >= spec.threshold > current
    if spec.edge == "LOW":
        return previous > spec.threshold >= current
    if spec.edge == "HIGH":
        return previous < spec.threshold <= current
    raise ValueError(f"unknown event edge: {spec.edge}")


def build_native_events(
    rows: list[dict[str, float | int]], reference_time: float
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    emitted: set[str] = set()
    for previous_row, row in zip(rows, rows[1:]):
        for spec in EVENT_SPECS:
            if spec.tag in emitted:
                continue
            previous = float(previous_row[spec.field])
            current = float(row[spec.field])
            if not event_crossed(spec, previous, current):
                continue
            event_time = float(row["time_s"])
            events.append({
                "event_sequence": len(events) + 1,
                "event_time_ms": round(event_time * 1000),
                "source_time_ms": round(event_time * 1000),
                "time_s": f"{event_time:.9f}",
                "relative_to_event_s": f"{event_time - reference_time:.9f}",
                "phase": "PRE_EVENT" if event_time < reference_time else
                    ("AT_EVENT" if math.isclose(event_time, reference_time, abs_tol=1e-9)
                     else "POST_EVENT"),
                "source_system": spec.system,
                "source_file": "ECMS-native-physical.csv",
                "tag": spec.tag,
                "canonical_tag": spec.tag,
                # RISE/HIGH and an analog LOW threshold all mean that the
                # named event condition became active.  FALL is reserved for
                # source-state tags such as *.CLOSED or *.RUN_FB clearing.
                "event_state": "1" if spec.edge in ("RISE", "HIGH", "LOW") else "0",
                "event_class": spec.event_class,
                "severity": spec.severity,
                "source_signal": spec.field,
                "old_value": previous,
                "new_value": current,
                "value": current,
                "threshold": spec.threshold,
                "unit": spec.unit,
                "quality": "GOOD",
                "provenance": "LIVE_OPC_UA_OPENMODELICA",
                "rule_status": "ACTIVE",
                "description": spec.description,
            })
            emitted.add(spec.tag)
    return events


def validate_lp_bfp(
    rows: list[dict[str, float | int]],
    command_time: float,
    post_gt_trip_seconds: float = 30.0,
) -> dict[str, object]:
    before = [row for row in rows if row["time_s"] < command_time]
    after = [row for row in rows if row["time_s"] >= command_time + 0.2]
    errors: list[str] = []
    changed = 0
    gt_trip_time: float | None = None
    observed_post_trip = 0.0
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
        post_trip_requirements = {
            "hp_admission_position_pu": ("LOW", 0.05),
            "ip_admission_position_pu": ("LOW", 0.05),
            "lp_admission_position_pu": ("LOW", 0.05),
            "hp_bypass_position_pu": ("HIGH", 0.95),
            "lp_bypass_position_pu": ("HIGH", 0.95),
            "hp_spray_position_pu": ("HIGH", 0.95),
            "lp_spray_position_pu": ("HIGH", 0.95),
            "gtg_power_mw": ("LOW", 1.0),
            "gtg_speed_rpm": ("LOW", 3564.0),
        }
        for field, (direction, threshold) in post_trip_requirements.items():
            values = [float(row[field]) for row in after]
            reached = min(values) <= threshold if direction == "LOW" else max(values) >= threshold
            if not reached:
                errors.append(f"post-Trip terminal state missing: {field}")
        trip_rows = [row for row in rows if int(row["gt_trip_latch"]) == 1]
        if trip_rows:
            gt_trip_time = float(trip_rows[0]["time_s"])
            observed_post_trip = float(rows[-1]["time_s"]) - gt_trip_time
            if observed_post_trip < post_gt_trip_seconds - 1e-6:
                errors.append(
                    "post-GT-Trip observation shorter than "
                    f"{post_gt_trip_seconds:.3f} s: {observed_post_trip:.6f} s"
                )
        else:
            gt_trip_time = None
            observed_post_trip = 0.0
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
        "terminal_time_s": rows[-1]["time_s"] if rows else None,
        "gt_trip_time_s": gt_trip_time,
        "post_gt_trip_observation_s": observed_post_trip,
        "required_post_gt_trip_s": post_gt_trip_seconds,
        "termination_reason": "GT_TRIP_PLUS_30_SECONDS" if
            observed_post_trip >= post_gt_trip_seconds - 1e-6
            else "STOP_TIME",
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
    parser.add_argument("--stop-time", type=float, default=120.0)
    parser.add_argument("--step-size", type=float, default=0.05)
    parser.add_argument("--command-time", type=float, default=20.0)
    parser.add_argument("--post-gt-trip-seconds", type=float, default=30.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.step_size <= 0 or not math.isclose(
        args.stop_time / args.step_size, round(args.stop_time / args.step_size), abs_tol=1e-9
    ):
        parser.error("stop time must be an integer multiple of step size")
    if args.post_gt_trip_seconds < 30.0:
        parser.error("post-GT-Trip observation must be at least 30 seconds")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    l_alarm, ll_alarm, ll_trips_gt, ll_trips_st = load_lp_rules()
    client = connect(args.endpoint, 180.0)
    rows: list[dict[str, float | int]] = []
    runtime_error: str | None = None
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
        gt_trip_time: float | None = None
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
            if gt_trip_time is None and int(row["gt_trip_latch"]) == 1:
                gt_trip_time = next_time
            if gt_trip_time is not None and (
                next_time >= gt_trip_time + args.post_gt_trip_seconds - 1e-9
            ):
                break
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
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
    events = build_native_events(rows, args.command_time)
    with (args.output_dir / "EVENT.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(events)
    report = validate_lp_bfp(rows, args.command_time, args.post_gt_trip_seconds)
    report["event_count"] = len(events)
    report["runtime_error"] = runtime_error
    if runtime_error:
        report["status"] = "FAIL"
        report["errors"].insert(0, runtime_error)
    missing_event_tags = sorted({spec.tag for spec in EVENT_SPECS} - {
        str(event["canonical_tag"]) for event in events
    })
    if missing_event_tags:
        report["status"] = "FAIL"
        report["errors"].append(
            "EVENT.csv missing required events: " + ", ".join(missing_event_tags)
        )
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
