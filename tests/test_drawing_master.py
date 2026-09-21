"""Drawing Master indexes existing draw.io cells without changing the source XML."""
import hashlib
import json
from pathlib import Path
import unittest


DRAWING = '''<?xml version="1.0" encoding="utf-8"?>
<mxfile host="app.diagrams.net" triplens_schema="2">
  <diagram id="rule:AL-HP" name="HP Drum · AL-HP" scope="rule" rule_ids="[&quot;AL-HP&quot;]">
    <mxGraphModel pageWidth="1200" pageHeight="800"><root>
      <mxCell id="0"/><mxCell id="1" parent="0"/>
      <object id="operation:AL-HP" kind="operation" rule_id="AL-HP" group_id="IG-001" label="HPBP command">
        <mxCell vertex="1" parent="1" style=""><mxGeometry x="300" y="120" width="240" height="90" as="geometry"/></mxCell>
      </object>
      <object id="output:AL-HP:vppHPDrumLevelM" kind="source" rule_id="AL-HP" tag_id="vppHPDrumLevelM" label="vppHPDrumLevelM">
        <mxCell vertex="1" parent="1" style=""><mxGeometry x="620" y="120" width="240" height="90" as="geometry"/></mxCell>
      </object>
    </root></mxGraphModel>
  </diagram>
</mxfile>'''


class DrawingMasterTest(unittest.TestCase):
    def test_indexes_cells_with_verifiable_refs_and_searches_tag_or_logic(self):
        from scripts.logic_assets.drawing_master import create_drawing_master, search_drawing_master

        index = create_drawing_master(
            DRAWING,
            file_path="logic_diagrams/TripLens_Logic_Master_Current_V8.drawio",
            canonical_tags={"vppHPDrumLevelM": "HP.DRUM.LEVEL"},
        )

        self.assertEqual(index["schema_version"], 1)
        self.assertEqual(index["counts"]["drawings"], 1)
        self.assertEqual(index["counts"]["cells"], 2)
        tag = next(row for row in index["entries"] if row["canonical_tag"] == "HP.DRUM.LEVEL")
        self.assertEqual(tag["logic_id"], "AL-HP")
        self.assertEqual(tag["page_name"], "HP Drum · AL-HP")
        self.assertEqual(tag["source_ref"], "logic_diagrams/TripLens_Logic_Master_Current_V8.drawio#page=rule:AL-HP&cell=output:AL-HP:vppHPDrumLevelM")
        self.assertEqual(tag["verification_status"], "INDEXED_FROM_DRAWIO_XML")
        self.assertEqual(search_drawing_master(index, "HPBP")[0]["cell_id"], "operation:AL-HP")
        self.assertEqual(search_drawing_master(index, "HP.DRUM.LEVEL")[0]["cell_id"], "output:AL-HP:vppHPDrumLevelM")

    def test_published_index_is_hash_bound_to_existing_drawio(self):
        root = Path(__file__).resolve().parents[1]
        index_path = root / "logic_diagrams" / "drawing_master_index.json"
        drawio_path = root / "logic_diagrams" / "TripLens_Logic_Master_Current_V8.drawio"
        if not index_path.exists() or not drawio_path.exists():
            self.skipTest("published Drawing Master snapshot is not present")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(index["source_sha256"], hashlib.sha256(drawio_path.read_bytes()).hexdigest())
        self.assertGreater(index["counts"]["pages"], 0)
        self.assertGreater(index["counts"]["cells"], 0)
        self.assertTrue(all("#page=" in row["source_ref"] and "&cell=" in row["source_ref"] for row in index["entries"]))

    def test_mobile_drawing_master_tab_wraps_for_touch(self):
        viewer = Path(__file__).resolve().parents[1] / "scripts" / "logic_assets" / "viewer.html"
        source = viewer.read_text(encoding="utf-8")
        self.assertIn(".tabs{display:flex;flex-wrap:wrap", source)
        self.assertIn("#tab-drawings{flex-basis:100%}", source)


if __name__ == "__main__":
    unittest.main()
