from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def run_script(
        self,
        script: str,
        *arguments: str,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), *arguments],
            cwd=cwd or ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def read_csv(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    @staticmethod
    def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def normalize_fixture(self, target: Path, *, cwd: Path | None = None) -> Path:
        processbus = target / "processbus.csv"
        result = self.run_script(
            "normalize_processbus.py",
            "--input", str(ROOT / "tests/fixtures/thermosyspro-raw.csv"),
            "--output", str(processbus),
            "--mapping-review", str(target / "signal-mapping-review.json"),
            "--trip-time", "2",
            cwd=cwd,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return processbus

    def create_bundle(self, target: Path, fault_preset: str = "none") -> None:
        shutil.copy2(ROOT / "tests/fixtures/thermosyspro-raw.csv", target / "thermosyspro-raw.csv")
        processbus = self.normalize_fixture(target)
        result = self.run_script(
            "generate_ecms.py",
            "--processbus", str(processbus),
            "--trip-time", "2",
            "--fault-preset", fault_preset,
            "--trend-output", str(target / "ecms-trend.csv"),
            "--event-output", str(target / "ecms-events.csv"),
            "--feeder-output", str(target / "ecms-feeders.csv"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        static_files = [
            "config/ecms_a_settings.csv",
            "config/ecms_a_equipment.csv",
            "config/ecms_command_catalog.csv",
            "config/fault_presets.json",
            "config/signal_map.json",
            "examples/bfp_trip_commands.csv",
            "data/ecms_m_links.csv",
            "data/ecms_tag_catalog.csv",
            "data/thermo_vpp_m_locked_tags.csv",
            "data/m_layer_manifest.json",
            "topology/triplens_ecms_vpp.svg",
            "topology/triplens_ecms_6p9kv.svg",
            "matlab/triplens_ecms_editor.m",
            "matlab/triplens_ecms_vpp_editor.m",
            "matlab/triplens_ecms_vpp_simulate.m",
            "matlab/run_cloud_result.m",
            "ECMSVPP.m",
            "ECMS_START.m",
            "ECMS_RUN.m",
            "ECMS_RESULT.m",
            "ECMS_DIAGNOSE.m",
            "ECMS_SELF_TEST.m",
        ]
        for relative in static_files:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        manifest = self.run_script(
            "build_manifest.py",
            "--output-dir", str(target),
            "--trip-time", "2",
            "--trip-ramp-duration", "1",
            "--stop-time", "5",
            "--fault-preset", fault_preset,
            "--thermosyspro-commit", "test-commit",
            "--openmodelica-image", "test-image",
        )
        self.assertEqual(manifest.returncode, 0, manifest.stderr)

    def test_render_modelica_replaces_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_script(
                "render_modelica.py",
                "--trip-time", "2",
                "--trip-ramp-duration", "1",
                "--stop-time", "5",
                "--intervals", "50",
                "--output-dir", directory,
                cwd=Path(directory),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            model = (Path(directory) / "TripLens_CombinedCycle_TripTAC.mo").read_text()
            mos = (Path(directory) / "run.mos").read_text()
            self.assertIn('tripTime(unit="s") = 2', model)
            self.assertIn("numberOfIntervals=50", mos)
            self.assertNotIn("@TRIP_TIME@", model)

    def test_normalize_and_generate_ecms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = target / "processbus.csv"
            review = target / "review.json"
            normalize = self.run_script(
                "normalize_processbus.py",
                "--input", str(ROOT / "tests/fixtures/thermosyspro-raw.csv"),
                "--output", str(processbus),
                "--mapping-review", str(review),
                "--trip-time", "2",
            )
            self.assertEqual(normalize.returncode, 0, normalize.stderr)
            with processbus.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[1]["gt_trip_cmd"], "0")
            self.assertEqual(rows[2]["gt_trip_cmd"], "1")
            mapping = json.loads(review.read_text())
            self.assertEqual(mapping["resolved"]["stg_power_w"], "Alternateur.Welec")

            trend = target / "ecms-trend.csv"
            events = target / "ecms-events.csv"
            generate = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--trip-time", "2",
                "--fault-preset", "none",
                "--trend-output", str(trend),
                "--event-output", str(events),
            )
            self.assertEqual(generate.returncode, 0, generate.stderr)
            with events.open(newline="") as stream:
                event_rows = list(csv.DictReader(stream))
            tags = {row["tag"] for row in event_rows}
            self.assertIn("GT.TRIP.CMD", tags)
            self.assertIn("52GT.CLOSED", tags)
            self.assertNotIn("52SST-A.CLOSED", tags)
            with trend.open(newline="") as stream:
                trend_rows = list(csv.DictReader(stream))
            after_trip = next(row for row in trend_rows if int(row["source_time_ms"]) >= 3000)
            self.assertEqual(after_trip["gt_main_transformer_direction"], "IMPORT")
            self.assertEqual(float(after_trip["bus_a_voltage_kv"]), 6.9)
            self.assertEqual(after_trip["cb_in_a_closed"], "1")

    def test_grid_loss_removes_reverse_receiving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = target / "processbus.csv"
            normalize = self.run_script(
                "normalize_processbus.py",
                "--input", str(ROOT / "tests/fixtures/thermosyspro-raw.csv"),
                "--output", str(processbus),
                "--trip-time", "2",
            )
            self.assertEqual(normalize.returncode, 0, normalize.stderr)
            trend = target / "trend.csv"
            generate = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--trip-time", "2",
                "--fault-preset", "grid_loss",
                "--trend-output", str(trend),
                "--event-output", str(target / "events.csv"),
            )
            self.assertEqual(generate.returncode, 0, generate.stderr)
            with trend.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            settled = next(row for row in rows if int(row["source_time_ms"]) >= 3000)
            self.assertEqual(settled["gt_main_transformer_direction"], "DEAD")
            self.assertEqual(float(settled["bus_a_voltage_kv"]), 0.0)

    def test_faultbus_injection_starts_at_the_declared_trip_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = self.normalize_fixture(target)
            trend = target / "trend.csv"
            result = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--trip-time", "2",
                "--fault-preset", "bus_a_fault",
                "--trend-output", str(trend),
                "--event-output", str(target / "events.csv"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = self.read_csv(trend)
            before = next(row for row in rows if row["source_time_ms"] == "1980")
            at_trip = next(row for row in rows if row["source_time_ms"] == "2000")
            self.assertEqual(before["bus_a_voltage_kv"], "6.900000")
            self.assertEqual(at_trip["bus_a_voltage_kv"], "0.000000")

    def test_m_layer_contains_only_locked_model_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "m.csv"
            manifest = Path(directory) / "manifest.json"
            result = self.run_script(
                "build_m_layer.py",
                "--output", str(output),
                "--manifest", str(manifest),
                cwd=Path(directory),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with output.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(rows)
            self.assertTrue(all(row["tag_class"] == "M" and row["value_basis"] == "M" for row in rows))
            metadata = json.loads(manifest.read_text())
            self.assertEqual(metadata["m_row_count"], len(rows))
            self.assertEqual(metadata["ecms_m_link_count"], 10)

    def test_unknown_fault_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = target / "processbus.csv"
            normalize = self.run_script(
                "normalize_processbus.py",
                "--input", str(ROOT / "tests/fixtures/thermosyspro-raw.csv"),
                "--output", str(processbus),
                "--trip-time", "2",
            )
            self.assertEqual(normalize.returncode, 0, normalize.stderr)
            generate = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--trip-time", "2",
                "--fault-preset", "invented_fault",
                "--trend-output", str(target / "trend.csv"),
                "--event-output", str(target / "events.csv"),
            )
            self.assertNotEqual(generate.returncode, 0)
            self.assertIn("unknown fault preset", generate.stderr)

    def test_generator_consumes_equipment_and_is_location_aware(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = self.normalize_fixture(target, cwd=target)
            equipment_rows = self.read_csv(ROOT / "config/ecms_a_equipment.csv")[:2]
            equipment_rows[0]["label_ko"] = "사용자 피더"
            equipment_rows[0]["feeder_id"] = "VCB-CUSTOM"
            equipment_rows[0]["normal_breaker_state"] = "OPEN"
            equipment_rows[1]["rated_kw"] = "690"
            equipment_path = target / "custom-equipment.csv"
            self.write_csv(equipment_path, equipment_rows)

            trend = target / "trend-dir/ecms-trend.csv"
            events = target / "event-dir/ecms-events.csv"
            result = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--a-equipment", str(equipment_path),
                "--trip-time", "2",
                "--trend-output", str(trend),
                "--event-output", str(events),
                cwd=target,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(events.exists())
            feeder_path = trend.with_name("ecms-feeders.csv")
            with feeder_path.open(encoding="utf-8-sig", newline="") as stream:
                feeder_fields = list(csv.DictReader(stream).fieldnames or [])
            self.assertEqual(feeder_fields, [
                "ecms_time_ms", "source_time_ms", "quality", "a_config_status",
                "equipment_id", "label_ko", "bus", "feeder_id", "configured_voltage_kv",
                "rated_kw", "breaker_closed", "energized", "bus_voltage_kv", "current_a",
                "priority", "equipment_status", "m_link_id", "source_m_tag_id", "provenance",
            ])
            feeder_rows = self.read_csv(feeder_path)
            trend_rows = self.read_csv(trend)
            self.assertEqual(len(feeder_rows), len(trend_rows) * 2)
            self.assertEqual({row["equipment_id"] for row in feeder_rows}, {"FWP-HP", "FWP-IP"})
            custom = next(row for row in feeder_rows if row["equipment_id"] == "FWP-HP")
            self.assertEqual(custom["label_ko"], "사용자 피더")
            self.assertEqual(custom["feeder_id"], "VCB-CUSTOM")
            self.assertEqual(custom["breaker_closed"], "0")
            self.assertEqual(custom["energized"], "0")
            rated = next(row for row in feeder_rows if row["equipment_id"] == "FWP-IP")
            self.assertAlmostEqual(float(rated["current_a"]), 690 / (3 ** 0.5 * 6.9 * 0.95), places=5)
            self.assertEqual(rated["m_link_id"], "M-LINK-004")
            self.assertEqual(rated["source_m_tag_id"], "TSP.DRUM.IP.FW_FLOW")

    def test_settings_drive_grid_status_and_undervoltage_delay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = self.normalize_fixture(target)
            settings_rows = self.read_csv(ROOT / "config/ecms_a_settings.csv")
            for row in settings_rows:
                row["status"] = "CONFIRMED_VPP"
                if row["setting_id"] == "GRID_VOLTAGE_KV":
                    row["value"] = "161"
                elif row["setting_id"] == "UNDERVOLTAGE_DELAY_MS":
                    row["value"] = "400"
            settings_path = target / "settings.csv"
            self.write_csv(settings_path, settings_rows)
            equipment_rows = self.read_csv(ROOT / "config/ecms_a_equipment.csv")
            for row in equipment_rows:
                row["status"] = "CONFIRMED_VPP"
            equipment_path = target / "equipment.csv"
            self.write_csv(equipment_path, equipment_rows)
            trend = target / "trend.csv"
            events = target / "events.csv"
            result = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--a-settings", str(settings_path),
                "--a-equipment", str(equipment_path),
                "--trip-time", "2",
                "--fault-preset", "grid_loss",
                "--trend-output", str(trend),
                "--event-output", str(events),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            trend_rows = self.read_csv(trend)
            self.assertTrue(all(row["a_config_status"] == "CONFIRMED_VPP" for row in trend_rows))
            self.assertEqual(float(trend_rows[0]["grid_voltage_kv"]), 161.0)
            self.assertEqual(float(next(row for row in trend_rows if row["source_time_ms"] == "2000")["grid_voltage_kv"]), 0.0)
            uv_event = next(row for row in self.read_csv(events) if row["tag"] == "BUS-A.27UV.OPERATE")
            self.assertEqual(uv_event["source_time_ms"], "2480")
            self.assertIn("400 ms", uv_event["description"])

    def test_auto_bus_tie_waits_for_the_configured_undervoltage_delay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = self.normalize_fixture(target)
            settings_rows = self.read_csv(ROOT / "config/ecms_a_settings.csv")
            next(row for row in settings_rows if row["setting_id"] == "AUTO_BUS_TIE_TRANSFER")["value"] = "1"
            next(row for row in settings_rows if row["setting_id"] == "UNDERVOLTAGE_DELAY_MS")["value"] = "300"
            settings_path = target / "settings.csv"
            self.write_csv(settings_path, settings_rows)
            trend = target / "trend.csv"
            events = target / "events.csv"
            result = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--a-settings", str(settings_path),
                "--trip-time", "2",
                "--fault-preset", "uat_a_fault",
                "--trend-output", str(trend),
                "--event-output", str(events),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = {row["source_time_ms"]: row for row in self.read_csv(trend)}
            self.assertEqual(rows["2280"]["cb_tie_ab_closed"], "0")
            self.assertEqual(rows["2300"]["bus_a_voltage_kv"], "0.000000")
            self.assertEqual(rows["2320"]["cb_tie_ab_closed"], "1")
            self.assertEqual(rows["2320"]["bus_a_voltage_kv"], "6.900000")
            uv_event = next(row for row in self.read_csv(events) if row["tag"] == "BUS-A.27UV.OPERATE")
            self.assertEqual(uv_event["source_time_ms"], "2300")

    def test_source_parallel_true_is_rejected_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = self.normalize_fixture(target)
            settings_rows = self.read_csv(ROOT / "config/ecms_a_settings.csv")
            next(row for row in settings_rows if row["setting_id"] == "ALLOW_SOURCE_PARALLEL")["value"] = "1"
            settings_path = target / "settings.csv"
            self.write_csv(settings_path, settings_rows)
            result = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--a-settings", str(settings_path),
                "--trip-time", "2",
                "--trend-output", str(target / "trend.csv"),
                "--event-output", str(target / "events.csv"),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no synchronism/phase-angle model", result.stderr)

    def test_config_status_combines_settings_and_equipment_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = self.normalize_fixture(target)
            settings_rows = self.read_csv(ROOT / "config/ecms_a_settings.csv")
            for row in settings_rows:
                row["status"] = "CONFIRMED_VPP"
            settings = target / "settings.csv"
            self.write_csv(settings, settings_rows)
            trend = target / "trend.csv"
            result = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--a-settings", str(settings),
                "--trip-time", "2",
                "--trend-output", str(trend),
                "--event-output", str(target / "events.csv"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(all(
                row["a_config_status"] == "PROVISIONAL" for row in self.read_csv(trend)
            ))

    def test_missing_or_unlocked_equipment_m_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = self.normalize_fixture(target)
            links = self.read_csv(ROOT / "data/ecms_m_links.csv")
            links = [row for row in links if row["ecms_equipment_id"] != "FWP-HP"]
            links_path = target / "links.csv"
            self.write_csv(links_path, links)
            missing = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--m-links", str(links_path),
                "--trip-time", "2",
                "--trend-output", str(target / "trend.csv"),
                "--event-output", str(target / "events.csv"),
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("exactly one locked M link", missing.stderr)
            links = self.read_csv(ROOT / "data/ecms_m_links.csv")
            links[0]["locked"] = "false"
            self.write_csv(links_path, links)
            unlocked = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--m-links", str(links_path),
                "--trip-time", "2",
                "--trend-output", str(target / "trend2.csv"),
                "--event-output", str(target / "events2.csv"),
            )
            self.assertNotEqual(unlocked.returncode, 0)
            self.assertIn("must remain locked", unlocked.stderr)

    def test_comms_loss_quality_propagates_to_all_ecms_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = self.normalize_fixture(target)
            trend = target / "trend.csv"
            events = target / "events.csv"
            feeders = target / "feeders.csv"
            result = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--trip-time", "2",
                "--fault-preset", "ecms_comms_loss",
                "--trend-output", str(trend),
                "--event-output", str(events),
                "--feeder-output", str(feeders),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            event_rows = self.read_csv(events)
            self.assertTrue(event_rows)
            self.assertTrue(all(row["quality"] == "BAD" for row in event_rows))
            comms = next(row for row in event_rows if row["tag"] == "ECMS.COMMS.QUALITY")
            self.assertEqual(comms["quality"], "BAD")
            for rows in (self.read_csv(trend), self.read_csv(feeders)):
                self.assertTrue(all(
                    row["quality"] == ("BAD" if int(row["source_time_ms"]) >= 2000 else "GOOD")
                    for row in rows
                ))

    def test_validator_checks_feeders_payload_and_manifest_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.create_bundle(target, "ecms_comms_loss")
            validate = self.run_script(
                "validate_outputs.py",
                "--output-dir", str(target),
                "--trip-time", "2",
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)
            with (target / "ecms-feeders.csv").open("a", encoding="utf-8") as stream:
                stream.write("\n")
            stale = self.run_script(
                "validate_outputs.py",
                "--output-dir", str(target),
                "--trip-time", "2",
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("byte count mismatch", stale.stderr)

    def test_validator_requires_the_vpp_editor_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.create_bundle(target)
            (target / "matlab/triplens_ecms_vpp_editor.m").unlink()
            validate = self.run_script(
                "validate_outputs.py",
                "--output-dir", str(target),
                "--trip-time", "2",
            )
            self.assertNotEqual(validate.returncode, 0)
            self.assertIn("matlab/triplens_ecms_vpp_editor.m", validate.stderr)

    def test_validator_rejects_an_event_outside_the_trend_horizon(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.create_bundle(target)
            events_path = target / "ecms-events.csv"
            rows = self.read_csv(events_path)
            rows[-1]["source_time_ms"] = "6000"
            rows[-1]["event_time_ms"] = "6000"
            self.write_csv(events_path, rows)
            rebuild = self.run_script(
                "build_manifest.py",
                "--output-dir", str(target),
                "--trip-time", "2",
                "--trip-ramp-duration", "1",
                "--stop-time", "5",
                "--fault-preset", "none",
                "--thermosyspro-commit", "test-commit",
                "--openmodelica-image", "test-image",
            )
            self.assertEqual(rebuild.returncode, 0, rebuild.stderr)
            validate = self.run_script(
                "validate_outputs.py",
                "--output-dir", str(target),
                "--trip-time", "2",
            )
            self.assertNotEqual(validate.returncode, 0)
            self.assertIn("outside the generated trend horizon", validate.stderr)

    def test_command_catalog_and_example_queue_are_valid_from_any_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog_rows = self.read_csv(ROOT / "config/ecms_command_catalog.csv")
            self.assertGreaterEqual(len(catalog_rows), 90)
            registered = {(row["equipment_id"], row["command"]) for row in catalog_rows}
            for equipment_id in ("CB-52GT", "CB-52ST", "CB-IN-A", "CB-IN-B", "CB-TIE-AB"):
                self.assertIn((equipment_id, "OPEN"), registered)
                self.assertIn((equipment_id, "CLOSE"), registered)
            for equipment_id in ("FWP-HP", "FWP-IP", "FWP-LP", "COND-PUMP", "CW-PUMP"):
                self.assertIn((equipment_id, "START"), registered)
                self.assertIn((equipment_id, "STOP"), registered)
                self.assertIn((equipment_id, "TRIP"), registered)
            result = self.run_script(
                "validate_commands.py",
                "--commands", str(ROOT / "examples/bfp_trip_commands.csv"),
                cwd=Path(directory),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1 queued commands", result.stdout)
            outside_horizon = self.run_script(
                "validate_commands.py",
                "--commands", str(ROOT / "examples/bfp_trip_commands.csv"),
                "--stop-time", "50",
                cwd=Path(directory),
            )
            self.assertNotEqual(outside_horizon.returncode, 0)
            self.assertIn("after --stop-time", outside_horizon.stderr)

    def test_commandbus_changes_electrical_and_feeder_outputs_without_mutating_m(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = self.normalize_fixture(target)
            original_processbus = processbus.read_bytes()
            catalog = self.read_csv(ROOT / "config/ecms_command_catalog.csv")
            queue_rows: list[dict[str, str]] = []
            for sequence, time_s, equipment_id, action in (
                (1, "0.5", "CB-IN-A", "OPEN"),
                (2, "1", "FWP-HP", "TRIP"),
                (3, "2", "GTG", "TRIP"),
            ):
                definition = next(
                    row for row in catalog
                    if row["equipment_id"] == equipment_id and row["command"] == action
                )
                queue_rows.append({
                    "sequence": str(sequence),
                    "time_s": time_s,
                    "equipment_id": equipment_id,
                    "equipment_label": definition["label_ko"],
                    "command": action,
                    "command_value": definition["default_value"],
                    "unit": definition["unit"],
                    "execution_layer": definition["execution_layer"],
                    "model_input": definition["model_input"],
                    "feedback_tag": definition["feedback_tag"],
                    "status": "QUEUED",
                    "note": "regression",
                })
            commands = target / "commands.csv"
            self.write_csv(commands, queue_rows)
            trend = target / "trend.csv"
            events = target / "events.csv"
            feeders = target / "feeders.csv"
            result = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--commands", str(commands),
                "--trip-time", "2",
                "--trend-output", str(trend),
                "--event-output", str(events),
                "--feeder-output", str(feeders),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(processbus.read_bytes(), original_processbus)
            trend_rows = {row["source_time_ms"]: row for row in self.read_csv(trend)}
            self.assertEqual(trend_rows["480"]["cb_in_a_closed"], "1")
            self.assertEqual(trend_rows["500"]["cb_in_a_closed"], "0")
            self.assertEqual(trend_rows["500"]["bus_a_voltage_kv"], "0.000000")
            feeder_rows = self.read_csv(feeders)
            before = next(row for row in feeder_rows if row["equipment_id"] == "FWP-HP" and row["source_time_ms"] == "980")
            after = next(row for row in feeder_rows if row["equipment_id"] == "FWP-HP" and row["source_time_ms"] == "1000")
            self.assertEqual(before["breaker_closed"], "1")
            self.assertEqual(after["breaker_closed"], "0")
            event_rows = self.read_csv(events)
            command_tags = {row["tag"] for row in event_rows if row["event_class"] == "COMMAND"}
            self.assertEqual(command_tags, {
                "COMMAND.CB-IN-A.OPEN", "COMMAND.FWP-HP.TRIP", "COMMAND.GTG.TRIP",
            })
            fwp_event = next(row for row in event_rows if row["tag"] == "COMMAND.FWP-HP.TRIP")
            self.assertIn("electrical indication only", fwp_event["description"])
            gt_trip = next(row for row in event_rows if row["tag"] == "GT.TRIP.CMD")
            self.assertEqual(gt_trip["provenance"], "USER_COMMAND")

    def test_unregistered_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "commands.csv"
            queue.write_text(
                "sequence,time_s,equipment_id,equipment_label,command,command_value,unit,execution_layer,model_input,feedback_tag,status,note\n"
                "1,1,FWP-HP,HP 급수펌프,FLY,0,BOOL,THERMO_ADAPTER_REQUIRED,FWP_HP_TRIP,TSP.DRUM.HP.FW_FLOW,QUEUED,test\n",
                encoding="utf-8",
            )
            result = self.run_script("validate_commands.py", "--commands", str(queue))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unregistered command", result.stderr)

    def test_pipeline_shell_is_location_aware_and_guards_stale_results(self) -> None:
        script = (ROOT / "scripts/run_pipeline.sh").read_text(encoding="utf-8")
        self.assertIn('BASH_SOURCE[0]', script)
        self.assertIn('rm -f "$project_root/build/thermosyspro_trip_tac_res.csv"', script)
        self.assertIn('rm -rf "$project_root/outputs"', script)
        self.assertIn("OpenModelica did not create a fresh non-empty result CSV", script)
        syntax = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts/run_pipeline.sh")],
            cwd=Path(tempfile.gettempdir()),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        workflow = (ROOT / ".github/workflows/run-thermosyspro.yml").read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: true", workflow)
        self.assertRegex(workflow, r"Upload simulation results\s+if: success\(\)")
        self.assertIn("command_scenario:", workflow)
        self.assertIn('"$COMMAND_SCENARIO"', workflow)

    def test_manifest_explicitly_distinguishes_physics_and_synthetic_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            common = (
                "--output-dir", str(target),
                "--trip-time", "2",
                "--trip-ramp-duration", "1",
                "--stop-time", "5",
                "--fault-preset", "none",
                "--thermosyspro-commit", "pinned-test-commit",
                "--openmodelica-image", "pinned-test-image",
            )
            physics = self.run_script("build_manifest.py", *common)
            self.assertEqual(physics.returncode, 0, physics.stderr)
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["runtime"]["thermosyspro_used"])
            self.assertEqual(manifest["runtime"]["engine"], "THERMOSYSPRO_OPENMODELICA")

            synthetic = self.run_script(
                "build_manifest.py", *common,
                "--source-kind", "synthetic_fixture",
                "--scenario-id", "BUNDLED_SYNTHETIC_DEMO",
            )
            self.assertEqual(synthetic.returncode, 0, synthetic.stderr)
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["runtime"]["thermosyspro_used"])
            self.assertIn("SYNTHETIC", manifest["runtime"]["engine"])
            self.assertEqual(manifest["scenario"]["id"], "BUNDLED_SYNTHETIC_DEMO")

    def test_matlab_public_function_and_authoritative_topology_contracts(self) -> None:
        public_files = [
            ROOT / "ECMSVPP.m",
            ROOT / "ECMS_START.m",
            ROOT / "ECMS_RUN.m",
            ROOT / "ECMS_RESULT.m",
            ROOT / "ECMS_DIAGNOSE.m",
            ROOT / "ECMS_SELF_TEST.m",
            ROOT / "matlab/run_cloud_result.m",
            ROOT / "matlab/triplens_ecms_editor.m",
            ROOT / "matlab/triplens_ecms_vpp_editor.m",
            ROOT / "matlab/triplens_ecms_vpp_simulate.m",
        ]
        for path in public_files:
            first_code_line = next(
                line.strip()
                for line in path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.lstrip().startswith("%")
            )
            match = re.match(
                r"function\s+(?:(?:\[[^]]+\]|\w+)\s*=\s*)?(\w+)\s*\(",
                first_code_line,
            )
            self.assertIsNotNone(match, f"{path.name}: first code line is not a public function")
            self.assertEqual(match.group(1), path.stem, f"{path.name}: function/file name mismatch")

        authoritative = [
            ROOT / "matlab/run_cloud_result.m",
            ROOT / "matlab/triplens_ecms_vpp_editor.m",
            ROOT / "matlab/triplens_ecms_vpp_simulate.m",
        ]
        for path in authoritative:
            code = "\n".join(
                line for line in path.read_text(encoding="utf-8-sig").splitlines()
                if not line.lstrip().startswith("%")
            )
            self.assertNotRegex(code, r"(?i)\bstart_here\s*\(")
            self.assertNotIn("6.6", code)
            self.assertNotRegex(code.upper(), r"SST-A|SST-B")

        editor = (ROOT / "matlab/triplens_ecms_vpp_editor.m").read_text(encoding="utf-8-sig")
        for route in ('"HV"', '"VH"', '"VHV"', '"HVH"'):
            self.assertIn(route, editor)
        # MATLAB releases that require character-vector name/value tokens
        # otherwise interpret these table options as ordinary data columns.
        self.assertNotRegex(editor, r'table\(\s*"Size"')
        self.assertNotIn('"VariableNames",commandQueue.Properties.VariableNames', editor)
        self.assertIn("table('Size'", editor)
        self.assertIn("'VariableNames',commandQueue.Properties.VariableNames", editor)
        self.assertLess(
            editor.index("fig.AutoResizeChildren = 'off'"),
            editor.index("fig.SizeChangedFcn = @resizeEditor"),
        )
        launcher = (ROOT / "ECMS_START.m").read_text(encoding="utf-8-sig")
        self.assertIn("triplens_ecms_vpp_editor();", launcher)
        self.assertNotRegex(launcher, r"(?m)^\s*triplens_ecms_editor\s*\(")


if __name__ == "__main__":
    unittest.main()
