from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.export_vpp_events import export_events, load_rules
from scripts.generate_vpp_modelica_logic import generate, load_bindings
from scripts.render_pump_fleet_model import transform
from tests.test_pump_physics import MINIMAL_UPSTREAM


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "config" / "vpp_event_logic_provisional.csv"
BINDINGS = ROOT / "config" / "vpp_modelica_signal_bindings.csv"
MATRIX = ROOT / "config" / "common_trip_matrix.csv"
TIMING = ROOT / "config" / "vpp_trip_timing_provisional.csv"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


class VPPEventEngineTests(unittest.TestCase):
    def test_provisional_rules_preserve_current_dcs_values_and_are_auditable(self) -> None:
        _, current = read_csv(ROOT / "config" / "dcs_alarm_rules.csv")
        _, draft = read_csv(RULES)
        by_id = {row["rule_id"]: row for row in draft}
        compared_fields = (
            "system",
            "source_signal",
            "alarm_tag",
            "direction",
            "threshold_mode",
            "threshold_value",
            "hysteresis_value",
            "delay_s",
            "severity",
            "unit",
        )
        self.assertEqual(len(current), 31)
        self.assertEqual(len(draft), 40)
        for current_rule in current:
            draft_rule = by_id[current_rule["rule_id"]]
            for field in compared_fields:
                self.assertEqual(current_rule[field], draft_rule[field])
        self.assertTrue(
            all(row["status"] == "PROVISIONAL_NOT_PLANT_APPROVED" for row in draft)
        )
        self.assertEqual(sum(row["logic_kind"] == "STATE" for row in draft), 9)
        self.assertEqual(sum(row["system"] == "DCS1" for row in draft), 15)
        self.assertEqual(sum(row["system"] == "DCS2" for row in draft), 25)

    def test_modelica_generator_owns_threshold_delay_hysteresis_and_trip_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "TripLens_VPPAlarmRuntime.mo"
            rules = generate(
                rules_path=RULES,
                bindings_path=BINDINGS,
                trip_matrix_path=MATRIX,
                timing_path=TIMING,
                output_path=output,
            )
            model = output.read_text(encoding="utf-8")
        self.assertEqual(sum(rule.kind != "STATE" for rule in rules), 31)
        self.assertIn("TripLens_VPPLogicBlocks.AnalogAlarm analog_D2_104", model)
        self.assertIn("setpoint=0.85", model)
        self.assertIn("hysteresis=0.02", model)
        self.assertIn("pickupDelay=0.5", model)
        self.assertIn(
            "gtTripRequest = alarm_D1_001 or alarm_D2_104 or "
            "alarm_D2_114 or alarm_D2_124",
            model,
        )
        self.assertIn("st_trip_cmd", model)
        blocks = (ROOT / "modelica" / "TripLens_VPPLogicBlocks.mo").read_text()
        self.assertIn("Modelica.Blocks.Logical.Hysteresis", blocks)
        self.assertIn("Modelica.Blocks.Logical.Timer", blocks)

    def test_standardized_csv_can_replace_a_setpoint_without_code_change(self) -> None:
        fields, rows = read_csv(RULES)
        target = next(row for row in rows if row["rule_id"] == "D2-104")
        target["threshold_value"] = "0.8123"
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            updated_rules = temp / "standardized.csv"
            with updated_rules.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            output = temp / "runtime.mo"
            generate(
                rules_path=updated_rules,
                bindings_path=BINDINGS,
                trip_matrix_path=MATRIX,
                timing_path=TIMING,
                output_path=output,
            )
            model = output.read_text(encoding="utf-8")
        self.assertIn("setpoint=0.8123", model)
        self.assertNotIn("setpoint=0.85,\n      hysteresis=0.02,\n      pickupDelay=0.5);\n    TripLens_VPPLogicBlocks.AnalogAlarm analog_D2_111", model)

    def test_pump_model_wires_every_physical_input_into_generated_runtime(self) -> None:
        bindings = {
            binding.source_signal: binding.expression
            for binding in load_bindings(BINDINGS)
        }
        model = transform(
            MINIMAL_UPSTREAM,
            trip_target=1,
            trip_time=300,
            vpp_runtime_bindings=bindings,
        )
        self.assertIn("TripLens_VPPAlarmRuntime.VPPAlarmRuntime alarmRuntime", model)
        self.assertNotIn("CommonDrumTripProtection commonTripProtection", model)
        for source, expression in bindings.items():
            self.assertIn(f"alarmRuntime.{source} = {expression};", model)
        self.assertIn("gtTripRequest = alarmRuntime.gtTripRequest", model)
        self.assertIn("gt52GClosed = alarmRuntime.breaker52GTClosed", model)

    def test_serializer_follows_model_state_not_physical_threshold(self) -> None:
        rules = load_rules(RULES)
        fieldnames = ["time"]
        for rule in rules:
            for column in (rule.state_candidates[0], rule.value_candidates[0]):
                if column not in fieldnames:
                    fieldnames.append(column)

        def base_row(time_s: str) -> dict[str, str]:
            row = {field: "0" for field in fieldnames}
            row["time"] = time_s
            for rule in rules:
                # A FALSE-active state is non-active when the raw CLOSED bit is true.
                row[rule.state_candidates[0]] = "false" if rule.active_when else "true"
                value_column = rule.value_candidates[0]
                if value_column not in {item.state_candidates[0] for item in rules}:
                    row[value_column] = "1"
            return row

        first = base_row("0")
        first["alarmRuntime.hp_drum_level_m"] = "0.70"
        before = base_row("1")
        before["alarmRuntime.hp_drum_level_m"] = "0.70"
        active = base_row("1")
        active["alarmRuntime.alarm_D2_104"] = "true"
        # This value is above both pickup and return setpoints.  The serializer
        # must still emit ACTIVE because Modelica's Boolean state says ACTIVE.
        active["alarmRuntime.hp_drum_level_m"] = "0.90"
        returned = base_row("2")
        returned["alarmRuntime.hp_drum_level_m"] = "0.91"

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "VPP_RAW.csv"
            with raw.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows([first, before, active, returned])
            events = export_events(
                raw_path=raw,
                rules_path=RULES,
                event_path=target / "VPP_EVENT.csv",
                dcs1_path=target / "DCS1_EVENT.csv",
                dcs2_path=target / "DCS2_EVENT.csv",
                snapshot_path=target / "VPP_LOGIC_SNAPSHOT.csv",
                manifest_path=target / "vpp-event-manifest.json",
            )
            validation = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "validate_vpp_event_bundle.py"),
                    "--output-dir",
                    str(target),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            manifest = json.loads(
                (target / "vpp-event-manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(validation.returncode, 0, validation.stderr)
        self.assertEqual([event["event_state"] for event in events], ["ACTIVE", "RETURN"])
        self.assertEqual([event["tag"] for event in events], [
            "HRSG.HP.DRUM.LEVEL.LL", "HRSG.HP.DRUM.LEVEL.LL"
        ])
        self.assertEqual(events[0]["time_s"], "1.000000000")
        self.assertEqual(events[0]["actual_value"], "0.9")
        self.assertEqual(events[0]["setpoint"], "0.85")
        self.assertEqual(events[0]["return_setpoint"], "0.87")
        self.assertEqual(events[0]["system"], "DCS2")
        self.assertEqual(events[0]["display_color"], "#F97316")
        self.assertEqual(events[0]["decision_owner"], "MODELICA_VPP_LOGIC_RUNTIME")
        self.assertFalse(manifest["boundary"]["serializer_recalculates_thresholds"])
        self.assertEqual(manifest["raw"]["duplicate_native_time_rows"], 1)

    def test_action_keeps_event_points_and_bypasses_old_alarm_generator(self) -> None:
        mos = (ROOT / "modelica" / "run_vpp_event_validated.mos.tpl").read_text()
        pipeline = (ROOT / "scripts" / "run_vpp_event_pipeline.sh").read_text()
        self.assertNotIn("-noEventEmit", mos)
        self.assertIn("alarmRuntime\\\\..*", mos)
        self.assertIn("render_vpp_event_validated.py", pipeline)
        self.assertIn("Simulation execution failed", pipeline)
        self.assertIn("export_vpp_events.py", pipeline)
        self.assertNotIn("generate_dcs_alarms.py", pipeline)
        self.assertNotIn("generate_ecms.py", pipeline)
        self.assertIn("cmp -s", pipeline)

    def test_validated_bfp_renderer_wires_the_runtime_and_event_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rendered = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "render_vpp_event_validated.py"),
                    "--event-time", "10",
                    "--coastdown-duration", "5",
                    "--stop-time", "70",
                    "--intervals", "700",
                    "--final-rpm", "1000",
                    "--output-dir", str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            model = (output / "TripLens_CombinedCycle_VPPEvent.mo").read_text()
            mos = (output / "run_vpp_event.mos").read_text()
            runtime = (output / "TripLens_VPPAlarmRuntime.mo").read_text()

        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn("VPP_PHYSICAL_ADAPTER=VALIDATED_BFP_BOUNDARY", rendered.stdout)
        self.assertIn("EVENT_RULES=40", rendered.stdout)
        self.assertIn("TripLens_VPPAlarmRuntime.VPPAlarmRuntime alarmRuntime", model)
        self.assertIn("bfpHPBreakerClosed = not (time >= bfpEventTime)", model)
        self.assertIn("Starttime=bfpEventTime", model)
        self.assertIn("Finalvalue=bfpResidualSpeed", model)
        self.assertIn("alarmRuntime.hp_drum_level_m = BallonHP.yLevel.signal", model)
        self.assertIn('fileNamePrefix="triplens_vpp_event"', mos)
        self.assertIn("output Boolean alarm_D2_104", runtime)


if __name__ == "__main__":
    unittest.main()
