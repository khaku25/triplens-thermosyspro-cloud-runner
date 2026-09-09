from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_stodola_turbine import MARKER, patch_text  # noqa: E402


NATIVE = '''within ThermoSysPro.WaterSteam.Machines;
model StodolaTurbine
protected
  parameter Real pcrit=1;
equation
  if noEvent((Pe > pcrit) or (Te > Tcrit)) then
    Q = sqrt((Pe^2 - Ps^2)/(Cst*Te));
  else
    Q = sqrt((Pe^2 - Ps^2)/(Cst*Te*proe.x));
  end if;
end StodolaTurbine;
'''


class StodolaPatchTests(unittest.TestCase):
    def test_regularizes_only_when_component_parameter_is_enabled(self) -> None:
        patched = patch_text(NATIVE)

        self.assertEqual(patched.count(MARKER), 1)
        self.assertIn("parameter Boolean regularizePressureCrossover=false", patched)
        self.assertIn("function regularizedPositivePressureSquare", patched)
        self.assertIn("if regularizePressureCrossover then", patched)
        self.assertIn("max(proe.x, 1e-6)", patched)
        self.assertIn("elseif noEvent", patched)
        self.assertEqual(patch_text(patched), patched)

    def test_rejects_unrecognized_upstream_equations(self) -> None:
        with self.assertRaisesRegex(ValueError, "ellipse equations"):
            patch_text(NATIVE.replace("Pe^2 - Ps^2", "Pe^2 + Ps^2", 1))


if __name__ == "__main__":
    unittest.main()
