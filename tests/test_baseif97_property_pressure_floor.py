from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_baseif97_property_pressure_floor import (  # noqa: E402
    FUNCTIONS,
    MARKER,
    patch_text,
)


def _fixture() -> str:
    blocks = []
    for name, basic in (("boilingcurve_p", "g1"), ("dewcurve_p", "g2")):
        blocks.append(
            f'''    function {name}
      input Modelica.SIunits.Pressure p "pressure";
      output Real bpro;
    protected
      Real pv "partial derivative of p w.r.t v";
      Modelica.SIunits.Pressure plim=min(p, data.PCRIT - 1e-7);
    algorithm
      bpro.R := data.RH2O;
      bpro.T := Basic.tsat(plim);
      g := Basic.{basic}(p, bpro.T);
      bpro.d := p/(bpro.R*bpro.T*g.pi*g.gpi);
      bpro.h := if p > plim then 1 else 0;
      bpro.vt := bpro.R/p*(g.pi*g.gpi);
      bpro.vp := bpro.R*bpro.T/(p*p)*g.pi*g.gpipi;
      bpro.pt := -p/bpro.T;
    end {name};
'''
        )
    return "within ThermoSysPro.Properties.WaterSteam;\npackage BaseIF97\n" + "".join(blocks) + "end BaseIF97;\n"


class BaseIF97PatchTests(unittest.TestCase):
    def test_guards_saturation_boundaries(self) -> None:
        patched = patch_text(_fixture())
        self.assertEqual(patched.count(MARKER), len(FUNCTIONS))
        self.assertEqual(patched.count("max(p, 1000.0)"), 4)
        self.assertIn("Basic.g1(pthermo", patched)
        self.assertIn("Basic.g2(pthermo", patched)
        self.assertIn("bpro.R/pthermo", patched)
        self.assertIn("pthermo*pthermo", patched)
        self.assertNotIn("Basic.g1(p,", patched)
        self.assertNotIn("Basic.g2(p,", patched)
        self.assertEqual(patch_text(patched), patched)


if __name__ == "__main__":
    unittest.main()
