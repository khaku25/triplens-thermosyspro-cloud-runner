from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common_trip import load_common_trip_matrix, resolve_common_trips


class TripContractTests(unittest.TestCase):
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

    @staticmethod
    def run_script(name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def basic_processbus(self, path: Path, extra: dict[str, list[object]] | None = None) -> None:
        extra = extra or {}
        times = [index / 100 for index in range(201)]
        rows: list[dict[str, object]] = []
        for index, time_s in enumerate(times):
            row: dict[str, object] = {
                "scenario_id": "CONTRACT_TEST",
                "time_s": f"{time_s:.2f}",
                "stg_power_w": 250_000_000,
            }
            for field, values in extra.items():
                row[field] = values[index]
            rows.append(row)
        self.write_csv(path, rows)

    def generate_ecms(
        self,
        target: Path,
        processbus: Path,
        *extra: str,
        event_time: str = "1",
    ) -> tuple[Path, Path, Path]:
        trend = target / "trend.csv"
        events = target / "events.csv"
        feeders = target / "feeders.csv"
        result = self.run_script(
            "generate_ecms.py",
            "--processbus", str(processbus),
            "--event-time", event_time,
            "--sampling-profile", "incident_1ms",
            "--incident-pre-ms", "1000",
            "--incident-post-ms", "1000",
            "--trend-output", str(trend),
            "--event-output", str(events),
            "--feeder-output", str(feeders),
            *extra,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return trend, events, feeders

    def test_exact_bfp_raw_headers_resolve_to_one_canonical_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "bfp-raw.csv"
            rows = [
                {
                    "time_s": time_s,
                    "SIM.FWP_HP_TRIP": trip,
                    "FWP_HP.RUN_ENABLE": 1 - trip,
                    "VCB_A01_TRIP_CMD": trip,
                    "VCB-A01.CLOSED": 1 - opened,
                    "FWP_HP.TRIP_LATCH": trip,
                    "FWP_HP.RUN_FB": 1 - trip,
                    "FWP_HP.SPEED_RPM": rpm,
                    "FWP_HP.SPEED_PROVEN": 1 - opened,
                    "FWP_HP.STATE_CODE": 5 if trip else 3,
                    "FWP_HP.TRIPPED": trip,
                    "ECMS.BUS-A.VOLTAGE": 6.9,
                    "quality": "GOOD",
                }
                for time_s, trip, opened, rpm in (
                    (0, 0, 0, 1390.59),
                    (1, 1, 0, 1390.59),
                    (1.08, 1, 1, 1283.62),
                    (5, 0, 1, 25.42),
                )
            ]
            self.write_csv(raw, rows)
            before = hashlib.sha256(raw.read_bytes()).hexdigest()
            processbus = target / "ProcessBus.csv"
            review = target / "review.json"
            result = self.run_script(
                "normalize_processbus.py",
                "--input", str(raw),
                "--output", str(processbus),
                "--mapping-review", str(review),
                "--event-time", "1",
                "--no-legacy-gt-trip-cmd",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), before)
            first = self.read_csv(processbus)[0]
            expected = {
                "quality", "fwp_hp_trip_input", "fwp_hp_run_enable",
                "fwp_hp_vcb_trip_cmd", "fwp_hp_vcb_closed", "fwp_hp_trip_latch",
                "fwp_hp_run_cmd_feedback", "fwp_hp_speed_rpm",
                "fwp_hp_speed_proven", "fwp_hp_state_code", "fwp_hp_tripped",
                "ecms_bus_a_voltage_kv",
            }
            self.assertTrue(expected.issubset(first))
            metadata = json.loads(review.read_text(encoding="utf-8"))
            self.assertTrue(expected.issubset(metadata["canonical_signals_present"]))

    def test_gt_trip_intertrips_st_before_st_power_falls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = target / "processbus.csv"
            self.basic_processbus(processbus)
            trend, events, _ = self.generate_ecms(target, processbus)
            event_rows = self.read_csv(events)
            by_tag = {row["tag"]: int(row["source_time_ms"]) for row in event_rows}
            self.assertEqual(by_tag["GT.TRIP.REQUEST"], 1000)
            self.assertEqual(by_tag["ST.TRIP.REQUEST"], 1000)
            self.assertEqual(by_tag["52ST.TRIP.CMD"], 1000)
            self.assertEqual(by_tag["52GT.CLOSED"], 1080)
            self.assertEqual(by_tag["52ST.CLOSED"], 1100)
            row = next(row for row in self.read_csv(trend) if row["source_time_ms"] == "1100")
            self.assertNotIn("stg_low_state", row)
            self.assertEqual(row["cb_52st_closed"], "0")

    def test_every_common_trip_cause_resolves_the_declared_gt_st_requests(self) -> None:
        rules = load_common_trip_matrix(ROOT / "config/common_trip_matrix.csv")
        expected = {
            "DIRECT_GT_TRIP": (1000, 1000),
            "DIRECT_ST_TRIP": (None, 1000),
            "HP_DRUM_HH": (None, 1000),
            "IP_DRUM_HH": (None, 1000),
            "LP_DRUM_HH": (None, 1000),
            "HP_DRUM_LL": (1000, 1000),
            "IP_DRUM_LL": (1000, 1000),
            "LP_DRUM_LL": (1000, 1000),
        }
        for rule in rules:
            with self.subTest(cause=rule.cause_id):
                rows = [{"time_s": "0"}, {"time_s": "1"}]
                commands: list[dict[str, str]] = []
                if rule.source_layer == "COMMAND":
                    commands.append({
                        "time_s": "1",
                        "equipment_id": "GTG" if rule.source_signal == "gt_trip_cmd" else "STG",
                        "command": "TRIP",
                    })
                else:
                    rows[0][rule.source_signal] = "0"
                    rows[1][rule.source_signal] = "1"
                resolution = resolve_common_trips(
                    rules,
                    rows,
                    commands,
                    [],
                    scenario_gt_trip_ms=None,
                )
                self.assertEqual(
                    (resolution.gt_request_ms, resolution.st_request_ms),
                    expected[rule.cause_id],
                )
                if expected[rule.cause_id][0] is not None:
                    self.assertIn(rule.cause_id, resolution.gt_causes)
                if expected[rule.cause_id][1] is not None:
                    self.assertIn(rule.cause_id, resolution.st_causes)

    def test_drum_ll_matrix_trips_gt_and_st_without_direct_gt_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = target / "processbus.csv"
            values = [0] * 100 + [1] * 101
            self.basic_processbus(processbus, {"hp_drum_level_ll": values})
            _, events, _ = self.generate_ecms(
                target, processbus, "--no-scenario-gt-trip"
            )
            rows = self.read_csv(events)
            tags = {row["tag"]: row for row in rows}
            self.assertNotIn("GT.TRIP.CMD", tags)
            self.assertIn("HP_DRUM_LL", tags["GT.TRIP.REQUEST"]["description"])
            self.assertIn("HP_DRUM_LL", tags["ST.TRIP.REQUEST"]["description"])
            self.assertEqual(tags["52GT.CLOSED"]["source_time_ms"], "1080")
            self.assertEqual(tags["52ST.CLOSED"]["source_time_ms"], "1100")

    def test_fwp_stop_keeps_vcb_closed_and_trip_requires_reset_then_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = target / "processbus.csv"
            self.basic_processbus(processbus)
            catalog = self.read_csv(ROOT / "config/ecms_command_catalog.csv")
            lookup = {(row["equipment_id"], row["command"]): row for row in catalog}
            specifications = [
                (1, 0.50, "FWP-HP", "STOP"),
                (2, 0.70, "FWP-HP", "START"),
                (3, 1.00, "FWP-HP", "TRIP"),
                (4, 1.20, "FWP-HP", "RESET"),
                (5, 1.30, "VCB-A01", "CLOSE"),
                (6, 1.40, "FWP-HP", "START"),
            ]
            queue = []
            for sequence, time_s, equipment_id, command in specifications:
                definition = lookup[(equipment_id, command)]
                queue.append({
                    "sequence": sequence,
                    "time_s": time_s,
                    "equipment_id": equipment_id,
                    "equipment_label": definition["label_ko"],
                    "command": command,
                    "command_value": definition["default_value"],
                    "unit": definition["unit"],
                    "execution_layer": definition["execution_layer"],
                    "model_input": definition["model_input"],
                    "feedback_tag": definition["feedback_tag"],
                    "status": "QUEUED",
                    "note": "contract test",
                })
            commands = target / "commands.csv"
            self.write_csv(commands, queue)
            _, _, feeders = self.generate_ecms(
                target, processbus, "--no-scenario-gt-trip", "--commands", str(commands)
            )
            rows = {
                row["source_time_ms"]: row
                for row in self.read_csv(feeders) if row["equipment_id"] == "FWP-HP"
            }
            self.assertEqual(rows["500"]["breaker_closed"], "1")
            self.assertEqual(rows["500"]["run_enable"], "0")
            self.assertEqual(rows["700"]["breaker_closed"], "1")
            self.assertEqual(rows["700"]["run_enable"], "1")
            self.assertEqual(rows["1000"]["breaker_closed"], "1")
            self.assertEqual(rows["1000"]["trip_latched"], "1")
            self.assertEqual(rows["1080"]["breaker_closed"], "0")
            self.assertEqual(rows["1200"]["trip_latched"], "0")
            self.assertEqual(rows["1200"]["breaker_closed"], "0")
            self.assertEqual(rows["1300"]["breaker_closed"], "1")
            self.assertEqual(rows["1400"]["run_enable"], "1")

    def test_one_ms_logic_clock_uses_sample_hold_not_fake_interpolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "p.csv"
            self.write_csv(raw, [
                {"time_s": 0.9, "x": 1, "quality": "GOOD"},
                {"time_s": 1.0, "x": 0, "quality": "GOOD"},
                {"time_s": 1.1, "x": 0, "quality": "GOOD"},
                {"time_s": 1.2, "x": 0, "quality": "GOOD"},
                {"time_s": 1.3, "x": 0, "quality": "GOOD"},
            ])
            rules = target / "rules.csv"
            self.write_csv(rules, [{
                "rule_id": "T-1", "system": "DCS2", "source_signal": "x",
                "alarm_tag": "X.L", "description_ko": "test", "direction": "LOW",
                "threshold_mode": "ABSOLUTE", "threshold_value": 0,
                "hysteresis_value": 0, "delay_s": 0.205, "severity": "WARNING",
                "unit": "-", "status": "TEST", "calibration_basis": "test",
            }])
            metadata = target / "meta.json"
            metadata.write_text("{}\n", encoding="utf-8")
            result = self.run_script(
                "generate_dcs_alarms.py",
                "--incident-raw", str(raw),
                "--metadata", str(metadata),
                "--rules", str(rules),
                "--trip-time", "1",
                "--logic-period-ms", "1",
                "--dcs1-output", str(target / "DCS1.csv"),
                "--dcs2-output", str(target / "DCS2.csv"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            event = self.read_csv(target / "DCS2.csv")[0]
            self.assertEqual(event["source_time_ms"], "1205")
            summary = json.loads(metadata.read_text(encoding="utf-8"))["alarm_summary"]
            self.assertEqual(summary["input_timing_policy"], "ZERO_ORDER_HOLD_BETWEEN_SOURCE_SAMPLES")

    def test_provisional_feeder_fault_runs_50_and_51_to_vcb_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = target / "processbus.csv"
            self.basic_processbus(processbus)
            _, events, feeders = self.generate_ecms(
                target,
                processbus,
                "--no-scenario-gt-trip",
                "--fault-preset", "fwp_hp_feeder_fault",
            )
            tags = {row["tag"]: row for row in self.read_csv(events)}
            self.assertEqual(tags["50FWP-HP.OPERATE"]["source_time_ms"], "1015")
            self.assertEqual(tags["VCB-A01.TRIP.CMD"]["source_time_ms"], "1015")
            self.assertEqual(tags["VCB-A01.CLOSED"]["source_time_ms"], "1095")
            rows = {
                row["source_time_ms"]: row
                for row in self.read_csv(feeders) if row["equipment_id"] == "FWP-HP"
            }
            self.assertEqual(rows["1000"]["fault_current_a"], "12000.000000")
            self.assertEqual(rows["1000"]["terminal_voltage_kv"], "1.380000")
            self.assertEqual(rows["1095"]["breaker_closed"], "0")
            self.assertEqual(rows["1095"]["fault_current_a"], "0.000000")

    def test_removed_equipment_is_absent_from_executable_contracts(self) -> None:
        removed = {"CW-PUMP", "COND-PUMP", "RECIRC-HP", "RECIRC-IP", "RECIRC-LP"}
        for relative, field in (
            ("config/ecms_a_equipment.csv", "equipment_id"),
            ("config/ecms_command_catalog.csv", "equipment_id"),
            ("data/ecms_m_links.csv", "ecms_equipment_id"),
        ):
            values = {row[field] for row in self.read_csv(ROOT / relative)}
            self.assertFalse(removed & values, relative)
        topology = (ROOT / "topology/triplens_ecms_6p9kv.svg").read_text(encoding="utf-8")
        for equipment_id in removed:
            self.assertNotIn(equipment_id, topology)


if __name__ == "__main__":
    unittest.main()
