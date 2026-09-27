import json
import unittest
from pathlib import Path

from scripts.logic_assets.drawing_master import search_drawing_master
from scripts.logic_assets.xmlio import read_table


ROOT = Path(__file__).resolve().parents[1]


class STGridPowerMasterTest(unittest.TestCase):
    def test_supplemental_live_readback_is_qualified_as_private_partial_evidence(self):
        current_v8 = ROOT / "data/current_v8"
        provenance = json.loads(
            (current_v8 / "live_census_provenance.json").read_text(encoding="utf-8")
        )["supplemental_evidence"]
        evidence = current_v8 / provenance["file"]

        self.assertFalse(provenance["published"])
        self.assertEqual(
            provenance["publication_status"], "WITHHELD_RAW_PLANT_TELEMETRY"
        )
        self.assertFalse(evidence.exists(), "private RAW plant telemetry must not ship")
        self.assertEqual(len(provenance["sha256"]), 64)
        self.assertIn("node_id and 52ST-open response were not captured", provenance["evidence_scope"])

    def test_st_grid_power_is_searchable_without_rewriting_run54_live_census(self):
        live = read_table(
            ROOT / "data/current_v8/masters/06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx",
            "01_Live_OPCUA_Tag_Master",
            "raw_tag_id",
        )
        source = read_table(
            ROOT / "data/current_v8/masters/06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx",
            "11_Model_Source_Observed",
            "raw_tag_id",
        )
        self.assertNotIn("vppSTGridPowerMW", {row["raw_tag_id"] for row in live})
        tag = next(row for row in source if row["raw_tag_id"] == "vppSTGridPowerMW")
        self.assertEqual(tag["equipment_id"], "STG")
        self.assertEqual(tag["unit"], "MW")
        self.assertEqual(tag["runtime_inclusion"], "SEARCH_ONLY")

        proof = json.loads((ROOT / "data/current_v8/st_power_evidence_20260924.json").read_text())
        later = proof["later_runtime_verification"]
        self.assertEqual(later["open_behavior_test_status"], "RUNTIME_VERIFIED")
        self.assertTrue(later["st_grid_power_zero_verified"])

    def test_st_grid_power_resolves_to_exact_st_drawing_cell(self):
        drawing_master = json.loads(
            (ROOT / "logic_diagrams/drawing_master_index.json").read_text(encoding="utf-8")
        )

        matches = search_drawing_master(drawing_master, "vppSTGridPowerMW")
        exact = [
            item
            for item in matches
            if item["tag_id"] == "vppSTGridPowerMW"
            and item["page_name"] == "ST Protection"
            and item["object_type"] == "source"
        ]

        self.assertTrue(exact, "ST grid MW must open an exact source cell on the ST drawing")
        self.assertIn("page=screen:", exact[0]["source_ref"])
        self.assertIn("cell=output:RESP-ST-GRID-POWER:", exact[0]["source_ref"])

    def test_breaker_open_runtime_ledger_is_declared(self):
        import csv
        current = ROOT / "data/current_v8"
        provenance = json.loads((current / "live_census_provenance.json").read_text())
        self.assertEqual(provenance["expected_vpp_count"], 603)
        runtime = provenance["runtime_behavior_evidence"]
        self.assertEqual(runtime["status"], "RUNTIME_VERIFIED")
        ledger = ROOT / runtime["evidence_csv"]
        self.assertTrue(ledger.exists())
        with ledger.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertTrue(any(r["signal"] == "vppCauseSTBreakerOpenWhileRunning" and r["value"] == "1" for r in rows))
        self.assertTrue(any(r["signal"] == "vppSTGridPowerMW" and r["value"] == "0" and r["verification_status"] == "RUNTIME_VERIFIED" for r in rows))



if __name__ == "__main__":
    unittest.main()
