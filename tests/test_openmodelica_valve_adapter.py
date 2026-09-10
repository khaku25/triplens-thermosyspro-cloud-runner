from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_fmu_valve_controls import MARKER, POINTS, patch_model as patch_fmu  # noqa: E402
from patch_turbine_bypass_model import patch_model as patch_bypass  # noqa: E402
from tests.test_turbine_bypass_patch import UPSTREAM_STUB  # noqa: E402

ADDITIONAL_NATIVE_CONNECTIONS = """  connect(regulation_Niveau_HP.SortieReelle1, vanne_alimentationHP.Ouv);
  connect(constante_vanne_vapeurHP.y, vanne_vapeurHP.Ouv);
  connect(regulation_Niveau_MP.SortieReelle1, vanne_alimentationMP.Ouv);
  connect(constante_vanne_vapeurMP.y, vanne_vapeurMP.Ouv);
  connect(vanne_alimentationBP.Ouv, constante_vanne_vapeurBP.y);
  connect(Vanne_alimentationMPHP.Ouv, constante_ballonBP.y);
  connect(regulation_Niveau_Condenseur.SortieReelle1, vanne_extraction.Ouv);
  connect(arretPomesMp1.y, Vanne_alimentationMPHP1.Ouv);
  connect(arretPomesHP1.y, Vanne_alimentationMPHP2.Ouv);
"""
FULL_UPSTREAM_STUB = UPSTREAM_STUB.replace(
    "end CombinedCycle_TripTAC;",
    ADDITIONAL_NATIVE_CONNECTIONS + "end CombinedCycle_TripTAC;",
)


class OpenModelicaValveAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patched = patch_fmu(patch_bypass(FULL_UPSTREAM_STUB))

    def test_all_twelve_native_valves_are_singly_driven(self):
        self.assertEqual(len(POINTS), 12)
        self.assertIn(MARKER, self.patched)
        for point in POINTS:
            assignment = f"{point.object_name}.Ouv.signal = fmuVlv{point.key}Fb"
            self.assertEqual(self.patched.count(assignment), 1, point.key)
            prefix = f"fmuVlv{point.key}"
            self.assertIn(f"{prefix}Cv = {point.object_name}.Cv", self.patched)
            self.assertIn(
                f"{prefix}MassFlow = 3.6*{point.object_name}.Q",
                self.patched,
            )
            self.assertIn(
                f"{prefix}Dp = {point.object_name}.deltaP",
                self.patched,
            )
        self.assertIn(
            "when {initial(), sample(0.01, 0.01)} then",
            self.patched,
        )
            if point.original_connect:
                self.assertNotIn(f"connect({point.original_connect})", self.patched)

    def test_fmi_inputs_exist_for_every_valve(self):
        for point in POINTS:
            prefix = f"fmuVlv{point.key}"
            self.assertIn(
                f"input Boolean {prefix}ModeAuto(start=true) = true",
                self.patched,
            )
            self.assertIn(
                f"input Real {prefix}ManualCmd(min=0, max=1, "
                f"start={point.initial:g}) = {point.initial:g}",
                self.patched,
            )
            self.assertIn(
                f"input Boolean {prefix}FaultEnable(start=false) = false",
                self.patched,
            )
            self.assertIn(
                f"input Real {prefix}FaultValue(min=0, max=1, start=0) = 0",
                self.patched,
            )

    def test_fault_override_does_not_rewrite_selected_command(self):
        for point in POINTS:
            prefix = f"fmuVlv{point.key}"
            self.assertIn(
                f"{prefix}Cmd = if {prefix}ModeAuto then {prefix}AutoCmd",
                self.patched,
            )
            self.assertIn(
                f"{prefix}Target = if {prefix}FaultEnable then "
                f"noEvent(min(1, max(0, {prefix}FaultValue))) else {prefix}Cmd",
                self.patched,
            )
            self.assertIn(f"{prefix}Deviation = {prefix}Cmd - {prefix}Fb", self.patched)

    def test_existing_trip_actuator_states_take_adapter_targets(self):
        self.assertIn(
            "der(vppHPAdmissionPos) =\n"
            "    (fmuVlvHPTurbAdmTarget - vppHPAdmissionPos)",
            self.patched,
        )
        self.assertIn(
            "der(vppIPAdmissionPos) =\n"
            "    (fmuVlvIPTurbAdmTarget - vppIPAdmissionPos)",
            self.patched,
        )
        self.assertIn(
            "der(vppLPDrumAdmissionMultiplier) =\n"
            "    (fmuVlvLPSteamTarget - vppLPDrumAdmissionMultiplier)",
            self.patched,
        )
        self.assertIn(
            "Real vppLPDrumAdmissionMultiplier(start=0.8",
            self.patched,
        )

    def test_previous_direct_admission_equations_are_removed(self):
        self.assertNotIn(
            "vanne_entree_TurbineHP.Ouv.signal = vppHPAdmissionPos",
            self.patched,
        )
        self.assertNotIn(
            "vanne_entree_TurbineMP.Ouv.signal = vppIPAdmissionPos",
            self.patched,
        )
        self.assertNotIn(
            "regulation_Niveau_BP.SortieReelle1.signal*"
            "vppLPDrumAdmissionMultiplier",
            self.patched,
        )

    def test_patch_fails_closed_when_reapplied_or_out_of_order(self):
        with self.assertRaisesRegex(ValueError, "already applied"):
            patch_fmu(self.patched)
        with self.assertRaisesRegex(ValueError, "must be applied first"):
            patch_fmu(UPSTREAM_STUB)


if __name__ == "__main__":
    unittest.main()
