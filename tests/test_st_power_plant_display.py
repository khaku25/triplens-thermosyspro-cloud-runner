import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANT_DRAWING = (ROOT / "apps/web/components/PlantDrawingMaster.js").read_text(encoding="utf-8")


class STPowerPlantDisplayTest(unittest.TestCase):
    def test_plant_view_does_not_emphasize_st_power_as_a_separate_card(self):
        self.assertNotIn("ST_POWER_DISPLAY", PLANT_DRAWING)
        self.assertNotIn("ST POWER", PLANT_DRAWING)
        self.assertNotIn("52ST 차단기 위치", PLANT_DRAWING)
        self.assertIn("<ProcessViewCanvas", PLANT_DRAWING)

    def test_plant_view_does_not_invent_a_numeric_value_or_runtime_disclaimer(self):
        self.assertNotIn("263.315", PLANT_DRAWING)
        self.assertNotIn("실시간 아님", PLANT_DRAWING)


if __name__ == "__main__":
    unittest.main()
