from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CausalExportTests(unittest.TestCase):
    @staticmethod
    def write_processbus(path: Path, *, precursor: bool = False) -> None:
        fields = [
            "scenario_id", "time_s", "gt_trip_cmd", "stg_power_w",
            "gt_exhaust_mass_flow_kg_s", "gt_exhaust_temperature_k",
            "hp_drum_level_m", "hp_drum_pressure_pa", "hp_steam_flow_kg_s",
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for index in range(101):
                time_s = index / 10
                elapsed = max(0.0, time_s - 5.0)
                flow = 606.94
                if precursor and time_s >= 4.0:
                    flow = 580.0
                if time_s >= 5.0:
                    flow = max(50.0, 606.94 - elapsed * 150.0)
                writer.writerow({
                    "scenario_id": "CAUSAL_TEST",
                    "time_s": f"{time_s:.1f}",
                    "gt_trip_cmd": int(time_s >= 5.0),
                    "stg_power_w": f"{250_000_000 * max(0.04, 1 - elapsed / 4):.3f}",
                    "gt_exhaust_mass_flow_kg_s": f"{flow:.6f}",
                    "gt_exhaust_temperature_k": f"{max(423.0, 893.75 - elapsed * 150):.6f}",
                    "hp_drum_level_m": f"{max(0.80, 1.05 - elapsed * 0.06):.6f}",
                    "hp_drum_pressure_pa": f"{max(8_000_000, 12_703_151 - elapsed * 1_000_000):.3f}",
                    "hp_steam_flow_kg_s": f"{max(20, 150 - elapsed * 35):.6f}",
                })

    @staticmethod
    def read_csv(path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def run_script(self, name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def extract(self, target: Path, *, precursor: bool = False) -> None:
        processbus = target / "processbus.csv"
        self.write_processbus(processbus, precursor=precursor)
        result = self.run_script(
            "extract_incident_window.py",
            "--processbus", str(processbus),
            "--trip-time", "5",
            "--pre-seconds", "2",
            "--post-seconds", "4",
            "--baseline-seconds", "2",
            "--baseline-guard-seconds", "0.5",
            "--raw-output", str(target / "incident-raw.csv"),
            "--changes-output", str(target / "important-changes.csv"),
            "--metadata-output", str(target / "incident-window.json"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_stable_pretrip_is_preserved_without_fabricated_alarm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.extract(target)
            raw = self.read_csv(target / "incident-raw.csv")
            self.assertEqual(float(raw[0]["time_s"]), 3.0)
            self.assertEqual(float(raw[-1]["time_s"]), 9.0)
            self.assertTrue(all(row["gt_trip_cmd"] == "0" for row in raw if float(row["time_s"]) < 5))
            changes = self.read_csv(target / "important-changes.csv")
            command = next(row for row in changes if row["change_kind"] == "COMMAND")
            self.assertEqual(command["change_time_s"], "5.000000000")
            self.assertFalse(any(
                row["change_kind"] == "PROCESS" and row["phase"] == "PRE_TRIP"
                for row in changes
            ))

            result = self.run_script(
                "generate_dcs_alarms.py",
                "--incident-raw", str(target / "incident-raw.csv"),
                "--metadata", str(target / "incident-window.json"),
                "--rules", str(ROOT / "config/dcs_alarm_rules.csv"),
                "--trip-time", "5",
                "--dcs1-output", str(target / "DCS1.csv"),
                "--dcs2-output", str(target / "DCS2.csv"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            dcs1 = self.read_csv(target / "DCS1.csv")
            dcs2 = self.read_csv(target / "DCS2.csv")
            self.assertTrue(dcs1)
            self.assertTrue(dcs2)
            self.assertFalse(any(row["phase"] == "PRE_TRIP" for row in dcs1 + dcs2))
            trip = next(row for row in dcs1 if row["tag"] == "GT.TRIP.CMD")
            self.assertEqual(trip["source_time_ms"], "5000")
            self.assertEqual(trip["provenance"], "SCENARIO_INPUT")
            self.assertTrue(any(row["provenance"] == "PHYSICS_THRESHOLD_DERIVED" for row in dcs1))
            self.assertEqual(
                [int(row["source_time_ms"]) for row in dcs1],
                sorted(int(row["source_time_ms"]) for row in dcs1),
            )
            metadata = json.loads((target / "incident-window.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["alarm_summary"]["pretrip_event_count"], 0)
            self.assertFalse(metadata["alarm_summary"]["pretrip_alarm_fabricated"])

    def test_real_persistent_precursor_is_reported_before_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.extract(target, precursor=True)
            changes = self.read_csv(target / "important-changes.csv")
            precursor = next(
                row for row in changes
                if row["signal"] == "gt_exhaust_mass_flow_kg_s"
            )
            self.assertEqual(precursor["change_time_s"], "4.000000000")
            self.assertEqual(precursor["phase"], "PRE_TRIP")
            metadata = json.loads((target / "incident-window.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(metadata["pretrip_process_change_count"], 1)
            self.assertFalse(metadata["detection"]["root_cause_inferred"])

    def test_complete_causal_bundle_contract_passes_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            shutil.copy2(
                ROOT / "tests/fixtures/thermosyspro-raw.csv",
                target / "thermosyspro-raw.csv",
            )
            static_files = [
                "config/ecms_a_settings.csv", "config/ecms_a_equipment.csv",
                "config/ecms_command_catalog.csv", "config/fault_presets.json",
                "config/vpp_baseline_v1.json",
                "config/signal_map.json", "config/common_trip_matrix.csv",
                "config/tag_alias_contract.csv", "config/dcs_alarm_rules.csv",
                "examples/bfp_trip_commands.csv", "data/ecms_m_links.csv",
                "data/ecms_tag_catalog.csv", "data/thermo_vpp_m_locked_tags.csv",
                "data/m_layer_manifest.json", "topology/triplens_ecms_vpp.svg",
                "topology/triplens_ecms_6p9kv.svg", "matlab/triplens_ecms_editor.m",
                "matlab/triplens_ecms_vpp_editor.m", "matlab/triplens_ecms_vpp_simulate.m",
                "matlab/run_cloud_result.m", "ECMSVPP.m", "ECMS_START.m", "ECMS_RUN.m",
                "ECMS_RESULT.m", "ECMS_DIAGNOSE.m", "ECMS_SELF_TEST.m",
            ]
            for relative in static_files:
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            (target / "signal-mapping-review.json").write_text(
                '{"test_fixture": true}\n', encoding="utf-8"
            )
            self.write_processbus(target / "processbus.csv")
            shutil.copy2(target / "processbus.csv", target / "GT_TRIP_RAW_DATA.csv")
            self.extract(target)
            dcs = self.run_script(
                "generate_dcs_alarms.py",
                "--incident-raw", str(target / "incident-raw.csv"),
                "--metadata", str(target / "incident-window.json"),
                "--rules", str(ROOT / "config/dcs_alarm_rules.csv"),
                "--trip-time", "5",
                "--dcs1-output", str(target / "DCS1.csv"),
                "--dcs2-output", str(target / "DCS2.csv"),
            )
            self.assertEqual(dcs.returncode, 0, dcs.stderr)
            ecms = self.run_script(
                "generate_ecms.py",
                "--processbus", str(target / "processbus.csv"),
                "--trip-time", "5",
                "--sampling-profile", "causal_100ms",
                "--trend-output", str(target / "ecms-trend.csv"),
                "--event-output", str(target / "ecms-events.csv"),
                "--feeder-output", str(target / "ecms-feeders.csv"),
            )
            self.assertEqual(ecms.returncode, 0, ecms.stderr)
            shutil.copy2(target / "ecms-events.csv", target / "ECMS.csv")
            shutil.copy2(ROOT / "config/dcs_alarm_rules.csv", target / "config/dcs_alarm_rules.csv")
            manifest = self.run_script(
                "build_manifest.py",
                "--output-dir", str(target),
                "--trip-time", "5",
                "--trip-ramp-duration", "2",
                "--stop-time", "10",
                "--sampling-profile", "causal_100ms",
                "--output-intervals", "100",
                "--analysis-pre-s", "2",
                "--analysis-post-s", "4",
                "--fault-preset", "none",
                "--source-kind", "synthetic_fixture",
                "--thermosyspro-commit", "test-commit",
                "--openmodelica-image", "test-image",
            )
            self.assertEqual(manifest.returncode, 0, manifest.stderr)
            validate = self.run_script(
                "validate_outputs.py",
                "--output-dir", str(target),
                "--trip-time", "5",
                "--sampling-profile", "causal_100ms",
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)


if __name__ == "__main__":
    unittest.main()
