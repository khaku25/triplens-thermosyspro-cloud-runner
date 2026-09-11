from __future__ import annotations

import csv
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "scripts" / "patch_hp_ip_fwp_opcua.py"
CONTRACT = ROOT / "data" / "opcua_hp_ip_fwp_nodes_v1.csv"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def patched_input() -> str:
    return '''within ThermoSysPro.Examples.CombinedCyclePowerPlant;
model CombinedCycle_TripTAC
  // TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V13
  // TRIPLENS_LP_FWP_OPCUA_ADAPTER_V1
  // TRIPLENS_ALL_FWP_CHECK_VALVES_OPCUA_V1
  parameter Real CstHP(fixed=false,start=7618660.65374636);
equation
  connect(PompeAlimHP.rpm_or_mpower, arretPomesHP.y);
  connect(PompeAlimMP.rpm_or_mpower, arretPomesMp.y);
  connect(PompeAlimHP.C2, vppHPFWPCheckValve.C1);
  connect(vppHPFWPCheckValve.C2, Vanne_alimentationMPHP1.C1);
  connect(PompeAlimMP.C2, vppIPFWPCheckValve.C1);
  connect(vppIPFWPCheckValve.C2, Vanne_alimentationMPHP2.C1);
  // TRIPLENS_NATIVE_OPCUA_BOUNDARY_INSERTION_POINT
end CombinedCycle_TripTAC;
'''


class HPIPFWPOPCUATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.patcher = load_module("patch_hp_ip_fwp_opcua", PATCHER)
        with CONTRACT.open(encoding="utf-8-sig", newline="") as stream:
            cls.nodes = list(csv.DictReader(stream))

    def test_patcher_replaces_only_native_speed_sources(self) -> None:
        patched = self.patcher.patch_model(patched_input())
        self.assertNotIn(
            "connect(PompeAlimHP.rpm_or_mpower, arretPomesHP.y);", patched
        )
        self.assertNotIn(
            "connect(PompeAlimMP.rpm_or_mpower, arretPomesMp.y);", patched
        )
        self.assertIn(
            "connect(vppHPFWPHydraulicSpeedCommand, PompeAlimHP.rpm_or_mpower);",
            patched,
        )
        self.assertIn(
            "connect(vppIPFWPHydraulicSpeedCommand, PompeAlimMP.rpm_or_mpower);",
            patched,
        )

    def test_run_and_breaker_are_independent_fail_closed_boundaries(self) -> None:
        patched = self.patcher.patch_model(patched_input())
        for name in (
            "vppFWPHPRunEnableNative",
            "vppVCBA01ClosedNative",
            "vppFWPIPRunEnableNative",
            "vppVCBB01ClosedNative",
        ):
            self.assertIn(f"input Real {name}", patched)
            self.assertNotIn(f"der({name})", patched)
        self.assertIn(
            "vppHPFWPMotorEnergized = vppFWPHPRunEnableNative >= 0.5 and\n"
            "    vppVCBA01ClosedNative >= 0.5;",
            patched,
        )
        self.assertIn(
            "vppIPFWPMotorEnergized = vppFWPIPRunEnableNative >= 0.5 and\n"
            "    vppVCBB01ClosedNative >= 0.5;",
            patched,
        )
        self.assertIn("vppHPFWPDrive.breakerClosed.signal", patched)
        self.assertIn("vppIPFWPDrive.breakerClosed.signal", patched)

    def test_existing_check_valve_patch_remains_sole_nrv_owner(self) -> None:
        patched = self.patcher.patch_model(patched_input())
        for token in (
            "connect(PompeAlimHP.C2, vppHPFWPCheckValve.C1);",
            "connect(vppHPFWPCheckValve.C2, Vanne_alimentationMPHP1.C1);",
            "connect(PompeAlimMP.C2, vppIPFWPCheckValve.C1);",
            "connect(vppIPFWPCheckValve.C2, Vanne_alimentationMPHP2.C1);",
        ):
            self.assertEqual(patched.count(token), 1)
        self.assertNotIn("SpringLoadedCheckValve vppHPFWPCheckValve", patched)
        self.assertNotIn("SpringLoadedCheckValve vppIPFWPCheckValve", patched)

    def test_patcher_rejects_partial_or_duplicate_application(self) -> None:
        missing_marker = patched_input().replace(
            "  // TRIPLENS_ALL_FWP_CHECK_VALVES_OPCUA_V1\n", ""
        )
        with self.assertRaisesRegex(ValueError, "required previous patch"):
            self.patcher.patch_model(missing_marker)
        once = self.patcher.patch_model(patched_input())
        with self.assertRaisesRegex(ValueError, "already applied"):
            self.patcher.patch_model(once)

    def test_contract_has_complete_symmetric_hp_ip_boundary(self) -> None:
        self.assertEqual(len(self.nodes), 22)
        self.assertEqual(len({row["canonical_tag"] for row in self.nodes}), 22)
        self.assertEqual(len({row["opcua_browse_name"] for row in self.nodes}), 22)
        for level, breaker in (("HP", "A01"), ("IP", "B01")):
            by_tag = {row["canonical_tag"]: row for row in self.nodes}
            self.assertEqual(by_tag[f"DCS.FWP-{level}.RUN_ENABLE"]["direction"], "WRITE")
            self.assertEqual(by_tag[f"ECMS.VCB-{breaker}.CLOSED"]["direction"], "WRITE")
            self.assertEqual(by_tag[f"TSP.FWP-{level}.SPEED_RPM"]["direction"], "READ")
            self.assertEqual(by_tag[f"TSP.FWP-{level}.MASS_FLOW"]["direction"], "READ")
            self.assertEqual(by_tag[f"TSP.FWP-{level}.MECH_POWER"]["direction"], "READ")

    def test_adapter_is_native_only_and_exports_solved_feedback(self) -> None:
        source = PATCHER.read_text(encoding="utf-8")
        forbidden = ("live_fmu_gateway", "fmi2", "Simulink")
        self.assertFalse(any(token in source for token in forbidden))
        for level, pump in (("HP", "PompeAlimHP"), ("IP", "PompeAlimMP")):
            self.assertIn(f"vpp{level}FWPDrive.pumpPower.signal = {pump}.Wm", source)
            self.assertIn(f"vpp{level}FWPMassFlowTH = 3.6*{pump}.Q", source)
            self.assertIn(f"vpp{level}FWPVolumeFlowM3S = {pump}.Qv", source)
            self.assertIn(f"vpp{level}FWPDeltaPPa = {pump}.deltaP", source)
            self.assertIn(f"vpp{level}FWPMechanicalPowerW = {pump}.Wm", source)


if __name__ == "__main__":
    unittest.main()
