from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_native_opcua_dashboard import dashboard_groups  # noqa: E402
from native_ecms_opcua_client import SIGNALS  # noqa: E402


class NativeOPCUADashboardTests(unittest.TestCase):
    def test_ssot_panel_ownership_and_full_signal_coverage(self) -> None:
        groups = dashboard_groups()
        self.assertEqual(set(groups), {"DCS1", "DCS2", "ECMS"})
        field_sets = {
            owner: {field.field for field in fields}
            for owner, fields in groups.items()
        }
        self.assertFalse(field_sets["DCS1"] & field_sets["DCS2"])
        self.assertFalse(field_sets["DCS1"] & field_sets["ECMS"])
        self.assertFalse(field_sets["DCS2"] & field_sets["ECMS"])

        self.assertTrue({
            "gtg_power_mw", "gtg_speed_rpm", "stg_power_w",
            "hp_turbine_flow_th", "ip_turbine_flow_th", "lp_turbine_flow_th",
        } <= field_sets["DCS1"])
        self.assertTrue({
            "lp_fwp_speed_rpm", "lp_fwp_mass_flow_th", "lp_drum_level_m",
            "lp_drum_level_l_alarm", "lp_drum_level_ll_alarm",
        } <= field_sets["DCS2"])
        self.assertTrue({
            "lp_fwp_trip_command_readback", "lp_fwp_trip_latch_readback",
            "vcb_a02_trip_command_readback", "vcb_a02_closed_readback",
            "common_gt_trip_request", "common_st_trip_request",
            "gt_trip_latch", "st_trip_latch",
            "gt_breaker_closed", "st_breaker_closed",
        } <= field_sets["ECMS"])
        self.assertNotIn("lp_fwp_motor_energized", field_sets["DCS1"])

        displayed = set().union(*field_sets.values())
        self.assertTrue({signal.field for signal in SIGNALS} <= displayed)

    def test_renderer_embeds_terminal_and_event_summary(self) -> None:
        groups = dashboard_groups()
        fields = {
            field.field
            for panel in groups.values()
            for field in panel
        }
        row = {field: "1" for field in fields}
        row["time_s"] = "117.08"
        row["sequence"] = "1"

        proof = {
            "status": "PASS",
            "frames_received": 2953,
            "values_received": 200804,
            "changed_physical_fields": 31,
            "event_count": 28,
            "gt_trip_time_s": 87.08,
            "terminal_time_s": 117.08,
            "post_gt_trip_observation_s": 30.0,
            "termination_reason": "GT_TRIP_PLUS_30_SECONDS",
        }
        event = {
            "event_sequence": "28",
            "time_s": "117.080000000",
            "source_system": "ECMS",
            "canonical_tag": "TRIPLENS.SCENARIO.TERMINAL",
            "event_state": "1",
            "quality": "GOOD",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            capture = temp / "ECMS-native-physical.csv"
            proof_path = temp / "native-opcua-proof.json"
            output = temp / "dashboard.html"
            with capture.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            with (temp / "EVENT.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(event))
                writer.writeheader()
                writer.writerow(event)
            proof_path.write_text(json.dumps(proof), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build_native_opcua_dashboard.py"),
                    "--capture", str(capture),
                    "--proof", str(proof_path),
                    "--output", str(output),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            document = output.read_text(encoding="utf-8")

        self.assertIn("rows=1 events=1", completed.stdout)
        self.assertIn("DCS1'?' | GT / ST'", document)
        self.assertIn("DCS2'?' | HRSG / BOP'", document)
        self.assertIn("COMMAND / LATCH / BREAKER / PROTECTION", document)
        self.assertIn("LP DRUM LEVEL L ALARM", document)
        self.assertIn("LP DRUM LEVEL LL ALARM", document)
        self.assertIn("COMMON GT TRIP REQUEST", document)
        self.assertIn("COMMON ST TRIP REQUEST", document)
        self.assertIn("GT TRIP → TERMINAL", document)
        self.assertIn("30.000 s", document)
        self.assertIn("GT_TRIP_PLUS_30_SECONDS", document)
        self.assertIn("EVENT.csv | CHRONOLOGICAL EVENT SUMMARY", document)
        self.assertIn("TRIPLENS.SCENARIO.TERMINAL", document)


if __name__ == "__main__":
    unittest.main()
