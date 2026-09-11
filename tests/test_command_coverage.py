from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_command_coverage import (  # noqa: E402
    ACK_RESULT_EVIDENCE,
    INDEPENDENT_FEEDBACK_EVIDENCE,
    TRANSACTION_QUALITY_EVIDENCE,
    VERIFIED_PHYSICAL_TRANSACTIONS,
    build_rows,
    read_catalog,
    strict_class_for,
    validate_coverage,
    write_outputs,
)


class CommandCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = read_catalog(ROOT / "config/ecms_command_catalog.csv")
        self.coverage = build_rows(self.catalog)

    def test_strict_87_command_counts_and_physical_allowlist(self) -> None:
        self.assertEqual(len(self.catalog), 87)
        self.assertEqual(len(self.coverage), 87)
        self.assertEqual(
            Counter(row["strict_class"] for row in self.coverage),
            {
                "PHYSICAL_CONNECTED": 2,
                "THERMO_ADAPTER_REQUIRED": 49,
                "ELECTRICAL_ENGINE_ONLY": 36,
            },
        )
        physical = {
            (row["equipment_id"], row["command"])
            for row in self.coverage
            if row["strict_class"] == "PHYSICAL_CONNECTED"
        }
        self.assertEqual(physical, set(VERIFIED_PHYSICAL_TRANSACTIONS))
        self.assertEqual(physical, {("GTG", "TRIP"), ("FWP-LP", "TRIP")})

    def test_physical_paths_do_not_overstate_transaction_completion(self) -> None:
        physical = {
            (row["equipment_id"], row["command"]): row
            for row in self.coverage
            if row["strict_class"] == "PHYSICAL_CONNECTED"
        }
        self.assertEqual(set(physical), {("GTG", "TRIP"), ("FWP-LP", "TRIP")})
        for key, row in physical.items():
            self.assertEqual(
                row["transaction_status"],
                "PHYSICAL_PATH_PROVEN_ACK_RESULT_PENDING",
            )
            self.assertEqual(
                row["native_dispatch_status"], "SCENARIO_NATIVE_PATH_PROVEN"
            )
            self.assertNotEqual(row["transaction_status"], "VERIFIED_CLOSED_LOOP")
            self.assertNotEqual(row["independent_feedback_status"], "VERIFIED")
            self.assertNotIn(ACK_RESULT_EVIDENCE, TRANSACTION_QUALITY_EVIDENCE.get(key, set()))
            self.assertNotIn(
                INDEPENDENT_FEEDBACK_EVIDENCE,
                TRANSACTION_QUALITY_EVIDENCE.get(key, set()),
            )

        self.assertEqual(
            physical[("GTG", "TRIP")]["independent_feedback_status"],
            "STATIC_FIX_PENDING_LIVE_PROOF",
        )
        self.assertEqual(
            physical[("FWP-LP", "TRIP")]["independent_feedback_status"],
            "BREAKER_PHYSICS_PROVEN_ECMS_STATE_WRITE_ECHO",
        )

    def test_completion_labels_fail_closed_without_quality_evidence(self) -> None:
        transaction_rows = deepcopy(self.coverage)
        gt_trip = next(
            row
            for row in transaction_rows
            if (row["equipment_id"], row["command"]) == ("GTG", "TRIP")
        )
        gt_trip["transaction_status"] = "VERIFIED_CLOSED_LOOP"
        with self.assertRaisesRegex(ValueError, "ACK/RESULT correlation evidence"):
            validate_coverage(transaction_rows)

        feedback_rows = deepcopy(self.coverage)
        lp_trip = next(
            row
            for row in feedback_rows
            if (row["equipment_id"], row["command"]) == ("FWP-LP", "TRIP")
        )
        lp_trip["independent_feedback_status"] = "VERIFIED"
        with self.assertRaisesRegex(ValueError, "independent readback evidence"):
            validate_coverage(feedback_rows)

    def test_connected_vpp_never_implies_physical_connection(self) -> None:
        legacy_connected = [
            row for row in self.catalog if row["status"] == "CONNECTED_VPP"
        ]
        self.assertEqual(len(legacy_connected), 51)
        classified_physical = [
            row for row in legacy_connected if strict_class_for(row) == "PHYSICAL_CONNECTED"
        ]
        self.assertEqual(len(classified_physical), 2)
        synthetic = dict(legacy_connected[0])
        synthetic["equipment_id"] = "UNREVIEWED"
        synthetic["command"] = "TRIP"
        synthetic["status"] = "CONNECTED_VPP"
        synthetic["execution_layer"] = "ELECTRICAL_ENGINE"
        self.assertEqual(strict_class_for(synthetic), "ELECTRICAL_ENGINE_ONLY")

    def test_vcb_transactions_are_adapter_required_until_verified(self) -> None:
        vcb_rows = [row for row in self.coverage if row["equipment_id"].startswith("VCB-")]
        self.assertEqual(len(vcb_rows), 12)
        self.assertTrue(
            all(row["strict_class"] == "THERMO_ADAPTER_REQUIRED" for row in vcb_rows)
        )
        self.assertTrue(all(row["native_dispatch_status"] == "REQUIRED" for row in vcb_rows))

    def test_generated_csv_and_json_are_complete_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            csv_path = Path(folder) / "coverage.csv"
            json_path = Path(folder) / "coverage.json"
            write_outputs(self.coverage, csv_path, json_path)
            with csv_path.open(encoding="utf-8", newline="") as stream:
                csv_rows = list(csv.DictReader(stream))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(len(csv_rows), 87)
        self.assertEqual(len(payload["commands"]), 87)
        self.assertEqual(
            payload["summary"],
            {
                "PHYSICAL_CONNECTED": 2,
                "THERMO_ADAPTER_REQUIRED": 49,
                "ELECTRICAL_ENGINE_ONLY": 36,
            },
        )
        self.assertEqual(
            payload["classification_policy"],
            "FAIL_CLOSED_EXPLICIT_PHYSICAL_REGISTRY",
        )
        self.assertTrue(all(row["evidence"] for row in payload["commands"]))

    def test_checked_in_outputs_match_generator(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            csv_path = Path(folder) / "coverage.csv"
            json_path = Path(folder) / "coverage.json"
            write_outputs(self.coverage, csv_path, json_path)
            self.assertEqual(
                csv_path.read_bytes(),
                (ROOT / "data/ecms_command_coverage_v1.csv").read_bytes(),
            )
            self.assertEqual(
                json_path.read_bytes(),
                (ROOT / "data/ecms_command_coverage_v1.json").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
