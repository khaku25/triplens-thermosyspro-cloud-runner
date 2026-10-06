from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_tsp42_if97_domain_guard import (  # noqa: E402
    DIRECT_WATER_PH_CALL,
    DIRECT_WATER_PH_DER_CALL,
    HELPER_MARKER,
    MARKER,
    PH_DER_SOURCE,
    SAFE_WATER_PH_CALL,
    SAFE_WATER_PH_DER_CALL,
    patch_fluid_directory,
    patch_helper_text,
    patch_text,
)


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

    def test_property_helpers_route_direct_if97_calls_through_guard(self) -> None:
        helper = f'''within ThermoSysPro.Properties.Fluid;
function Temperature_Ph
  input Units.SI.AbsolutePressure P;
  input Units.SI.SpecificEnthalpy h;
  input Integer mode;
  output Units.SI.Temperature T;
protected
  ThermoSysPro.Properties.WaterSteam.Common.ThermoProperties_ph pro;
algorithm
  pro := {DIRECT_WATER_PH_CALL};
  T := pro.T;
end Temperature_Ph;
'''
        patched, calls = patch_helper_text(helper)

        self.assertEqual(calls, 1)
        self.assertIn(HELPER_MARKER, patched)
        self.assertIn(SAFE_WATER_PH_CALL, patched)
        self.assertNotIn(DIRECT_WATER_PH_CALL, patched)
        with self.assertRaisesRegex(ValueError, "already applied"):
            patch_helper_text(patched)

    def test_helper_patch_ignores_commented_calls(self) -> None:
        commented = (
            "within ThermoSysPro.Properties.Fluid;\n"
            "// " + DIRECT_WATER_PH_CALL + "\n"
        )
        patched, calls = patch_helper_text(commented)

        self.assertEqual(calls, 0)
        self.assertEqual(patched, commented)

    def test_directory_patch_updates_ph_and_every_helper_call(self) -> None:
        helper = f'''within ThermoSysPro.Properties.Fluid;
function Density_Ph
  input Units.SI.AbsolutePressure P;
  input Units.SI.SpecificEnthalpy h;
  input Integer mode;
  output Units.SI.Density rho;
protected
  ThermoSysPro.Properties.WaterSteam.Common.ThermoProperties_ph pro;
algorithm
  pro := {DIRECT_WATER_PH_CALL};
  rho := pro.d;
end Density_Ph;
'''
        derivative_helper = f'''within ThermoSysPro.Properties.Fluid;
function derDensity_derP_derh
  input Units.SI.AbsolutePressure P;
  input Units.SI.SpecificEnthalpy h;
  input Integer mode;
  input Real der_P;
  input Real der_h;
  output ThermoSysPro.Properties.WaterSteam.Common.ThermoProperties_ph der_pro;
protected
algorithm
  der_pro := {DIRECT_WATER_PH_DER_CALL};
end derDensity_derP_derh;
'''
        with tempfile.TemporaryDirectory() as temp:
            fluid = Path(temp) / "ThermoSysPro" / "Properties" / "Fluid"
            fluid.mkdir(parents=True)
            (fluid / "Ph.mo").write_text(UPSTREAM, encoding="utf-8")
            (fluid / "Density_Ph.mo").write_text(helper, encoding="utf-8")
            (fluid / "derDensity_derP_derh.mo").write_text(
                derivative_helper, encoding="utf-8"
            )

            patches = patch_fluid_directory(fluid)

            self.assertEqual(
                patches,
                [("Density_Ph.mo", 1), ("derDensity_derP_derh.mo", 1)],
            )
            self.assertIn(MARKER, (fluid / "Ph.mo").read_text(encoding="utf-8"))
            patched_helper = (fluid / "Density_Ph.mo").read_text(encoding="utf-8")
            self.assertIn(SAFE_WATER_PH_CALL, patched_helper)
            self.assertNotIn(DIRECT_WATER_PH_CALL, patched_helper)
            der_patched = (fluid / "derDensity_derP_derh.mo").read_text(encoding="utf-8")
            self.assertIn(SAFE_WATER_PH_DER_CALL, der_patched)
            self.assertNotIn(DIRECT_WATER_PH_DER_CALL, der_patched)
            self.assertTrue(PH_DER_SOURCE.startswith("within ThermoSysPro.Properties.Fluid;"))
            self.assertIn("p_der = 0, h_der = 0", PH_DER_SOURCE)
            self.assertTrue((fluid / "Ph_der.mo").is_file())
            with self.assertRaisesRegex(ValueError, "already applied"):
                patch_fluid_directory(fluid)

    def test_rejects_unrecognized_or_already_patched_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "Water_Ph anchor"):
            patch_text(UPSTREAM.replace("Water_Ph(P, h, mode)", "Water_Ph(P, h, 1)"))

        with self.assertRaisesRegex(ValueError, "already applied"):
            patch_text(UPSTREAM.replace("end Ph;", f"// {MARKER}\nend Ph;"))


if __name__ == "__main__":
    unittest.main()
