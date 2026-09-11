from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_fmu_valve_controls import patch_model as patch_legacy_fmu  # noqa: E402
from patch_native_opcua_valve_controls import (  # noqa: E402
    FORBIDDEN_LEGACY_MARKER,
    MARKER,
    POINTS,
    CAUSAL_PHYSICAL_POINT_IDS,
    patch_model as patch_native,
)
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


class NativeOpenModelicaValveAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bypass = patch_bypass(FULL_UPSTREAM_STUB)
        cls.patched = patch_native(cls.bypass)
        with (ROOT / "data" / "opcua_native_valve_nodes_v1.csv").open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            cls.nodes = list(csv.DictReader(stream))

    def test_all_144_contract_browse_names_exist_in_model(self) -> None:
        self.assertEqual(len(self.nodes), 144)
        for row in self.nodes:
            self.assertIn(row["opcua_browse_name"], self.patched)

    def test_all_twelve_native_valves_are_singly_driven(self) -> None:
        self.assertEqual(len(POINTS), 12)
        self.assertIn(MARKER, self.patched)
        for point in POINTS:
            stem = f"vppVlv{point.suffix}"
            self.assertEqual(
                self.patched.count(f"{point.object_name}.Ouv.signal = {stem}Fb"),
                1,
                point.control_point_id,
            )
            self.assertIn(f"{stem}MassFlowTH = 3.6*{point.object_name}.Q", self.patched)
            self.assertIn(
                f"output Real {stem}Cv(start=0, fixed=true, "
                "stateSelect=StateSelect.always)",
                self.patched,
            )
            self.assertIn(f"der({stem}Cv) = ({point.object_name}.Cv - {stem}Cv)/", self.patched)
            self.assertNotIn(f"\n  {stem}Cv = ", self.patched)
            self.assertIn(f"\n  {stem}MassFlowTH = ", self.patched)
            self.assertIn(
                f"output Real {stem}DPPa(start=0, fixed=true, "
                "stateSelect=StateSelect.always",
                self.patched,
            )
            self.assertIn(f"der({stem}DPPa) = (", self.patched)
            self.assertNotIn(
                f"\n  {stem}DPPa = ",
                self.patched,
            )
            if point.original_connect:
                self.assertNotIn(f"connect({point.original_connect})", self.patched)

    def test_pressure_drop_telemetry_is_outside_continuous_initialization_dae(self) -> None:
        self.assertNotIn("when sample(", self.patched)
        self.assertEqual(self.patched.count("der(vppVlv"), 31)
        self.assertNotIn("output discrete Real", self.patched)

    def test_only_traced_physical_valve_positions_are_causally_tracked(self) -> None:
        expected_sampled = {
            "HP_STEAM_VLV",
            "IP_STEAM_VLV",
            "LP_FW_VLV",
            "LP_TO_HPIP_FW_VLV",
            "COND_EXTRACTION_VLV",
            "HP_FW_ISO_VLV",
            "IP_FW_ISO_VLV",
        }
        self.assertEqual(CAUSAL_PHYSICAL_POINT_IDS, expected_sampled)
        self.assertEqual(self.patched.count("when sample("), 0)
        for point in POINTS:
            stem = f"vppVlv{point.suffix}"
            self.assertIn(f"Real {stem}Target(min=0, max=1);", self.patched)
            self.assertIn(f"\n  {stem}Target = if", self.patched)
            if point.control_point_id in expected_sampled:
                self.assertIn(
                    f"Real {stem}Applied(start={point.initial:g}, fixed=true, "
                    "stateSelect=StateSelect.always, min=0, max=1)",
                    self.patched,
                )
                self.assertIn(
                    f"der({stem}Applied) = ({stem}Target - {stem}Applied)/",
                    self.patched,
                )
                self.assertIn(f"{stem}Fb = {stem}Applied;", self.patched)
            else:
                self.assertNotIn(f"{stem}Applied", self.patched)
        self.assertNotIn("discrete Real vppVlv", self.patched)

    def test_trip_admission_targets_remain_continuous(self) -> None:
        for suffix in ("HPTurbAdm", "IPTurbAdm", "LPSteam"):
            self.assertNotIn(f"vppVlv{suffix}Applied", self.patched)
            self.assertIn(f"Real vppVlv{suffix}Target", self.patched)

    def test_48_native_commands_are_top_level_opcua_inputs_not_dae_states(self) -> None:
        inputs = 0
        for point in POINTS:
            stem = f"vppVlv{point.suffix}"
            for suffix in (
                "ModeAutoNative",
                "ManualCmdNative",
                "FaultEnableNative",
                "FaultValueNative",
            ):
                name = f"{stem}{suffix}"
                self.assertIn(f"input Real {name}", self.patched)
                self.assertNotIn(f"der({name})", self.patched)
                inputs += 1
        self.assertEqual(inputs, 48)
        for line in self.patched.splitlines():
            if "input Real vppVlv" in line:
                self.assertNotIn("StateSelect.always", line)

    def test_fault_override_does_not_rewrite_selected_command(self) -> None:
        for point in POINTS:
            stem = f"vppVlv{point.suffix}"
            self.assertIn(
                f"{stem}Cmd = if {stem}ModeAutoNative >= 0.5 then {stem}AutoCmd",
                self.patched,
            )
            self.assertIn(
                f"{stem}Target = if {stem}FaultEnableNative >= 0.5 then "
                f"noEvent(min(1, max(0, {stem}FaultValueNative))) else {stem}Cmd",
                self.patched,
            )
            self.assertIn(f"{stem}Deviation = {stem}Cmd - {stem}Fb", self.patched)

    def test_trip_actuator_states_use_native_adapter_targets(self) -> None:
        self.assertIn(
            "der(vppHPAdmissionPos) =\n"
            "    (vppVlvHPTurbAdmTarget - vppHPAdmissionPos)",
            self.patched,
        )
        self.assertIn(
            "der(vppIPAdmissionPos) =\n"
            "    (vppVlvIPTurbAdmTarget - vppIPAdmissionPos)",
            self.patched,
        )
        self.assertIn(
            "der(vppLPDrumAdmissionMultiplier) =\n"
            "    (vppVlvLPSteamTarget - vppLPDrumAdmissionMultiplier)",
            self.patched,
        )

    def test_patch_fails_closed_when_reapplied_out_of_order_or_mixed_with_fmu(self) -> None:
        with self.assertRaisesRegex(ValueError, "already applied"):
            patch_native(self.patched)
        with self.assertRaisesRegex(ValueError, "must be applied first"):
            patch_native(UPSTREAM_STUB)
        legacy = patch_legacy_fmu(self.bypass)
        self.assertIn(FORBIDDEN_LEGACY_MARKER, legacy)
        with self.assertRaisesRegex(ValueError, "legacy FMU valve adapter conflicts"):
            patch_native(legacy)

    def test_native_adapter_introduces_no_fmu_or_simulink_names(self) -> None:
        added = self.patched.replace(self.bypass, "")
        self.assertNotIn("fmuVlv", self.patched)
        self.assertNotIn("Simulink", added)


if __name__ == "__main__":
    unittest.main()
