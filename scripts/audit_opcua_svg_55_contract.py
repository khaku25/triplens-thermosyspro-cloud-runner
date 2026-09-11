#!/usr/bin/env python3
"""Audit the authoritative seven-screen, 55-object OPC UA SVG contract."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "data" / "opcua_svg_55_contract_v1.csv"
SOURCE_WORKBOOK = "TripLens_TSP31_OPCUA_SVG_100pct_Contract_v1.xlsx"
SOURCE_SHEET = "SVG 구현"
EXPECTED_SCREENS = {
    "OVERVIEW": 9,
    "TRIP_SEQUENCE": 6,
    "HRSG": 6,
    "TURBINE_BYPASS": 5,
    "VALVE_MATRIX": 12,
    "ELECTRICAL": 15,
    "ALARMS": 2,
}
EXPECTED_FILES = {
    "topology/triplens_ecms_vpp.svg",
    "topology/trip_sequence.svg",
    "topology/hrsg_three_pressure.svg",
    "topology/turbine_bypass_vpp.svg",
    "topology/native_valves_12.svg",
    "topology/triplens_ecms_6p9kv.svg",
    "topology/alarm_banner.svg",
}
def normalized_svg_path(raw: str) -> str:
    return raw.removeprefix("NEW: ").strip()


def load_contract(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or ()), list(reader)


def inspect_row(row: dict[str, str], root: Path = ROOT) -> tuple[str, str]:
    relative = normalized_svg_path(row["svg_file"])
    path = root / relative
    if not path.is_file():
        return "MISSING_SVG_FILE", f"{relative} does not exist"
    try:
        svg = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return "INVALID_SVG_XML", f"{relative} XML parse failed: {exc}"
    target = next((element for element in svg.iter() if element.get("id") == row["root_dom_id"]), None)
    if target is None:
        return "MISSING_ROOT_DOM_ID", f"{relative} exists but id={row['root_dom_id']} is absent"
    binding = (target.get("data-bind") or "").strip()
    expected_binding = row["binding_tags"].strip()
    if not binding:
        return "MISSING_DATA_BINDING", f"id={row['root_dom_id']} has no data-bind attribute"
    if binding != expected_binding:
        return (
            "BINDING_TAG_MISMATCH",
            f"id={row['root_dom_id']} data-bind differs from authoritative binding_tags",
        )
    if (target.get("data-quality") or "").upper() != "BAD":
        return "UNSAFE_DEFAULT_QUALITY", f"id={row['root_dom_id']} must default data-quality=BAD"
    if (target.get("data-state") or "").upper() != "UNBOUND":
        return "UNSAFE_DEFAULT_STATE", f"id={row['root_dom_id']} must default data-state=UNBOUND"
    return "BOUND_UNVERIFIED_RUNTIME", f"id={row['root_dom_id']} has a binding attribute; live DataValue is not proven"


def validate_structure(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    if len(rows) != 55:
        errors.append(f"expected 55 SVG objects, found {len(rows)}")
    numbers = [int(row["no"]) for row in rows]
    if numbers != list(range(1, 56)):
        errors.append("object numbers must be exactly 1..55 in source order")
    screen_counts = Counter(row["screen"] for row in rows)
    if dict(screen_counts) != EXPECTED_SCREENS:
        errors.append(f"screen counts differ: {dict(screen_counts)}")
    paths = {normalized_svg_path(row["svg_file"]) for row in rows}
    if paths != EXPECTED_FILES:
        errors.append(f"screen files differ: {sorted(paths)}")
    ids = [row["root_dom_id"] for row in rows]
    duplicates = sorted(name for name, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append("duplicate Root DOM IDs: " + ", ".join(duplicates))
    return errors


def audit(path: Path = DEFAULT_CONTRACT, root: Path = ROOT) -> dict[str, object]:
    _fields, rows = load_contract(path)
    errors = validate_structure(rows)
    computed = [inspect_row(row, root) for row in rows]
    stale = [
        int(row["no"])
        for row, (status, evidence) in zip(rows, computed)
        if row["audit_status"] != status or row["audit_evidence"] != evidence
    ]
    if stale:
        errors.append("stale audit classifications at object(s): " + ", ".join(map(str, stale)))
    counts = Counter(status for status, _evidence in computed)
    bound = counts.get("BOUND_UNVERIFIED_RUNTIME", 0)
    return {
        "source_workbook": SOURCE_WORKBOOK,
        "source_sheet": SOURCE_SHEET,
        "status": "PASS_CONTRACT_CURRENT" if not errors else "FAIL_CONTRACT_STALE",
        "acceptance": "PASS" if bound == 55 else "FAIL_CLOSED",
        "object_count": len(rows),
        "screen_count": len({row["screen"] for row in rows}),
        "screen_file_count": len({normalized_svg_path(row["svg_file"]) for row in rows}),
        "classification_counts": dict(sorted(counts.items())),
        "live_runtime_bound_count": 0,
        "errors": errors,
    }


def update(path: Path = DEFAULT_CONTRACT, root: Path = ROOT) -> None:
    fields, rows = load_contract(path)
    structure_errors = validate_structure(rows)
    if structure_errors:
        raise ValueError("; ".join(structure_errors))
    for row in rows:
        row["audit_status"], row["audit_evidence"] = inspect_row(row, root)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--require-bound", action="store_true")
    args = parser.parse_args()
    if args.update:
        update(args.contract)
    report = audit(args.contract)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] != "PASS_CONTRACT_CURRENT":
        return 1
    if args.require_bound and report["acceptance"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
