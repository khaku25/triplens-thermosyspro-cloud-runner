from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitHubCloudBridgeTests(unittest.TestCase):
    def make_artifact(self, target: Path) -> None:
        target.mkdir(parents=True)
        fields = [
            "sequence", "time_s", "cb_52gt_open_command_sent",
            "ecms_cb_52gt_closed", "gt_in_service",
            "gt_trip_from_52gt_open", "ecms_command_sent",
            "gt_trip_command_readback", "round_trip_ms",
            "gt_trip_latch", "stg_power_w", "gt_exhaust_flow_th",
            "gt_exhaust_temperature_k", "hp_turbine_flow_th",
            "ip_turbine_flow_th", "lp_turbine_flow_th", "hp_drum_level_m",
            "ip_drum_level_m", "lp_drum_level_m", "hp_drum_pressure_pa",
            "ip_drum_pressure_pa", "lp_drum_pressure_pa",
        ]
        rows = []
        # Root command, breaker feedback, derived Trip and physical response
        # are deliberately separated so the test can detect a reversed chain.
        for sequence, time_s in enumerate((0.10, 0.20, 0.25, 0.26, 0.50, 1.00)):
            open_command = time_s >= 0.25
            breaker_open = time_s >= 0.26
            derived_trip = time_s >= 0.26
            tripped = time_s >= 0.50
            rows.append({
                "sequence": sequence,
                "time_s": time_s,
                "cb_52gt_open_command_sent": int(open_command),
                "ecms_cb_52gt_closed": int(not breaker_open),
                "gt_in_service": 1,
                "gt_trip_from_52gt_open": int(derived_trip),
                "ecms_command_sent": int(tripped),
                "gt_trip_command_readback": int(tripped),
                "round_trip_ms": 1.0,
                "gt_trip_latch": int(tripped),
                "stg_power_w": 250_000_000 - (100_000_000 if tripped else 0),
                "gt_exhaust_flow_th": 2185.2 - (1200 if tripped else 0),
                "gt_exhaust_temperature_k": 893.75 - (300 if tripped else 0),
                "hp_turbine_flow_th": 540 - (300 if tripped else 0),
                "ip_turbine_flow_th": 140 - (80 if tripped else 0),
                "lp_turbine_flow_th": 45 - (20 if tripped else 0),
                "hp_drum_level_m": 1.05 - (0.02 if tripped else 0),
                "ip_drum_level_m": 1.05,
                "lp_drum_level_m": 1.75,
                "hp_drum_pressure_pa": 12_703_151 - (500_000 if tripped else 0),
                "ip_drum_pressure_pa": 2_732_895,
                "lp_drum_pressure_pa": 450_000,
            })
        with (target / "ECMS-native-physical.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        (target / "native-opcua-proof.json").write_text(json.dumps({
            "status": "PASS",
            "command_time_s": 0.25,
            "root_cause_time_s": 0.25,
            "scenario_id": "RUNNING_52GT_OPEN_TO_GT_TRIP",
            "root_cause": "52GT_OPEN_WHILE_GT_IN_SERVICE",
            "causal_order_verified": True,
            "actual_plant_logic_used": False,
            "breaker_open_trip_policy": "VPP_PROVISIONAL_NOT_PLANT_LOGIC",
            "transport_scope": "REAL_OPC_UA_TCP_INSIDE_GITHUB_HOSTED_RUNNER",
            "client_implementation": "PYTHON_OPCUA_ADAPTER_CONTROLLED_BY_MATLAB_R2026A",
            "matlab_release": "R2026a",
        }), encoding="utf-8")

    def test_imports_opcua_capture_into_atomic_cloud_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            artifact = temporary / "artifact"
            output = temporary / "runs"
            self.make_artifact(artifact)
            completed = subprocess.run([
                sys.executable,
                str(ROOT / "scripts" / "github_opcua_cloud_bridge.py"),
                "--package-root", str(ROOT),
                "--output-root", str(output),
                "--artifact-dir", str(artifact),
                "--github-run-id", "12345",
                "--github-run-url", "https://github.com/example/actions/runs/12345",
                "--no-update-latest",
            ], cwd=ROOT, check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            marker = "TRIPLENS_GITHUB_BRIDGE_RESULT="
            result_line = next(
                line for line in completed.stdout.splitlines() if line.startswith(marker)
            )
            result = json.loads(result_line[len(marker):])
            run = Path(result["RunFolder"])
            for name in (
                "github-opcua-received.csv", "native-opcua-proof.json",
                "processbus.csv", "ecms-trend.csv", "ecms-events.csv",
                "ecms-feeders.csv", "manifest.json", "DCS1.csv", "DCS2.csv",
            ):
                self.assertTrue((run / name).is_file(), name)
            with (run / "processbus.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertNotIn("gt_trip_cmd", rows[0])
            self.assertEqual(rows[2]["cb_52gt_open_command"], "1")
            self.assertEqual(rows[2]["ecms_cb_52gt_closed"], "1")
            self.assertEqual(rows[3]["ecms_cb_52gt_closed"], "0")
            self.assertEqual(rows[3]["gt_trip_from_52gt_open"], "1")
            self.assertEqual(rows[0]["gt_exhaust_mass_flow_t_h"], "2185.2")
            self.assertEqual(rows[0]["stg_power_w"], "250000000")
            with (run / "ecms-events.csv").open(encoding="utf-8", newline="") as stream:
                ecms_events = list(csv.DictReader(stream))
            event_time = {
                row["canonical_tag"]: int(row["source_time_ms"])
                for row in ecms_events
            }
            self.assertEqual(event_time["CMD.CB-52GT.OPEN"], 250)
            self.assertEqual(event_time["ECMS.52GT.CLOSED"], 260)
            self.assertEqual(event_time["CTRL.GTG.TRIP_FROM_52GT_OPEN"], 260)
            self.assertLessEqual(
                event_time["ECMS.52GT.CLOSED"],
                event_time["CTRL.GTG.TRIP_FROM_52GT_OPEN"],
            )
            self.assertNotIn("CMD.GTG.TRIP", event_time)
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["runtime"]["engine"],
                "THERMOSYSPRO_OPENMODELICA_OPCUA_GITHUB",
            )
            self.assertTrue(manifest["runtime"]["thermosyspro_used"])
            self.assertFalse(manifest["opcua_capture"]["mutated"])
            self.assertFalse(manifest["root_cause_label_injected"])
            self.assertEqual(manifest["scenario"]["root_cause"], "52GT_OPEN_WHILE_GT_IN_SERVICE")
            self.assertTrue(manifest["scenario"]["causal_order_verified"])
            self.assertFalse(manifest["scenario"]["actual_plant_logic_used"])

    def test_matlab_entrypoint_never_puts_token_on_command_line(self) -> None:
        source = (ROOT / "ECMS_GITHUB.m").read_text(encoding="utf-8")
        self.assertIn('getenv("TRIPLENS_GITHUB_TOKEN")', source)
        command_block = source.split("arguments = [", 1)[1].split("];", 1)[0]
        self.assertNotIn("token", command_block.lower())
        self.assertIn("matlab-native-opcua-ecms.yml", source)


if __name__ == "__main__":
    unittest.main()
