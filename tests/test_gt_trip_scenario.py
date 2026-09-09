from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GtTripScenarioTests(unittest.TestCase):
    @staticmethod
    def baseline(path: Path) -> None:
        path.write_text(json.dumps({
            "schema_version": "1.0",
            "ratings": {
                "gt_power_mw": 160,
                "st_power_mw": 250,
                "gt_speed_rpm": 3600,
                "st_speed_rpm": 3600,
            },
            "timing": {
                "trip_receive_delay_ms": 20,
                "lockout_operate_delay_ms": 35,
                "gt_breaker_open_delay_ms": 80,
                "st_breaker_open_delay_ms": 100,
            },
            "dynamics": {
                "gt_power_decay_s": 0.35,
                "st_power_decay_s": 0.8,
                "gt_coastdown_tau_s": 1.2,
                "st_coastdown_tau_s": 2.5,
            },
        }), encoding="utf-8")

    @staticmethod
    def read_csv(path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    @staticmethod
    def run_script(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/generate_gt_trip_scenario.py"), *arguments],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )

    def test_default_1ms_raw_is_label_free_and_has_exact_causal_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            baseline = target / "baseline.json"
            raw = target / "VPP.RAW.csv"
            oracle = target / "expected.json"
            manifest = target / "manifest.json"
            self.baseline(baseline)
            result = self.run_script(
                "--baseline", str(baseline), "--raw-output", str(raw),
                "--oracle-output", str(oracle), "--manifest-output", str(manifest),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = self.read_csv(raw)
            self.assertEqual(len(rows), 5001)
            forbidden = ("scenario", "fault", "root_cause", "answer", "expected")
            self.assertFalse(any(
                token in field.lower() for field in rows[0] for token in forbidden
            ))
            by_ms = {round(float(row["time_s"]) * 1000): row for row in rows}
            self.assertEqual(by_ms[999]["gt_trip_cmd"], "0")
            self.assertEqual(by_ms[1000]["gt_trip_cmd"], "1")
            self.assertEqual(by_ms[1000]["st_trip_request"], "1")
            self.assertEqual(by_ms[1054]["cb_52gt_trip_cmd"], "0")
            self.assertEqual(by_ms[1055]["cb_52gt_trip_cmd"], "1")
            self.assertEqual(by_ms[1079]["cb_52gt_closed"], "1")
            self.assertEqual(by_ms[1080]["cb_52gt_closed"], "0")
            self.assertEqual(by_ms[1099]["cb_52st_closed"], "1")
            self.assertEqual(by_ms[1100]["cb_52st_closed"], "0")
            self.assertEqual(float(by_ms[1080]["gtg_power_mw"]), 0.0)
            self.assertEqual(float(by_ms[1100]["stg_power_w"]), 0.0)
            self.assertLess(float(rows[-1]["gtg_speed_rpm"]), 3600.0)
            self.assertLess(float(rows[-1]["stg_speed_rpm"]), 3600.0)

            expected = json.loads(oracle.read_text(encoding="utf-8"))
            self.assertEqual(expected["case_id"], "GT_TRIP_01")
            self.assertEqual(
                expected["exact_event_times_ms"]["ECMS.52GT.CLOSED_1_TO_0"], 1080
            )
            raw_manifest = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertFalse(raw_manifest["boundary"]["raw_contains_scenario_label"])

    def test_sampling_can_be_selected_for_long_window_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            baseline = target / "baseline.json"
            raw = target / "raw.csv"
            self.baseline(baseline)
            result = self.run_script(
                "--baseline", str(baseline), "--raw-output", str(raw),
                "--pre-seconds", "300", "--post-seconds", "120", "--step-ms", "1000",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = self.read_csv(raw)
            self.assertEqual(len(rows), 421)
            self.assertEqual(rows[0]["time_s"], "0.000")
            self.assertEqual(rows[-1]["time_s"], "420.000")
            self.assertEqual(rows[299]["gt_trip_cmd"], "0")
            self.assertEqual(rows[300]["gt_trip_cmd"], "1")

    def test_missing_or_incomplete_baseline_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "raw.csv"
            missing = self.run_script(
                "--baseline", str(target / "missing.json"), "--raw-output", str(raw)
            )
            self.assertNotEqual(missing.returncode, 0)
            incomplete = target / "incomplete.json"
            incomplete.write_text('{"ratings": {}}', encoding="utf-8")
            result = self.run_script(
                "--baseline", str(incomplete), "--raw-output", str(raw)
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing required numeric key", result.stderr)


if __name__ == "__main__":
    unittest.main()
