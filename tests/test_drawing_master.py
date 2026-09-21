"""Drawing Master indexes existing draw.io cells without changing the source XML."""
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


if __name__ == "__main__":
    unittest.main()
