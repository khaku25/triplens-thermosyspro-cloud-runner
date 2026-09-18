#!/usr/bin/env python3
"""Bounded, fail-closed evidence tools for the TripLens Gemini agent.

Python owns parsing, filtering, time alignment helpers, evidence lookup, and
response-size guards. It does not decide Primary Cause, Direct Trigger,
Propagation, or Critical Events. Those are agent judgments produced from these
tools and later checked by the Verification Gate.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FORBIDDEN = {"scenario_id", "root_cause", "fault_injection", "fault_preset", "expected_root_cause"}
VISIBLE_EVENT_CLASSES = {"ALARM", "OPERATOR_ACTION", "PROTECTION", "ACK", "SYSTEM"}
RAW_META_COLUMNS = {"record_sequence", "session_id", "incident_id", "model_time_s", "wall_time_utc", "quality"}

DEFAULT_LIMITS = {
    "max_tool_calls": 8,
    "search_events": 20,
    "event_window": 30,
    "event_window_seconds": 10.0,
    "raw_window_rows": 50,
    "raw_window_seconds": 10.0,
    "raw_tags_per_call": 8,
    "tag_series_points": 50,
    "logic_context": 12,
    "equipment_state_events": 10,
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        leaked = sorted(FORBIDDEN.intersection(fields))
        if leaked:
            raise ValueError(f"answer/fault metadata leaked: {leaked}")
        return fields, list(reader)


def _clamp_int(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _clamp_seconds(value: Any, default: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if not math.isfinite(parsed):
        parsed = default
    return max(0.0, min(parsed, maximum))


def _downsample(items: list[Any], limit: int) -> list[Any]:
    if len(items) <= limit:
        return items
    if limit <= 1:
        return [items[0]]
    indexes = [round(i * (len(items) - 1) / (limit - 1)) for i in range(limit)]
    return [items[i] for i in indexes]


def _event_public(row: dict[str, str]) -> dict[str, Any]:
    return {
        "evidence_id": row.get("event_id", ""),
        "event_id": row.get("event_id", ""),
        "event_sequence": int(float(row.get("event_sequence") or 0)),
        "model_time_s": _finite(row.get("model_time_s")),
        "wall_time_utc": row.get("wall_time_utc", ""),
        "priority": row.get("priority", ""),
        "event_class": row.get("event_class", ""),
        "equipment": row.get("equipment", ""),
        "tag": row.get("tag", ""),
        "state": row.get("state", ""),
        "value": row.get("value", ""),
        "unit": row.get("unit", ""),
        "message": row.get("message", ""),
        "source": row.get("source", ""),
    }


@dataclass
class EvidenceStore:
    event_csv: Path
    raw_csv: Path
    logic_rows: Iterable[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        self.event_fields, event_rows = _read_csv(Path(self.event_csv))
        self.raw_fields, raw_rows = _read_csv(Path(self.raw_csv))
        incident_id = event_rows[-1].get("incident_id", "") if event_rows else ""
        if incident_id:
            event_rows = [row for row in event_rows if row.get("incident_id", "") == incident_id]
            raw_rows = [row for row in raw_rows if row.get("incident_id", "") in {"", incident_id}]
        self.incident_id = incident_id
        self.event_rows = [row for row in event_rows if row.get("event_class") in VISIBLE_EVENT_CLASSES]
        self.event_rows.sort(key=lambda row: (_finite(row.get("model_time_s")) is None, _finite(row.get("model_time_s")) or 0.0, row.get("event_id", "")))
        self.raw_rows = sorted(raw_rows, key=lambda row: (_finite(row.get("model_time_s")) is None, _finite(row.get("model_time_s")) or 0.0))
        self.logic_rows = [dict(row) for row in (self.logic_rows or [])]

    def search_events(
        self,
        query: str = "",
        *,
        equipment: str | None = None,
        event_class: str | None = None,
        tags: list[str] | None = None,
        limit: int = DEFAULT_LIMITS["search_events"],
    ) -> list[dict[str, Any]]:
        cap = _clamp_int(limit, DEFAULT_LIMITS["search_events"], DEFAULT_LIMITS["search_events"])
        q = str(query or "").strip().lower()
        equipment_key = str(equipment or "").strip().lower()
        class_key = str(event_class or "").strip().upper()
        tag_keys = {str(tag).strip().upper() for tag in (tags or []) if str(tag).strip()}
        matches: list[dict[str, Any]] = []
        for row in self.event_rows:
            if equipment_key and equipment_key not in row.get("equipment", "").lower():
                continue
            if class_key and row.get("event_class", "").upper() != class_key:
                continue
            if tag_keys and row.get("tag", "").upper() not in tag_keys:
                continue
            if q:
                haystack = " ".join([
                    row.get("message", ""), row.get("tag", ""), row.get("equipment", ""),
                    row.get("state", ""), row.get("event_class", ""), row.get("source", ""),
                ]).lower()
                if q not in haystack:
                    continue
            matches.append(_event_public(row))
            if len(matches) >= cap:
                break
        return matches

    def get_event_window(
        self,
        center_time_s: float,
        *,
        before_s: float = 5.0,
        after_s: float = 5.0,
        limit: int = DEFAULT_LIMITS["event_window"],
    ) -> list[dict[str, Any]]:
        center = float(center_time_s)
        before = _clamp_seconds(before_s, 5.0, DEFAULT_LIMITS["event_window_seconds"])
        after = _clamp_seconds(after_s, 5.0, DEFAULT_LIMITS["event_window_seconds"])
        cap = _clamp_int(limit, DEFAULT_LIMITS["event_window"], DEFAULT_LIMITS["event_window"])
        rows = []
        for row in self.event_rows:
            when = _finite(row.get("model_time_s"))
            if when is None or when < center - before or when > center + after:
                continue
            rows.append(_event_public(row))
        rows.sort(key=lambda item: (item["model_time_s"] is None, item["model_time_s"] or 0.0, item["event_id"]))
        return rows[:cap]

    def get_raw_window(
        self,
        tags: list[str],
        start_time_s: float,
        end_time_s: float,
        *,
        max_rows: int = DEFAULT_LIMITS["raw_window_rows"],
    ) -> dict[str, Any]:
        requested = [str(tag).strip() for tag in tags if str(tag).strip()]
        requested = requested[: DEFAULT_LIMITS["raw_tags_per_call"]]
        available = [tag for tag in requested if tag in self.raw_fields and tag not in RAW_META_COLUMNS]
        missing = [tag for tag in requested if tag not in available]
        start = float(start_time_s); end = float(end_time_s)
        if end < start:
            start, end = end, start
        max_span = DEFAULT_LIMITS["raw_window_seconds"] * 2
        if end - start > max_span:
            end = start + max_span
        cap = _clamp_int(max_rows, DEFAULT_LIMITS["raw_window_rows"], DEFAULT_LIMITS["raw_window_rows"])
        compact: list[dict[str, Any]] = []
        for row in self.raw_rows:
            when = _finite(row.get("model_time_s"))
            if when is None or when < start or when > end:
                continue
            item: dict[str, Any] = {"model_time_s": when}
            for tag in available:
                parsed = _finite(row.get(tag))
                item[tag] = parsed if parsed is not None else row.get(tag, "")
            compact.append(item)
        return {
            "tags": available,
            "missing_tags": missing,
            "rows": _downsample(compact, cap),
            "truncated": len(compact) > cap,
        }

    def get_tag_series(
        self,
        tag: str,
        start_time_s: float,
        end_time_s: float,
        *,
        max_points: int = DEFAULT_LIMITS["tag_series_points"],
    ) -> dict[str, Any]:
        tag = str(tag).strip()
        if tag not in self.raw_fields or tag in RAW_META_COLUMNS:
            return {"tag": tag, "status": "UNREGISTERED_OR_MISSING", "points": [], "summary": {}}
        start = float(start_time_s); end = float(end_time_s)
        if end < start:
            start, end = end, start
        cap = _clamp_int(max_points, DEFAULT_LIMITS["tag_series_points"], DEFAULT_LIMITS["tag_series_points"])
        points: list[dict[str, float]] = []
        for row in self.raw_rows:
            when = _finite(row.get("model_time_s")); value = _finite(row.get(tag))
            if when is None or value is None or when < start or when > end:
                continue
            points.append({"model_time_s": when, "value": value})
        sampled = _downsample(points, cap)
        summary: dict[str, Any] = {}
        if points:
            first = points[0]["value"]; last = points[-1]["value"]; delta = last - first
            duration = points[-1]["model_time_s"] - points[0]["model_time_s"]
            summary = {
                "first": first,
                "last": last,
                "min": min(p["value"] for p in points),
                "max": max(p["value"] for p in points),
                "delta": delta,
                "percent_change": None if abs(first) < 1e-12 else 100.0 * delta / abs(first),
                "slope_per_s": None if abs(duration) < 1e-12 else delta / duration,
                "sample_count": len(points),
            }
        return {"tag": tag, "status": "OK", "points": sampled, "summary": summary, "truncated": len(points) > cap}

    def get_logic_context(self, tags: list[str], *, limit: int = DEFAULT_LIMITS["logic_context"]) -> dict[str, Any]:
        requested = [str(tag).strip() for tag in tags if str(tag).strip()]
        cap = _clamp_int(limit, DEFAULT_LIMITS["logic_context"], DEFAULT_LIMITS["logic_context"])
        items: list[dict[str, Any]] = []
        matched_tags: set[str] = set()
        fields = ("tag_id", "canonical_tag", "event_tag", "source_node")
        for row in self.logic_rows:
            row_values = {str(row.get(field, "")).strip() for field in fields if str(row.get(field, "")).strip()}
            linked = str(row.get("linked_tag_ids", "") or "")
            if linked:
                row_values.update(part.strip() for part in linked.replace(",", ";").split(";") if part.strip())
            hits = [tag for tag in requested if tag in row_values]
            if not hits:
                continue
            items.append(dict(row))
            matched_tags.update(hits)
            if len(items) >= cap:
                break
        unregistered = [tag for tag in requested if tag not in matched_tags]
        return {
            "items": items,
            "unregistered_tags": unregistered,
            "infer_unregistered_logic": False,
            "status": "VERIFIED" if requested and not unregistered else "PARTIAL_OR_UNREGISTERED",
        }

    def get_equipment_state(
        self,
        equipment: str,
        at_time_s: float,
        *,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        equipment_key = str(equipment or "").strip().lower()
        when = float(at_time_s)
        related = [
            _event_public(row) for row in self.event_rows
            if equipment_key and equipment_key in row.get("equipment", "").lower()
            and _finite(row.get("model_time_s")) is not None
            and abs((_finite(row.get("model_time_s")) or 0.0) - when) <= 5.0
        ]
        related.sort(key=lambda item: abs((item["model_time_s"] or 0.0) - when))
        related = related[: DEFAULT_LIMITS["equipment_state_events"]]
        raw_values: dict[str, Any] = {}
        requested = [str(tag).strip() for tag in (tags or []) if str(tag).strip()][: DEFAULT_LIMITS["raw_tags_per_call"]]
        if requested and self.raw_rows:
            candidates = [(abs((_finite(row.get("model_time_s")) or 0.0) - when), row) for row in self.raw_rows if _finite(row.get("model_time_s")) is not None]
            if candidates:
                _, nearest = min(candidates, key=lambda item: item[0])
                for tag in requested:
                    if tag in self.raw_fields and tag not in RAW_META_COLUMNS:
                        parsed = _finite(nearest.get(tag))
                        raw_values[tag] = parsed if parsed is not None else nearest.get(tag, "")
        return {
            "equipment": equipment,
            "at_time_s": when,
            "events": related,
            "raw_values": raw_values,
            "raw_tag_inference_performed": False,
        }

    def build_agent_bootstrap(self, *, run_id: str = "", data_digest: str = "") -> dict[str, Any]:
        """Return a deliberately small first-turn context; bulk evidence stays behind tools."""
        return {
            "mode": "HYBRID_AGENT_EVIDENCE_TOOLS_V1",
            "run_id": str(run_id or ""),
            "data_digest": str(data_digest or ""),
            "incident_id": self.incident_id,
            "event_row_count": len(self.event_rows),
            "raw_row_count": len(self.raw_rows),
            "decision_authority": "GEMINI_AGENT",
            "python_role": "EVIDENCE_PROVIDER_AND_VERIFIER",
            "tool_manifest": self.tool_manifest(),
        }

    def tool_manifest(self) -> dict[str, Any]:
        return {
            "mode": "HYBRID_AGENT_EVIDENCE_TOOLS_V1",
            "python_role": "EVIDENCE_PROVIDER_AND_VERIFIER",
            "agent_role": "SELECT_COMPARE_AND_CAUSAL_REASONING",
            "max_tool_calls_per_analysis": DEFAULT_LIMITS["max_tool_calls"],
            "response_limits": dict(DEFAULT_LIMITS),
            "tools": [
                {"name":"search_events","description":"Search filtered EVENT evidence; returns at most 20 evidence-linked rows.","parameters":{"query":"string","equipment":"string?","event_class":"string?","tags":"string[]?","limit":"integer<=20"}},
                {"name":"get_event_window","description":"Read chronological EVENT evidence around a model-time center.","parameters":{"center_time_s":"number","before_s":"number<=10","after_s":"number<=10","limit":"integer<=30"}},
                {"name":"get_raw_window","description":"Read only explicitly requested RAW tags in a bounded time window.","parameters":{"tags":"string[]<=8","start_time_s":"number","end_time_s":"number","max_rows":"integer<=50"}},
                {"name":"get_tag_series","description":"Read one RAW tag with downsampled points plus numeric summary.","parameters":{"tag":"string","start_time_s":"number","end_time_s":"number","max_points":"integer<=50"}},
                {"name":"get_logic_context","description":"Return exact Logic Master matches only; never infer unregistered logic.","parameters":{"tags":"string[]","limit":"integer<=12"}},
                {"name":"get_equipment_state","description":"Return nearby equipment events and only explicitly requested RAW tags.","parameters":{"equipment":"string","at_time_s":"number","tags":"string[]<=8?"}},
            ],
            "decision_fields_reserved_for_agent": [
                "critical_events", "primary_cause", "direct_trigger", "propagation", "causal_chain"
            ],
        }


class AgentToolSession:
    """Per-analysis call budget so tool loops cannot grow without bound."""

    def __init__(self, store: EvidenceStore, max_calls: int = DEFAULT_LIMITS["max_tool_calls"]):
        self.store = store
        self.max_calls = min(max(1, int(max_calls)), DEFAULT_LIMITS["max_tool_calls"])
        self.calls_used = 0

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        if self.calls_used >= self.max_calls:
            raise RuntimeError("TripLens agent tool-call budget exceeded")
        if name not in {
            "search_events", "get_event_window", "get_raw_window", "get_tag_series", "get_logic_context", "get_equipment_state"
        }:
            raise KeyError(f"unknown TripLens tool: {name}")
        self.calls_used += 1
        fn = getattr(self.store, name)
        return fn(**(arguments or {}))

    def budget(self) -> dict[str, int]:
        return {"used": self.calls_used, "remaining": self.max_calls - self.calls_used, "max": self.max_calls}
