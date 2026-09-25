import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANT_DRAWING = (ROOT / "apps/web/components/PlantDrawingMaster.js").read_text(encoding="utf-8")


class STPowerPlantDisplayTest(unittest.TestCase):
    def test_plant_view_renders_exact_st_power_identity_and_logic_link(self):
        self.assertIn("ST_POWER_DISPLAY", PLANT_DRAWING)
        self.assertIn("ST_POWER_DISPLAY.label", PLANT_DRAWING)
        self.assertIn("ST_POWER_DISPLAY.tag", PLANT_DRAWING)
        self.assertIn("ST_POWER_DISPLAY.unit", PLANT_DRAWING)
        self.assertIn("href={ST_POWER_DISPLAY.href}", PLANT_DRAWING)
        self.assertIn("로직 연결 보기", PLANT_DRAWING)

    def test_plant_view_does_not_invent_a_numeric_value_or_runtime_disclaimer(self):
        self.assertNotIn("263.315", PLANT_DRAWING)
        self.assertNotIn("실시간 아님", PLANT_DRAWING)


if __name__ == "__main__":
    unittest.main()
