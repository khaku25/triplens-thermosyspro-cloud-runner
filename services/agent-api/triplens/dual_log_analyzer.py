#!/usr/bin/env python3
"""Build scenario-neutral evidence readiness from TripLens EVENT.csv + RAW.csv.

This module may classify and rank observations for evidence readiness, but it
must not decide Primary Cause, Direct Trigger, Propagation, Critical Events, or
Causal Chain. Those decisions remain with the Gemini agent and the subsequent
Verification Gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import deque
from pathlib import Path
from typing import Any

FORBIDDEN = {
    "scenario_id", "scenario", "scenario_name",
    "root_cause", "expected_root_cause", "expected_cause",
    "ground_truth", "answer_label",
    "fault_injection", "fault_preset",
}
VISIBLE_EVENT_CLASSES = {"ALARM", "OPERATOR_ACTION", "PROTECTION", "ACK", "SYSTEM"}
RAW_META_COLUMNS = {
    "record_sequence", "session_id", "incident_id", "model_time_s", "wall_time_utc",
    "collector_quality", "quality",
}
READINESS_VERSION = "GENERIC_DUAL_LOG_EVIDENCE_V2"
MAX_EVENT_EVIDENCE = 20
MAX_PROTECTION_CANDIDATES = 24
MAX_RAW_TRANSITIONS = 24
MAX_PROCESS_CHANGES = 20


def rows(path: Path, tail: int | None = None) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        if tail is None:
            return fields, list(reader)
        kept: deque[dict[str, str]] = deque(maxlen=tail)
        kept.extend(reader)
        return fields, list(kept)


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def event_text(row: dict[str, str]) -> str:
    wall = row.get("wall_time_utc", "")
    clock = wall[11:23] if len(wall) >= 23 else wall
    return f"{clock} {row.get('message') or row.get('tag', '')}".strip()


def _event_sort_key(row: dict[str, str]) -> tuple[bool, float, int, str]:
    when = finite(row.get("model_time_s"))
    try:
        sequence = int(float(row.get("event_sequence") or 0))
    except (TypeError, ValueError):
        sequence = 0
    return (when is None, when or 0.0, sequence, row.get("event_id", ""))


def _candidate_role(row: dict[str, str]) -> str:
    event_class = str(row.get("event_class", "")).upper()
    tag = str(row.get("tag", "")).upper()
    message = str(row.get("message", "")).upper()
    state = str(row.get("state", "")).upper()
    blob = " ".join((tag, message, state))

    if event_class == "OPERATOR_ACTION":
        return "OPERATOR_ACTION"
    if "REQUEST" in blob:
        return "TRIP_REQUEST"
    if any(token in blob for token in ("86GT", "86ST", "LOCKOUT", "OPERATE", "LATCH")):
        return "PROTECTION_ACTUATION"
    if any(token in blob for token in ("TRIP_CMD", "TRIP.CMD", "TRIP COMMAND", "TRIP COMMAND")):
        return "PROTECTION_ACTUATION"
    if event_class == "PROTECTION" and any(token in blob for token in ("BREAKER OPEN", ".CLOSED", "_CLOSED", " OPEN")):
        return "STATE_FEEDBACK"
    if event_class == "PROTECTION":
        return "PROTECTION_EVENT"
    if event_class == "ALARM":
        return "ALARM"
    if event_class == "ACK":
        return "ACK"
    return "SYSTEM"


def _event_candidate(row: dict[str, str]) -> dict[str, Any]:
    return {
        "evidence_id": row.get("event_id", ""),
        "model_time_s": finite(row.get("model_time_s")),
        "event_class": row.get("event_class", ""),
        "equipment": row.get("equipment", ""),
        "tag": row.get("tag", ""),
        "state": row.get("state", ""),
        "value": row.get("value", ""),
        "message": row.get("message", ""),
        "source": row.get("source", ""),
        "candidate_role": _candidate_role(row),
    }


def _numeric_series(raw_rows: list[dict[str, str]], field: str) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for row in raw_rows:
        when = finite(row.get("model_time_s"))
        value = finite(row.get(field))
        if when is None or value is None:
            continue
        out.append((when, value))
    return out


def _is_binary_series(series: list[tuple[float, float]]) -> bool:
    if len(series) < 2:
        return False
    values = [value for _, value in series]
    return all(abs(value) <= 1e-9 or abs(value - 1.0) <= 1e-9 for value in values)


def raw_transition_candidates(
    raw_fields: list[str],
    raw_rows: list[dict[str, str]],
    *,
    limit: int = MAX_RAW_TRANSITIONS,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for field in raw_fields:
        if field in RAW_META_COLUMNS:
            continue
        series = _numeric_series(raw_rows, field)
        if not _is_binary_series(series):
            continue
        previous_time, previous = series[0]
        for when, current in series[1:]:
            if abs(current - previous) <= 1e-9:
                previous_time, previous = when, current
                continue
            candidates.append(
                {
                    "tag": field,
                    "model_time_s": when,
                    "from": previous,
                    "to": current,
                    "edge": "RISE" if current > previous else "FALL",
                    "evidence_kind": "RAW_DIGITAL_TRANSITION",
                }
            )
            break
    candidates.sort(key=lambda item: (item["model_time_s"], item["tag"]))
    return candidates[:limit]


def process_change_candidates(
    raw_fields: list[str],
    raw_rows: list[dict[str, str]],
    *,
    limit: int = MAX_PROCESS_CHANGES,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for field in raw_fields:
        if field in RAW_META_COLUMNS:
            continue
        series = _numeric_series(raw_rows, field)
        if len(series) < 2 or _is_binary_series(series):
            continue
        first_time, first = series[0]
        last_time, last = series[-1]
        low = min(value for _, value in series)
        high = max(value for _, value in series)
        delta = last - first
        scale = max(abs(low), abs(high), 1e-12)
        normalized_change = abs(delta) / scale
        if abs(delta) <= max(scale * 1e-9, 1e-12):
            continue
        candidates.append(
            {
                "tag": field,
                "from_model_time_s": first_time,
                "to_model_time_s": last_time,
                "first": first,
                "last": last,
                "min": low,
                "max": high,
                "delta": delta,
                "direction": "INCREASE" if delta > 0 else "DECREASE",
                "normalized_change": normalized_change,
                "sample_count": len(series),
                "evidence_kind": "RAW_PROCESS_CHANGE",
            }
        )
    candidates.sort(key=lambda item: (-item["normalized_change"], item["tag"]))
    return candidates[:limit]


def analyze_dual_logs(event_csv: Path, raw_csv: Path) -> dict[str, Any]:
    event_fields, event_rows = rows(event_csv)
    raw_fields, raw_rows = rows(raw_csv, tail=7200)

    forbidden_event = sorted(FORBIDDEN.intersection(event_fields))
    forbidden_raw = sorted(FORBIDDEN.intersection(raw_fields))
    if forbidden_event or forbidden_raw:
        raise ValueError(
            f"answer/fault metadata leaked: EVENT={forbidden_event}, RAW={forbidden_raw}"
        )

    if not event_rows:
        return {
            "readiness_version": READINESS_VERSION,
            "status": "WAITING",
            "status_scope": "EVIDENCE_READINESS_ONLY",
            "mode": "DUAL_INPUT_EVENT_PLUS_RAW",
            "analysis_role": "EVIDENCE_PROVIDER_ONLY",
            "decision_authority": "GEMINI_AGENT",
            "decision_fields_generated_by_python": [],
            "message": "EVENT evidence 대기",
            "event_input_read": True,
            "raw_input_read": True,
            "event_rows": 0,
            "raw_rows": len(raw_rows),
            "coverage": {
                "event_chronology_ready": False,
                "raw_timeseries_ready": len(raw_rows) >= 2,
                "protection_or_action_candidates": 0,
                "raw_digital_transitions": 0,
                "raw_process_changes": 0,
            },
            "candidate_evidence": {
                "onset_candidate": None,
                "protection_chain_candidates": [],
                "raw_transition_candidates": [],
                "process_response_candidates": [],
            },
            "agent_policy": {
                "max_tool_calls_per_analysis": 8,
                "reserved_decisions": [
                    "critical_events", "primary_cause", "direct_trigger", "propagation", "causal_chain",
                ],
                "python_may_filter_and_rank_candidates": True,
                "python_may_finalize_causal_decisions": False,
            },
        }

    incident_id = event_rows[-1].get("incident_id", "")
    if incident_id:
        event_rows = [row for row in event_rows if row.get("incident_id", "") == incident_id]
        raw_rows = [row for row in raw_rows if row.get("incident_id", "") in {"", incident_id}]

    visible_events = [
        row for row in event_rows
        if str(row.get("event_class", "")).upper() in VISIBLE_EVENT_CLASSES
    ]
    visible_events.sort(key=_event_sort_key)

    onset = next(
        (
            row for row in visible_events
            if str(row.get("event_class", "")).upper() in {"OPERATOR_ACTION", "PROTECTION", "ALARM"}
        ),
        visible_events[0] if visible_events else event_rows[0],
    )

    event_candidates = [_event_candidate(row) for row in visible_events]
    protection_candidates = [
        item for item in event_candidates
        if item["candidate_role"] in {
            "TRIP_REQUEST", "PROTECTION_ACTUATION", "STATE_FEEDBACK", "PROTECTION_EVENT"
        }
    ][:MAX_PROTECTION_CANDIDATES]

    raw_transitions = raw_transition_candidates(raw_fields, raw_rows)
    process_changes = process_change_candidates(raw_fields, raw_rows)

    event_times = [
        finite(row.get("model_time_s")) for row in visible_events
        if finite(row.get("model_time_s")) is not None
    ]
    raw_times = [
        finite(row.get("model_time_s")) for row in raw_rows
        if finite(row.get("model_time_s")) is not None
    ]
    event_chronology_ready = bool(event_times)
    raw_timeseries_ready = len(raw_times) >= 2 and max(raw_times) >= min(raw_times)

    status = "PASS" if event_chronology_ready and raw_timeseries_ready else "COLLECTING"
    if status == "PASS":
        conclusion = (
            "EVENT chronology와 RAW time-series가 Agent 분석에 사용 가능한 상태입니다. "
            "Python은 특정 설비나 시나리오를 가정하지 않으며 인과 결론을 확정하지 않습니다."
        )
    else:
        conclusion = (
            "EVENT 또는 RAW 시간축 증거가 충분하지 않아 추가 수집이 필요합니다. "
            "Python은 특정 설비나 시나리오를 가정하지 않으며 인과 결론을 확정하지 않습니다."
        )

    raw_evidence = [
        f"{item['tag']} {item['from']:.0f}→{item['to']:.0f} @ {item['model_time_s']:.3f}s"
        for item in raw_transitions[:12]
    ]
    raw_evidence.extend(
        f"{item['tag']} {item['first']:.6g}→{item['last']:.6g} ({item['direction']})"
        for item in process_changes[:8]
    )

    return {
        "readiness_version": READINESS_VERSION,
        "status": status,
        "status_scope": "EVIDENCE_READINESS_ONLY",
        "mode": "DUAL_INPUT_EVENT_PLUS_RAW",
        "analysis_role": "EVIDENCE_PROVIDER_ONLY",
        "decision_authority": "GEMINI_AGENT",
        "decision_fields_generated_by_python": [],
        "incident_id": incident_id,
        "event_input_read": True,
        "raw_input_read": True,
        "event_path": str(event_csv),
        "raw_path": str(raw_csv),
        "event_rows": len(event_rows),
        "raw_rows": len(raw_rows),
        "onset": {
            "model_time_s": finite(onset.get("model_time_s", "")),
            "tag": onset.get("tag", ""),
            "message": onset.get("message", ""),
            "event_class": onset.get("event_class", ""),
        },
        "event_evidence": [event_text(row) for row in visible_events[:MAX_EVENT_EVIDENCE]],
        "raw_evidence": raw_evidence,
        "coverage": {
            "event_chronology_ready": event_chronology_ready,
            "raw_timeseries_ready": raw_timeseries_ready,
            "visible_event_count": len(visible_events),
            "protection_or_action_candidates": len(protection_candidates),
            "raw_digital_transitions": len(raw_transitions),
            "raw_process_changes": len(process_changes),
        },
        "candidate_evidence": {
            "onset_candidate": _event_candidate(onset),
            "protection_chain_candidates": protection_candidates,
            "raw_transition_candidates": raw_transitions,
            "process_response_candidates": process_changes,
        },
        "agent_policy": {
            "max_tool_calls_per_analysis": 8,
            "reserved_decisions": [
                "critical_events", "primary_cause", "direct_trigger", "propagation", "causal_chain",
            ],
            "python_may_filter_and_rank_candidates": True,
            "python_may_finalize_causal_decisions": False,
        },
        "conclusion": conclusion,
        "forbidden_metadata_columns": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze_dual_logs(args.event, args.raw)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] in {"PASS", "COLLECTING", "WAITING"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
