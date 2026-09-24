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

    def test_st_grid_power_is_registered_as_operational_raw_tag(self):
        rows = read_table(
            ROOT / "data/current_v8/masters/06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx",
            "01_Live_OPCUA_Tag_Master",
            "raw_tag_id",
        )
        tag = next(row for row in rows if row["raw_tag_id"] == "vppSTGridPowerMW")

        self.assertEqual(tag["equipment_id"], "STG")
        self.assertEqual(tag["unit"], "MW")
        self.assertEqual(tag["signal_role"], "PHYSICAL_OR_PROCESS")
        self.assertEqual(tag["local_display_alias"], "ST_OUTPUT_MW")
        self.assertEqual(tag["writable"], "N")

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


if __name__ == "__main__":
    unittest.main()
