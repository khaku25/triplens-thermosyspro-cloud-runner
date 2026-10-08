from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_tsp42_specific_enthalpy_nominal import ALIAS_PATCH, patch_text  # noqa: E402


UPSTREAM = '''within ThermoSysPro.Units;
package SI
  type SpecificEnergy = Real(final quantity = "SpecificEnergy", final unit = "J/kg");
  type SpecificEnthalpy = SpecificEnergy;
  type SpecificInternalEnergy = SpecificEnergy;
end SI;
'''


class SpecificEnthalpyNominalTests(unittest.TestCase):
    def test_scales_only_specific_enthalpy_to_mj_per_kg(self) -> None:
        patched = patch_text(UPSTREAM)

        self.assertEqual(patched.count(ALIAS_PATCH), 1)
        self.assertIn("type SpecificEnergy = Real(", patched)
        self.assertIn("type SpecificInternalEnergy = SpecificEnergy;", patched)
        self.assertIn("type SpecificEnthalpy = SpecificEnergy(nominal = 1e6);", patched)

    def test_rejects_unrecognized_or_already_patched_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "SpecificEnthalpy alias"):
            patch_text(UPSTREAM.replace("type SpecificEnthalpy = SpecificEnergy;", "type SpecificEnthalpy = Real;"))
        with self.assertRaisesRegex(ValueError, "already applied"):
            patch_text(UPSTREAM.replace("type SpecificEnthalpy = SpecificEnergy;", ALIAS_PATCH))
        mixed = UPSTREAM.replace(
            "type SpecificEnthalpy = SpecificEnergy;",
            "type SpecificEnthalpy = SpecificEnergy;\n  " + ALIAS_PATCH,
        )
        with self.assertRaisesRegex(ValueError, "must occur exactly once"):
            patch_text(mixed)


if __name__ == "__main__":
    unittest.main()
