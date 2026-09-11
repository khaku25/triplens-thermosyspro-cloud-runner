#!/usr/bin/env python3
"""Build the fail-closed 87-command implementation coverage manifest.

The source catalog's ``status=CONNECTED_VPP`` is a legacy execution-status label.
It is deliberately *not* accepted as evidence of a physical OPC UA closed loop.
Only paths listed in VERIFIED_PHYSICAL_TRANSACTIONS may be classified as
PHYSICAL_CONNECTED.  That class means a native physical effect has been observed;
it does not mean that the command transaction, ACK/RESULT correlation, or
independent feedback proof is complete.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = PROJECT_ROOT / "config" / "ecms_command_catalog.csv"
DEFAULT_CSV = PROJECT_ROOT / "data" / "ecms_command_coverage_v1.csv"
DEFAULT_JSON = PROJECT_ROOT / "data" / "ecms_command_coverage_v1.json"

STRICT_CLASSES = {
    "PHYSICAL_CONNECTED",
    "THERMO_ADAPTER_REQUIRED",
    "ELECTRICAL_ENGINE_ONLY",
}

# A physical classification is a reviewed exception, never an inference from
# execution_layer, feedback_tag, or the legacy CONNECTED_VPP status.
VERIFIED_PHYSICAL_TRANSACTIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("GTG", "TRIP"): {
        "transaction_status": "PHYSICAL_PATH_PROVEN_ACK_RESULT_PENDING",
        "native_dispatch_status": "SCENARIO_NATIVE_PATH_PROVEN",
        "independent_feedback_status": "STATIC_FIX_PENDING_LIVE_PROOF",
        "evidence": [
            "scripts/patch_turbine_bypass_model.py",
            "modelica/TripLens_CombinedCycle_TripTAC.mo.tpl",
            "tests/test_gt_st_trip_independence.py",
            "data/opcua_lp_bfp_nodes_v1.csv",
        ],
    },
    ("FWP-LP", "TRIP"): {
        "transaction_status": "PHYSICAL_PATH_PROVEN_ACK_RESULT_PENDING",
        "native_dispatch_status": "SCENARIO_NATIVE_PATH_PROVEN",
        "independent_feedback_status": "BREAKER_PHYSICS_PROVEN_ECMS_STATE_WRITE_ECHO",
        "evidence": [
            "scripts/patch_lp_fwp_opcua.py",
            "scripts/native_ecms_opcua_client.py",
            "data/opcua_lp_bfp_nodes_v1.csv",
        ],
    },
}

# Completion labels remain fail-closed.  A path must have the named evidence
# before it can be called a verified command transaction or verified independent
# feedback.  No current command has either proof set.
TRANSACTION_QUALITY_EVIDENCE: dict[tuple[str, str], set[str]] = {}
ACK_RESULT_EVIDENCE = "REQUEST_ACK_RESULT_CORRELATION"
INDEPENDENT_FEEDBACK_EVIDENCE = "INDEPENDENT_READBACK"

# Every VCB operation changes the pump electrical boundary and therefore needs
# a Thermo adapter unless its complete command transaction is explicitly proven.
THERMO_ADAPTER_EQUIPMENT = {"VCB-A01", "VCB-B01", "VCB-A02"}

CSV_FIELDS = [
    "catalog_index",
    "equipment_id",
    "label_ko",
    "system",
    "equipment_type",
    "command",
    "source_execution_layer",
    "source_status",
    "model_input",
    "feedback_tag",
    "strict_class",
    "transaction_status",
    "native_dispatch_status",
    "independent_feedback_status",
    "evidence",
]


def read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    if len(rows) != 87:
        raise ValueError(f"expected exactly 87 catalog commands, found {len(rows)}")
    keys = [(row["equipment_id"].strip(), row["command"].strip()) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("catalog contains duplicate equipment_id/command transactions")
    missing_verified = set(VERIFIED_PHYSICAL_TRANSACTIONS).difference(keys)
    if missing_verified:
        raise ValueError(f"verified transaction missing from catalog: {sorted(missing_verified)}")
    return rows


def strict_class_for(row: dict[str, str]) -> str:
    """Return a physical class without trusting legacy connectivity labels."""
    key = (row["equipment_id"].strip(), row["command"].strip())
    if key in VERIFIED_PHYSICAL_TRANSACTIONS:
        return "PHYSICAL_CONNECTED"
    if (
        row["execution_layer"].strip() in {"THERMO_ADAPTER_REQUIRED", "THERMO_BOUNDARY"}
        or row["equipment_id"].strip() in THERMO_ADAPTER_EQUIPMENT
    ):
        return "THERMO_ADAPTER_REQUIRED"
    return "ELECTRICAL_ENGINE_ONLY"


def build_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    for index, source in enumerate(catalog_rows, start=1):
        key = (source["equipment_id"].strip(), source["command"].strip())
        strict_class = strict_class_for(source)
        if strict_class == "PHYSICAL_CONNECTED":
            proof = VERIFIED_PHYSICAL_TRANSACTIONS[key]
        elif strict_class == "THERMO_ADAPTER_REQUIRED":
            proof = {
                "transaction_status": "NOT_PHYSICALLY_CONNECTED",
                "native_dispatch_status": "REQUIRED",
                "independent_feedback_status": "NOT_VERIFIED",
                "evidence": [
                    "config/ecms_command_catalog.csv",
                    f"required_model_input:{source['model_input']}",
                ],
            }
        else:
            proof = {
                "transaction_status": "ECMS_STATE_MACHINE_ONLY",
                "native_dispatch_status": "NOT_APPLICABLE",
                "independent_feedback_status": "ELECTRICAL_ONLY",
                "evidence": [
                    "config/ecms_command_catalog.csv",
                    f"electrical_feedback:{source['feedback_tag']}",
                ],
            }
        coverage.append(
            {
                "catalog_index": index,
                "equipment_id": source["equipment_id"],
                "label_ko": source["label_ko"],
                "system": source["system"],
                "equipment_type": source["equipment_type"],
                "command": source["command"],
                "source_execution_layer": source["execution_layer"],
                "source_status": source["status"],
                "model_input": source["model_input"],
                "feedback_tag": source["feedback_tag"],
                "strict_class": strict_class,
                **proof,
            }
        )
    validate_coverage(coverage)
    return coverage


def validate_coverage(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 87:
        raise ValueError(f"coverage must contain 87 commands, found {len(rows)}")
    counts = Counter(row["strict_class"] for row in rows)
    expected = {
        "PHYSICAL_CONNECTED": 2,
        "THERMO_ADAPTER_REQUIRED": 49,
        "ELECTRICAL_ENGINE_ONLY": 36,
    }
    if dict(counts) != expected:
        raise ValueError(f"strict class count mismatch: expected {expected}, found {dict(counts)}")
    physical_keys = {
        (row["equipment_id"], row["command"])
        for row in rows
        if row["strict_class"] == "PHYSICAL_CONNECTED"
    }
    if physical_keys != set(VERIFIED_PHYSICAL_TRANSACTIONS):
        raise ValueError(
            "physical coverage must equal the explicit verified transaction registry"
        )
    for row in rows:
        if row["strict_class"] not in STRICT_CLASSES:
            raise ValueError(f"unknown strict class: {row['strict_class']}")
        if not row["evidence"]:
            raise ValueError(
                f"missing evidence for {row['equipment_id']}/{row['command']}"
            )
        # Fail closed: CONNECTED_VPP alone can never promote an unreviewed row.
        key = (row["equipment_id"], row["command"])
        if row["strict_class"] == "PHYSICAL_CONNECTED" and key not in VERIFIED_PHYSICAL_TRANSACTIONS:
            raise ValueError(f"unreviewed physical classification: {key}")
        quality_evidence = TRANSACTION_QUALITY_EVIDENCE.get(key, set())
        if (
            row["transaction_status"] == "VERIFIED_CLOSED_LOOP"
            and ACK_RESULT_EVIDENCE not in quality_evidence
        ):
            raise ValueError(
                f"closed-loop transaction lacks ACK/RESULT correlation evidence: {key}"
            )
        if (
            row["independent_feedback_status"] == "VERIFIED"
            and INDEPENDENT_FEEDBACK_EVIDENCE not in quality_evidence
        ):
            raise ValueError(
                f"feedback marked verified without independent readback evidence: {key}"
            )


def write_outputs(rows: list[dict[str, Any]], csv_path: Path, json_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row["evidence"] = ";".join(row["evidence"])
            writer.writerow(csv_row)
    payload = {
        "schema_version": "TRIPLENS-COMMAND-COVERAGE/1",
        "source": "config/ecms_command_catalog.csv",
        "classification_policy": "FAIL_CLOSED_EXPLICIT_PHYSICAL_REGISTRY",
        "summary": dict(Counter(row["strict_class"] for row in rows)),
        "commands": rows,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    rows = build_rows(read_catalog(args.catalog))
    write_outputs(rows, args.csv, args.json)
    counts = Counter(row["strict_class"] for row in rows)
    print(
        "generated 87-command coverage: "
        f"physical={counts['PHYSICAL_CONNECTED']} "
        f"adapter={counts['THERMO_ADAPTER_REQUIRED']} "
        f"electrical_only={counts['ELECTRICAL_ENGINE_ONLY']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
