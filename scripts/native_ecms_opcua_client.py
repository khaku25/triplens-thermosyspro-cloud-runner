#!/usr/bin/env python3
"""Drive native OpenModelica and prove the LP FWP Trip OPC UA closed loop."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from generate_ecms import motor_feeder_state
from opcua_common import (
    AccessEvidence,
    BoundNode,
    DataSample,
    NodeBindingError,
    NodeContract,
    Quality,
    assert_write_role_allowed,
    bind_nodes,
    read_access_evidence,
    sample_from_datavalue,
)

PROTOCOL = "TRIPLENS-NATIVE-OPCUA/1"
ROOT = Path(__file__).resolve().parents[1]
ALARM_RULES = ROOT / "config" / "dcs_alarm_rules.csv"
TRIP_MATRIX = ROOT / "config" / "common_trip_matrix.csv"
ECMS_WRITE_ROLE = "ECMS_COMMAND"
MODEL_STALE_AFTER_S = 5.0


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

DATAVALUE_FIELDS = (
    "sequence", "simulation_time_s", "canonical_tag", "browse_name",
    "direction", "evidence_kind", "value", "status_code", "status_name",
    "source_timestamp_utc", "source_time_ms", "server_timestamp_utc",
    "server_time_ms", "received_timestamp_utc", "received_time_ms", "quality",
    "namespace_uri", "namespace_index", "node_id",
    "advertised_access_level", "advertised_user_access_level",
    "advertised_current_write", "advertised_user_current_write",
    "write_service_status", "write_echo_status",
)

EVENT_SPECS = (
    EventSpec("lp_fwp_trip_command_readback", "CMD.FWP-LP.TRIP", "ECMS", "COMMAND", "INFO", "RISE", 0.5, "BOOL", "LP feedwater pump Trip command OPC UA write echo"),
    EventSpec("lp_fwp_trip_latch_readback", "CTRL.FWP-LP.TRIP_LATCH", "ECMS", "TRIP", "CRITICAL", "RISE", 0.5, "BOOL", "ECMS-owned LP feedwater pump Trip latch OPC UA write echo"),
    EventSpec("vcb_a02_trip_command_readback", "ECMS.VCB-A02.TRIP_CMD", "ECMS", "COMMAND", "CRITICAL", "RISE", 0.5, "BOOL", "VCB-A02 Trip command OPC UA write echo"),
    EventSpec("vcb_a02_closed_readback", "ECMS.VCB-A02.CLOSED", "ECMS", "STATUS", "CRITICAL", "FALL", 0.5, "BOOL", "ECMS-owned VCB-A02 auxiliary contact OPC UA write echo"),
    EventSpec("lp_fwp_motor_energized", "FWP-LP.MOTOR_ENERGIZED", "DCS1", "STATUS", "CRITICAL", "FALL", 0.5, "BOOL", "LP feedwater pump motor de-energized"),
    EventSpec("lp_fwp_speed_proven", "DCS.FWP-LP.SPEED_PROVEN", "DCS1", "STATUS", "WARNING", "FALL", 0.5, "BOOL", "LP feedwater pump speed no longer proven"),
    EventSpec("lp_fwp_running", "DCS.FWP-LP.RUN_FB", "DCS1", "STATUS", "WARNING", "FALL", 0.5, "BOOL", "LP feedwater pump run feedback cleared"),
    EventSpec("lp_fwp_check_valve_open", "TSP.FWP-LP.DISCHARGE_CHECK_VALVE.OPEN", "DCS2", "STATUS", "INFO", "FALL", 0.5, "BOOL", "LP feedwater pump discharge check valve closed"),
    EventSpec("lp_drum_level_l_alarm", "HRSG.LP.DRUM.LEVEL.L", "DCS2", "ALARM", "WARNING", "RISE", 0.5, "BOOL", "LP drum level low alarm after configured delay"),
    EventSpec("lp_drum_level_ll_alarm", "HRSG.LP.DRUM.LEVEL.LL", "DCS2", "ALARM", "CRITICAL", "RISE", 0.5, "BOOL", "LP drum level low-low alarm after configured delay"),
    EventSpec("common_gt_trip_request", "COMMON.GT_TRIP.REQUEST", "ECMS", "PROTECTION", "CRITICAL", "RISE", 0.5, "BOOL", "LP drum LL requested GT Trip"),
    EventSpec("common_st_trip_request", "COMMON.ST_TRIP.REQUEST", "ECMS", "PROTECTION", "CRITICAL", "RISE", 0.5, "BOOL", "Independent LP drum LL ST Trip request OPC UA write echo"),
    EventSpec("gt_trip_command_readback", "GT.TRIP.CMD", "DCS1", "COMMAND", "CRITICAL", "RISE", 0.5, "BOOL", "GT Trip request OPC UA write echo"),
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
    "common_st_trip_request": "vppExternalSTTripCommandNative",
    "lp_fwp_trip_command_readback": "vppLPFWPTripCommandNative",
    "lp_fwp_trip_latch_readback": "vppLPFWPTripLatchNative",
    "vcb_a02_trip_command_readback": "vppVCBA02TripCommandNative",
    "vcb_a02_closed_readback": "vppVCBA02ClosedNative",
}

# These ECMS results are calculated from a trusted physical LP-drum level
# sample.  Their EVENT.csv evidence must retain that DataValue's quality and
# SourceTimestamp instead of inventing GOOD/simulation-time metadata.
DERIVED_EVENT_EVIDENCE = {
    "lp_drum_level_l_alarm": "lp_drum_level_m",
    "lp_drum_level_ll_alarm": "lp_drum_level_m",
    "common_gt_trip_request": "lp_drum_level_m",
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


def resolve_ll_trip_requests(
    ll_active: bool, ll_trips_gt: bool, ll_trips_st: bool
) -> tuple[bool, bool]:
    """Resolve GT and ST outputs independently from the common-trip matrix."""

    return ll_active and ll_trips_gt, ll_active and ll_trips_st


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


def _walk_address_space(root) -> list[object]:
    pending = list(root.get_children())
    result: list[object] = []
    visited: set[str] = set()
    while pending:
        node = pending.pop(0)
        identity = str(getattr(node, "nodeid", node))
        if identity in visited:
            continue
        visited.add(identity)
        result.append(node)
        try:
            pending.extend(node.get_children())
        except Exception:
            pass
    return result


def discover_model_namespace_uri(client, required: set[str]) -> str:
    """Find the one namespace URI containing the complete model interface.

    OpenModelica may assign a different namespace index and numeric NodeId on
    another build or reconnect.  We discover the URI from NamespaceArray and
    then perform the authoritative bind with ``(URI, BrowseName)``.  A mere
    BrowseName-only match is never returned to the caller as a binding.
    """

    namespaces = tuple(str(uri) for uri in client.get_namespace_array())
    names_by_uri: dict[str, set[str]] = {}
    for node in _walk_address_space(client.get_objects_node()):
        try:
            qualified = node.get_browse_name()
            index = int(qualified.NamespaceIndex)
            name = str(qualified.Name)
        except Exception:
            continue
        if not 0 <= index < len(namespaces):
            raise NodeBindingError(
                f"OPC UA node {name} has unknown namespace index {index}"
            )
        # Namespace zero contains the solver-control exception, never the
        # TripLens model-variable contract.
        if index != 0:
            names_by_uri.setdefault(namespaces[index], set()).add(name)
    matches = [uri for uri, names in names_by_uri.items() if required <= names]
    if len(matches) != 1:
        detail = "none" if not matches else ", ".join(sorted(matches))
        raise NodeBindingError(
            "expected exactly one OPC UA model namespace containing every "
            f"required BrowseName; candidates={detail}"
        )
    return matches[0]


def full_native_valve_read_contracts(namespace_uri: str) -> tuple[NodeContract, ...]:
    path = ROOT / "data" / "opcua_native_valve_nodes_v1.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return tuple(
        NodeContract(
            canonical_tag=row["canonical_tag"],
            namespace_uri=namespace_uri,
            browse_name=row["opcua_browse_name"],
            direction="READ",
            data_type="Boolean" if row["data_type"].upper() in {"BOOL", "BOOLEAN"} else "Double",
            stale_after_s=MODEL_STALE_AFTER_S,
        )
        for row in rows
        if row["direction"].strip().upper() == "READ"
    )


def full_native_valve_read_browse_names() -> set[str]:
    """Return valve READ BrowseNames without constructing bound contracts.

    Namespace URI discovery happens before the model namespace is known.  A
    ``NodeContract`` intentionally rejects an empty URI, so required-name
    discovery must read the CSV directly instead of calling
    ``model_node_contracts(\"\", ...)``.
    """

    path = ROOT / "data" / "opcua_native_valve_nodes_v1.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {
            row["opcua_browse_name"].strip()
            for row in csv.DictReader(stream)
            if row["direction"].strip().upper() == "READ"
            and row["opcua_browse_name"].strip()
        }


def model_node_contracts(
    namespace_uri: str, *, include_full_valve_outputs: bool = False
) -> tuple[NodeContract, ...]:
    command_contracts = tuple(
        NodeContract(
            canonical_tag=field,
            namespace_uri=namespace_uri,
            browse_name=browse_name,
            direction="WRITE",
            data_type="Double",
            stale_after_s=MODEL_STALE_AFTER_S,
            write_roles=(ECMS_WRITE_ROLE,),
        )
        for field, browse_name in COMMAND_NODES.items()
    )
    signal_contracts = tuple(
        NodeContract(
            canonical_tag=signal.field,
            namespace_uri=namespace_uri,
            browse_name=signal.node_name,
            direction="READ",
            data_type="Boolean" if signal.unit == "BOOL" else "Double",
            stale_after_s=MODEL_STALE_AFTER_S,
        )
        for signal in SIGNALS
    )
    contracts = command_contracts + signal_contracts
    if include_full_valve_outputs:
        known = {item.browse_name for item in contracts}
        contracts += tuple(
            item for item in full_native_valve_read_contracts(namespace_uri)
            if item.browse_name not in known
        )
    return contracts


def wait_for_model_bindings(
    client, required: set[str], timeout_s: float, *, include_full_valve_outputs: bool = False
) -> tuple[str, dict[str, BoundNode]]:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            namespace_uri = discover_model_namespace_uri(client, required)
            return namespace_uri, bind_nodes(
                client, model_node_contracts(
                    namespace_uri,
                    include_full_valve_outputs=include_full_valve_outputs,
                )
            )
        except NodeBindingError as exc:
            last_error = exc
            time.sleep(0.1)
    raise NodeBindingError(f"native OPC UA model binding failed: {last_error}")


def request_step(step_node, time_node, previous: float, ua, timeout_s: float) -> float:
    """Advance the solver using OpenModelica's documented ns=0 exception.

    ``ns=0;i=10000`` (step) and ``ns=0;i=10004`` (time) are server-control
    nodes, not model variables.  Model READ/WRITE nodes must never use numeric
    NodeIds; they are bound by Namespace URI plus BrowseName above.
    """
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


def batch_read_model_samples(
    client,
    bindings: dict[str, BoundNode],
    ua,
    *,
    received_timestamp: datetime | None = None,
) -> dict[str, DataSample]:
    """Read every model node in one service call without stripping DataValue."""

    ordered = list(bindings.items())
    values = client.uaclient.get_attributes(
        [bound.node.nodeid for _, bound in ordered], ua.AttributeIds.Value
    )
    if len(values) != len(ordered):
        raise ValueError(
            "OPC UA batch read returned "
            f"{len(values)} DataValues for {len(ordered)} requested nodes"
        )
    received = received_timestamp or datetime.now(timezone.utc)
    return {
        field: sample_from_datavalue(
            bound.contract, data_value, received_timestamp=received
        )
        for (field, bound), data_value in zip(ordered, values)
    }


def require_trusted_model_samples(samples: dict[str, DataSample]) -> None:
    """Fail closed before any untrusted value can drive protection logic."""

    errors = []
    for field, sample in samples.items():
        if sample.quality != Quality.GOOD:
            errors.append(f"{field}={sample.quality.value}")
        elif sample.source_timestamp is None:
            errors.append(f"{field}=MISSING_SOURCE_TIMESTAMP")
    if errors:
        raise ValueError("untrusted OPC UA DataValue: " + ", ".join(errors))


def _timestamp_ms(value: datetime | None) -> int | str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return round(value.timestamp() * 1000)


def _timestamp_text(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def datavalue_rows(
    sequence: int,
    simulation_time_s: float,
    bindings: dict[str, BoundNode],
    samples: dict[str, DataSample],
    access_evidence: dict[str, AccessEvidence],
    write_service_status: dict[str, str],
    write_echo_status: dict[str, str],
) -> list[dict[str, object]]:
    rows = []
    for field, bound in bindings.items():
        sample = samples[field]
        advertised = access_evidence[field]
        rows.append({
            "sequence": sequence,
            "simulation_time_s": f"{simulation_time_s:.9f}",
            "canonical_tag": field,
            "browse_name": bound.contract.browse_name,
            "direction": bound.contract.direction,
            "evidence_kind": (
                "WRITE_ECHO" if bound.contract.direction == "WRITE"
                else "MODEL_FEEDBACK"
            ),
            "value": sample.value,
            "status_code": "" if sample.status_code is None else sample.status_code,
            "status_name": sample.status_name or "",
            "source_timestamp_utc": _timestamp_text(sample.source_timestamp),
            "source_time_ms": _timestamp_ms(sample.source_timestamp),
            "server_timestamp_utc": _timestamp_text(sample.server_timestamp),
            "server_time_ms": _timestamp_ms(sample.server_timestamp),
            "received_timestamp_utc": _timestamp_text(sample.received_timestamp),
            "received_time_ms": _timestamp_ms(sample.received_timestamp),
            "quality": sample.quality.value,
            "namespace_uri": bound.contract.namespace_uri,
            "namespace_index": bound.namespace_index,
            "node_id": bound.node_id,
            "advertised_access_level": advertised.access_level,
            "advertised_user_access_level": advertised.user_access_level,
            "advertised_current_write": int(
                advertised.current_write_advertised
            ),
            "advertised_user_current_write": int(
                advertised.user_current_write_advertised
            ),
            "write_service_status": write_service_status.get(field, "NOT_APPLICABLE"),
            "write_echo_status": write_echo_status.get(field, "NOT_APPLICABLE"),
        })
    return rows


def evaluate_write_echoes(
    samples: dict[str, DataSample], written: dict[str, float]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for field, expected in written.items():
        sample = samples.get(field)
        if sample is None:
            result[field] = "MISSING_SAMPLE"
            continue
        if sample.quality != Quality.GOOD:
            result[field] = f"UNTRUSTED_{sample.quality.value}"
            continue
        try:
            actual = float(sample.value)
        except (TypeError, ValueError):
            result[field] = "NON_NUMERIC"
            continue
        result[field] = (
            "VERIFIED" if math.isclose(actual, expected, abs_tol=1e-12)
            else f"MISMATCH_EXPECTED_{expected:.17g}_ACTUAL_{actual:.17g}"
        )
    return result


def require_verified_write_echoes(write_echo_status: dict[str, str]) -> None:
    failures = [
        f"{field}={status}"
        for field, status in write_echo_status.items()
        if status != "VERIFIED"
    ]
    if failures:
        raise ValueError(
            "OPC UA Write service lacked matching DataValue echo: "
            + ", ".join(failures)
        )


def number(value: object) -> float | int:
    if isinstance(value, bool):
        return int(value)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("OPC UA returned a non-finite value")
    return result


def set_real_once(
    bound: BoundNode,
    value: float,
    written: dict[str, float],
    field: str,
    ua,
    write_service_status: dict[str, str],
) -> None:
    if written.get(field) != value:
        # Application direction/role is always enforced before transport.  The
        # authoritative server decision is the Write service result, followed
        # by a DataValue echo check after the solver step.  AccessLevel remains
        # recorded evidence because OpenModelica may advertise CurrentRead only.
        assert_write_role_allowed(bound, ECMS_WRITE_ROLE)
        try:
            bound.node.set_value(ua.Variant(value, ua.VariantType.Double))
        except Exception:
            write_service_status[field] = "REJECTED"
            raise
        write_service_status[field] = "ACCEPTED"
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
    rows: list[dict[str, float | int]],
    reference_time: float,
    sample_rows: list[dict[str, DataSample]],
) -> list[dict[str, object]]:
    if len(sample_rows) != len(rows):
        raise ValueError("EVENT evidence rows do not align with physical frames")
    events: list[dict[str, object]] = []
    emitted: set[str] = set()
    for index, (previous_row, row) in enumerate(zip(rows, rows[1:]), start=1):
        for spec in EVENT_SPECS:
            if spec.tag in emitted:
                continue
            previous = float(previous_row[spec.field])
            current = float(row[spec.field])
            if not event_crossed(spec, previous, current):
                continue
            event_time = float(row["time_s"])
            evidence_field = DERIVED_EVENT_EVIDENCE.get(spec.field, spec.field)
            try:
                sample = sample_rows[index][evidence_field]
            except KeyError as exc:
                raise ValueError(
                    f"EVENT {spec.tag} lacks OPC UA DataValue evidence: "
                    f"{evidence_field}"
                ) from exc
            if sample.quality != Quality.GOOD or sample.source_timestamp is None:
                raise ValueError(
                    f"EVENT {spec.tag} has untrusted DataValue evidence: "
                    f"quality={sample.quality.value}, "
                    f"source_timestamp={sample.source_timestamp!r}"
                )
            is_write_echo = evidence_field in COMMAND_NODES
            provenance = (
                "LIVE_OPC_UA_WRITE_ECHO_DATAVALUE" if is_write_echo else
                "DERIVED_FROM_OPC_UA_DATAVALUE" if spec.field in DERIVED_EVENT_EVIDENCE else
                "LIVE_OPC_UA_OPENMODELICA_DATAVALUE"
            )
            events.append({
                "event_sequence": len(events) + 1,
                "event_time_ms": _timestamp_ms(sample.received_timestamp),
                "source_time_ms": _timestamp_ms(sample.source_timestamp),
                "time_s": f"{event_time:.9f}",
                "relative_to_event_s": f"{event_time - reference_time:.9f}",
                "phase": "PRE_EVENT" if event_time < reference_time else
                    ("AT_EVENT" if math.isclose(event_time, reference_time, abs_tol=1e-9)
                     else "POST_EVENT"),
                "source_system": spec.system,
                "source_file": "OPCUA-DATAVALUE.csv",
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
                "quality": sample.quality.value,
                "provenance": provenance,
                "rule_status": "ACTIVE",
                "description": spec.description,
            })
            emitted.add(spec.tag)
    return events


def validate_lp_bfp(
    rows: list[dict[str, float | int]],
    command_time: float,
    post_gt_trip_seconds: float = 30.0,
    observed_node_count: int | None = None,
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
        "values_received": len(rows) * (observed_node_count or (len(SIGNALS) + len(COMMAND_NODES))),
        "observed_nodes_per_frame": observed_node_count or (len(SIGNALS) + len(COMMAND_NODES)),
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
    sample_rows: list[dict[str, DataSample]] = []
    data_value_evidence: list[dict[str, object]] = []
    runtime_error: str | None = None
    model_namespace_uri: str | None = None
    access_evidence: dict[str, AccessEvidence] = {}
    write_service_status: dict[str, str] = {}
    try:
        # Build the required BrowseName set without creating NodeContracts
        # before namespace discovery.  NodeContract deliberately rejects an
        # empty namespace URI; the URI is only known after walking the server.
        required = {
            *COMMAND_NODES.values(),
            *(signal.node_name for signal in SIGNALS),
            *full_native_valve_read_browse_names(),
        }
        model_namespace_uri, bindings = wait_for_model_bindings(
            client, required, 60.0, include_full_valve_outputs=True
        )
        access_evidence = {
            field: read_access_evidence(bound)
            for field, bound in bindings.items()
        }
        time_node = client.get_node(ua.NodeId(10004, 0))
        step_node = client.get_node(ua.NodeId(10000, 0))
        command_nodes = {
            field: bindings[field] for field in COMMAND_NODES
        }
        current = float(time_node.get_value())
        written: dict[str, float] = {}
        gt_trip_requested = False
        st_trip_requested = False
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
                # These are ECMS-owned writes.  Their later reads are transport
                # echoes, not independent actuator feedback.
                "gt_trip_command_readback": float(gt_trip_requested),
                "common_st_trip_request": float(st_trip_requested),
                "lp_fwp_trip_command_readback": float(command),
                "lp_fwp_trip_latch_readback": float(electrical.trip_latched),
                "vcb_a02_trip_command_readback": float(electrical.trip_commanded),
                "vcb_a02_closed_readback": float(electrical.breaker_closed),
            }
            for field, value in updates.items():
                set_real_once(
                    command_nodes[field], value, written, field, ua,
                    write_service_status,
                )
            sent_ns = time.time_ns()
            next_time = request_step(step_node, time_node, current, ua, 30.0)
            row: dict[str, float | int] = {
                "sequence": len(rows), "time_s": next_time,
                "ecms_command_sent": int(command),
                "round_trip_ms": (time.time_ns() - sent_ns) / 1e6,
            }
            samples = batch_read_model_samples(client, bindings, ua)
            write_echo_status = evaluate_write_echoes(samples, written)
            data_value_evidence.extend(
                datavalue_rows(
                    len(rows), next_time, bindings, samples, access_evidence,
                    write_service_status, write_echo_status,
                )
            )
            require_trusted_model_samples(samples)
            require_verified_write_echoes(write_echo_status)
            for field in command_nodes:
                row[field] = int(float(samples[field].value) >= 0.5)
            for signal in SIGNALS:
                row[signal.field] = number(samples[signal.field].value)
            level = float(row["lp_drum_level_m"])
            row["lp_drum_level_l_alarm"] = int(l_alarm.update(next_time, level))
            row["lp_drum_level_ll_alarm"] = int(ll_alarm.update(next_time, level))
            ll_active = bool(row["lp_drum_level_ll_alarm"])
            gt_trip_requested, st_trip_requested = resolve_ll_trip_requests(
                ll_active, ll_trips_gt, ll_trips_st
            )
            row["common_gt_trip_request"] = int(gt_trip_requested)
            rows.append(row)
            sample_rows.append(samples)
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
    with (args.output_dir / "OPCUA-DATAVALUE.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=DATAVALUE_FIELDS)
        writer.writeheader()
        writer.writerows(data_value_evidence)
    if not rows:
        raise SystemExit(
            "NATIVE_OPCUA_FAIL: no trusted frames received"
            + (f"; {runtime_error}" if runtime_error else "")
        )
    with (args.output_dir / "ECMS-native-physical.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    events = build_native_events(rows, args.command_time, sample_rows)
    with (args.output_dir / "EVENT.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(events)
    report = validate_lp_bfp(
        rows, args.command_time, args.post_gt_trip_seconds,
        observed_node_count=len(bindings),
    )
    report["event_count"] = len(events)
    report["model_namespace_uri"] = model_namespace_uri
    report["model_binding"] = "NAMESPACE_URI_AND_BROWSE_NAME"
    report["model_datavalue_rows"] = len(data_value_evidence)
    report["model_datavalue_fields"] = [
        "Value", "StatusCode", "SourceTimestamp", "ServerTimestamp"
    ]
    report["solver_control_exception"] = {
        "namespace": 0,
        "step_node_id": 10000,
        "time_node_id": 10004,
        "scope": "OPENMODELICA_SERVER_CONTROL_ONLY",
    }
    report["write_authorization_and_proof"] = {
        "application_role": ECMS_WRITE_ROLE,
        "application_role_enforced_before_service": True,
        "advertised_access_is_evidence_not_service_result": True,
        "advertised_nonwritable_write_nodes": sorted(
            field for field in COMMAND_NODES
            if field in access_evidence and not (
                access_evidence[field].current_write_advertised and
                access_evidence[field].user_current_write_advertised
            )
        ),
        "write_service_status": {
            field: write_service_status.get(field, "NOT_ATTEMPTED")
            for field in COMMAND_NODES
        },
        "datavalue_echo_required": True,
    }
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
