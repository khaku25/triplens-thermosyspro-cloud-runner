from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/run-native-opcua-ecms.yml"


class NativeWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_physical_patch_order_matches_adapter_preconditions(self) -> None:
        patch_step = self.workflow.split(
            "      - name: Render and pin the physical plant", 1
        )[1].split("      - name: Install pinned Modelica dependency", 1)[0]
        scripts = (
            "scripts/patch_turbine_bypass_model.py",
            "scripts/patch_native_opcua_valve_controls.py",
            "scripts/patch_lp_fwp_opcua.py",
            "scripts/patch_all_fwp_check_valves.py",
            "scripts/patch_hp_ip_fwp_opcua.py",
        )
        offsets = [patch_step.index(script) for script in scripts]
        self.assertEqual(offsets, sorted(offsets))

    def test_init_xml_gate_is_generated_from_exact_csv_contracts(self) -> None:
        for contract in (
            "data/opcua_native_valve_nodes_v1.csv",
            "data/opcua_hp_ip_fwp_nodes_v1.csv",
            "data/opcua_lp_bfp_nodes_v1.csv",
        ):
            self.assertIn(contract, self.workflow)
        self.assertIn("row count mismatch: expected", self.workflow)
        self.assertIn("vppExternalSTTripCommandNative", self.workflow)
        self.assertIn("contracted OPC UA variables", self.workflow)

    def test_lp_proof_keeps_gt_plus_30_second_terminal_condition(self) -> None:
        self.assertIn('LIVE_POST_GT_TRIP_S: "30"', self.workflow)
        self.assertIn('--post-gt-trip-seconds "$LIVE_POST_GT_TRIP_S"', self.workflow)
        self.assertIn("GT-Trip observation", self.workflow)

    def test_native_runtime_keeps_proven_default_dassl_solver(self) -> None:
        # Valve pressure telemetry is sampled outside the continuous DAE, so
        # the native proof can retain the validated default DASSL runtime.
        self.assertNotIn("-nlssMaxDensity=0", self.workflow)
        self.assertNotIn("-s=ida", self.workflow)
        self.assertNotIn("-iim=none", self.workflow)


if __name__ == "__main__":
    unittest.main()
