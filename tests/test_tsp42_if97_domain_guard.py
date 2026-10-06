from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_tsp42_if97_domain_guard import MARKER, patch_text  # noqa: E402


UPSTREAM = '''within ThermoSysPro.Properties.Fluid;
function Ph
  input Units.SI.AbsolutePressure P "Pressure";
  input Units.SI.SpecificEnthalpy h "Specific enthalpy";
  input Integer mode = 0 "IF97 region - 0:automatic computation";
  input Integer fluid = 1 "Fluid number";
  output ThermoSysPro.Properties.WaterSteam.Common.ThermoProperties_ph pro annotation(
    Placement(transformation(extent = {{-80, 40}, {-40, 80}}, rotation = 0)));
algorithm
  if (fluid == 1) then
    pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(P, h, mode);
  elseif (fluid == 2) then
    pro := ThermoSysPro.Properties.C3H3F5.C3H3F5_Ph(P, h);
  elseif (fluid == 7) then
    pro := ThermoSysPro.Properties.WaterSteamSimple.SimpleWater.Water_Ph(P, h, mode);
  else
    assert(false, "Prop.Ph : incorrect fluid number");
  end if;
  annotation(smoothOrder = 2);
end Ph;
'''


class Tsp42IF97DomainGuardTests(unittest.TestCase):
    def test_only_out_of_domain_if97_inputs_are_guarded(self) -> None:
        patched = patch_text(UPSTREAM)

        self.assertEqual(patched.count(MARKER), 1)
        self.assertIn("min(max(P, 700)", patched)
        self.assertIn("hlowerofp1(pEval)", patched)
        self.assertIn("hupperofp5(pEval)", patched)
        self.assertIn("hupperofp2(pEval)", patched)
        self.assertIn("hUpper - 1", patched)
        self.assertIn("Water_Ph(pEval, hEval, 0)", patched)
        self.assertIn("(P <= 611.657)", patched)
        self.assertIn("(P > ThermoSysPro.Properties.WaterSteam.BaseIF97.data.PLIMIT1)", patched)
        self.assertIn("Water_Ph(P, h, mode)", patched)
        self.assertIn("elseif (fluid == 2) then", patched)
        self.assertIn("C3H3F5_Ph(P, h)", patched)
        self.assertIn("elseif (fluid == 7) then", patched)
        self.assertLess(patched.index("protected\n"), patched.index("algorithm\n"))
        self.assertEqual(patched.count("algorithm\n"), 1)

    def test_rejects_unrecognized_or_already_patched_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "Water_Ph anchor"):
            patch_text(UPSTREAM.replace("Water_Ph(P, h, mode)", "Water_Ph(P, h, 1)"))

        with self.assertRaisesRegex(ValueError, "already applied"):
            patch_text(UPSTREAM.replace("end Ph;", f"// {MARKER}\nend Ph;"))


if __name__ == "__main__":
    unittest.main()
