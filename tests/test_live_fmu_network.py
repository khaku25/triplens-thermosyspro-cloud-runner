from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from live_protocol import (  # noqa: E402
    COMMAND_INPUTS,
    LIVE_SIGNALS,
    PROCESS_TELEMETRY,
    PROTOCOL,
    VALVE_POINTS,
    contract_sha256,
    encode_frame,
    read_frame,
    scenario_commands,
)
from prepare_standard_init_fmu import (  # noqa: E402
    CMAKE_SOURCE,
    EXPECTED_REPLACEMENTS,
    FMI_INIT_CALL,
    FULL_DEFINITIONS,
    FULL_LIBRARY_TARGET,
    MINIMAL_DEFINITIONS,
    MINIMAL_LIBRARY_TARGET,
    RUNTIME_SOURCE,
    STANDARD_INIT_CALL,
    prepare,
)


class LiveFMUNetworkTests(unittest.TestCase):
    def test_contract_covers_all_native_valves_and_physical_values(self) -> None:
        self.assertEqual(len(VALVE_POINTS), 12)
        self.assertEqual(len(COMMAND_INPUTS), 48)
        self.assertEqual(len(LIVE_SIGNALS), 105)
        self.assertEqual(len(PROCESS_TELEMETRY), 9)
        self.assertEqual(len({item.fmu_name for item in COMMAND_INPUTS}), 48)
        self.assertEqual(len({item.field for item in LIVE_SIGNALS}), 105)
        self.assertTrue(all(item.fmi_causality == "input" for item in COMMAND_INPUTS))
        self.assertTrue(all(item.owner == "DCS2" for item in PROCESS_TELEMETRY))
        self.assertTrue(all(
            point.owner == "DCS1" for point in VALVE_POINTS
            if "Steam" in point.key or "TurbAdm" in point.key
        ))

    def test_scenario_changes_real_fmi_inputs(self) -> None:
        before = scenario_commands(0.10)
        hp = scenario_commands(0.50)
        ip = scenario_commands(1.50)
        self.assertEqual(set(before), {item.fmu_name for item in COMMAND_INPUTS})
        self.assertIs(before["fmuVlvHPSteamModeAuto"], True)
        self.assertIs(hp["fmuVlvHPSteamModeAuto"], False)
        self.assertEqual(hp["fmuVlvHPSteamManualCmd"], 0.45)
        self.assertIs(ip["fmuVlvIPTurbAdmFaultEnable"], True)
        self.assertEqual(ip["fmuVlvIPTurbAdmFaultValue"], 0.60)

    def test_wire_encoding_and_contract_hash_are_deterministic(self) -> None:
        payload = {"protocol": PROTOCOL, "type": "command", "seq": 3}
        first = encode_frame(payload)
        second = encode_frame(dict(reversed(list(payload.items()))))
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        parsed, raw = read_frame(io.BytesIO(first))
        self.assertEqual(parsed, payload)
        self.assertEqual(raw, first)
        self.assertEqual(len(contract_sha256()), 64)

    def test_runner_uses_two_processes_and_csv_only_after_receive(self) -> None:
        runner = (ROOT / "scripts" / "run_live_fmu_ecms.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "run-live-fmu-ecms.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("live_fmu_gateway.py", runner)
        self.assertIn("live_ecms_client.py", runner)
        self.assertIn("gateway_pid=$!", runner)
        self.assertIn("LD_LIBRARY_PATH=$runtime_library_path", runner)
        self.assertNotIn("LD_PRELOAD", runner)
        self.assertNotIn("cp build/thermosyspro", runner)
        self.assertIn('LIVE_STEP_SIZE_S: "0.01"', workflow)
        self.assertIn('LIVE_STOP_TIME_S: "2"', workflow)
        self.assertIn("SOURCE_FMU_SHA256", workflow)
        self.assertIn("prepare_standard_init_fmu.py", workflow)
        self.assertIn("actions/cache/restore@v4", workflow)
        self.assertIn("actions/cache/save@v4", workflow)
        self.assertIn("Restore full-runtime compiler objects", workflow)
        self.assertIn("Save full-runtime compiler objects", workflow)
        self.assertIn("2000-01-01T00:00:00Z", workflow)
        self.assertIn("build/runtime-artifact/TripLens_Native_Valve_Control_V1.fmu", workflow)
        self.assertIn("Extract the matching full OpenModelica runtime", workflow)
        self.assertIn("FMU_RUNTIME_LIBRARY=", workflow)
        self.assertIn("OPENMODELICA_RUNTIME_DIRECTORY", workflow)
        self.assertIn("libSimulationRuntimeC.so", workflow)
        self.assertIn("liblapack.so.3", workflow)
        self.assertIn("libblas.so.3", workflow)
        self.assertIn("gh run download", workflow)

    def test_fmu_preparer_changes_only_runtime_wiring(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.fmu"
            runtime_text = "before\n" + (FMI_INIT_CALL + "\n") * EXPECTED_REPLACEMENTS + "after\n"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(RUNTIME_SOURCE.as_posix(), runtime_text)
                archive.writestr(
                    CMAKE_SOURCE.as_posix(),
                    f"before\n{MINIMAL_LIBRARY_TARGET}\nmiddle\n{MINIMAL_DEFINITIONS}\nafter\n",
                )
                archive.writestr("modelDescription.xml", "<fmiModelDescription/>")
            work = root / "work"
            manifest = root / "manifest.json"
            result = prepare(source, work, manifest)
            patched = (work / RUNTIME_SOURCE).read_text(encoding="utf-8")
            self.assertNotIn(FMI_INIT_CALL, patched)
            self.assertEqual(patched.count(STANDARD_INIT_CALL), EXPECTED_REPLACEMENTS)
            cmake = (work / CMAKE_SOURCE).read_text(encoding="utf-8")
            self.assertNotIn(MINIMAL_LIBRARY_TARGET, cmake)
            self.assertNotIn(MINIMAL_DEFINITIONS, cmake)
            self.assertIn(FULL_LIBRARY_TARGET, cmake)
            self.assertIn(FULL_DEFINITIONS, cmake)
            self.assertIn("LINKER:--no-as-needed", cmake)
            self.assertFalse(result["physical_equations_changed"])
            self.assertFalse(result["embedded_minimal_runtime"])
            self.assertTrue(manifest.is_file())


if __name__ == "__main__":
    unittest.main()
