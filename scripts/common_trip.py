#!/usr/bin/env python3
"""Resolve plant-wide GT/ST Trip requests from one authoritative C&E matrix."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommonTripRule:
    cause_id: str
    source_signal: str
    source_layer: str
    source_event_tag: str
    gt_trip_request: bool
    st_trip_request: bool
    notes: str


@dataclass(frozen=True)
class TripTrigger:
    cause_id: str
    source_signal: str
    source_layer: str
    source_event_tag: str
    time_ms: int


@dataclass(frozen=True)
class TripResolution:
    triggers: tuple[TripTrigger, ...]
    gt_request_ms: int | None
    st_request_ms: int | None
    gt_causes: tuple[str, ...]
    st_causes: tuple[str, ...]


def parse_bool(raw: str, label: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on", "active"}:
        return True
    if value in {"0", "false", "no", "off", "return", "clear", "cleared"}:
        return False
    raise ValueError(f"{label} must be BOOL, got {raw!r}")


def load_common_trip_matrix(path: Path) -> list[CommonTripRule]:
    required = {
        "cause_id", "source_signal", "source_layer", "source_event_tag",
        "gt_trip_request", "st_trip_request", "notes",
    }
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        missing = required.difference(fields)
        if missing:
            raise ValueError("common Trip matrix is missing: " + ", ".join(sorted(missing)))
        rows = list(reader)
    if not rows:
        raise ValueError("common Trip matrix is empty")

    result: list[CommonTripRule] = []
    cause_ids: set[str] = set()
    for number, row in enumerate(rows, start=2):
        cause_id = row["cause_id"].strip().upper()
        source_signal = row["source_signal"].strip()
        source_layer = row["source_layer"].strip().upper()
        source_event_tag = row["source_event_tag"].strip().upper()
        if not cause_id or not source_signal or not source_layer or not source_event_tag:
            raise ValueError(f"common Trip matrix row {number} has an empty identifier")
        if cause_id in cause_ids:
            raise ValueError(f"duplicate common Trip cause_id: {cause_id}")
        if source_layer not in {"COMMAND", "LAYER1_ALARM"}:
            raise ValueError(f"{cause_id}: unsupported source_layer {source_layer!r}")
        cause_ids.add(cause_id)
        result.append(CommonTripRule(
            cause_id=cause_id,
            source_signal=source_signal,
            source_layer=source_layer,
            source_event_tag=source_event_tag,
            gt_trip_request=parse_bool(row["gt_trip_request"], f"{cause_id} gt_trip_request"),
            st_trip_request=parse_bool(row["st_trip_request"], f"{cause_id} st_trip_request"),
            notes=row["notes"].strip(),
        ))
    return result


def first_signal_assertion_ms(rows: list[dict[str, str]], field: str) -> int | None:
    if not rows or field not in rows[0]:
        return None
    previous = False
    for number, row in enumerate(rows, start=2):
        raw = (row.get(field) or "").strip()
        if not raw:
            previous = False
            continue
        try:
            asserted = parse_bool(raw, f"ProcessBus row {number} {field}")
        except ValueError:
            try:
                asserted = float(raw) >= 0.5
            except ValueError as exc:
                raise ValueError(f"ProcessBus row {number} {field} is not boolean") from exc
        if asserted and not previous:
            time_s = float(row["time_s"])
            if not math.isfinite(time_s):
                raise ValueError(f"ProcessBus row {number} time_s is not finite")
            return round(time_s * 1000)
        previous = asserted
    return None


def load_asserted_event_times(paths: list[Path]) -> dict[str, int]:
    asserted: dict[str, int] = {}
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or [])
            if "tag" not in fields or not ({"source_time_ms", "event_time_ms"} & fields):
                raise ValueError(f"{path}: DCS event file lacks tag/time columns")
            for number, row in enumerate(reader, start=2):
                state = (row.get("alarm_state") or row.get("new_value") or "").strip()
                event_class = (row.get("event_class") or "").strip().upper()
                if state:
                    try:
                        is_asserted = parse_bool(state, f"{path.name} row {number} state")
                    except ValueError:
                        is_asserted = event_class in {"ALARM", "TRIP", "PICKUP", "OPERATE"}
                else:
                    is_asserted = event_class in {"ALARM", "TRIP", "PICKUP", "OPERATE"}
                if not is_asserted:
                    continue
                tag = row["tag"].strip().upper()
                raw_time = (row.get("source_time_ms") or row.get("event_time_ms") or "").strip()
                try:
                    time_ms = round(float(raw_time))
                except ValueError as exc:
                    raise ValueError(f"{path.name} row {number} has invalid time") from exc
                asserted[tag] = min(asserted.get(tag, time_ms), time_ms)
    return asserted


def resolve_common_trips(
    rules: list[CommonTripRule],
    processbus_rows: list[dict[str, str]],
    commands: list[dict[str, str]],
    dcs_event_paths: list[Path],
    *,
    scenario_gt_trip_ms: int | None,
) -> TripResolution:
    """Resolve requests; ST low power is deliberately not an accepted source."""
    dcs_times = load_asserted_event_times(dcs_event_paths)
    triggers: list[TripTrigger] = []

    for rule in rules:
        candidates: list[int] = []
        # In the legacy cloud scenario, the explicit workflow event time is
        # authoritative; its synthesized ProcessBus gt_trip_cmd can be aligned
        # to a coarser source sample and must not pull the request earlier.
        signal_time = (
            None
            if rule.source_signal == "gt_trip_cmd" and scenario_gt_trip_ms is not None
            else first_signal_assertion_ms(processbus_rows, rule.source_signal)
        )
        if signal_time is not None:
            candidates.append(signal_time)
        if rule.source_layer == "COMMAND":
            if rule.source_signal == "gt_trip_cmd" and scenario_gt_trip_ms is not None:
                candidates.append(scenario_gt_trip_ms)
            equipment_id = "GTG" if rule.source_signal == "gt_trip_cmd" else "STG"
            candidates.extend(
                round(float(row["time_s"]) * 1000)
                for row in commands
                if row["equipment_id"].strip().upper() == equipment_id
                and row["command"].strip().upper() == "TRIP"
            )
        else:
            event_time = dcs_times.get(rule.source_event_tag)
            if event_time is not None:
                candidates.append(event_time)
        if candidates:
            triggers.append(TripTrigger(
                cause_id=rule.cause_id,
                source_signal=rule.source_signal,
                source_layer=rule.source_layer,
                source_event_tag=rule.source_event_tag,
                time_ms=min(candidates),
            ))

    triggers.sort(key=lambda item: (item.time_ms, item.cause_id))
    by_cause = {rule.cause_id: rule for rule in rules}
    gt_triggers = [item for item in triggers if by_cause[item.cause_id].gt_trip_request]
    st_triggers = [item for item in triggers if by_cause[item.cause_id].st_trip_request]
    gt_request_ms = min((item.time_ms for item in gt_triggers), default=None)
    st_request_ms = min((item.time_ms for item in st_triggers), default=None)
    return TripResolution(
        triggers=tuple(triggers),
        gt_request_ms=gt_request_ms,
        st_request_ms=st_request_ms,
        gt_causes=tuple(item.cause_id for item in gt_triggers if item.time_ms == gt_request_ms),
        st_causes=tuple(item.cause_id for item in st_triggers if item.time_ms == st_request_ms),
    )
