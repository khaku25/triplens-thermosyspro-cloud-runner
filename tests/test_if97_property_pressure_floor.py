from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_if97_property_pressure_floor import MARKER, TARGETS, patch_text  # noqa: E402


def _fixture() -> str:
    blocks = []
    for name, token in TARGETS.items():
        blocks.append(
            f'''    function {name}
      input Modelica.SIunits.AbsolutePressure {token} "Pressure";
      output Real result;
    algorithm
      result := {token};
      result := helper({token}={token});
    annotation (smoothOrder=1);
    end {name};
'''
        )
    return "within ThermoSysPro.Properties.WaterSteam.IF97;\npackage IF97_packages\n" + "".join(blocks) + "end IF97_packages;\n"


class IF97PatchTests(unittest.TestCase):
    def test_guards_all_direct_pressure_functions(self) -> None:
        patched = patch_text(_fixture())
        self.assertEqual(patched.count(MARKER), len(TARGETS))
        self.assertEqual(patched.count("max(P, 1000.0)"), 2)
        self.assertEqual(patched.count("max(p, 1000.0)"), 8)
        self.assertIn("result := Pthermo;", patched)
        self.assertIn("result := pthermo;", patched)
        self.assertEqual(patch_text(patched), patched)

    def test_rejects_missing_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing target functions"):
            patch_text(_fixture().replace("function Water_Ph_der", "function Missing_Ph_der"))


if __name__ == "__main__":
    unittest.main()

