#!/usr/bin/env python3
"""Read EVENT.csv and RAW.csv together and build evidence-bound LP-BFP analysis."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import deque
from pathlib import Path
from typing import Any


FORBIDDEN = {"scenario_id", "root_cause", "fault_injection", "fault_preset", "expected_root_cause"}
CHAIN = (
    ("LP_BFP_TRIP_CMD", "vppLPFWPTripCommandNative", "RISE"),
    ("LP_BFP_TRIP_LATCH", "vppLPFWPTripLatchNative", "RISE"),
    ("VCB_A02_TRIP_CMD", "vppVCBA02TripCommandNative", "RISE"),
    ("VCB_A02_CLOSED", "vppECMSVCBA02Closed", "FALL"),
)
ANALOG = (
    ("LP_BFP_SPEED", "vppLPFWPSpeedRPM", "rpm"),
    ("LP_FW_FLOW", "vppLPFWPMassFlowTH", "t/h"),
    ("LP_DRUM_LEVEL", "vppLPDrumLevelM", "m"),
)


def rows(path: Path, tail: int | None = None) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        if tail is None:
            return fields, list(reader)
        kept: deque[dict[str, str]] = deque(maxlen=tail)
        kept.extend(reader)
        return fields, list(kept)


def finite(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def event_text(row: dict[str, str]) -> str:
    wall = row.get("wall_time_utc", "")
    clock = wall[11:23] if len(wall) >= 23 else wall
    return f"{clock} {row.get('message') or row.get('tag', '')}".strip()


def first_edge(raw_rows: list[dict[str, str]], field: str, edge: str) -> dict[str, Any] | None:
    previous: float | None = None
    for row in raw_rows:
        current = finite(row.get(field, ""))
        if current is None:
            continue
        if previous is not None:
            crossed = previous < 0.5 <= current if edge == "RISE" else previous >= 0.5 > current
            if crossed:
                return {
                    "tag": field,
                    "from": previous,
                    "to": current,
                    "model_time_s": finite(row.get("model_time_s", "")),
                }
        previous = current
    return None


def analog_change(raw_rows: list[dict[str, str]], field: str) -> dict[str, Any] | None:
    samples = [
        (finite(row.get("model_time_s", "")), finite(row.get(field, "")))
        for row in raw_rows
    ]
    samples = [(when, value) for when, value in samples if when is not None and value is not None]
    if len(samples) < 2:
        return None
    before_t, before = samples[0]
    after_t, after = samples[-1]
    delta = after - before
    pct = None if abs(before) < 1e-12 else 100.0 * delta / abs(before)
    return {
        "tag": field, "before": before, "after": after, "delta": delta,
        "percent": pct, "from_model_time_s": before_t, "to_model_time_s": after_t,
    }


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
            "candidate_evidence": {
                "onset_candidate": None,
                "protection_chain_candidates": [],
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
        if row.get("event_class") in {"ALARM", "OPERATOR_ACTION", "PROTECTION", "ACK", "SYSTEM"}
    ]
    event_evidence = [event_text(row) for row in visible_events[-12:]]

    chain_evidence: list[dict[str, Any]] = []
    raw_evidence: list[str] = []
    for label, field, edge in CHAIN:
        if field not in raw_fields:
            raw_evidence.append(f"{label}: TAG MISSING")
            continue
        crossing = first_edge(raw_rows, field, edge)
        if crossing is None:
            raw_evidence.append(f"{label}: 변화 대기")
            continue
        chain_evidence.append({"label": label, **crossing})
        raw_evidence.append(
            f"{label} {crossing['from']:.0f}→{crossing['to']:.0f} "
            f"@ {crossing['model_time_s']:.3f}s"
        )

    process_changes: list[dict[str, Any]] = []
    for label, field, unit in ANALOG:
        if field not in raw_fields:
            raw_evidence.append(f"{label}: TAG MISSING")
            continue
        change = analog_change(raw_rows, field)
        if change is None:
            raw_evidence.append(f"{label}: 표본 부족")
            continue
        process_changes.append({"label": label, "unit": unit, **change})
        direction = "감소" if change["delta"] < 0 else "증가"
        raw_evidence.append(
            f"{label} {change['before']:.4g}→{change['after']:.4g} {unit} ({direction})"
        )

    onset = next(
        (row for row in visible_events if row.get("event_class") in {"OPERATOR_ACTION", "PROTECTION", "ALARM"}),
        visible_events[0] if visible_events else event_rows[0],
    )
    chain_labels = [item["label"] for item in chain_evidence]
    expected_labels = [item[0] for item in CHAIN]
    chain_complete = chain_labels == expected_labels
    analog_decrease = {
        item["label"]: item["delta"] < 0 for item in process_changes
    }
    response_verified = analog_decrease.get("LP_BFP_SPEED", False) and analog_decrease.get("LP_FW_FLOW", False)
    if chain_complete and response_verified:
        status = "PASS"
        conclusion = (
            "EVENT/RAW 증거 묶음이 Agent 분석에 충분한 상태입니다. "
            "Python은 원인·Trigger·Propagation을 확정하지 않습니다."
        )
    else:
        status = "COLLECTING"
        conclusion = (
            "Agent 분석용 EVENT/RAW 증거를 추가 수집 중입니다. "
            "Python은 인과 결론을 생성하지 않습니다."
        )
    return {
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
        },
        "event_evidence": event_evidence,
        "raw_evidence": raw_evidence,
        "chain": chain_evidence,
        "chain_complete": chain_complete,
        "process_response_verified": response_verified,
        "candidate_evidence": {
            "onset_candidate": {
                "model_time_s": finite(onset.get("model_time_s", "")),
                "tag": onset.get("tag", ""),
                "message": onset.get("message", ""),
            },
            "protection_chain_candidates": chain_evidence,
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
