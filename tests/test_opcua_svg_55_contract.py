from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data" / "opcua_svg_55_contract_v1.csv"
AUDITOR = ROOT / "scripts" / "audit_opcua_svg_55_contract.py"


def load_auditor():
    spec = importlib.util.spec_from_file_location("audit_opcua_svg_55_contract", AUDITOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class OPCUASVG55ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.auditor = load_auditor()
        with CONTRACT.open(encoding="utf-8", newline="") as stream:
            cls.rows = list(csv.DictReader(stream))

    def test_authoritative_inventory_is_exactly_seven_screens_and_55_objects(self):
        self.assertEqual(
            self.auditor.SOURCE_WORKBOOK,
            "TripLens_TSP31_OPCUA_SVG_100pct_Contract_v1.xlsx",
        )
        self.assertEqual(self.auditor.SOURCE_SHEET, "SVG 구현")
        self.assertEqual(self.auditor.validate_structure(self.rows), [])
        self.assertEqual(len(self.rows), 55)
        self.assertEqual(len({row["root_dom_id"] for row in self.rows}), 55)

    def test_all_static_bindings_are_present_but_runtime_remains_unproven(self):
        report = self.auditor.audit()
        self.assertEqual(report["status"], "PASS_CONTRACT_CURRENT")
        self.assertEqual(report["acceptance"], "PASS")
        self.assertEqual(report["live_runtime_bound_count"], 0)
        self.assertEqual(
            report["classification_counts"],
            {"BOUND_UNVERIFIED_RUNTIME": 55},
        )

    def test_every_root_uses_exact_authoritative_binding_and_bad_unbound_default(self):
        for row in self.rows:
            relative = self.auditor.normalized_svg_path(row["svg_file"])
            svg = ET.parse(ROOT / relative).getroot()
            target = next(
                element for element in svg.iter()
                if element.get("id") == row["root_dom_id"]
            )
            self.assertEqual(target.get("data-bind"), row["binding_tags"])
            self.assertEqual(target.get("data-quality"), "BAD")
            self.assertEqual(target.get("data-state"), "UNBOUND")

    def test_binding_attribute_is_still_not_live_runtime_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            svg = root / "topology" / "trip_sequence.svg"
            svg.parent.mkdir(parents=True)
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<g id="trip-gt-cmd" data-bind="TSP.TRIP.GT.CMD_READBACK" '
                'data-quality="BAD" data-state="UNBOUND"/>'
                '</svg>',
                encoding="utf-8",
            )
            row = next(row for row in self.rows if row["root_dom_id"] == "trip-gt-cmd")
            status, _evidence = self.auditor.inspect_row(row, root)
            self.assertEqual(status, "BOUND_UNVERIFIED_RUNTIME")

    def test_binding_mismatch_and_unsafe_default_fail_closed(self):
        row = next(row for row in self.rows if row["root_dom_id"] == "trip-gt-cmd")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            svg = root / "topology" / "trip_sequence.svg"
            svg.parent.mkdir(parents=True)
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<g id="trip-gt-cmd" data-bind="WRONG" '
                'data-quality="GOOD" data-state="BOUND"/>'
                '</svg>',
                encoding="utf-8",
            )
            status, _evidence = self.auditor.inspect_row(row, root)
            self.assertEqual(status, "BINDING_TAG_MISMATCH")


if __name__ == "__main__":
    unittest.main()
