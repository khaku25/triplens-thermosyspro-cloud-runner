from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_fluid_ph_property_floor import MARKER, patch_text  # noqa: E402


NATIVE = '''within ThermoSysPro.Properties.Fluid;
function Ph
  input Modelica.SIunits.AbsolutePressure P "Pressure";
  input Modelica.SIunits.SpecificEnthalpy h "Specific enthalpy";
  input Integer mode = 0 "IF97 region - 0:automatic computation";
  input Integer fluid = 1 "Fluid number - 1: IF97 - 2: C3H3F5";

  output ThermoSysPro.Properties.WaterSteam.Common.ThermoProperties_ph pro
    "properties";
algorithm

  if (fluid == 1) then
    pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(P, h, mode);
  elseif (fluid == 2) then
    pro := C3H3F5.C3H3F5_Ph(P, h);
  else
    assert(false, "Prop.Ph : incorrect fluid number");
  end if;
end Ph;
'''


class FluidPhPatchTests(unittest.TestCase):
    def test_guards_both_fluid_property_paths(self) -> None:
        patched = patch_text(NATIVE)
        self.assertEqual(patched.count(MARKER), 1)
        self.assertIn("Pthermo := noEvent(max(P, 1000.0));", patched)
        self.assertIn("Water_Ph(Pthermo, h, mode)", patched)
        self.assertIn("C3H3F5_Ph(Pthermo, h)", patched)
        self.assertEqual(patch_text(patched), patched)

    def test_rejects_missing_call(self) -> None:
        with self.assertRaisesRegex(ValueError, "Water_Ph call"):
            patch_text(NATIVE.replace("Water_Ph(P, h, mode)", "Water_Ph(P, h, 1)"))


if __name__ == "__main__":
    unittest.main()

