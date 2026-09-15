from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_pressure_loss_property_floor import (  # noqa: E402
    DENSITY_MARKER,
    MARKER,
    patch_text,
)


def _fixture() -> str:
    return '''within ThermoSysPro.WaterSteam.PressureLosses;
model PipePressureLoss
  parameter Modelica.SIunits.MassFlowRate Qeps=1.e-3
    "Small mass flow for continuous flow reversal";
public
  Modelica.SIunits.Density rho(start=998);
  Modelica.SIunits.AbsolutePressure Pm(start=1.e5);
equation
  pro = ThermoSysPro.Properties.Fluid.Ph(Pm, h, mode, fluid);
  if (p_rho > 0) then
    rho = p_rho;
  else
    rho = pro.d;
  end if;
end PipePressureLoss;
'''


class PressureLossPatchTests(unittest.TestCase):
    def test_pipe_floor_guards_only_invalid_newton_density(self) -> None:
        patched = patch_text(_fixture(), "PipePressureLoss")
        self.assertIn(MARKER, patched)
        self.assertIn(DENSITY_MARKER, patched)
        self.assertIn("densityFloor=0.1", patched)
        self.assertIn("rho = noEvent(max(densityFloor, pro.d));", patched)
        self.assertIn("rho = p_rho;", patched)
        self.assertEqual(patch_text(patched, "PipePressureLoss"), patched)


if __name__ == "__main__":
    unittest.main()
