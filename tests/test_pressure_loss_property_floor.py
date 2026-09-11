from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_pressure_loss_property_floor import MARKER, patch_text  # noqa: E402


def fixture(name: str) -> str:
    return f'''model {name}
protected
  parameter Modelica.SIunits.MassFlowRate Qeps=1.e-3
    "Small mass flow for continuous flow reversal";
public
  Modelica.SIunits.AbsolutePressure Pm(start=1.e5) "Average pressure";
  Modelica.SIunits.SpecificEnthalpy h;
equation
  Pm = (C1.P + C2.P)/2;
  pro = ThermoSysPro.Properties.Fluid.Ph(Pm, h, mode, fluid);
end {name};
'''


class PressureLossPropertyFloorTests(unittest.TestCase):
    def test_both_pressure_loss_components_keep_physics_and_guard_properties(self) -> None:
        for name in ("ControlValve", "PipePressureLoss"):
            patched = patch_text(fixture(name), name)
            self.assertIn(MARKER, patched)
            self.assertIn("Pm = (C1.P + C2.P)/2;", patched)
            self.assertIn("propertyPressureFloor=611.657", patched)
            self.assertIn(
                "Pthermo = noEvent(max(propertyPressureFloor, Pm));", patched
            )
            self.assertIn(
                "Fluid.Ph(Pthermo, h, mode, fluid)", patched
            )
            self.assertNotIn("Fluid.Ph(Pm, h, mode, fluid)", patched)

    def test_duplicate_or_changed_upstream_source_fails_closed(self) -> None:
        patched = patch_text(fixture("ControlValve"), "ControlValve")
        with self.assertRaisesRegex(ValueError, "already applied"):
            patch_text(patched, "ControlValve")
        with self.assertRaisesRegex(ValueError, "Fluid.Ph call"):
            patch_text(
                fixture("ControlValve").replace("Fluid.Ph(Pm", "Fluid.Ph(C1.P"),
                "ControlValve",
            )


if __name__ == "__main__":
    unittest.main()
