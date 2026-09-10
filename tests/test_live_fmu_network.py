from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from live_protocol import (  # noqa: E402
    COMMAND_INPUT,
    LIVE_SIGNALS,
    PROTOCOL,
    encode_frame,
)


class LiveFMUNetworkTests(unittest.TestCase):
    def test_wire_contract_is_stable_and_has_only_physical_outputs(self) -> None:
        fields = [item[0] for item in LIVE_SIGNALS]
        variables = [item[1] for item in LIVE_SIGNALS]
        self.assertEqual(len(fields), 31)
        self.assertEqual(len(fields), len(set(fields)))
        self.assertEqual(len(variables), len(set(variables)))
        self.assertEqual(COMMAND_INPUT, "vppExternalTripCommand")
        self.assertTrue(all(name.startswith("vpp") for name in variables))
        self.assertIn("hp_drum_level_m", fields)
        self.assertIn("hp_bypass_steam_flow_t_h", fields)

    def test_json_line_encoding_is_deterministic(self) -> None:
        payload = {"protocol": PROTOCOL, "type": "command", "seq": 3}
        first = encode_frame(payload)
        second = encode_frame(dict(reversed(list(payload.items()))))
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))

    def test_model_has_real_external_input_and_command_driven_outputs(self) -> None:
        wrapper = (ROOT / "modelica" / "TripLens_CombinedCycle_TripTAC.mo.tpl").read_text(
            encoding="utf-8"
        )
        patcher = (ROOT / "scripts" / "patch_turbine_bypass_model.py").read_text(
            encoding="utf-8"
        )
        renderer = (ROOT / "scripts" / "render_modelica.py").read_text(encoding="utf-8")
        self.assertIn("input Boolean vppExternalTripCommand", patcher)
        self.assertIn("vppUseExternalTripInput and vppExternalTripCommand", patcher)
        self.assertIn("vppGTExhaustMassFlowCommand.signal", patcher)
        self.assertIn("vppUseExternalTripInput=@EXTERNAL_TRIP_ENABLED@", wrapper)
        self.assertIn("output Real vppHPDrumLevelM", wrapper)
        self.assertIn("--external-trip-input", renderer)

    def test_external_render_suppresses_scheduled_trip_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "render_modelica.py"),
                    "--external-trip-input",
                    "--trip-time", "2",
                    "--trip-ramp-duration", "2",
                    "--stop-time", "10",
                    "--intervals", "10000",
                    "--output-dir", directory,
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            model = (Path(directory) / "TripLens_CombinedCycle_TripTAC.mo").read_text(
                encoding="utf-8"
            )
            self.assertIn("vppUseExternalTripInput=true", model)
            self.assertIn("vppTripTime=11", model)
            self.assertIn("parameter Boolean enableGTTrip = false", model)
            self.assertIn("[0,exhaustFlowNormalTH/3.6; 10,exhaustFlowNormalTH/3.6]", model)

    def test_workflow_uses_two_processes_and_not_csv_as_transport(self) -> None:
        runner = (ROOT / "scripts" / "run_live_fmu_ecms.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "run-live-fmu-ecms.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("live_fmu_gateway.py", runner)
        self.assertIn("live_ecms_client.py", runner)
        self.assertIn("gateway_pid=$!", runner)
        self.assertIn("TCP", runner)
        self.assertNotIn("cp build/thermosyspro", runner)
        self.assertIn('LIVE_STEP_SIZE_S: "0.001"', workflow)
        self.assertIn("requirements-live.txt", workflow)


if __name__ == "__main__":
    unittest.main()
