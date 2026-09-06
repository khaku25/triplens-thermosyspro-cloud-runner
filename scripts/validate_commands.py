#!/usr/bin/env python3
"""Validate the device-neutral TripLens CommandBus CSV contract."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_FIELDS = {
    "equipment_id", "label_ko", "system", "equipment_type", "command",
    "button_label", "value_type", "min_value", "max_value", "default_value",
    "unit", "execution_layer", "model_input", "feedback_tag", "status", "notes",
}
QUEUE_FIELDS = {
    "sequence", "time_s", "equipment_id", "equipment_label", "command",
    "command_value", "unit", "execution_layer", "model_input", "feedback_tag",
    "status", "note",
}
LAYERS = {"ELECTRICAL_ENGINE", "THERMO_BOUNDARY", "THERMO_ADAPTER_REQUIRED"}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"{path}: missing CSV header")
        return list(reader.fieldnames), list(reader)


def finite_number(raw: str, name: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} is not numeric: {raw!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def load_catalog(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    fields, rows = read_csv(path)
    missing = CATALOG_FIELDS.difference(fields)
    if missing:
        raise ValueError("command catalog is missing fields: " + ", ".join(sorted(missing)))
    catalog: dict[tuple[str, str], dict[str, str]] = {}
    for number, row in enumerate(rows, start=2):
        key = (row["equipment_id"].strip(), row["command"].strip())
        if not all(key):
            raise ValueError(f"catalog row {number}: equipment_id and command are required")
        if key in catalog:
            raise ValueError(f"catalog row {number}: duplicate command {key[0]}/{key[1]}")
        if row["execution_layer"] not in LAYERS:
            raise ValueError(f"catalog row {number}: unknown execution_layer {row['execution_layer']!r}")
        if row["value_type"] not in {"REAL", "DIGITAL"}:
            raise ValueError(f"catalog row {number}: unknown value_type {row['value_type']!r}")
        if row["value_type"] == "REAL":
            low = finite_number(row["min_value"], f"catalog row {number} min_value")
            high = finite_number(row["max_value"], f"catalog row {number} max_value")
            default = finite_number(row["default_value"], f"catalog row {number} default_value")
            if not low <= default <= high:
                raise ValueError(f"catalog row {number}: default_value is outside limits")
        catalog[key] = row
    if not catalog:
        raise ValueError("command catalog is empty")
    return catalog


def validate_queue(path: Path, catalog: dict[tuple[str, str], dict[str, str]]) -> list[dict[str, str]]:
    fields, rows = read_csv(path)
    missing = QUEUE_FIELDS.difference(fields)
    if missing:
        raise ValueError("command queue is missing fields: " + ", ".join(sorted(missing)))
    previous = (-1.0, -1)
    sequences: set[int] = set()
    for number, row in enumerate(rows, start=2):
        try:
            sequence = int(row["sequence"])
        except ValueError as exc:
            raise ValueError(f"queue row {number}: sequence must be an integer") from exc
        time_s = finite_number(row["time_s"], f"queue row {number} time_s")
        if sequence in sequences:
            raise ValueError(f"queue row {number}: duplicate sequence {sequence}")
        sequences.add(sequence)
        if time_s < 0:
            raise ValueError(f"queue row {number}: time_s must be non-negative")
        if (time_s, sequence) < previous:
            raise ValueError(f"queue row {number}: commands must be sorted by time_s and sequence")
        previous = (time_s, sequence)
        key = (row["equipment_id"].strip(), row["command"].strip())
        if key not in catalog:
            raise ValueError(f"queue row {number}: unregistered command {key[0]}/{key[1]}")
        definition = catalog[key]
        for field in ("execution_layer", "model_input", "feedback_tag"):
            if row[field] != definition[field]:
                raise ValueError(f"queue row {number}: {field} does not match catalog")
        if definition["value_type"] == "REAL":
            value = finite_number(row["command_value"], f"queue row {number} command_value")
            low = float(definition["min_value"])
            high = float(definition["max_value"])
            if not low <= value <= high:
                raise ValueError(f"queue row {number}: command_value is outside [{low}, {high}]")
        elif row["command_value"] != definition["default_value"]:
            raise ValueError(
                f"queue row {number}: command_value must match catalog default {definition['default_value']}"
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=PROJECT_ROOT / "config/ecms_command_catalog.csv")
    parser.add_argument("--commands", type=Path)
    parser.add_argument("--stop-time", type=float)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    if args.commands:
        rows = validate_queue(args.commands, catalog)
        if args.stop_time is not None:
            if not math.isfinite(args.stop_time) or args.stop_time <= 0:
                raise ValueError("--stop-time must be a positive finite number")
            if any(float(row["time_s"]) > args.stop_time for row in rows):
                raise ValueError("command queue contains a command after --stop-time")
        print(f"validated {len(catalog)} catalog commands and {len(rows)} queued commands")
    else:
        print(f"validated {len(catalog)} catalog commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
