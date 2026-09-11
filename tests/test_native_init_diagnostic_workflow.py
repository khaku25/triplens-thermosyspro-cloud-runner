from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = ROOT / ".github/workflows/diagnose-native-opcua-init.yml"
PRODUCTION = ROOT / ".github/workflows/run-native-opcua-ecms.yml"


class NativeInitDiagnosticWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.diagnostic = DIAGNOSTIC.read_text(encoding="utf-8")
        self.production = PRODUCTION.read_text(encoding="utf-8")

    def test_exactly_two_parallel_boundary_probes(self) -> None:
        profiles = re.findall(r"^\s+- profile: ([a-z-]+)$", self.diagnostic, re.M)
        self.assertEqual(profiles, ["lp-only", "lp-with-all-nrvs"])
        self.assertIn("max-parallel: 2", self.diagnostic)
        self.assertIn("fail-fast: false", self.diagnostic)

    def test_profiles_apply_only_the_intended_optional_adapter(self) -> None:
        self.assertIn('apply_all_check_valves: "false"', self.diagnostic)
        self.assertIn('apply_all_check_valves: "true"', self.diagnostic)
        self.assertLess(
            self.diagnostic.index("scripts/patch_turbine_bypass_model.py"),
            self.diagnostic.index("scripts/patch_lp_fwp_opcua.py"),
        )
        self.assertLess(
            self.diagnostic.index("scripts/patch_lp_fwp_opcua.py"),
            self.diagnostic.index("scripts/patch_all_fwp_check_valves.py"),
        )
        self.assertNotIn("APPLY_NATIVE_VALVES", self.diagnostic)
        self.assertNotIn("APPLY_HP_IP", self.diagnostic)

    def test_probe_keeps_default_dassl_and_captures_failure_evidence(self) -> None:
        build_template = (ROOT / "modelica/build_native_opcua.mos.tpl").read_text(
            encoding="utf-8"
        )
        self.assertIn('method="dassl"', build_template)
        self.assertIn('INIT_STOP_TIME_S: "0.04"', self.diagnostic)
        self.assertIn("--intervals 10", self.diagnostic)
        self.assertIn("-lv=LOG_SUCCESS,LOG_NLS", self.diagnostic)
        self.assertIn("The initialization finished successfully", self.diagnostic)
        self.assertIn("build/TripLens_Native_OPCUA_info.json", self.diagnostic)
        self.assertIn("build/TripLens_Native_OPCUA_init.xml", self.diagnostic)
        for solver_override in (
            "-s=ida",
            "-nls=",
            "-nlsLS=",
            "-nlssMaxDensity=",
            "-iim=none",
        ):
            self.assertNotIn(solver_override, self.diagnostic)

    def test_production_workflow_has_no_temporary_probe(self) -> None:
        self.assertNotIn("lp-only", self.production)
        self.assertNotIn("lp-with-all-nrvs", self.production)


if __name__ == "__main__":
    unittest.main()
