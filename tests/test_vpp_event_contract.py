from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.build_vpp_event_bundle import build_bundle, read_csv
from scripts.read_event_feed import read_event_feed
from scripts.validate_vpp_event_bundle import validate_bundle


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "event_contract_v1.json"
RULES = ROOT / "config" / "ecms_event_map_v1.csv"
ACTUAL_ECMS = ROOT / "tests" / "fixtures" / "ecms_fwp_hp_actual_trip_transitions.csv"


class VPPEventContractTests(unittest.TestCase):
    def build_actual(self, target: Path, run_id: str = "RND-ACTION-34322671655"):
        return build_bundle(
            bundle_dir=target,
            run_id=run_id,
            contract_path=CONTRACT,
            ecms_raw=ACTUAL_ECMS,
            ecms_rules=RULES,
        )

    def test_actual_ecms_raw_becomes_transition_only_event_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            events = self.build_actual(bundle)
            report = validate_bundle(bundle, CONTRACT)
            fields, written = read_csv(bundle / "public" / "ECMS_EVENT.csv")

        self.assertEqual(len(events), 9)
        self.assertEqual(len(written), 9)
        self.assertEqual(report["public_files"], ["ECMS_EVENT.csv", "VPP_EVENT.csv"])
        self.assertNotIn("FWP_HP_SPEED_RPM", fields)
        self.assertNotIn("THERMO_FWP_HP_SPEED_INPUT_RPM", fields)
        self.assertFalse(report["raw_published_to_consumers"])

        at_trip = [row for row in events if row["event_time_s"] == "18.000000000"]
        self.assertEqual(len(at_trip), 6)
        self.assertEqual(
            [row["same_time_order"] for row in at_trip],
            ["1", "2", "3", "4", "5", "6"],
        )
        self.assertEqual(at_trip[0]["tag"], "ECMS.FWP-HP.TRIP.REQUEST")
        breaker = next(row for row in events if row["tag"] == "ECMS.VCB-A01.CLOSED")
        self.assertEqual(breaker["event_time_s"], "18.081000000")
        self.assertEqual(breaker["event_time_ns"], "18081000000")
        self.assertEqual(breaker["state"], "OPEN")
        speed = next(row for row in events if row["tag"] == "ECMS.FWP-HP.SPEED.PROVEN")
        self.assertEqual(speed["event_time_s"], "18.100000000")
        self.assertEqual(speed["state"], "LOST")

    def test_identical_timestamps_are_preserved_without_one_tick_shift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "duplicate-native-time.csv"
            rows = []
            _, fixture = read_csv(ACTUAL_ECMS)
            before = dict(fixture[0])
            before["time_s"] = "18.080"
            after = dict(before)
            after["VCB_A01_CLOSED"] = "0"
            rows.extend([before, after])
            with raw.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            events = build_bundle(
                bundle_dir=target / "bundle",
                run_id="DUPLICATE-TIME",
                contract_path=CONTRACT,
                ecms_raw=raw,
                ecms_rules=RULES,
            )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["tag"], "ECMS.VCB-A01.CLOSED")
        self.assertEqual(events[0]["event_time_s"], "18.080000000")
        self.assertEqual(events[0]["same_time_order"], "1")

    def test_alarm_console_and_ai_share_the_same_event_only_reader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            self.build_actual(bundle)
            event_path = bundle / "public" / "ECMS_EVENT.csv"
            alarm = read_event_feed(event_path, CONTRACT, "alarm-console")
            ai = read_event_feed(event_path, CONTRACT, "triplens-ai")
            with self.assertRaisesRegex(ValueError, "accepts VPP_EVENT.csv or ECMS_EVENT.csv only"):
                read_event_feed(ACTUAL_ECMS, CONTRACT, "triplens-ai")

        self.assertEqual(alarm, ai)
        self.assertEqual(len(alarm), 9)

    def test_public_boundary_fails_if_raw_is_added(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            self.build_actual(bundle)
            shutil.copy2(ACTUAL_ECMS, bundle / "public" / "ECMS_RAW.csv")
            with self.assertRaisesRegex(ValueError, "must contain exactly VPP_EVENT.csv and ECMS_EVENT.csv"):
                validate_bundle(bundle, CONTRACT)

    def test_scenario_answer_column_is_rejected_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            fields, rows = read_csv(ACTUAL_ECMS)
            fields.append("expected_root_cause")
            contaminated = target / "contaminated.csv"
            with contaminated.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({**row, "expected_root_cause": "FWP trip"})
            with self.assertRaisesRegex(ValueError, "forbidden answer/RAW columns"):
                build_bundle(
                    bundle_dir=target / "bundle",
                    run_id="LEAK-TEST",
                    contract_path=CONTRACT,
                    ecms_raw=contaminated,
                    ecms_rules=RULES,
                )

    def test_answer_label_aliases_cannot_bypass_the_publication_gate(self) -> None:
        blocked_aliases = ("ScenarioName", "answer_key", "raw_payload_json")
        for blocked_alias in blocked_aliases:
            with self.subTest(blocked_alias=blocked_alias):
                with tempfile.TemporaryDirectory() as directory:
                    target = Path(directory)
                    fields, rows = read_csv(ACTUAL_ECMS)
                    fields.append(blocked_alias)
                    contaminated = target / "contaminated.csv"
                    with contaminated.open("w", encoding="utf-8", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=fields)
                        writer.writeheader()
                        for row in rows:
                            writer.writerow({**row, blocked_alias: "hidden-label"})
                    with self.assertRaisesRegex(
                        ValueError, "forbidden answer/RAW columns"
                    ):
                        build_bundle(
                            bundle_dir=target / "bundle",
                            run_id="LEAK-ALIAS-TEST",
                            contract_path=CONTRACT,
                            ecms_raw=contaminated,
                            ecms_rules=RULES,
                        )

    def test_dcs_and_ecms_sources_merge_into_one_canonical_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            dcs = target / "DCS2_EVENT.csv"
            with dcs.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=[
                    "event_sequence", "event_time_ms", "source_time_ms", "time_s",
                    "system", "tag", "alarm_state", "event_class", "severity",
                    "source_signal", "value", "threshold", "quality", "provenance",
                    "rule_status", "description",
                ])
                writer.writeheader()
                writer.writerow({
                    "event_sequence": "1",
                    "event_time_ms": "18070",
                    "source_time_ms": "18150",
                    "time_s": "18.150",
                    "system": "DCS2",
                    "tag": "HRSG.HP.DRUM.LEVEL.LL",
                    "alarm_state": "ACTIVE",
                    "event_class": "ALARM",
                    "severity": "CRITICAL",
                    "source_signal": "hp_drum_level_m",
                    "value": "0.84",
                    "threshold": "0.85",
                    "quality": "GOOD",
                    "provenance": "MODELICA_LOGIC_STATE",
                    "rule_status": "PROVISIONAL_NOT_PLANT_APPROVED",
                    "description": "HP 드럼 수위 저저",
                })
            events = build_bundle(
                bundle_dir=target / "bundle",
                run_id="MERGE-TEST",
                contract_path=CONTRACT,
                ecms_raw=ACTUAL_ECMS,
                ecms_rules=RULES,
                source_events=[dcs],
            )
            validate_bundle(target / "bundle", CONTRACT)

        self.assertEqual(len(events), 10)
        dcs_event = next(row for row in events if row["system"] == "DCS2")
        self.assertEqual(dcs_event["event_time_s"], "18.150000000")
        self.assertEqual(dcs_event["platform_time_s"], "18.070000000")
        self.assertEqual(dcs_event["event_type"], "PROCESS_ALARM")
        self.assertEqual((dcs_event["old_value"], dcs_event["new_value"]), ("0", "1"))
        self.assertNotIn("value", dcs_event)
        self.assertNotIn("threshold", dcs_event)

    def test_output_is_byte_deterministic_for_the_same_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            first = target / "first"
            second = target / "second"
            self.build_actual(first, "DETERMINISTIC-RUN")
            self.build_actual(second, "DETERMINISTIC-RUN")
            first_bytes = (first / "public" / "ECMS_EVENT.csv").read_bytes()
            second_bytes = (second / "public" / "ECMS_EVENT.csv").read_bytes()

        self.assertEqual(first_bytes, second_bytes)

    def test_final_contract_does_not_depend_on_retired_pr6_physics(self) -> None:
        retired = [
            ROOT / "modelica" / "TripLens_PumpPhysics.mo",
            ROOT / "scripts" / "render_pump_fleet_model.py",
            ROOT / "config" / "pump_physics_registry.csv",
        ]
        self.assertTrue(all(not path.exists() for path in retired))
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["official_outputs"], ["public/VPP_EVENT.csv", "public/ECMS_EVENT.csv"])

    def test_every_ecms_event_uses_a_registered_tag_master_id(self) -> None:
        _, tags = read_csv(ROOT / "data" / "ecms_tag_catalog.csv")
        known = {row["ecms_tag_id"] for row in tags}
        self.assertEqual(len(known), len(tags))
        _, rules = read_csv(RULES)
        breaker = next(row for row in rules if row["rule_id"] == "FWP-HP-012")
        self.assertEqual(breaker["tag"], "ECMS.VCB-A01.CLOSED")
        self.assertEqual(
            {row["tag"] for row in rules}.difference(known),
            set(),
        )

    def test_versioned_example_is_a_valid_event_only_feed(self) -> None:
        example = ROOT / "examples" / "fwp_hp_actual_event_v1" / "EVENT.csv"
        fields, rows = read_csv(example)
        from scripts.build_vpp_event_bundle import validate_events
        validate_events(fields, rows, json.loads(CONTRACT.read_text(encoding="utf-8")))
        self.assertEqual(len(rows), 9)
        self.assertEqual({row["system"] for row in rows}, {"ECMS"})

    def test_workflow_uploads_public_event_and_internal_raw_separately(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "validate-vpp-event-contract.yml"
        ).read_text(encoding="utf-8")
        public_step = workflow.split("Upload Alarm Console and AI input only", 1)[1]
        public_step = public_step.split("Upload internal evidence separately", 1)[0]
        self.assertIn("outputs/vpp-final/public/VPP_EVENT.csv", public_step)
        self.assertIn("outputs/vpp-final/public/ECMS_EVENT.csv", public_step)
        self.assertNotIn("RAW", public_step)
        self.assertNotIn("internal/", public_step)
        self.assertIn("outputs/vpp-final/internal/", workflow)


if __name__ == "__main__":
    unittest.main()
