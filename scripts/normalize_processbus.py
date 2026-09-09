#!/usr/bin/env python3
"""Normalize any numeric process CSV into the TripLens ProcessBus contract.

The contract has a small stable core (scenario_id, time_s and optional event
markers), canonical fields for known plant signals, and deterministic dynamic
passthrough fields for every additional numeric source column.  Unknown process
signals are therefore preserved instead of being discarded merely because a
scenario-specific mapping does not exist yet.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def canonical_header(value: str) -> str:
    return value.lstrip("\ufeff").strip().strip('"')


def resolve_column(headers: list[str], aliases: list[str]) -> str | None:
    canonical = {canonical_header(h): h for h in headers}
    for alias in aliases:
        if alias in canonical:
            return canonical[alias]
    for alias in aliases:
        matches = [raw for name, raw in canonical.items() if name.endswith("." + alias)]
        if len(matches) == 1:
            return matches[0]
    return None


def parse_float(value: str, field: str, row_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"row {row_number}: {field} is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"row {row_number}: {field} is not finite")
    return number


def normalize_typed_value(
    raw: str,
    field: str,
    definition: dict[str, object],
    row_number: int,
) -> str:
    """Normalize a mapped value without changing the immutable source CSV."""
    configured_type = definition.get("data_type")
    if configured_type is None and definition.get("value_type") == "boolean":
        configured_type = "BOOL"
    data_type = str(configured_type or "REAL").strip().upper()
    if data_type == "REAL":
        return f"{parse_float(raw, field, row_number):.12g}"
    if data_type == "INTEGER":
        value = parse_float(raw, field, row_number)
        if not value.is_integer():
            raise ValueError(f"row {row_number}: {field} must be an integer, got {raw!r}")
        return str(int(value))
    if data_type == "BOOL":
        normalized = raw.strip().lower()
        if normalized in {"1", "1.0", "true", "yes", "on"}:
            return "1"
        if normalized in {"0", "0.0", "false", "no", "off"}:
            return "0"
        raise ValueError(f"row {row_number}: {field} must be BOOL, got {raw!r}")
    if data_type == "ENUM":
        value = raw.strip().upper()
        allowed = {str(item).upper() for item in definition.get("allowed_values", [])}
        if allowed and value not in allowed:
            raise ValueError(
                f"row {row_number}: {field} must be one of {sorted(allowed)}, got {raw!r}"
            )
        return value
    raise ValueError(f"{field}: unsupported data_type {data_type!r}")


def extend_aliases_from_contract(
    signals: dict[str, dict[str, object]],
    path: Path,
) -> dict[str, object]:
    """Apply the canonical alias registry to the ProcessBus mapping."""
    required = {"kind", "canonical_name", "alias", "owner", "processbus_field", "status"}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        missing = required.difference(fields)
        if missing:
            raise ValueError("tag alias contract is missing: " + ", ".join(sorted(missing)))
        rows = list(reader)
    if not rows:
        raise ValueError("tag alias contract is empty")

    alias_owner: dict[str, str] = {}
    applied = 0
    for number, row in enumerate(rows, start=2):
        alias = row["alias"].strip()
        processbus_field = row["processbus_field"].strip()
        canonical_name = row["canonical_name"].strip()
        if not alias or not canonical_name:
            raise ValueError(f"tag alias contract row {number} has an empty name")
        if not processbus_field:
            continue
        if processbus_field not in signals:
            raise ValueError(
                f"tag alias contract row {number} references unknown ProcessBus field "
                f"{processbus_field!r}"
            )
        previous = alias_owner.get(alias)
        if previous is not None and previous != processbus_field:
            raise ValueError(
                f"tag alias {alias!r} maps to both {previous!r} and {processbus_field!r}"
            )
        alias_owner[alias] = processbus_field
        aliases = signals[processbus_field].setdefault("aliases", [])
        if alias not in aliases:
            aliases.append(alias)
        applied += 1
    return {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "row_count": len(rows),
        "processbus_alias_count": applied,
    }


def numeric_source_column(rows: list[dict[str, str]], header: str) -> bool:
    """Return True when every non-empty sample is finite numeric and at least one exists."""
    seen = False
    for row in rows:
        raw = (row.get(header) or "").strip()
        if not raw:
            continue
        seen = True
        try:
            value = float(raw)
        except ValueError:
            return False
        if not math.isfinite(value):
            return False
    return seen


def dynamic_signal_name(source_header: str, prefix: str, used: set[str]) -> str:
    canonical = canonical_header(source_header)
    # Keep names machine-friendly while the review JSON preserves the exact raw header.
    slug = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", canonical)
    slug = re.sub(r"[^0-9A-Za-z]+", "_", slug).strip("_").lower()
    if not slug:
        slug = "signal"
    if slug[0].isdigit():
        slug = "n_" + slug
    base = prefix + slug
    candidate = base
    if candidate in used:
        digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:8]
        candidate = f"{base}__{digest}"
        suffix = 2
        while candidate in used:
            candidate = f"{base}__{digest}_{suffix}"
            suffix += 1
    used.add(candidate)
    return candidate


def resolve_event_time(args: argparse.Namespace) -> tuple[float | None, bool]:
    if args.event_time is not None and args.trip_time is not None:
        if not math.isclose(args.event_time, args.trip_time, abs_tol=1e-12):
            raise ValueError("--event-time and legacy --trip-time disagree")
    event_time = args.event_time if args.event_time is not None else args.trip_time
    if event_time is not None and not math.isfinite(event_time):
        raise ValueError("event time must be finite")
    if args.legacy_gt_trip_cmd is None:
        legacy_gt_trip_cmd = args.trip_time is not None
    else:
        legacy_gt_trip_cmd = args.legacy_gt_trip_cmd
    if legacy_gt_trip_cmd and event_time is None:
        raise ValueError("--legacy-gt-trip-cmd requires --event-time or --trip-time")
    return event_time, legacy_gt_trip_cmd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, default=PROJECT_ROOT / "config/signal_map.json")
    parser.add_argument(
        "--alias-contract",
        type=Path,
        default=PROJECT_ROOT / "config/tag_alias_contract.csv",
    )
    parser.add_argument("--mapping-review", type=Path)
    parser.add_argument(
        "--event-time",
        type=float,
        help="Generic reference event time. Does not imply a GT trip.",
    )
    parser.add_argument(
        "--trip-time",
        type=float,
        help="Legacy alias for --event-time; keeps gt_trip_cmd for compatibility.",
    )
    parser.add_argument("--scenario-id", default="UNSPECIFIED")
    parser.add_argument(
        "--include-unmapped-numeric",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Preserve every additional finite numeric raw column as a dynamic ProcessBus signal.",
    )
    parser.add_argument("--dynamic-prefix", default="raw__")
    parser.add_argument(
        "--legacy-gt-trip-cmd",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Explicitly enable/disable the legacy synthesized gt_trip_cmd field.",
    )
    args = parser.parse_args()

    event_time, legacy_gt_trip_cmd = resolve_event_time(args)
    specification = json.loads(args.mapping.read_text(encoding="utf-8"))
    signals = specification.get("signals")
    if not isinstance(signals, dict) or "time_s" not in signals:
        raise ValueError("signal mapping must contain a signals.time_s definition")
    alias_contract = extend_aliases_from_contract(signals, args.alias_contract)

    with args.input.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("input CSV has no header")
        source_rows = list(reader)
        headers = list(reader.fieldnames)
    if len(source_rows) < 2:
        raise ValueError("input CSV must contain at least two data rows")

    resolved: dict[str, str | None] = {}
    missing_required: list[str] = []
    for target, definition in signals.items():
        aliases = list(definition.get("aliases", []))
        source = resolve_column(headers, aliases)
        resolved[target] = source
        if definition.get("required") and source is None:
            missing_required.append(target)
    if missing_required:
        raise ValueError("required ProcessBus source signals were not found: " + ", ".join(missing_required))

    time_source = resolved["time_s"]
    assert time_source is not None

    canonical_targets = [target for target in signals if target != "time_s"]
    mapped_present = [
        target for target in canonical_targets if resolved.get(target) is not None
    ]
    consumed_sources = {source for source in resolved.values() if source is not None}
    used_fields = {"scenario_id", "time_s", *canonical_targets}
    if event_time is not None:
        used_fields.add("event_marker")
    if legacy_gt_trip_cmd:
        used_fields.add("gt_trip_cmd")

    dynamic_sources: dict[str, str] = {}
    skipped_non_numeric: list[str] = []
    if args.include_unmapped_numeric:
        if not args.dynamic_prefix:
            raise ValueError("--dynamic-prefix must not be empty")
        for header in headers:
            if header in consumed_sources:
                continue
            if numeric_source_column(source_rows, header):
                field = dynamic_signal_name(header, args.dynamic_prefix, used_fields)
                dynamic_sources[field] = header
            else:
                skipped_non_numeric.append(canonical_header(header))

    output_fields = ["scenario_id", "time_s"]
    if event_time is not None:
        output_fields.append("event_marker")
    if legacy_gt_trip_cmd:
        output_fields.append("gt_trip_cmd")
    output_fields.extend(canonical_targets)
    output_fields.extend(dynamic_sources)

    normalized: list[dict[str, str | int | float]] = []
    previous_time: float | None = None
    duplicate_time_rows_collapsed = 0

    for row_index, source_row in enumerate(source_rows, start=2):
        time_s = parse_float(source_row[time_source], "time_s", row_index)
        if previous_time is not None and time_s < previous_time:
            raise ValueError(f"row {row_index}: time_s must be nondecreasing")

        target_row: dict[str, str | int | float] = {
            "scenario_id": args.scenario_id,
            "time_s": f"{time_s:.9f}",
        }
        if event_time is not None:
            target_row["event_marker"] = int(time_s >= event_time)
        if legacy_gt_trip_cmd:
            target_row["gt_trip_cmd"] = int(time_s >= event_time)

        for target in canonical_targets:
            source = resolved[target]
            if source is None:
                target_row[target] = ""
                continue
            raw = (source_row.get(source) or "").strip()
            target_row[target] = (
                "" if not raw
                else normalize_typed_value(raw, target, signals[target], row_index)
            )

        for target, source in dynamic_sources.items():
            raw = (source_row.get(source) or "").strip()
            target_row[target] = "" if not raw else f"{parse_float(raw, target, row_index):.12g}"

        if previous_time is not None and time_s == previous_time:
            # OpenModelica may emit pre-event and post-event values at one timestamp.
            # ProcessBus keeps only the final state while RAW remains untouched.
            normalized[-1] = target_row
            duplicate_time_rows_collapsed += 1
        else:
            normalized.append(target_row)
        previous_time = time_s

    if event_time is not None and not (
        float(normalized[0]["time_s"]) <= event_time <= float(normalized[-1]["time_s"])
    ):
        raise ValueError("event time is outside the source time range")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(normalized)

    review_path = args.mapping_review or args.output.with_name("signal-mapping-review.json")
    review = {
        "schema_version": specification.get("schema_version", "2.0"),
        "processbus_contract_version": "2.0",
        "tag_alias_contract": alias_contract,
        "input_file": args.input.name,
        "scenario_id": args.scenario_id,
        "reference_event_time_s": event_time,
        "legacy_gt_trip_cmd": legacy_gt_trip_cmd,
        "source_column_count": len(headers),
        "processbus_field_count": len(output_fields),
        "duplicate_time_rows_collapsed": duplicate_time_rows_collapsed,
        "duplicate_time_policy": "keep_last_event_state",
        "resolved": resolved,
        "canonical_signals_present": mapped_present,
        "missing_optional": [
            name for name, source in resolved.items()
            if source is None and not signals[name].get("required")
        ],
        "dynamic_passthrough": {
            "enabled": args.include_unmapped_numeric,
            "numeric_only": True,
            "prefix": args.dynamic_prefix,
            "count": len(dynamic_sources),
            "signals": [
                {"processbus_field": target, "source_column": canonical_header(source)}
                for target, source in dynamic_sources.items()
            ],
            "skipped_non_numeric_source_columns": skipped_non_numeric,
        },
        "raw_data_policy": "source CSV is read-only; values are not modified in place",
    }
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
