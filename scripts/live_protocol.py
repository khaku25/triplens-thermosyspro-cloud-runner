#!/usr/bin/env python3
"""Versioned ECMS <-> native-valve OpenModelica FMU wire contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import BinaryIO


PROTOCOL = "TRIPLENS-LIVE/2"
MAX_FRAME_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ValvePoint:
    key: str
    label: str
    owner: str
    initial: float


@dataclass(frozen=True)
class VariableSpec:
    field: str
    fmu_name: str
    kind: str
    unit: str
    owner: str
    fmi_causality: str
    initial: float | bool | None = None


# DCS1 is deliberately limited to steam-turbine valves. HRSG/BOP valves are DCS2.
VALVE_POINTS = (
    ValvePoint("HPFWCV", "HP FWCV", "DCS2", 0.8),
    ValvePoint("HPSteam", "HP STEAM VALVE", "DCS1", 0.5),
    ValvePoint("IPFWCV", "IP FWCV", "DCS2", 0.8),
    ValvePoint("IPSteam", "IP STEAM VALVE", "DCS1", 0.5),
    ValvePoint("LPSteam", "LP STEAM VALVE", "DCS1", 0.8),
    ValvePoint("LPFW", "LP FEEDWATER VALVE", "DCS2", 0.5),
    ValvePoint("LPToHPIPFW", "LP TO HP/IP FW VALVE", "DCS2", 1.0),
    ValvePoint("CondExtraction", "CONDENSATE EXTRACTION VALVE", "DCS2", 0.8),
    ValvePoint("HPTurbAdm", "HP TURBINE ADMISSION", "DCS1", 0.8),
    ValvePoint("HPFWIso", "HP FW ISOLATION", "DCS2", 0.8),
    ValvePoint("IPFWIso", "IP FW ISOLATION", "DCS2", 0.8),
    ValvePoint("IPTurbAdm", "IP TURBINE ADMISSION", "DCS1", 0.8),
)


def _snake(value: str) -> str:
    result: list[str] = []
    for index, character in enumerate(value):
        if character.isupper() and index and not value[index - 1].isupper():
            result.append("_")
        result.append(character.lower())
    return "".join(result)


COMMAND_INPUTS = tuple(
    spec
    for point in VALVE_POINTS
    for spec in (
        VariableSpec(
            f"{_snake(point.key)}_mode_auto", f"fmuVlv{point.key}ModeAuto",
            "Boolean", "BOOL", point.owner, "input", True,
        ),
        VariableSpec(
            f"{_snake(point.key)}_manual_cmd", f"fmuVlv{point.key}ManualCmd",
            "Real", "pu", point.owner, "input", point.initial,
        ),
        VariableSpec(
            f"{_snake(point.key)}_fault_enable", f"fmuVlv{point.key}FaultEnable",
            "Boolean", "BOOL", point.owner, "input", False,
        ),
        VariableSpec(
            f"{_snake(point.key)}_fault_value", f"fmuVlv{point.key}FaultValue",
            "Real", "pu", point.owner, "input", 0.0,
        ),
    )
)


_OUTPUT_SUFFIXES = (
    ("auto_cmd", "AutoCmd", "Real", "pu"),
    ("cmd", "Cmd", "Real", "pu"),
    ("fb", "Fb", "Real", "pu"),
    ("deviation", "Deviation", "Real", "pu"),
    ("fault_active", "FaultActive", "Boolean", "BOOL"),
    ("cv", "Cv", "Real", "Cv"),
    ("mass_flow", "MassFlow", "Real", "t/h"),
    ("delta_p", "Dp", "Real", "Pa"),
)


VALVE_TELEMETRY = tuple(
    VariableSpec(
        f"{_snake(point.key)}_{field_suffix}",
        f"fmuVlv{point.key}{fmu_suffix}",
        kind,
        unit,
        point.owner,
        "output",
    )
    for point in VALVE_POINTS
    for field_suffix, fmu_suffix, kind, unit in _OUTPUT_SUFFIXES
)


# These are continuous states solved inside the same FMU. They are intentionally
# labelled "local" instead of pretending they have FMI output causality.
PROCESS_TELEMETRY = (
    VariableSpec("hp_drum_level", "BallonHP.yLevel.signal", "Real", "m", "DCS2", "local"),
    VariableSpec("ip_drum_level", "BallonMP.yLevel.signal", "Real", "m", "DCS2", "local"),
    VariableSpec("lp_drum_level", "BallonBP.yLevel.signal", "Real", "m", "DCS2", "local"),
    VariableSpec("hp_drum_pressure", "BallonHP.P", "Real", "Pa", "DCS2", "local"),
    VariableSpec("ip_drum_pressure", "BallonMP.P", "Real", "Pa", "DCS2", "local"),
    VariableSpec("lp_drum_pressure", "BallonBP.P", "Real", "Pa", "DCS2", "local"),
    VariableSpec("hp_drum_temperature", "BallonHP.Tp", "Real", "K", "DCS2", "local"),
    VariableSpec("ip_drum_temperature", "BallonMP.Tp", "Real", "K", "DCS2", "local"),
    VariableSpec("lp_drum_temperature", "BallonBP.Tp", "Real", "K", "DCS2", "local"),
)


LIVE_SIGNALS = VALVE_TELEMETRY + PROCESS_TELEMETRY


def command_defaults() -> dict[str, float | bool]:
    return {spec.fmu_name: spec.initial for spec in COMMAND_INPUTS}  # type: ignore[misc]


def scenario_commands(sim_time_s: float) -> dict[str, float | bool]:
    """Deterministic commissioning commands, applied directly to FMI inputs."""
    values = command_defaults()
    if sim_time_s >= 0.25:
        values["fmuVlvHPSteamModeAuto"] = False
        values["fmuVlvHPSteamManualCmd"] = 0.45
    if sim_time_s >= 0.75:
        values["fmuVlvIPTurbAdmFaultEnable"] = True
        values["fmuVlvIPTurbAdmFaultValue"] = 0.60
    return values


def contract_sha256() -> str:
    encoded = json.dumps(
        {
            "protocol": PROTOCOL,
            "inputs": [asdict(item) for item in COMMAND_INPUTS],
            "telemetry": [asdict(item) for item in LIVE_SIGNALS],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def encode_frame(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def read_frame(stream: BinaryIO) -> tuple[dict[str, object], bytes]:
    raw = stream.readline(MAX_FRAME_BYTES + 1)
    if not raw:
        raise EOFError("peer closed the TCP stream")
    if len(raw) > MAX_FRAME_BYTES:
        raise ValueError("network frame exceeded the 2 MiB limit")
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
