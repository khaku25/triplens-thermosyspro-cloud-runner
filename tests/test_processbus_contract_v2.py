from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProcessBusContractV2Tests(unittest.TestCase):
    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def read_csv(path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_unknown_numeric_processes_are_preserved_without_mapping_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "arbitrary-raw.csv"
            self.write_csv(raw, [
                {"time": 0, "New.Sensor.Value": 10, "Unseen.Pressure": 100, "status": "OK"},
                {"time": 1, "New.Sensor.Value": 10, "Unseen.Pressure": 100, "status": "OK"},
                {"time": 2, "New.Sensor.Value": 12, "Unseen.Pressure": 95, "status": "EVENT"},
                {"time": 3, "New.Sensor.Value": 15, "Unseen.Pressure": 90, "status": "EVENT"},
                {"time": 4, "New.Sensor.Value": 15, "Unseen.Pressure": 90, "status": "EVENT"},
            ])
            processbus = target / "processbus.csv"
            review = target / "review.json"
            result = self.run_script(
                "normalize_processbus.py",
                "--input", str(raw),
                "--output", str(processbus),
                "--mapping-review", str(review),
                "--event-time", "2",
                "--scenario-id", "ARBITRARY_TEST",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = self.read_csv(processbus)
            self.assertIn("raw__new_sensor_value", rows[0])
            self.assertIn("raw__unseen_pressure", rows[0])
            self.assertNotIn("status", rows[0])
            self.assertNotIn("gt_trip_cmd", rows[0])
            self.assertEqual(rows[1]["event_marker"], "0")
            self.assertEqual(rows[2]["event_marker"], "1")

            metadata = json.loads(review.read_text(encoding="utf-8"))
            dynamic = metadata["dynamic_passthrough"]
            self.assertEqual(dynamic["count"], 2)
            self.assertEqual(
                {item["source_column"] for item in dynamic["signals"]},
                {"New.Sensor.Value", "Unseen.Pressure"},
            )
            self.assertEqual(dynamic["skipped_non_numeric_source_columns"], ["status"])

    def test_generic_incident_extractor_analyzes_dynamic_processes_without_gt_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "raw.csv"
            self.write_csv(raw, [
                {"time": 0, "New.Sensor.Value": 10},
                {"time": 1, "New.Sensor.Value": 10},
                {"time": 2, "New.Sensor.Value": 12},
                {"time": 3, "New.Sensor.Value": 15},
                {"time": 4, "New.Sensor.Value": 15},
            ])
            processbus = target / "processbus.csv"
            normalize = self.run_script(
                "normalize_processbus.py",
                "--input", str(raw),
                "--output", str(processbus),
                "--event-time", "2",
            )
            self.assertEqual(normalize.returncode, 0, normalize.stderr)

            extract = self.run_script(
                "extract_incident_window.py",
                "--processbus", str(processbus),
                "--event-time", "2",
                "--pre-seconds", "2",
                "--post-seconds", "2",
                "--baseline-seconds", "2",
                "--baseline-guard-seconds", "0",
                "--persistence-samples", "2",
                "--raw-output", str(target / "incident.csv"),
                "--changes-output", str(target / "changes.csv"),
                "--metadata-output", str(target / "metadata.json"),
            )
            self.assertEqual(extract.returncode, 0, extract.stderr)
            changes = self.read_csv(target / "changes.csv")
            self.assertTrue(any(
                row["change_kind"] == "PROCESS"
                and row["signal"] == "raw__new_sensor_value"
                for row in changes
            ))
            self.assertTrue(any(
                row["change_kind"] == "REFERENCE_EVENT"
                and row["signal"] == "event_marker"
                for row in changes
            ))
            metadata = json.loads((target / "metadata.json").read_text(encoding="utf-8"))
            self.assertTrue(metadata["detection"]["dynamic_processbus_signals_analyzed"])
            self.assertNotIn("observed_gt_trip_cmd_assertion_s", metadata)

    def test_bfp_aliases_use_the_same_general_normalizer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "bfp.csv"
            self.write_csv(raw, [
                {
                    "time": 0,
                    "PompeAlimHP.Vr": 1400,
                    "CapteurDebitEauHP.Q": 100,
                    "PompeAlimHP.Wm": 1000000,
                    "PompeAlimHP.deltaP": 3000000,
                },
                {
                    "time": 1,
                    "PompeAlimHP.Vr": 1200,
                    "CapteurDebitEauHP.Q": 90,
                    "PompeAlimHP.Wm": 800000,
                    "PompeAlimHP.deltaP": 2500000,
                },
            ])
            processbus = target / "processbus.csv"
            review = target / "signal-mapping-review.json"
            result = self.run_script(
                "normalize_processbus.py",
                "--input", str(raw),
                "--output", str(processbus),
                "--scenario-id", "BFP_TEST",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = self.read_csv(processbus)
            self.assertEqual(rows[0]["fwp_hp_speed_rpm"], "1400")
            self.assertEqual(rows[0]["fwp_hp_mass_flow_t_h"], "360")
            self.assertEqual(rows[0]["fwp_hp_mechanical_power_w"], "1000000")
            self.assertIn("raw__pompe_alim_hp_delta_p", rows[0])
            metadata = json.loads(review.read_text(encoding="utf-8"))
            conversion = next(
                item for item in metadata["published_unit_conversions"]
                if item["processbus_field"] == "fwp_hp_mass_flow_t_h"
            )
            self.assertEqual(conversion["multiplier"], 3.6)
            self.assertEqual(conversion["published_unit"], "t/h")

    def test_legacy_trip_time_keeps_gt_trip_command_for_existing_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "raw.csv"
            self.write_csv(raw, [
                {"time": 0, "Alternateur.Welec": 100},
                {"time": 1, "Alternateur.Welec": 100},
                {"time": 2, "Alternateur.Welec": 90},
                {"time": 3, "Alternateur.Welec": 80},
            ])
            processbus = target / "processbus.csv"
            result = self.run_script(
                "normalize_processbus.py",
                "--input", str(raw),
                "--output", str(processbus),
                "--trip-time", "2",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = self.read_csv(processbus)
            self.assertEqual(rows[1]["gt_trip_cmd"], "0")
            self.assertEqual(rows[2]["gt_trip_cmd"], "1")


if __name__ == "__main__":
    unittest.main()
