#!/usr/bin/env python3
"""Generate ECMS observations while keeping ThermoSysPro M data immutable.

M values enter through ProcessBus. Electrical topology, ratings and delays are
external A settings. Breaker states and electrical values are E/C outputs.
There is no SST: GT/ST main transformers can reverse-feed the auxiliary buses.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from bisect import bisect_left
from dataclasses import dataclass, replace
from pathlib import Path

from common_trip import load_common_trip_matrix, resolve_common_trips
from validate_commands import load_catalog, validate_queue


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_ECMS_TREND_SAMPLES = 125_000


@dataclass(frozen=True)
class Event:
    time_ms: int
    tag: str
    old_value: str
    new_value: str
    event_class: str
    description: str
    provenance: str = "E_DERIVED"
    quality: str = "GOOD"


def load_processbus(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) < 2:
        raise ValueError("ProcessBus must contain at least two rows")
    return rows


def parse_bool(raw: str, field: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{field} must be a BOOL value, got {raw!r}")


def derive_config_status(rows: list[dict[str, str]], label: str) -> str:
    statuses = {row.get("status", "").strip().upper() for row in rows}
    statuses.discard("")
    if not statuses:
        raise ValueError(f"{label} contain no configuration status")
    if "PROVISIONAL" in statuses:
        return "PROVISIONAL"
    if len(statuses) == 1:
        return next(iter(statuses))
    return "MIXED"


def combine_config_status(settings_status: str, equipment_status: str) -> str:
    if "PROVISIONAL" in {settings_status, equipment_status}:
        return "PROVISIONAL"
    if settings_status == equipment_status:
        return settings_status
    return "MIXED"


def load_a_settings(path: Path) -> tuple[dict[str, float | bool | str], str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("A settings are empty")
    settings: dict[str, float | bool | str] = {}
    for row in rows:
        key = row["setting_id"].strip()
        if not key:
            raise ValueError("A setting has an empty setting_id")
        if key in settings:
            raise ValueError(f"duplicate A setting: {key}")
        raw = row["value"].strip()
        if row["unit"].strip().upper() == "BOOL":
            settings[key] = parse_bool(raw, key)
        else:
            try:
                settings[key] = float(raw)
            except ValueError:
                settings[key] = raw
    required = {
        "AUX_BUS_VOLTAGE_KV", "POWER_FACTOR", "GTG_PRETRIP_POWER_MW",
        "GT_TERMINAL_VOLTAGE_KV", "ST_TERMINAL_VOLTAGE_KV",
        "TRIP_RECEIVE_DELAY_MS", "LOCKOUT_OPERATE_DELAY_MS",
        "GT_BREAKER_OPEN_DELAY_MS", "GT_POWER_DECAY_MS",
        "ST_BREAKER_OPEN_DELAY_MS", "MOTOR_BREAKER_OPEN_DELAY_MS",
        "FEEDER_FAULT_CURRENT_A", "FEEDER_FAULT_RESIDUAL_VOLTAGE_PU",
        "FEEDER_50_PICKUP_A", "FEEDER_50_DELAY_MS", "FEEDER_51_PICKUP_A",
        "FEEDER_51_TIME_MULTIPLIER",
        "UNDERVOLTAGE_PICKUP_PU", "UNDERVOLTAGE_DELAY_MS",
        "TREND_PERIOD_MS", "CLOCK_OFFSET_MS", "AUTO_BUS_TIE_TRANSFER",
        "GRID_VOLTAGE_KV", "ALLOW_SOURCE_PARALLEL",
    }
    missing = required.difference(settings)
    if missing:
        raise ValueError("A settings are missing: " + ", ".join(sorted(missing)))
    for key in ("GRID_VOLTAGE_KV", "GT_TERMINAL_VOLTAGE_KV", "ST_TERMINAL_VOLTAGE_KV", "AUX_BUS_VOLTAGE_KV"):
        if not math.isfinite(float(settings[key])) or float(settings[key]) <= 0:
            raise ValueError(f"{key} must be greater than zero")
    if not 0 < float(settings["POWER_FACTOR"]) <= 1:
        raise ValueError("POWER_FACTOR must be in (0, 1]")
    if not 0 < float(settings["UNDERVOLTAGE_PICKUP_PU"]) <= 1:
        raise ValueError("UNDERVOLTAGE_PICKUP_PU must be in (0, 1]")
    if not 0 <= float(settings["FEEDER_FAULT_RESIDUAL_VOLTAGE_PU"]) < 1:
        raise ValueError("FEEDER_FAULT_RESIDUAL_VOLTAGE_PU must be in [0, 1)")
    for key in (
        "FEEDER_FAULT_CURRENT_A", "FEEDER_50_PICKUP_A", "FEEDER_51_PICKUP_A",
        "FEEDER_51_TIME_MULTIPLIER",
    ):
        if not math.isfinite(float(settings[key])) or float(settings[key]) <= 0:
            raise ValueError(f"{key} must be greater than zero")
    for key in (
        "TRIP_RECEIVE_DELAY_MS", "LOCKOUT_OPERATE_DELAY_MS",
        "GT_BREAKER_OPEN_DELAY_MS", "GT_POWER_DECAY_MS",
        "ST_BREAKER_OPEN_DELAY_MS", "MOTOR_BREAKER_OPEN_DELAY_MS", "FEEDER_50_DELAY_MS",
        "UNDERVOLTAGE_DELAY_MS",
    ):
        if not math.isfinite(float(settings[key])) or float(settings[key]) < 0:
            raise ValueError(f"{key} must be non-negative")
    for key in (
        "TRIP_RECEIVE_DELAY_MS", "LOCKOUT_OPERATE_DELAY_MS",
        "GT_BREAKER_OPEN_DELAY_MS", "GT_POWER_DECAY_MS",
        "ST_BREAKER_OPEN_DELAY_MS", "MOTOR_BREAKER_OPEN_DELAY_MS", "FEEDER_50_DELAY_MS",
        "UNDERVOLTAGE_DELAY_MS",
        "TREND_PERIOD_MS", "CLOCK_OFFSET_MS",
    ):
        value = float(settings[key])
        if not value.is_integer():
            raise ValueError(f"{key} must be an integer number of milliseconds")
    if int(settings["TREND_PERIOD_MS"]) <= 0:
        raise ValueError("TREND_PERIOD_MS must be greater than zero")
    if bool(settings["ALLOW_SOURCE_PARALLEL"]):
        raise ValueError(
            "ALLOW_SOURCE_PARALLEL=true is unsupported: the VPP has no synchronism/phase-angle model"
        )
    return settings, derive_config_status(rows, "A settings")


def load_a_equipment(path: Path) -> list[dict[str, str]]:
    required = {
        "equipment_id", "label_ko", "bus", "feeder_id", "voltage_kv",
        "rated_kw", "normal_breaker_state", "normal_run_state", "priority", "status",
    }
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        missing = required.difference(fields)
        if missing:
            raise ValueError("A equipment is missing columns: " + ", ".join(sorted(missing)))
        rows = list(reader)
    if not rows:
        raise ValueError("A equipment is empty")
    equipment_ids: set[str] = set()
    feeder_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        equipment_id = row["equipment_id"].strip().upper()
        feeder_id = row["feeder_id"].strip()
        if not equipment_id or not feeder_id:
            raise ValueError(f"A equipment row {row_number} has an empty ID")
        if equipment_id in equipment_ids:
            raise ValueError(f"duplicate equipment_id: {equipment_id}")
        if feeder_id in feeder_ids:
            raise ValueError(f"duplicate feeder_id: {feeder_id}")
        equipment_ids.add(equipment_id)
        feeder_ids.add(feeder_id)
        row["equipment_id"] = equipment_id
        row["feeder_id"] = feeder_id
        row["bus"] = row["bus"].strip().upper()
        if row["bus"] not in {"BUS-A", "BUS-B"}:
            raise ValueError(f"{equipment_id}: bus must be BUS-A or BUS-B")
        try:
            voltage_kv = float(row["voltage_kv"])
        except ValueError as exc:
            raise ValueError(f"{equipment_id}: voltage_kv is not numeric") from exc
        if not math.isfinite(voltage_kv) or voltage_kv <= 0:
            raise ValueError(f"{equipment_id}: voltage_kv must be a positive finite number")
        if row["rated_kw"].strip():
            try:
                rated_kw = float(row["rated_kw"])
            except ValueError as exc:
                raise ValueError(f"{equipment_id}: rated_kw is not numeric") from exc
            if not math.isfinite(rated_kw) or rated_kw < 0:
                raise ValueError(f"{equipment_id}: rated_kw must be non-negative")
        row["normal_breaker_state"] = row["normal_breaker_state"].strip().upper()
        if row["normal_breaker_state"] not in {"OPEN", "CLOSED"}:
            raise ValueError(f"{equipment_id}: normal_breaker_state must be OPEN or CLOSED")
        row["normal_run_state"] = row["normal_run_state"].strip().upper()
        if row["normal_run_state"] not in {"RUNNING", "STOPPED"}:
            raise ValueError(f"{equipment_id}: normal_run_state must be RUNNING or STOPPED")
        if not row["status"].strip():
            raise ValueError(f"{equipment_id}: status is empty")
    return rows


def load_m_links(path: Path, m_tags_path: Path) -> dict[str, list[tuple[str, str]]]:
    required = {"link_id", "ecms_equipment_id", "source_m_tag_id", "locked"}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        missing = required.difference(fields)
        if missing:
            raise ValueError("M links are missing columns: " + ", ".join(sorted(missing)))
        rows = list(reader)
    link_ids: set[str] = set()
    result: dict[str, list[tuple[str, str]]] = {}
    for row_number, row in enumerate(rows, start=2):
        if not parse_bool(row["locked"], f"M links row {row_number} locked"):
            raise ValueError("every ECMS M link must remain locked")
        equipment_id = row["ecms_equipment_id"].strip().upper()
        link_id = row["link_id"].strip()
        source_tag = row["source_m_tag_id"].strip()
        if not equipment_id or not link_id or not source_tag:
            raise ValueError(f"M links row {row_number} has an empty locked-link identifier")
        if link_id in link_ids:
            raise ValueError(f"duplicate M link_id: {link_id}")
        link_ids.add(link_id)
        result.setdefault(equipment_id, []).append((link_id, source_tag))

    with m_tags_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        required_tags = {"tag_id", "tag_class", "value_basis"}
        missing = required_tags.difference(fields)
        if missing:
            raise ValueError("M-tag catalog is missing columns: " + ", ".join(sorted(missing)))
        tag_rows = list(reader)
    tag_ids = [row["tag_id"].strip() for row in tag_rows]
    if len(tag_ids) != len(set(tag_ids)):
        raise ValueError("M-tag catalog contains a duplicate tag_id")
    if any(
        row["tag_class"].strip().upper() != "M" or row["value_basis"].strip().upper() != "M"
        for row in tag_rows
    ):
        raise ValueError("M-tag catalog contains a non-M row")
    known_tags = set(tag_ids)
    unknown = sorted({source for links in result.values() for _, source in links}.difference(known_tags))
    if unknown:
        raise ValueError("M links reference unknown M tags: " + ", ".join(unknown))
    return result


@dataclass(frozen=True)
class LinearSeries:
    """Prepared scalar series for repeated linear interpolation.

    ProcessBus rows are sampled many times while producing a fine-grained ECMS
    trend. Preparing numeric columns once and locating each interval with a
    binary search avoids rescanning and reparsing the complete ProcessBus for
    every output sample.
    """

    times_s: tuple[float, ...]
    values: tuple[float, ...]

    @classmethod
    def from_rows(cls, rows: list[dict[str, str]], field: str) -> "LinearSeries":
        if field not in rows[0]:
            return cls((), ())
        samples = [
            (float(row["time_s"]), float(row[field]))
            for row in rows if row.get(field, "").strip()
        ]
        if not samples:
            return cls((), ())
        return cls(
            tuple(item[0] for item in samples),
            tuple(item[1] for item in samples),
        )

    def at(self, time_s: float) -> float:
        if not self.times_s:
            return 0.0
        if time_s <= self.times_s[0]:
            return self.values[0]
        right_index = bisect_left(self.times_s, time_s, 1)
        if right_index >= len(self.times_s):
            return self.values[-1]
        left_index = right_index - 1
        t0, t1 = self.times_s[left_index], self.times_s[right_index]
        v0, v1 = self.values[left_index], self.values[right_index]
        ratio = (time_s - t0) / (t1 - t0)
        return v0 + ratio * (v1 - v0)


def interpolate(rows: list[dict[str, str]], field: str, time_s: float) -> float:
    """Compatibility wrapper for one-off interpolation calls."""
    return LinearSeries.from_rows(rows, field).at(time_s)


@dataclass(frozen=True)
class StepSeries:
    """Prepared zero-order-hold series for digital state and metadata."""

    times_ms: tuple[int, ...]
    values: tuple[str, ...]

    @classmethod
    def from_rows(cls, rows: list[dict[str, str]], field: str) -> "StepSeries":
        if not rows or field not in rows[0]:
            return cls((), ())
        samples = [
            (round(float(row["time_s"]) * 1000), row[field].strip())
            for row in rows if row.get(field, "").strip()
        ]
        return cls(
            tuple(item[0] for item in samples),
            tuple(item[1] for item in samples),
        )

    def at(self, time_ms: int) -> str | None:
        if not self.times_ms or time_ms < self.times_ms[0]:
            return None
        right = bisect_left(self.times_ms, time_ms + 1)
        return self.values[right - 1]

    def bool_at(self, time_ms: int) -> bool | None:
        raw = self.at(time_ms)
        return None if raw is None else parse_bool(raw, "observed ProcessBus state")

    def transition_events(
        self,
        tag: str,
        event_class: str,
        description: str,
        provenance: str,
    ) -> list[Event]:
        events: list[Event] = []
        for index in range(1, len(self.values)):
            if self.values[index] != self.values[index - 1]:
                events.append(Event(
                    self.times_ms[index], tag, self.values[index - 1], self.values[index],
                    event_class, description, provenance,
                ))
        return events

    def first_falling_edge_ms(self) -> int | None:
        for index in range(1, len(self.values)):
            before = parse_bool(self.values[index - 1], "observed ProcessBus state")
            after = parse_bool(self.values[index], "observed ProcessBus state")
            if before and not after:
                return self.times_ms[index]
        return None


def build_sample_times(
    start_ms: int,
    stop_ms: int,
    normal_period_ms: int,
    trip_ms: int,
    sampling_profile: str,
    incident_period_ms: int,
    incident_pre_ms: int,
    incident_post_ms: int,
) -> tuple[list[int], int | None, int | None]:
    """Build a deterministic uniform or incident-window ECMS sampling grid."""
    if stop_ms < start_ms:
        raise ValueError("ECMS stop time must not precede start time")
    if normal_period_ms <= 0:
        raise ValueError("normal ECMS trend period must be greater than zero")
    if sampling_profile not in {"standard", "causal_100ms", "incident_1ms"}:
        raise ValueError(f"unknown sampling profile: {sampling_profile}")
    if incident_period_ms <= 0:
        raise ValueError("incident period must be greater than zero")
    if incident_period_ms > normal_period_ms:
        raise ValueError("incident period must not exceed the normal trend period")
    if sampling_profile == "incident_1ms" and incident_period_ms != 1:
        raise ValueError("incident_1ms requires an incident period of exactly 1 ms")
    if incident_pre_ms < 0 or incident_post_ms < 0:
        raise ValueError("incident window lengths must be non-negative")

    incident_start_ms: int | None = None
    incident_stop_ms: int | None = None
    estimated_samples = (stop_ms - start_ms) // normal_period_ms + 3
    if sampling_profile == "incident_1ms":
        incident_start_ms = max(start_ms, trip_ms - incident_pre_ms)
        incident_stop_ms = min(stop_ms, trip_ms + incident_post_ms)
        estimated_samples += (
            (incident_stop_ms - incident_start_ms) // incident_period_ms + 3
        )
    if estimated_samples > MAX_ECMS_TREND_SAMPLES:
        raise ValueError(
            "requested ECMS sampling grid is too large; shorten the run/window "
            "or increase the normal trend period"
        )

    sample_times = set(range(start_ms, stop_ms + 1, normal_period_ms))
    sample_times.update({start_ms, stop_ms})
    if sampling_profile == "incident_1ms":
        assert incident_start_ms is not None and incident_stop_ms is not None
        sample_times.update(
            range(incident_start_ms, incident_stop_ms + 1, incident_period_ms)
        )
        sample_times.update({incident_start_ms, incident_stop_ms, trip_ms})
    return sorted(sample_times), incident_start_ms, incident_stop_ms


def decay(time_ms: int, start_ms: int, duration_ms: int) -> float:
    if time_ms <= start_ms:
        return 1.0
    if duration_ms <= 0 or time_ms >= start_ms + duration_ms:
        return 0.0
    return 1.0 - (time_ms - start_ms) / duration_ms


def rms_current_a(power_mw: float, voltage_kv: float, power_factor: float) -> float:
    if voltage_kv <= 0 or power_factor <= 0:
        return 0.0
    return abs(power_mw) * 1_000.0 / (math.sqrt(3.0) * voltage_kv * power_factor)


def iec_standard_inverse_ms(current_a: float, pickup_a: float, time_multiplier: float) -> int | None:
    """IEC standard-inverse overcurrent time; settings remain explicitly provisional."""
    multiple = current_a / pickup_a
    if multiple <= 1.0:
        return None
    seconds = time_multiplier * 0.14 / (multiple**0.02 - 1.0)
    return max(1, math.ceil(seconds * 1000.0))


@dataclass(frozen=True)
class FeederProtection:
    equipment_id: str
    feeder_id: str
    fault_start_ms: int
    fault_current_a: float
    residual_voltage_pu: float
    relay_50_operate_ms: int | None
    relay_51_operate_ms: int | None
    trip_command_ms: int | None
    breaker_open_ms: int | None


def resolve_feeder_protection(
    fault: dict[str, object],
    equipment: list[dict[str, str]],
    settings: dict[str, float | bool | str],
    fault_start_ms: int,
) -> FeederProtection | None:
    equipment_id = str(fault.get("feeder_fault", "")).strip().upper()
    if not equipment_id:
        return None
    matches = [item for item in equipment if item["equipment_id"] == equipment_id]
    if len(matches) != 1:
        raise ValueError(f"fault preset references unknown feeder equipment {equipment_id!r}")
    current_a = float(fault.get("feeder_fault_current_a", settings["FEEDER_FAULT_CURRENT_A"]))
    if not math.isfinite(current_a) or current_a <= 0:
        raise ValueError("feeder fault current must be a positive finite RMS value")
    residual_pu = float(settings["FEEDER_FAULT_RESIDUAL_VOLTAGE_PU"])
    relay_50_ms = (
        fault_start_ms + int(settings["FEEDER_50_DELAY_MS"])
        if current_a >= float(settings["FEEDER_50_PICKUP_A"]) else None
    )
    relay_51_delay_ms = iec_standard_inverse_ms(
        current_a,
        float(settings["FEEDER_51_PICKUP_A"]),
        float(settings["FEEDER_51_TIME_MULTIPLIER"]),
    )
    relay_51_ms = (
        None if relay_51_delay_ms is None else fault_start_ms + relay_51_delay_ms
    )
    trip_command_ms = min(
        (value for value in (relay_50_ms, relay_51_ms) if value is not None),
        default=None,
    )
    breaker_open_ms = (
        None if trip_command_ms is None
        else trip_command_ms + int(settings["MOTOR_BREAKER_OPEN_DELAY_MS"])
    )
    item = matches[0]
    return FeederProtection(
        equipment_id=equipment_id,
        feeder_id=item["feeder_id"],
        fault_start_ms=fault_start_ms,
        fault_current_a=current_a,
        residual_voltage_pu=residual_pu,
        relay_50_operate_ms=relay_50_ms,
        relay_51_operate_ms=relay_51_ms,
        trip_command_ms=trip_command_ms,
        breaker_open_ms=breaker_open_ms,
    )


def first_below(rows: list[dict[str, str]], field: str, threshold: float) -> int | None:
    for row in rows:
        if abs(float(row[field])) < threshold:
            return round(float(row["time_s"]) * 1000)
    return None


def command_rows_for(
    commands: list[dict[str, str]], equipment_id: str, time_ms: int,
) -> list[dict[str, str]]:
    equipment_id = equipment_id.upper()
    return [
        row for row in commands
        if row["equipment_id"].strip().upper() == equipment_id
        and round(float(row["time_s"]) * 1000) <= time_ms
    ]


def apply_availability_command(
    initial_state: bool,
    commands: list[dict[str, str]],
    equipment_id: str,
    time_ms: int,
) -> bool:
    relevant = command_rows_for(commands, equipment_id, time_ms)
    if not relevant:
        return initial_state
    action = relevant[-1]["command"].strip().upper()
    if action in {"IN_SERVICE", "RESTORE", "START", "CLOSE"}:
        return True
    if action in {"OUT_OF_SERVICE", "LOSS", "STOP", "TRIP", "OPEN"}:
        return False
    return initial_state


def breaker_with_automatic_trip(
    initial_state: bool,
    automatic_trip_ms: int | None,
    time_ms: int,
    commands: list[dict[str, str]],
    equipment_id: str,
) -> bool:
    state = initial_state
    latched = False
    automatic_applied = automatic_trip_ms is None
    for row in command_rows_for(commands, equipment_id, time_ms):
        command_ms = round(float(row["time_s"]) * 1000)
        if not automatic_applied and automatic_trip_ms is not None and automatic_trip_ms <= command_ms:
            state = False
            latched = True
            automatic_applied = True
        action = row["command"].strip().upper()
        if action == "RESET":
            latched = False
        elif action in {"OPEN", "TRIP", "OUT_OF_SERVICE", "LOSS"}:
            state = False
            if action == "TRIP":
                latched = True
        elif action in {"CLOSE", "IN_SERVICE", "RESTORE"} and not latched:
            state = True
    if not automatic_applied and automatic_trip_ms is not None and automatic_trip_ms <= time_ms:
        state = False
    return state


@dataclass(frozen=True)
class MotorFeederState:
    breaker_closed: bool
    run_enable: bool
    run_command_feedback: bool
    run_feedback: bool
    speed_proven: bool | None
    trip_latched: bool
    trip_commanded: bool
    state_code: int | None


def motor_feeder_state(
    *,
    initial_breaker_closed: bool,
    initial_running: bool,
    time_ms: int,
    commands: list[dict[str, str]],
    equipment_id: str,
    feeder_id: str,
    breaker_open_delay_ms: int,
    automatic_trip_command_ms: int | None = None,
    observed: dict[str, StepSeries] | None = None,
) -> MotorFeederState:
    """Separate motor run control from its normally closed feeder breaker."""
    breaker_closed = initial_breaker_closed
    run_enable = initial_running
    run_command_feedback = initial_running
    run_feedback = initial_running and initial_breaker_closed
    trip_latched = False
    trip_commanded = False
    pending_breaker_opens: list[int] = []

    relevant = [
        row for row in commands
        if row["equipment_id"].strip().upper() in {equipment_id.upper(), feeder_id.upper()}
        and round(float(row["time_s"]) * 1000) <= time_ms
    ]
    relevant.sort(key=lambda row: (round(float(row["time_s"]) * 1000), int(row.get("sequence") or 0)))
    if automatic_trip_command_ms is not None and automatic_trip_command_ms <= time_ms:
        relevant.append({
            "time_s": str(automatic_trip_command_ms / 1000),
            "equipment_id": feeder_id,
            "command": "TRIP",
            "sequence": "999999999",
        })
        relevant.sort(key=lambda row: (round(float(row["time_s"]) * 1000), int(row.get("sequence") or 0)))

    for row in relevant:
        command_ms = round(float(row["time_s"]) * 1000)
        due_opens = [open_ms for open_ms in pending_breaker_opens if open_ms <= command_ms]
        if due_opens:
            breaker_closed = False
            run_feedback = False
            pending_breaker_opens = [
                open_ms for open_ms in pending_breaker_opens if open_ms > command_ms
            ]
        action = row["command"].strip().upper()
        target = row["equipment_id"].strip().upper()
        is_motor_command = target == equipment_id.upper()
        if action == "RESET":
            trip_latched = False
            trip_commanded = False
        elif action == "TRIP":
            trip_latched = True
            trip_commanded = True
            run_enable = False
            run_command_feedback = False
            pending_breaker_opens.append(command_ms + breaker_open_delay_ms)
        elif target == feeder_id.upper() and action in {"OPEN", "OUT_OF_SERVICE", "LOSS"}:
            breaker_closed = False
            run_enable = False
            run_command_feedback = False
            run_feedback = False
        elif target == feeder_id.upper() and action in {"CLOSE", "IN_SERVICE", "RESTORE"}:
            if not trip_latched:
                breaker_closed = True
        elif is_motor_command and action == "STOP":
            # Normal STOP removes the run command but deliberately leaves VCB CLOSED.
            run_enable = False
            run_command_feedback = False
            run_feedback = False
        elif is_motor_command and action == "START" and not trip_latched and breaker_closed:
            run_enable = True
            run_command_feedback = True
            run_feedback = True

    if any(open_ms <= time_ms for open_ms in pending_breaker_opens):
        breaker_closed = False
        run_feedback = False

    speed_proven: bool | None = run_feedback
    state_code: int | None = None
    if observed:
        overrides = {
            "breaker_closed": observed.get("breaker_closed"),
            "run_enable": observed.get("run_enable"),
            "run_command_feedback": observed.get("run_command_feedback"),
            "trip_latched": observed.get("trip_latched"),
            "trip_commanded": observed.get("trip_commanded"),
            "speed_proven": observed.get("speed_proven"),
        }
        values: dict[str, bool | None] = {
            name: series.bool_at(time_ms) if series is not None else None
            for name, series in overrides.items()
        }
        if values["breaker_closed"] is not None:
            breaker_closed = bool(values["breaker_closed"])
        if values["run_enable"] is not None:
            run_enable = bool(values["run_enable"])
        if values["run_command_feedback"] is not None:
            run_command_feedback = bool(values["run_command_feedback"])
        if values["trip_latched"] is not None:
            trip_latched = bool(values["trip_latched"])
        if values["trip_commanded"] is not None:
            trip_commanded = bool(values["trip_commanded"])
        if values["speed_proven"] is not None:
            speed_proven = bool(values["speed_proven"])
        state_series = observed.get("state_code")
        state_raw = state_series.at(time_ms) if state_series is not None else None
        if state_raw is not None:
            state_code = int(float(state_raw))
        # RUN_CMD_FB is intentionally not treated as physical current/run feedback.
        run_feedback = breaker_closed and (run_feedback or bool(speed_proven))

    return MotorFeederState(
        breaker_closed=breaker_closed,
        run_enable=run_enable,
        run_command_feedback=run_command_feedback,
        run_feedback=run_feedback,
        speed_proven=speed_proven,
        trip_latched=trip_latched,
        trip_commanded=trip_commanded,
        state_code=state_code,
    )


def relay_lockout_state(
    relay_operates: bool,
    lockout_ms: int,
    time_ms: int,
    commands: list[dict[str, str]],
) -> bool:
    state = relay_operates and time_ms >= lockout_ms
    if not state:
        return False
    return not any(
        row["command"].strip().upper() == "RESET"
        and lockout_ms <= round(float(row["time_s"]) * 1000) <= time_ms
        for row in command_rows_for(commands, "CB-52GT", time_ms)
    )


def write_events(path: Path, events: list[Event], clock_offset_ms: int) -> None:
    fields = [
        "event_time_ms", "source_time_ms", "system", "tag", "canonical_tag", "old_value",
        "new_value", "event_class", "quality", "provenance", "description",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        # Python's sort is stable, so equal-time protection events retain the
        # causal insertion order (Trip -> receive -> lockout -> breaker).
        for event in sorted(events, key=lambda item: item.time_ms):
            writer.writerow({
                "event_time_ms": event.time_ms + clock_offset_ms,
                "source_time_ms": event.time_ms,
                "system": "ECMS",
                "tag": event.tag,
                "canonical_tag": canonical_event_tag(event.tag),
                "old_value": event.old_value,
                "new_value": event.new_value,
                "event_class": event.event_class,
                "quality": event.quality,
                "provenance": event.provenance,
                "description": event.description,
            })


def canonical_event_tag(tag: str) -> str:
    """Return a stable external tag while retaining the legacy tag column."""
    explicit = {
        "GT.TRIP.CMD": "CMD.GTG.TRIP",
        "ST.TRIP.CMD": "CMD.STG.TRIP",
        "52GT.OPEN.CMD": "CMD.CB-52GT.OPEN",
        "GT.TRIP.FROM_52GT_OPEN": "CTRL.GTG.TRIP_FROM_52GT_OPEN",
        "GT.TRIP.OPCUA.READBACK": "CTRL.GTG.TRIP_OPCUA_READBACK",
        "GT.TRIP.PHYSICS.LATCH": "CTRL.GTG.TRIP_PHYSICS_LATCH",
        "GT.TRIP.LATCH": "CTRL.GTG.TRIP_LATCH",
        "ST.TRIP.LATCH": "CTRL.STG.TRIP_LATCH",
        "FWP-HP.TRIP.INPUT": "CMD.FWP-HP.TRIP",
        "52GT.CLOSED": "ECMS.52GT.CLOSED",
        "52ST.CLOSED": "ECMS.52ST.CLOSED",
        "CB-IN-A.CLOSED": "ECMS.CB-IN-A.CLOSED",
        "CB-IN-B.CLOSED": "ECMS.CB-IN-B.CLOSED",
        "CB-TIE-AB.CLOSED": "ECMS.CB-TIE-AB.CLOSED",
        "VCB-A01.TRIP.CMD": "ECMS.VCB-A01.TRIP_CMD",
        "VCB-A01.CLOSED": "ECMS.VCB-A01.CLOSED",
        "FWP-HP.TRIP.LATCH": "CTRL.FWP-HP.TRIP_LATCH",
    }
    if tag in explicit:
        return explicit[tag]
    if tag.startswith("VCB-") and tag.endswith(".TRIP.CMD"):
        return "ECMS." + tag.removesuffix(".TRIP.CMD") + ".TRIP_CMD"
    if tag.startswith("VCB-") and tag.endswith(".CLOSED"):
        return "ECMS." + tag
    if tag.startswith("COMMAND."):
        return "CMD." + tag.removeprefix("COMMAND.")
    if tag.startswith("CMD.") or tag.startswith("ECMS.") or tag.startswith("CTRL."):
        return tag
    return "ECMS." + tag


def add_undervoltage_events(
    trend_rows: list[dict[str, str | int]],
    events: list[Event],
    pickup_pu: float,
    delay_ms: int,
) -> None:
    """Add a 27UV event only after continuously low sampled bus voltage."""
    if not trend_rows:
        return
    last_time_ms = int(trend_rows[-1]["source_time_ms"])
    for bus_name, field in (("BUS-A", "bus_a_voltage_pu"), ("BUS-B", "bus_b_voltage_pu")):
        low_start_ms: int | None = None
        for row in trend_rows:
            source_time_ms = int(row["source_time_ms"])
            if float(row[field]) < pickup_pu:
                if low_start_ms is None:
                    low_start_ms = source_time_ms
                operate_ms = low_start_ms + delay_ms
                if source_time_ms >= operate_ms:
                    events.append(Event(
                        operate_ms,
                        f"{bus_name}.27UV.OPERATE",
                        "0",
                        "1",
                        "OPERATE",
                        f"{bus_name} undervoltage persisted for {delay_ms} ms",
                        quality=str(row["quality"]),
                    ))
                    break
            else:
                low_start_ms = None
        else:
            # A zero-delay event can fall exactly on the final trend sample.
            if low_start_ms is not None and low_start_ms + delay_ms <= last_time_ms:
                operate_ms = low_start_ms + delay_ms
                quality = next(
                    str(row["quality"])
                    for row in trend_rows
                    if int(row["source_time_ms"]) >= operate_ms
                )
                events.append(Event(
                    operate_ms,
                    f"{bus_name}.27UV.OPERATE",
                    "0",
                    "1",
                    "OPERATE",
                    f"{bus_name} undervoltage persisted for {delay_ms} ms",
                    quality=quality,
                ))


def write_feeders(
    path: Path,
    trend_rows: list[dict[str, str | int]],
    equipment: list[dict[str, str]],
    m_links: dict[str, tuple[str, str]],
    power_factor: float,
    commands: list[dict[str, str]],
    processbus_rows: list[dict[str, str]],
    breaker_open_delay_ms: int,
    automatic_trip_commands: dict[str, int] | None = None,
    feeder_protection: FeederProtection | None = None,
) -> None:
    fields = [
        "ecms_time_ms", "source_time_ms", "quality", "a_config_status",
        "equipment_id", "label_ko", "bus", "feeder_id", "configured_voltage_kv",
        "rated_kw", "breaker_closed", "run_enable", "run_command_feedback",
        "run_feedback", "speed_proven", "trip_latched", "trip_commanded", "state_code",
        "fault_present", "fault_current_a", "relay_50_operated", "relay_51_operated",
        "energized", "bus_voltage_kv", "terminal_voltage_kv", "current_a",
        "priority", "equipment_status", "m_link_id", "source_m_tag_id", "provenance",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    automatic_trip_commands = automatic_trip_commands or {}
    observations: dict[str, dict[str, StepSeries]] = {}
    for item in equipment:
        prefix = item["equipment_id"].strip().lower().replace("-", "_")
        observations[item["equipment_id"]] = {
            "breaker_closed": StepSeries.from_rows(processbus_rows, f"{prefix}_vcb_closed"),
            "run_enable": StepSeries.from_rows(processbus_rows, f"{prefix}_run_enable"),
            "run_command_feedback": StepSeries.from_rows(
                processbus_rows, f"{prefix}_run_cmd_feedback"
            ),
            "trip_latched": StepSeries.from_rows(processbus_rows, f"{prefix}_trip_latch"),
            "trip_commanded": StepSeries.from_rows(processbus_rows, f"{prefix}_vcb_trip_cmd"),
            "speed_proven": StepSeries.from_rows(processbus_rows, f"{prefix}_speed_proven"),
            "state_code": StepSeries.from_rows(processbus_rows, f"{prefix}_state_code"),
        }
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for trend in trend_rows:
            for item in equipment:
                bus_suffix = "a" if item["bus"] == "BUS-A" else "b"
                bus_voltage_kv = float(trend[f"bus_{bus_suffix}_voltage_kv"])
                motor_state = motor_feeder_state(
                    initial_breaker_closed=item["normal_breaker_state"] == "CLOSED",
                    initial_running=item["normal_run_state"] == "RUNNING",
                    time_ms=int(trend["source_time_ms"]),
                    commands=commands,
                    equipment_id=item["equipment_id"],
                    feeder_id=item["feeder_id"],
                    breaker_open_delay_ms=breaker_open_delay_ms,
                    automatic_trip_command_ms=automatic_trip_commands.get(item["equipment_id"]),
                    observed=observations[item["equipment_id"]],
                )
                breaker_closed = motor_state.breaker_closed
                energized = breaker_closed and bus_voltage_kv > 0
                source_time_ms = int(trend["source_time_ms"])
                is_faulted = (
                    feeder_protection is not None
                    and feeder_protection.equipment_id == item["equipment_id"]
                )
                fault_present = bool(
                    is_faulted and source_time_ms >= feeder_protection.fault_start_ms
                )
                fault_energized = fault_present and breaker_closed and bus_voltage_kv > 0
                fault_current_a = (
                    feeder_protection.fault_current_a if fault_energized else 0.0
                ) if is_faulted else None
                terminal_voltage_kv = (
                    bus_voltage_kv * feeder_protection.residual_voltage_pu
                    if fault_energized else (bus_voltage_kv if breaker_closed else 0.0)
                )
                relay_50_operated = bool(
                    is_faulted
                    and feeder_protection.relay_50_operate_ms is not None
                    and source_time_ms >= feeder_protection.relay_50_operate_ms
                )
                relay_51_operated = bool(
                    is_faulted
                    and feeder_protection.relay_51_operate_ms is not None
                    and source_time_ms >= feeder_protection.relay_51_operate_ms
                    and (
                        feeder_protection.breaker_open_ms is None
                        or feeder_protection.relay_51_operate_ms <= feeder_protection.breaker_open_ms
                    )
                )
                rated_kw = item["rated_kw"].strip()
                if fault_current_a is not None:
                    current_text = f"{fault_current_a:.6f}"
                elif rated_kw:
                    current_a = (
                        float(rated_kw) / (math.sqrt(3.0) * bus_voltage_kv * power_factor)
                        if energized else 0.0
                    )
                    current_text = f"{current_a:.6f}"
                else:
                    current_text = ""
                link_id, source_m_tag_id = m_links.get(item["equipment_id"].strip(), ("", ""))
                writer.writerow({
                    "ecms_time_ms": trend["ecms_time_ms"],
                    "source_time_ms": trend["source_time_ms"],
                    "quality": trend["quality"],
                    "a_config_status": trend["a_config_status"],
                    "equipment_id": item["equipment_id"].strip(),
                    "label_ko": item["label_ko"].strip(),
                    "bus": item["bus"],
                    "feeder_id": item["feeder_id"].strip(),
                    "configured_voltage_kv": item["voltage_kv"].strip(),
                    "rated_kw": rated_kw,
                    "breaker_closed": int(breaker_closed),
                    "run_enable": int(motor_state.run_enable),
                    "run_command_feedback": int(motor_state.run_command_feedback),
                    "run_feedback": int(motor_state.run_feedback),
                    "speed_proven": "" if motor_state.speed_proven is None else int(motor_state.speed_proven),
                    "trip_latched": int(motor_state.trip_latched),
                    "trip_commanded": int(motor_state.trip_commanded),
                    "state_code": "" if motor_state.state_code is None else motor_state.state_code,
                    "fault_present": int(fault_present),
                    "fault_current_a": "" if fault_current_a is None else f"{fault_current_a:.6f}",
                    "relay_50_operated": int(relay_50_operated),
                    "relay_51_operated": int(relay_51_operated),
                    "energized": int(energized),
                    "bus_voltage_kv": f"{bus_voltage_kv:.6f}",
                    "terminal_voltage_kv": f"{terminal_voltage_kv:.6f}",
                    "priority": item["priority"].strip(),
                    "current_a": current_text,
                    "equipment_status": item["status"].strip(),
                    "m_link_id": link_id,
                    "source_m_tag_id": source_m_tag_id,
                    "provenance": "A_CONFIGURED_E_DERIVED",
                })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processbus", type=Path, required=True)
    parser.add_argument("--a-settings", type=Path, default=PROJECT_ROOT / "config/ecms_a_settings.csv")
    parser.add_argument("--a-equipment", type=Path, default=PROJECT_ROOT / "config/ecms_a_equipment.csv")
    parser.add_argument("--m-links", type=Path, default=PROJECT_ROOT / "data/ecms_m_links.csv")
    parser.add_argument("--m-tags", type=Path, default=PROJECT_ROOT / "data/thermo_vpp_m_locked_tags.csv")
    parser.add_argument("--fault-presets", type=Path, default=PROJECT_ROOT / "config/fault_presets.json")
    parser.add_argument("--command-catalog", type=Path, default=PROJECT_ROOT / "config/ecms_command_catalog.csv")
    parser.add_argument(
        "--common-trip-matrix",
        type=Path,
        default=PROJECT_ROOT / "config/common_trip_matrix.csv",
    )
    parser.add_argument(
        "--dcs-events",
        type=Path,
        action="append",
        default=[],
        help="DCS1/DCS2 event CSV containing common Trip source alarms; repeatable.",
    )
    parser.add_argument("--commands", type=Path)
    parser.add_argument("--fault-preset", default="none")
    parser.add_argument("--event-time", type=float)
    parser.add_argument("--trip-time", type=float, help="Legacy alias for --event-time")
    parser.add_argument(
        "--scenario-gt-trip",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Assert a synthetic GT Trip at the reference event time (disable for observed RAW).",
    )
    parser.add_argument(
        "--sampling-profile",
        choices=("standard", "causal_100ms", "incident_1ms"),
        default="standard",
    )
    parser.add_argument("--incident-period-ms", type=int, default=1)
    parser.add_argument("--incident-pre-ms", type=int, default=2000)
    parser.add_argument("--incident-post-ms", type=int, default=5000)
    parser.add_argument("--trend-output", type=Path, required=True)
    parser.add_argument("--event-output", type=Path, required=True)
    parser.add_argument("--feeder-output", type=Path)
    args = parser.parse_args()

    if args.event_time is None and args.trip_time is None:
        raise ValueError("one of --event-time or legacy --trip-time is required")
    if args.event_time is not None and args.trip_time is not None and not math.isclose(
        args.event_time, args.trip_time, abs_tol=1e-12
    ):
        raise ValueError("--event-time and --trip-time disagree")
    event_time_s = args.event_time if args.event_time is not None else args.trip_time
    assert event_time_s is not None
    if not math.isfinite(event_time_s):
        raise ValueError("event time must be finite")

    rows = load_processbus(args.processbus)
    a, settings_status = load_a_settings(args.a_settings)
    equipment = load_a_equipment(args.a_equipment)
    equipment_status = derive_config_status(equipment, "A equipment")
    a_config_status = combine_config_status(settings_status, equipment_status)
    m_link_groups = load_m_links(args.m_links, args.m_tags)
    m_links: dict[str, tuple[str, str]] = {}
    for item in equipment:
        equipment_links = m_link_groups.get(item["equipment_id"], [])
        if len(equipment_links) != 1:
            raise ValueError(
                f"{item['equipment_id']}: equipment must have exactly one locked M link"
            )
        m_links[item["equipment_id"]] = equipment_links[0]
    aux_kv = float(a["AUX_BUS_VOLTAGE_KV"])
    for item in equipment:
        if not math.isclose(float(item["voltage_kv"]), aux_kv, abs_tol=1e-9):
            raise ValueError(
                f"{item['equipment_id']}: voltage_kv must match AUX_BUS_VOLTAGE_KV ({aux_kv:g})"
            )
    presets = json.loads(args.fault_presets.read_text(encoding="utf-8"))
    if args.fault_preset not in presets:
        raise ValueError(f"unknown fault preset: {args.fault_preset}")
    fault = presets[args.fault_preset]
    commands: list[dict[str, str]] = []
    if args.commands:
        commands = validate_queue(args.commands, load_catalog(args.command_catalog))

    trip_time_ms = event_time_s * 1000.0
    if not math.isclose(trip_time_ms, round(trip_time_ms), abs_tol=1e-9):
        raise ValueError("trip time must resolve to a whole millisecond")
    for command in commands:
        command_time_ms = float(command["time_s"]) * 1000.0
        if not math.isclose(command_time_ms, round(command_time_ms), abs_tol=1e-9):
            raise ValueError("command times must resolve to whole milliseconds")

    start_ms = round(float(rows[0]["time_s"]) * 1000)
    stop_ms = round(float(rows[-1]["time_s"]) * 1000)
    trip_ms = round(event_time_s * 1000)
    if not start_ms <= trip_ms <= stop_ms:
        raise ValueError("trip time is outside the ProcessBus time range")
    if any(
        not start_ms <= round(float(row["time_s"]) * 1000) <= stop_ms
        for row in commands
    ):
        raise ValueError("command queue contains a command outside the ProcessBus time range")
    mismatched_gt_trip = [
        row for row in commands
        if row["equipment_id"].strip().upper() == "GTG"
        and row["command"].strip().upper() == "TRIP"
        and round(float(row["time_s"]) * 1000) != trip_ms
    ]
    if mismatched_gt_trip and args.scenario_gt_trip:
        raise ValueError("a GTG TRIP command must match --trip-time in the cloud physics pipeline")
    feeder_protection = resolve_feeder_protection(fault, equipment, a, trip_ms)
    period_ms = int(a["TREND_PERIOD_MS"])
    sample_times_ms, incident_start_ms, incident_stop_ms = build_sample_times(
        start_ms,
        stop_ms,
        period_ms,
        trip_ms,
        args.sampling_profile,
        args.incident_period_ms,
        args.incident_pre_ms,
        args.incident_post_ms,
    )
    clock_offset_ms = int(a["CLOCK_OFFSET_MS"])
    common_trip_rules = load_common_trip_matrix(args.common_trip_matrix)
    trip_resolution = resolve_common_trips(
        common_trip_rules,
        rows,
        commands,
        args.dcs_events,
        scenario_gt_trip_ms=trip_ms if args.scenario_gt_trip else None,
    )
    gt_request_ms = trip_resolution.gt_request_ms
    st_request_ms = trip_resolution.st_request_ms
    relay_trip_ms = (
        None if gt_request_ms is None
        else gt_request_ms + int(a["TRIP_RECEIVE_DELAY_MS"])
    )
    lockout_ms = (
        None if relay_trip_ms is None
        else relay_trip_ms + int(a["LOCKOUT_OPERATE_DELAY_MS"])
    )
    automatic_gt_breaker_open_ms = (
        None if gt_request_ms is None
        else gt_request_ms + int(a["GT_BREAKER_OPEN_DELAY_MS"])
    )
    st_breaker_open_ms = (
        None if st_request_ms is None
        else st_request_ms + int(a["ST_BREAKER_OPEN_DELAY_MS"])
    )

    stg_power_series = LinearSeries.from_rows(rows, "stg_power_w")
    gt_trip_input_series = StepSeries.from_rows(rows, "gt_trip_cmd")
    cb_52gt_open_command_series = StepSeries.from_rows(rows, "cb_52gt_open_command")
    observed_gt_breaker_series = StepSeries.from_rows(rows, "ecms_cb_52gt_closed")
    gt_in_service_series = StepSeries.from_rows(rows, "gt_in_service")
    gt_trip_from_52gt_open_series = StepSeries.from_rows(rows, "gt_trip_from_52gt_open")
    gt_trip_command_readback_series = StepSeries.from_rows(rows, "gt_trip_command_readback")
    gt_trip_latch_series = StepSeries.from_rows(rows, "gt_trip_latch")
    observed_gt_breaker_open_ms = observed_gt_breaker_series.first_falling_edge_ms()
    gt_breaker_open_ms = (
        observed_gt_breaker_open_ms
        if observed_gt_breaker_open_ms is not None
        else automatic_gt_breaker_open_ms
    )
    observed_bus_a_voltage = LinearSeries.from_rows(rows, "ecms_bus_a_voltage_kv")

    relay_operates = gt_request_ms is not None and not fault.get("relay_fail", False)
    gt_breaker_opens = observed_gt_breaker_open_ms is not None or (
        relay_operates and not fault.get("gtg_breaker_fail", False)
    )
    grid_available_after_trip = not fault.get("grid_loss", False)
    gt_receive_available = not fault.get("gt_transformer_receive_fail", False)
    st_receive_available = not fault.get("st_transformer_receive_fail", False)
    uat_a_fault = bool(fault.get("uat_a_fault", False))
    uat_b_fault = bool(fault.get("uat_b_fault", False))
    bus_a_fault = bool(fault.get("bus_a_fault", False))
    bus_b_fault = bool(fault.get("bus_b_fault", False))
    gt_post_trip_direction = "IMPORT" if grid_available_after_trip and gt_receive_available else "DEAD"
    st_post_trip_direction = "IMPORT" if grid_available_after_trip and st_receive_available else "DEAD"

    trip_from_command = any(
        row["equipment_id"].strip().upper() == "GTG"
        and row["command"].strip().upper() == "TRIP"
        and round(float(row["time_s"]) * 1000) == gt_request_ms
        for row in commands
    )
    events: list[Event] = []
    if gt_request_ms is not None:
        direct_gt = "DIRECT_GT_TRIP" in trip_resolution.gt_causes
        if direct_gt:
            events.append(Event(
                gt_request_ms,
                "GT.TRIP.CMD",
                "0",
                "1",
                "TRIP",
                "GT Trip command asserted" if trip_from_command else "GT Trip input asserted",
                "USER_COMMAND" if trip_from_command else (
                    "SCENARIO_INPUT" if args.scenario_gt_trip else "RAW_OBSERVED"
                ),
            ))
        events.append(Event(
            gt_request_ms,
            "GT.TRIP.REQUEST",
            "0",
            "1",
            "TRIP_REQUEST",
            "Resolved GT Trip request from " + ", ".join(trip_resolution.gt_causes),
            "COMMON_TRIP_MATRIX",
        ))
        events.append(Event(
            gt_request_ms,
            "GT.TRIP.LATCH",
            "0",
            "1",
            "LATCH",
            "GT Trip latch set from resolved GT Trip request",
            "COMMON_TRIP_MATRIX",
        ))
    if st_request_ms is not None:
        if "DIRECT_ST_TRIP" in trip_resolution.st_causes:
            events.append(Event(
                st_request_ms, "ST.TRIP.CMD", "0", "1", "TRIP",
                "Direct ST Trip input asserted", "USER_COMMAND",
            ))
        events.extend([
            Event(
                st_request_ms,
                "ST.TRIP.REQUEST",
                "0",
                "1",
                "TRIP_REQUEST",
                "Resolved ST Trip request from " + ", ".join(trip_resolution.st_causes),
                "COMMON_TRIP_MATRIX",
            ),
            Event(
                st_request_ms,
                "ST.TRIP.LATCH",
                "0",
                "1",
                "LATCH",
                "ST Trip latch set from resolved ST Trip request",
                "COMMON_TRIP_MATRIX",
            ),
            Event(
                st_request_ms,
                "52ST.TRIP.CMD",
                "0",
                "1",
                "TRIP_COMMAND",
                "52ST Trip command latched from resolved ST Trip request",
                "COMMON_TRIP_MATRIX",
            ),
        ])
    if relay_operates and relay_trip_ms is not None and lockout_ms is not None:
        events.extend([
            Event(relay_trip_ms, "86GT.TRIP.RECEIVED", "0", "1", "PICKUP", "GT Trip received"),
            Event(lockout_ms, "86GT.OPERATE", "0", "1", "OPERATE", "GT lockout relay operated"),
            Event(lockout_ms, "52GT.TRIP.CMD", "0", "1", "TRIP_COMMAND", "52GT Trip command latched"),
        ])
    elif gt_request_ms is not None and relay_trip_ms is not None:
        events.append(Event(relay_trip_ms, "86GT.FAIL", "0", "1", "ALARM", "GT protection failed", "FAULTBUS"))
    if gt_breaker_opens and gt_breaker_open_ms is not None:
        observed_breaker = observed_gt_breaker_open_ms is not None
        events.extend([
            Event(
                gt_breaker_open_ms,
                "52GT.CLOSED",
                "1",
                "0",
                "POSITION",
                "Observed GT generator breaker opened while GT was in service"
                if observed_breaker else "GT generator breaker opened",
                "RAW_OBSERVED_ECMS" if observed_breaker else "E_DERIVED",
            ),
            Event(
                gt_breaker_open_ms,
                "TR-GT.DIRECTION",
                "EXPORT",
                gt_post_trip_direction,
                "STATE",
                "GT main transformer direction after observed breaker open"
                if observed_breaker else "GT main transformer post-trip direction",
            ),
        ])
    elif relay_operates and gt_breaker_open_ms is not None:
        events.append(Event(gt_breaker_open_ms, "52GT.FAIL_TO_OPEN", "0", "1", "ALARM", "GT generator breaker failed to open", "FAULTBUS"))
    if st_breaker_open_ms is not None:
        events.extend([
            Event(st_breaker_open_ms, "52ST.CLOSED", "1", "0", "POSITION", "ST generator breaker opened by resolved Trip command"),
            Event(st_breaker_open_ms, "TR-ST.DIRECTION", "EXPORT", st_post_trip_direction, "STATE", "ST main transformer post-trip direction"),
        ])

    observed_event_specs = [
        ("cb_52gt_open_command", "52GT.OPEN.CMD", "COMMAND", "Observed 52GT OPEN command", "RAW_OBSERVED_COMMANDBUS"),
        ("gt_trip_from_52gt_open", "GT.TRIP.FROM_52GT_OPEN", "TRIP_REQUEST", "GT Trip request derived after 52GT open feedback while running", "RAW_OBSERVED_PROTECTION"),
        ("gt_trip_command_readback", "GT.TRIP.OPCUA.READBACK", "FEEDBACK", "OpenModelica received derived GT Trip over OPC UA", "RAW_OBSERVED_OPCUA"),
        ("gt_trip_latch", "GT.TRIP.PHYSICS.LATCH", "LATCH", "Native physical Trip latch changed", "RAW_OBSERVED_PHYSICS"),
        ("fwp_hp_trip_input", "FWP-HP.TRIP.INPUT", "COMMAND", "Observed HP FWP Trip input", "RAW_OBSERVED_COMMANDBUS"),
        ("fwp_hp_vcb_trip_cmd", "VCB-A01.TRIP.CMD", "TRIP_COMMAND", "Observed VCB-A01 Trip command", "RAW_OBSERVED_ECMS"),
        ("fwp_hp_vcb_closed", "VCB-A01.CLOSED", "POSITION", "Observed VCB-A01 position", "RAW_OBSERVED_ECMS"),
        ("fwp_hp_trip_latch", "FWP-HP.TRIP.LATCH", "LATCH", "Observed HP FWP Trip latch", "RAW_OBSERVED_PROTECTION"),
    ]
    quality_series = StepSeries.from_rows(rows, "quality")
    for field, tag, event_class, description, provenance in observed_event_specs:
        series = StepSeries.from_rows(rows, field)
        for event in series.transition_events(tag, event_class, description, provenance):
            observed_quality = quality_series.at(event.time_ms)
            events.append(replace(event, quality=observed_quality or "GOOD"))
    if feeder_protection is not None:
        protection = feeder_protection
        events.append(Event(
            protection.fault_start_ms,
            f"{protection.equipment_id}.FEEDER.FAULT",
            "0",
            "1",
            "FAULT",
            f"Provisional RMS feeder fault asserted at {protection.fault_current_a:g} A",
            "A_CONFIGURED_RMS_FAULT_MODEL",
        ))
        if protection.fault_current_a >= float(a["FEEDER_50_PICKUP_A"]):
            events.append(Event(
                protection.fault_start_ms,
                f"50{protection.equipment_id}.PICKUP",
                "0", "1", "PICKUP", "Instantaneous overcurrent element picked up",
                "A_CONFIGURED_RMS_FAULT_MODEL",
            ))
        if protection.fault_current_a >= float(a["FEEDER_51_PICKUP_A"]):
            events.append(Event(
                protection.fault_start_ms,
                f"51{protection.equipment_id}.PICKUP",
                "0", "1", "PICKUP", "IEC standard-inverse overcurrent element picked up",
                "A_CONFIGURED_RMS_FAULT_MODEL",
            ))
        if protection.relay_50_operate_ms is not None:
            events.append(Event(
                protection.relay_50_operate_ms,
                f"50{protection.equipment_id}.OPERATE",
                "0", "1", "OPERATE", "Instantaneous overcurrent element operated",
                "A_CONFIGURED_RMS_FAULT_MODEL",
            ))
        if (
            protection.relay_51_operate_ms is not None
            and (
                protection.breaker_open_ms is None
                or protection.relay_51_operate_ms <= protection.breaker_open_ms
            )
        ):
            events.append(Event(
                protection.relay_51_operate_ms,
                f"51{protection.equipment_id}.OPERATE",
                "0", "1", "OPERATE", "IEC standard-inverse overcurrent element operated",
                "A_CONFIGURED_RMS_FAULT_MODEL",
            ))
        if protection.trip_command_ms is not None:
            events.append(Event(
                protection.trip_command_ms,
                f"{protection.feeder_id}.TRIP.CMD",
                "0", "1", "TRIP_COMMAND", "Feeder protection issued VCB Trip command",
                "A_CONFIGURED_RMS_FAULT_MODEL",
            ))
        if protection.breaker_open_ms is not None:
            events.append(Event(
                protection.breaker_open_ms,
                f"{protection.feeder_id}.CLOSED",
                "1", "0", "POSITION", "Feeder VCB opened and interrupted fault current",
                "A_CONFIGURED_RMS_FAULT_MODEL",
            ))
    if fault.get("grid_loss", False):
        events.append(Event(trip_ms, "GRID-154KV.AVAILABLE", "1", "0", "POSITION", "External grid source lost", "FAULTBUS"))
    for key, tag, description in [
        ("uat_a_fault", "UAT-A.FAULT", "UAT-A unavailable"),
        ("uat_b_fault", "UAT-B.FAULT", "UAT-B unavailable"),
        ("gt_transformer_receive_fail", "TR-GT.RECEIVE.FAIL", "GT transformer reverse receiving unavailable"),
        ("st_transformer_receive_fail", "TR-ST.RECEIVE.FAIL", "ST transformer reverse receiving unavailable"),
        ("bus_a_fault", "BUS-A.FAULT", "6.9 kV BUS-A fault"),
        ("bus_b_fault", "BUS-B.FAULT", "6.9 kV BUS-B fault"),
    ]:
        if fault.get(key, False):
            events.append(Event(trip_ms, tag, "0", "1", "FAULT", description, "FAULTBUS"))
    if fault.get("ecms_comms_loss", False):
        events.append(Event(trip_ms, "ECMS.COMMS.QUALITY", "GOOD", "BAD", "QUALITY", "ECMS communications lost", "FAULTBUS"))
    for command in commands:
        equipment_id = command["equipment_id"].strip().upper()
        action = command["command"].strip().upper()
        description = f"User command submitted to cloud ECMS: {equipment_id} {action}"
        if "THERMO_ADAPTER_REQUIRED" in command["execution_layer"].strip().upper():
            description += " (electrical indication only; no ThermoSysPro adapter)"
        events.append(Event(
            round(float(command["time_s"]) * 1000),
            f"COMMAND.{equipment_id}.{action}",
            "",
            command["command_value"].strip(),
            "COMMAND",
            description,
            "USER_COMMAND",
        ))

    grid_kv = float(a["GRID_VOLTAGE_KV"])
    pf = float(a["POWER_FACTOR"])
    gt_terminal_kv = float(a["GT_TERMINAL_VOLTAGE_KV"])
    st_terminal_kv = float(a["ST_TERMINAL_VOLTAGE_KV"])
    auto_tie = bool(a["AUTO_BUS_TIE_TRANSFER"])
    allow_source_parallel = bool(a["ALLOW_SOURCE_PARALLEL"])
    args.trend_output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ecms_time_ms", "source_time_ms", "quality", "a_config_status", "sampling_resolution",
        "cb_52gt_open_command", "gt_in_service", "gt_trip_from_52gt_open",
        "gt_trip_command_readback", "gt_trip_latch",
        "gt_trip_cmd", "gt_trip_request", "st_trip_request",
        "relay_86gt_operated", "cb_52gt_trip_cmd", "cb_52st_trip_cmd",
        "cb_52gt_closed", "cb_52st_closed",
        "cb_in_a_closed", "cb_in_b_closed", "cb_tie_ab_closed",
        "gt_main_transformer_direction", "st_main_transformer_direction",
        "gtg_power_mw", "gtg_current_a", "stg_power_mw", "stg_current_a",
        "grid_voltage_pu", "frequency_hz", "bus_a_voltage_pu", "bus_a_voltage_kv",
        "bus_b_voltage_pu", "bus_b_voltage_kv", "grid_voltage_kv",
        "source_parallel_allowed", "source_parallel_active",
    ]
    trend_rows: list[dict[str, str | int]] = []
    bus_a_native_loss_ms: int | None = None
    bus_b_native_loss_ms: int | None = None
    with args.trend_output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for time_ms in sample_times_ms:
            time_s = time_ms / 1000.0
            after_trip = time_ms >= trip_ms
            in_incident_window = (
                incident_start_ms is not None
                and incident_stop_ms is not None
                and incident_start_ms <= time_ms <= incident_stop_ms
            )
            grid_live = apply_availability_command(
                not after_trip or grid_available_after_trip, commands, "GRID-154KV", time_ms
            )
            gt_cb_closed = breaker_with_automatic_trip(
                True,
                gt_breaker_open_ms if gt_breaker_opens else None,
                time_ms,
                commands,
                "CB-52GT",
            )
            observed_gt_cb_closed = observed_gt_breaker_series.bool_at(time_ms)
            if observed_gt_cb_closed is not None:
                gt_cb_closed = observed_gt_cb_closed
            st_cb_closed = breaker_with_automatic_trip(
                True, st_breaker_open_ms, time_ms, commands, "CB-52ST"
            )
            gt_request_active = gt_request_ms is not None and time_ms >= gt_request_ms
            st_request_active = st_request_ms is not None and time_ms >= st_request_ms
            gt_power_pu = (
                decay(time_ms, gt_request_ms, int(a["GT_POWER_DECAY_MS"]))
                if gt_request_active and gt_request_ms is not None else 1.0
            )
            gtg_power_mw = float(a["GTG_PRETRIP_POWER_MW"]) * gt_power_pu if gt_cb_closed else 0.0
            stg_model_w = stg_power_series.at(time_s)
            stg_power_mw = stg_model_w / 1_000_000.0 if st_cb_closed else 0.0

            gt_generation_live = gt_cb_closed and gt_power_pu >= float(a["UNDERVOLTAGE_PICKUP_PU"])
            st_generation_live = st_cb_closed and stg_model_w > 0.0
            gt_transformer_live = apply_availability_command(
                gt_receive_available, commands, "TR-GT", time_ms
            )
            st_transformer_live = apply_availability_command(
                st_receive_available, commands, "TR-ST", time_ms
            )
            gt_reverse_live = grid_live and gt_transformer_live
            st_reverse_live = grid_live and st_transformer_live
            gt_aux_source_live = gt_generation_live or gt_reverse_live
            st_aux_source_live = st_generation_live or st_reverse_live

            uat_a_available = not (after_trip and uat_a_fault)
            uat_b_available = not (after_trip and uat_b_fault)
            uat_a_available = apply_availability_command(uat_a_available, commands, "UAT-A", time_ms)
            uat_b_available = apply_availability_command(uat_b_available, commands, "UAT-B", time_ms)
            bus_a_fault_active = after_trip and bus_a_fault
            bus_b_fault_active = after_trip and bus_b_fault
            in_a_closed = breaker_with_automatic_trip(
                True, None, time_ms, commands, "CB-IN-A"
            ) and uat_a_available and not bus_a_fault_active
            in_b_closed = breaker_with_automatic_trip(
                True, None, time_ms, commands, "CB-IN-B"
            ) and uat_b_available and not bus_b_fault_active
            bus_a_native = in_a_closed and gt_aux_source_live
            bus_b_native = in_b_closed and st_aux_source_live
            if bus_a_native:
                bus_a_native_loss_ms = None
            elif bus_a_native_loss_ms is None:
                bus_a_native_loss_ms = time_ms
            if bus_b_native:
                bus_b_native_loss_ms = None
            elif bus_b_native_loss_ms is None:
                bus_b_native_loss_ms = time_ms
            uv_delay_ms = int(a["UNDERVOLTAGE_DELAY_MS"])
            # The UV relay must remain picked up through a complete trend scan
            # before automatic transfer closes the tie. This preserves a
            # sampled low-voltage interval and an auditable 27UV event.
            bus_a_transfer_ready = (
                bus_a_native_loss_ms is not None
                and time_ms > bus_a_native_loss_ms + uv_delay_ms
            )
            bus_b_transfer_ready = (
                bus_b_native_loss_ms is not None
                and time_ms > bus_b_native_loss_ms + uv_delay_ms
            )
            transfer_ready = (
                (not bus_a_native and bus_b_native and bus_a_transfer_ready and not bus_a_fault_active)
                or (not bus_b_native and bus_a_native and bus_b_transfer_ready and not bus_b_fault_active)
            )
            tie_closed = auto_tie and transfer_ready and not (
                bus_a_fault_active and bus_b_fault_active
            )
            tie_closed = breaker_with_automatic_trip(
                tie_closed, None, time_ms, commands, "CB-TIE-AB"
            )
            # Break-before-make: isolate the dead native source before closing tie.
            if tie_closed and not bus_a_native:
                in_a_closed = False
            if tie_closed and not bus_b_native:
                in_b_closed = False
            source_parallel_active = (
                tie_closed and in_a_closed and in_b_closed
                and gt_aux_source_live and st_aux_source_live
            )
            if source_parallel_active and not allow_source_parallel:
                tie_closed = False
                source_parallel_active = False
            bus_a_live = bus_a_native or (tie_closed and bus_b_native and not bus_a_fault_active)
            bus_b_live = bus_b_native or (tie_closed and bus_a_native and not bus_b_fault_active)

            observed_bus_a_kv = (
                observed_bus_a_voltage.at(time_s)
                if observed_bus_a_voltage.times_s else None
            )
            bus_a_voltage_kv = (
                observed_bus_a_kv if observed_bus_a_kv is not None
                else (aux_kv if bus_a_live else 0.0)
            )
            bus_a_voltage_pu = bus_a_voltage_kv / aux_kv

            gt_direction = "EXPORT" if gt_generation_live else ("IMPORT" if gt_reverse_live else "DEAD")
            st_direction = "EXPORT" if st_generation_live else ("IMPORT" if st_reverse_live else "DEAD")
            quality = quality_series.at(time_ms) or "GOOD"
            if fault.get("ecms_comms_loss", False) and after_trip:
                quality = "BAD"
            raw_gt_trip = gt_trip_input_series.bool_at(time_ms)
            gt_trip_cmd = (
                int(time_ms >= trip_ms) if args.scenario_gt_trip
                else int(raw_gt_trip) if raw_gt_trip is not None else 0
            )
            trend_row: dict[str, str | int] = {
                "ecms_time_ms": time_ms + clock_offset_ms,
                "source_time_ms": time_ms,
                "quality": quality,
                "a_config_status": a_config_status,
                "sampling_resolution": (
                    f"INCIDENT_{args.incident_period_ms}MS"
                    if in_incident_window else f"NORMAL_{period_ms}MS"
                ),
                "cb_52gt_open_command": int(
                    cb_52gt_open_command_series.bool_at(time_ms) or False
                ),
                "gt_in_service": int(gt_in_service_series.bool_at(time_ms) or False),
                "gt_trip_from_52gt_open": int(
                    gt_trip_from_52gt_open_series.bool_at(time_ms) or False
                ),
                "gt_trip_command_readback": int(
                    gt_trip_command_readback_series.bool_at(time_ms) or False
                ),
                "gt_trip_latch": int(gt_trip_latch_series.bool_at(time_ms) or False),
                "gt_trip_cmd": gt_trip_cmd,
                "gt_trip_request": int(gt_request_active),
                "st_trip_request": int(st_request_active),
                "relay_86gt_operated": int(
                    relay_lockout_state(relay_operates, lockout_ms, time_ms, commands)
                    if lockout_ms is not None else False
                ),
                "cb_52gt_trip_cmd": int(
                    relay_operates and lockout_ms is not None and time_ms >= lockout_ms
                ),
                "cb_52st_trip_cmd": int(st_request_active),
                "cb_52gt_closed": int(gt_cb_closed),
                "cb_52st_closed": int(st_cb_closed),
                "cb_in_a_closed": int(in_a_closed),
                "cb_in_b_closed": int(in_b_closed),
                "cb_tie_ab_closed": int(tie_closed),
                "gt_main_transformer_direction": gt_direction,
                "st_main_transformer_direction": st_direction,
                "gtg_power_mw": f"{gtg_power_mw:.6f}",
                "gtg_current_a": f"{rms_current_a(gtg_power_mw, gt_terminal_kv, pf):.6f}",
                "stg_power_mw": f"{stg_power_mw:.6f}",
                "stg_current_a": f"{rms_current_a(stg_power_mw, st_terminal_kv, pf):.6f}",
                "grid_voltage_pu": f"{1.0 if grid_live else 0.0:.6f}",
                "grid_voltage_kv": f"{grid_kv if grid_live else 0.0:.6f}",
                "frequency_hz": f"{60.0 if (grid_live or gt_generation_live or st_generation_live) else 0.0:.6f}",
                "bus_a_voltage_pu": f"{bus_a_voltage_pu:.6f}",
                "bus_a_voltage_kv": f"{bus_a_voltage_kv:.6f}",
                "bus_b_voltage_pu": f"{1.0 if bus_b_live else 0.0:.6f}",
                "bus_b_voltage_kv": f"{aux_kv if bus_b_live else 0.0:.6f}",
                "source_parallel_allowed": int(allow_source_parallel),
                "source_parallel_active": int(source_parallel_active),
            }
            writer.writerow(trend_row)
            trend_rows.append(trend_row)

    add_undervoltage_events(
        trend_rows,
        events,
        float(a["UNDERVOLTAGE_PICKUP_PU"]),
        int(a["UNDERVOLTAGE_DELAY_MS"]),
    )
    if fault.get("ecms_comms_loss", False):
        events = [replace(event, quality="BAD") if event.time_ms >= trip_ms else event for event in events]
    events = [event for event in events if start_ms <= event.time_ms <= stop_ms]
    write_events(args.event_output, events, clock_offset_ms)
    feeder_output = args.feeder_output or args.trend_output.with_name("ecms-feeders.csv")
    write_feeders(
        feeder_output,
        trend_rows,
        equipment,
        m_links,
        pf,
        commands,
        rows,
        int(a["MOTOR_BREAKER_OPEN_DELAY_MS"]),
        ({feeder_protection.equipment_id: feeder_protection.trip_command_ms}
         if feeder_protection is not None and feeder_protection.trip_command_ms is not None
         else {}),
        feeder_protection,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
