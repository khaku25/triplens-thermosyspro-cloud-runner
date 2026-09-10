from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from native_ecms_opcua_client import PROTOCOL, SIGNALS, validate  # noqa: E402


class NativeOPCUAContractTests(unittest.TestCase):
    def test_owner_split_and_physical_inventory(self) -> None:
        self.assertEqual(PROTOCOL, "TRIPLENS-NATIVE-OPCUA/1")
        self.assertGreaterEqual(len(SIGNALS), 24)
        self.assertTrue(all(s.owner == "DCS1" for s in SIGNALS if "turbine" in s.field))
        self.assertTrue(all(s.owner == "DCS2" for s in SIGNALS if "drum" in s.field))

    def test_validator_requires_command_readback_and_native_response(self) -> None:
        def row(t: float, command: int, trip: int, hp_adm: float, hp_bp: float):
            values = {s.field: 1.0 + t for s in SIGNALS}
            values.update({
                "time_s": t,
                "gt_trip_command_readback": command,
                "gt_trip_latch": trip,
                "hp_admission_position_pu": hp_adm,
                "hp_bypass_position_pu": hp_bp,
            })
            return values
        report = validate([
            row(0.10, 0, 0, 0.8, 0.0),
            row(0.50, 1, 1, 0.1, 0.9),
        ], 0.25)
        self.assertEqual(report["status"], "PASS")
        bad = validate([
            row(0.10, 0, 0, 0.8, 0.0),
            row(0.50, 0, 0, 0.8, 0.0),
        ], 0.25)
        self.assertEqual(bad["status"], "FAIL")

    def test_native_build_uses_official_opcua_step_server(self) -> None:
        workflow = (ROOT / ".github/workflows/run-native-opcua-ecms.yml").read_text(encoding="utf-8")
        self.assertIn("-embeddedServer=opc-ua", workflow)
        self.assertIn("-embeddedServerPort=4841", workflow)
        self.assertIn("--network host", workflow)
        self.assertIn('LIVE_STEP_SIZE_S: "0.01"', workflow)
        self.assertIn('LIVE_STOP_TIME_S: "2"', workflow)
        self.assertNotIn("live_fmu_gateway.py", workflow)

    def test_client_uses_stable_openmodelica_control_node_ids(self) -> None:
        source = (ROOT / "scripts/native_ecms_opcua_client.py").read_text(encoding="utf-8")
        self.assertIn("ua.NodeId(10000, 0)", source)
        self.assertIn("ua.NodeId(10004, 0)", source)
        self.assertIn("wait_for_model_nodes", source)

    def test_external_trip_is_retained_as_a_native_input(self) -> None:
        patch = (ROOT / "scripts/patch_turbine_bypass_model.py").read_text(encoding="utf-8")
        self.assertIn("input Boolean vppExternalTripCommand(start=false) = false", patch)
        self.assertIn("Modelica.Blocks.Continuous.Integrator vppExternalTripCommandRegister", patch)
        self.assertIn("y(stateSelect=StateSelect.always)", patch)
        self.assertIn("vppExternalTripCommandRegister.u = Modelica.Constants.eps*sin(time)", patch)
        client = (ROOT / "scripts/native_ecms_opcua_client.py").read_text(encoding="utf-8")
        self.assertIn('command_name = "vppExternalTripCommandRegister.y"', client)
        self.assertIn("ua.VariantType.Double", client)


if __name__ == "__main__":
    unittest.main()
