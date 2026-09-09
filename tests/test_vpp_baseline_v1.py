from __future__ import annotations

import csv
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "config" / "vpp_baseline_v1.json"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class VppBaselineV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        cls.settings = {
            row["setting_id"]: row for row in read_csv(ROOT / "config" / "ecms_a_settings.csv")
        }

    def assert_setting(self, key: str, expected: float) -> None:
        self.assertIn(key, self.settings)
        self.assertTrue(math.isclose(float(self.settings[key]["value"]), expected))

    def test_baseline_is_locked_vpp_authority_not_plant_claim(self) -> None:
        self.assertEqual(self.baseline["baseline_id"], "VPP_BASELINE_V1")
        self.assertEqual(self.baseline["status"], "VPP_DESIGN_BASELINE")
        self.assertEqual(self.baseline["authority"]["vpp_design_status"], "LOCKED")
        self.assertEqual(
            self.baseline["authority"]["plant_approval_status"], "NOT_APPLICABLE"
        )

    def test_ratings_match_existing_execution_settings(self) -> None:
        ratings = self.baseline["ratings"]
        self.assertEqual(ratings["gt_power_mw"], 160.0)
        self.assertEqual(ratings["st_power_mw"], 250.0)
        self.assertEqual(ratings["gt_speed_rpm"], 3600.0)
        self.assertEqual(ratings["st_speed_rpm"], 3600.0)
        self.assert_setting("GRID_VOLTAGE_KV", ratings["grid_voltage_kv"])
        self.assert_setting("GT_TERMINAL_VOLTAGE_KV", ratings["generator_terminal_voltage_kv"]["GTG"])
        self.assert_setting("ST_TERMINAL_VOLTAGE_KV", ratings["generator_terminal_voltage_kv"]["STG"])
        self.assert_setting("AUX_BUS_VOLTAGE_KV", ratings["auxiliary_bus_voltage_kv"])
        self.assert_setting("GTG_PRETRIP_POWER_MW", ratings["active_power_mw"]["GTG"])
        self.assertEqual(
            ratings["active_power_mw"]["combined_cycle_reference"],
            ratings["active_power_mw"]["GTG"] + ratings["active_power_mw"]["STG"],
        )
        self.assertEqual(ratings["nominal_speed_rpm"]["FWP-HP"], 1400.0)

    def test_gt_scenario_dynamics_are_explicit(self) -> None:
        self.assertEqual(
            self.baseline["dynamics"],
            {
                "gt_power_decay_s": 0.35,
                "st_power_decay_s": 0.8,
                "gt_coastdown_tau_s": 1.2,
                "st_coastdown_tau_s": 2.5,
            },
        )

    def test_turbine_bypass_topology_is_hp_and_lp_only(self) -> None:
        bypass = self.baseline["turbine_bypass"]
        systems = bypass["systems"]
        self.assertTrue(systems["HPBP"]["installed"])
        self.assertFalse(systems["IPBP"]["installed"])
        self.assertTrue(systems["LPBP"]["installed"])
        self.assertEqual(systems["LPBP"]["bypassed_turbines"], ["IP", "LP"])
        self.assertTrue(systems["LPBP"]["not_lp_drum_steam_dump"])
        self.assertFalse(systems["LP_DRUM_STEAM_DUMP"]["installed"])

        tag_rows = read_csv(ROOT / "data" / "thermo_vpp_full_tag_list.csv")
        bypass_subsystems = {
            row["subsystem"] for row in tag_rows if "BYPASS" in row["subsystem"]
        }
        self.assertEqual(
            bypass_subsystems,
            {"HP_BYPASS", "HOT_REHEAT_LP_BYPASS"},
        )
        self.assertFalse(any(row["tag_id"].startswith("TSP.VLV.08.") for row in tag_rows))

        by_tag = {row["tag_id"]: row for row in tag_rows}
        expected_mappings = {
            "TSP.VLV.07.POS_CMD": "100*vppHPBypassCmd",
            "TSP.VLV.07.POS_FB": "100*vppHPBypassPos",
            "TSP.VLV.07.OPEN_LS": "vppHPBypassOpenLS",
            "TSP.VLV.07.CLOSE_LS": "vppHPBypassCloseLS",
            "TSP.VLV.07.MASS_FLOW": "vppHPBypassMassFlowTH",
            "TSP.VLV.07.P_IN": "vppHPBypassInletPressure",
            "TSP.VLV.07.P_OUT": "vppHPBypassOutletPressure",
            "TSP.VLV.09.POS_CMD": "100*vppLPBypassCmd",
            "TSP.VLV.09.POS_FB": "100*vppLPBypassPos",
            "TSP.VLV.09.OPEN_LS": "vppLPBypassOpenLS",
            "TSP.VLV.09.CLOSE_LS": "vppLPBypassCloseLS",
            "TSP.VLV.09.MASS_FLOW": "vppLPBypassMassFlowTH",
            "TSP.VLV.09.P_IN": "vppLPBypassInletPressure",
            "TSP.VLV.09.P_OUT": "vppLPBypassOutletPressure",
        }
        for tag_id, model_mapping in expected_mappings.items():
            self.assertEqual(by_tag[tag_id]["model_mapping"], model_mapping)
            self.assertNotIn("planned", by_tag[tag_id]["notes"].lower())

    def test_mass_flow_contract_is_tonnes_per_hour_end_to_end(self) -> None:
        unit_contract = self.baseline["unit_contract"]
        self.assertEqual(unit_contract["published_mass_flow_unit"], "t/h")
        self.assertEqual(unit_contract["published_signal_suffix"], "_t_h")
        self.assertEqual(unit_contract["model_to_published_multiplier"], 3.6)
        systems = self.baseline["turbine_bypass"]["systems"]
        self.assertTrue(math.isclose(
            systems["HPBP"]["nominal_steam_flow_t_h"], 151.696 * 3.6
        ))
        self.assertTrue(math.isclose(
            systems["LPBP"]["nominal_steam_flow_t_h"], 176.758 * 3.6
        ))

        signal_map = json.loads(
            (ROOT / "config" / "signal_map.json").read_text(encoding="utf-8")
        )["signals"]
        flow_signals = {
            name: definition for name, definition in signal_map.items()
            if "flow" in name
        }
        self.assertTrue(flow_signals)
        self.assertTrue(all(name.endswith("_t_h") for name in flow_signals))
        self.assertTrue(all(row["unit"] == "t/h" for row in flow_signals.values()))

        runtime_flow_rules = [
            row for row in read_csv(ROOT / "config" / "dcs_alarm_rules.csv")
            if "flow" in row["source_signal"]
        ]
        self.assertTrue(runtime_flow_rules)
        self.assertTrue(all(row["unit"] == "t/h" for row in runtime_flow_rules))

        logic_flow_rules = [
            row for row in read_csv(
                ROOT / "data" / "triplens_A-L_alarm_logic_master_absolute_v2.csv"
            )
            if row["absolute_conversion_status"]
            == "CALIBRATED_MODEL_MASS_FLOW_T_H"
        ]
        self.assertEqual(len(logic_flow_rules), 107)
        self.assertTrue(all(row["threshold_unit"] == "t/h" for row in logic_flow_rules))
        self.assertTrue(all(row["calibration_nominal_value"] == "360" for row in logic_flow_rules))

        public_contract_files = (
            "config/dcs_alarm_rules.csv",
            "config/signal_map.json",
            "config/vpp_baseline_v1.json",
            "config/fwp_hp_rnd_boundary.json",
            "data/ecms_m_links.csv",
            "data/thermo_vpp_full_tag_list.csv",
            "data/thermo_vpp_m_locked_tags.csv",
            "data/triplens_A-L_alarm_logic_master_absolute_v2.csv",
            "topology/turbine_bypass_vpp.svg",
        )
        for relative in public_contract_files:
            self.assertNotIn(
                "kg/s", (ROOT / relative).read_text(encoding="utf-8-sig"), relative
            )

    def test_breaker_and_protection_values_match_execution_settings(self) -> None:
        timing = self.baseline["timing"]
        expected = {
            "TRIP_RECEIVE_DELAY_MS": timing["trip_receive_delay_ms"],
            "LOCKOUT_OPERATE_DELAY_MS": timing["lockout_operate_delay_ms"],
            "GT_BREAKER_OPEN_DELAY_MS": timing["gt_breaker_open_delay_ms"],
            "ST_BREAKER_OPEN_DELAY_MS": timing["st_breaker_open_delay_ms"],
            "MOTOR_BREAKER_OPEN_DELAY_MS": timing["fwp_breaker_open_delay_ms"],
            "FEEDER_FAULT_CURRENT_A": self.baseline["relay"]["fault_current_a"],
            "FEEDER_FAULT_RESIDUAL_VOLTAGE_PU": self.baseline["relay"]["fault_residual_voltage_pu"],
            "FEEDER_50_PICKUP_A": self.baseline["relay"]["element_50"]["pickup_a"],
            "FEEDER_50_DELAY_MS": self.baseline["relay"]["element_50"]["operate_delay_ms"],
            "FEEDER_51_PICKUP_A": self.baseline["relay"]["element_51"]["pickup_a"],
            "FEEDER_51_TIME_MULTIPLIER": self.baseline["relay"]["element_51"]["time_multiplier"],
        }
        for key, value in expected.items():
            self.assert_setting(key, value)

    def test_alarm_catalog_is_complete_and_has_threshold_delay_hysteresis(self) -> None:
        contract = self.baseline["alarms"]
        rows = read_csv(ROOT / contract["rule_catalog"])
        self.assertEqual(len(rows), contract["rule_count"])
        self.assertEqual({row["rule_id"] for row in rows}, set(contract["required_rule_ids"]))
        for row in rows:
            self.assertIn(row["direction"], {"HIGH", "LOW"})
            float(row["threshold_value"])
            self.assertGreaterEqual(float(row["hysteresis_value"]), 0.0)
            self.assertGreaterEqual(float(row["delay_s"]), 0.0)

        by_tag = {row["alarm_tag"]: row for row in rows}
        for drum in ("HP", "IP", "LP"):
            prefix = f"HRSG.{drum}.DRUM.LEVEL"
            h = float(by_tag[f"{prefix}.H"]["threshold_value"])
            hh = float(by_tag[f"{prefix}.HH"]["threshold_value"])
            low = float(by_tag[f"{prefix}.L"]["threshold_value"])
            ll = float(by_tag[f"{prefix}.LL"]["threshold_value"])
            self.assertLess(ll, low)
            self.assertLess(low, h)
            self.assertLess(h, hh)

    def test_active_power_is_measurement_only(self) -> None:
        self.assertNotIn("ST_TRIP_POWER_PU", self.settings)

        alarm_rows = read_csv(ROOT / self.baseline["alarms"]["rule_catalog"])
        self.assertFalse(
            any("POWER" in row["alarm_tag"] for row in alarm_rows),
            "Active Power must not have H/HH/L/LL alarm rules",
        )

        tag_rows = read_csv(ROOT / "data" / "thermo_vpp_full_tag_list.csv")
        tag_ids = {row["tag_id"] for row in tag_rows}
        self.assertIn("TSP.GEN.ACTIVE_POWER", tag_ids)
        self.assertFalse(any(tag.endswith("POWER_LOW_EVT") for tag in tag_ids))

        logic_rows = read_csv(
            ROOT / "data" / "triplens_A-L_alarm_logic_master_absolute_v2.csv"
        )
        self.assertFalse(
            any(
                row["derived_signal"].strip().lower() == "active_power"
                and row["alarm_type"].strip().upper() in {"H", "HH", "L", "LL"}
                for row in logic_rows
            )
        )

        interface_rows = read_csv(
            ROOT / "logic_db" / "sources" / "a_logic_interface_v1.csv"
        )
        self.assertNotIn(
            "stg_low_state", {row["signal_name"] for row in interface_rows}
        )

    def test_trip_coupling_exactly_matches_matrix(self) -> None:
        declared = self.baseline["common_trip"]["rules"]
        rows = read_csv(ROOT / self.baseline["common_trip"]["matrix_source"])
        actual = {
            row["cause_id"]: {
                "gt_trip": row["gt_trip_request"] == "1",
                "st_trip": row["st_trip_request"] == "1",
            }
            for row in rows
        }
        self.assertEqual(actual, declared)

    def test_reset_never_recloses_and_fwp_stop_is_not_trip(self) -> None:
        policies = self.baseline["trip_latch_and_reset"]
        for policy in policies.values():
            self.assertFalse(policy["reset_closes_breaker"])
            self.assertTrue(policy["reclose_requires_separate_close"])
        self.assertFalse(policies["FWP"]["stop_sets_trip_latch"])
        self.assertFalse(policies["FWP"]["stop_opens_breaker"])

    def test_single_entrypoint_declares_existing_source_tables(self) -> None:
        sources = self.baseline["source_configs"]
        self.assertEqual(
            sources["strategy"],
            "BASELINE_JSON_IS_ENTRYPOINT_CSV_FILES_ARE_VALIDATED_EXECUTION_TABLES",
        )
        for key, value in sources.items():
            if key == "strategy":
                continue
            self.assertTrue((ROOT / value).is_file(), f"missing {key}: {value}")
        for logical_path, source_ref in self.baseline["setting_paths"].items():
            source_path = source_ref.split("#", 1)[0]
            self.assertTrue((ROOT / source_path).is_file(), f"{logical_path}: {source_ref}")


if __name__ == "__main__":
    unittest.main()
