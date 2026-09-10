#!/usr/bin/env python3
"""Shared, versioned ECMS <-> physical-FMU wire contract."""

from __future__ import annotations

import json
from typing import BinaryIO


PROTOCOL = "TRIPLENS-LIVE/1"
MAX_FRAME_BYTES = 1024 * 1024
COMMAND_INPUT = "vppExternalTripCommand"

# (ECMS field, FMU scalar variable, FMI type, engineering unit, display owner)
LIVE_SIGNALS: tuple[tuple[str, str, str, str, str], ...] = (
    ("gt_trip_cmd", "vppGTTripCmd", "Boolean", "BOOL", "DCS1"),
    ("gt_trip_latch", "vppGTTripLatch", "Boolean", "BOOL", "DCS1"),
    ("st_trip_latch", "vppSTTripLatchPublished", "Boolean", "BOOL", "DCS1"),
    ("cb_52gt_trip_cmd", "vpp52GTTripCmd", "Boolean", "BOOL", "ECMS"),
    ("cb_52gt_closed", "vpp52GTClosed", "Boolean", "BOOL", "ECMS"),
    ("cb_52st_trip_cmd", "vpp52STTripCmd", "Boolean", "BOOL", "ECMS"),
    ("cb_52st_closed", "vpp52STClosed", "Boolean", "BOOL", "ECMS"),
    ("gtg_power_mw", "vppGTGPowerMW", "Real", "MW", "DCS1"),
    ("gtg_speed_rpm", "vppGTGSpeedRPM", "Real", "rpm", "DCS1"),
    ("gt_exhaust_mass_flow_t_h", "vppGTExhaustMassFlowTH", "Real", "t/h", "DCS1"),
    ("gt_exhaust_temperature_k", "vppGTExhaustTemperatureK", "Real", "K", "DCS1"),
    ("hp_drum_level_m", "vppHPDrumLevelM", "Real", "m", "DCS2"),
    ("ip_drum_level_m", "vppIPDrumLevelM", "Real", "m", "DCS2"),
    ("lp_drum_level_m", "vppLPDrumLevelM", "Real", "m", "DCS2"),
    ("hp_drum_pressure_pa", "vppHPDrumPressurePa", "Real", "Pa", "DCS2"),
    ("ip_drum_pressure_pa", "vppIPDrumPressurePa", "Real", "Pa", "DCS2"),
    ("lp_drum_pressure_pa", "vppLPDrumPressurePa", "Real", "Pa", "DCS2"),
    ("hp_steam_flow_t_h", "vppHPTurbineSteamFlowTH", "Real", "t/h", "DCS2"),
    ("ip_steam_flow_t_h", "vppIPTurbineSteamFlowTH", "Real", "t/h", "DCS2"),
    ("lp_steam_flow_t_h", "vppLPTurbineSteamFlowTH", "Real", "t/h", "DCS2"),
    ("hp_admission_valve_pu", "vppHPAdmissionPositionPU", "Real", "pu", "DCS1"),
    ("ip_admission_valve_pu", "vppIPAdmissionPositionPU", "Real", "pu", "DCS1"),
    ("lp_admission_multiplier_pu", "vppLPAdmissionMultiplierPU", "Real", "pu", "DCS1"),
    ("hp_bypass_valve_pu", "vppHPBypassPositionPU", "Real", "pu", "DCS2"),
    ("lp_bypass_valve_pu", "vppLPBypassPositionPU", "Real", "pu", "DCS2"),
    ("hp_bypass_steam_flow_t_h", "vppHPBypassMassFlowTH", "Real", "t/h", "DCS2"),
    ("lp_bypass_steam_flow_t_h", "vppLPBypassMassFlowTH", "Real", "t/h", "DCS2"),
    ("hp_bypass_spray_flow_t_h", "vppHPSprayMassFlowTH", "Real", "t/h", "DCS2"),
    ("lp_bypass_spray_flow_t_h", "vppLPSprayMassFlowTH", "Real", "t/h", "DCS2"),
    ("condenser_pressure_pa", "vppCondenserPressurePa", "Real", "Pa", "DCS2"),
    ("condenser_level_m", "vppCondenserLevelM", "Real", "m", "DCS2"),
)


def encode_frame(payload: dict[str, object]) -> bytes:
    """Return one deterministic UTF-8 JSON-line network frame."""
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def read_frame(stream: BinaryIO) -> tuple[dict[str, object], bytes]:
    raw = stream.readline(MAX_FRAME_BYTES + 1)
    if not raw:
        raise EOFError("peer closed the TCP stream")
    if len(raw) > MAX_FRAME_BYTES:
        raise ValueError("network frame exceeded the 1 MiB limit")
    if not raw.endswith(b"\n"):
        raise ValueError("unterminated JSON-line frame")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("network frame must be a JSON object")
    if payload.get("protocol") != PROTOCOL:
        raise ValueError("network protocol version mismatch")
    return payload, raw


def write_frame(stream: BinaryIO, payload: dict[str, object]) -> bytes:
    raw = encode_frame(payload)
    stream.write(raw)
    stream.flush()
    return raw
