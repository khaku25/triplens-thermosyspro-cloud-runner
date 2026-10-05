from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_tsp42_pipe_pressure_floor import MARKER, patch_text  # noqa: E402


UPSTREAM = '''within ThermoSysPro.WaterSteam.PressureLosses;
model PipePressureLoss "Pipe generic pressure loss"
  Units.SI.AbsolutePressure Pm(start = 1.e5) "Average fluid pressure";
  Units.SI.SpecificEnthalpy h(start = 100000) "Fluid specific enthalpy";
protected
  constant Units.SI.Acceleration g = Modelica.Constants.g_n "Gravity constant";
equation
  C1.P - C2.P = deltaP;
  deltaP = deltaPf + deltaPg;
  Pm = (C1.P + C2.P)/2;
  pro = ThermoSysPro.Properties.Fluid.Ph(Pm, h, mode, fluid);
end PipePressureLoss;
'''


class Tsp42PipePressureFloorTests(unittest.TestCase):
    def test_bounds_only_if97_property_pressure_and_preserves_hydraulics(self) -> None:
        patched = patch_text(UPSTREAM)

        self.assertEqual(patched.count(MARKER), 1)
        floor = re.search(
            r"propertyPressureFloor\s*=\s*([0-9.eE+-]+)", patched
        )
        self.assertIsNotNone(floor)
        self.assertGreater(float(floor.group(1)), 611.657)
        self.assertNotIn("Pthermo", patched)
        self.assertIn(
            "pro = ThermoSysPro.Properties.Fluid.Ph("
            "noEvent(max(propertyPressureFloor, Pm)), h, mode, fluid);",
            patched,
        )
        self.assertIn("Pm = (C1.P + C2.P)/2;", patched)
        self.assertIn("C1.P - C2.P = deltaP;", patched)
        self.assertIn("deltaP = deltaPf + deltaPg;", patched)
        self.assertNotIn("Fluid.Ph(Pm, h, mode, fluid)", patched)

    def test_rejects_unrecognized_or_already_patched_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "Fluid.Ph anchor"):
            patch_text(UPSTREAM.replace("Fluid.Ph(Pm, h, mode, fluid)", "Fluid.Ph(Pm, h, mode, 3)"))

        with self.assertRaisesRegex(ValueError, "already applied"):
            patch_text(UPSTREAM.replace("end PipePressureLoss;", f"// {MARKER}\nend PipePressureLoss;"))


if __name__ == "__main__":
    unittest.main()
