from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from native_ecms_opcua_client import (  # noqa: E402
    COMMAND_NODES,
    DelayedLowAlarm,
    EVENT_SPECS,
    PROTOCOL,
    SIGNALS,
    build_native_events,
    lp_bfp_closed_loop_complete,
    load_lp_rules,
    validate_lp_bfp,
)


class NativeOPCUAContractTests(unittest.TestCase):
    def test_inventory_and_configured_lp_rules(self) -> None:
        self.assertEqual(PROTOCOL, "TRIPLENS-NATIVE-OPCUA/1")
        self.assertGreaterEqual(len(SIGNALS), 62)
        low, low_low, trips_gt, trips_st = load_lp_rules()
        self.assertEqual((low.threshold, low_low.threshold), (1.65, 1.55))
        self.assertEqual((low.delay_s, low_low.delay_s), (0.5, 0.5))
        self.assertTrue(trips_gt and trips_st)

    def test_low_alarm_delay_and_hysteresis(self) -> None:
        alarm = DelayedLowAlarm(1.55, 0.02, 0.5)
        self.assertFalse(alarm.update(1.0, 1.54))
        self.assertFalse(alarm.update(1.49, 1.54))
        self.assertTrue(alarm.update(1.50, 1.54))
        self.assertTrue(alarm.update(1.60, 1.56))
        self.assertFalse(alarm.update(1.70, 1.57))

    def test_validator_requires_complete_lp_closed_loop(self) -> None:
        def row(t: float, tripped: bool):
            values = {signal.field: 0.0 for signal in SIGNALS}
            values.update({
                "time_s": t,
                "lp_fwp_trip_command_readback": int(tripped),
                "lp_fwp_trip_latch_readback": int(tripped),
                "vcb_a02_trip_command_readback": int(tripped),
                "vcb_a02_closed_readback": int(not tripped),
                "lp_fwp_motor_energized": int(not tripped),
                "lp_fwp_speed_rpm": 500.0 if tripped else 1400.0,
                "lp_fwp_hydraulic_speed_rpm": 700.0 if tripped else 1400.0,
                "lp_fwp_mass_flow_th": 100.0 if tripped else 700.0,
                "lp_fwp_check_valve_open": int(not tripped),
                "lp_fwp_check_valve_opening": 0.01 if tripped else 1.0,
                "lp_drum_level_m": 1.45 if tripped else 1.75,
                "lp_drum_level_l_alarm": int(tripped),
                "lp_drum_level_ll_alarm": int(tripped),
                "common_gt_trip_request": int(tripped),
                "common_st_trip_request": int(tripped),
                "gt_trip_command_readback": int(tripped),
                "gt_trip_latch": int(tripped),
                "st_trip_latch": int(tripped),
                "gt_breaker_trip_command": int(tripped),
                "st_breaker_trip_command": int(tripped),
                "gt_breaker_closed": int(not tripped),
                "st_breaker_closed": int(not tripped),
                "lp_fwp_speed_proven": int(not tripped),
                "lp_fwp_running": int(not tripped),
                "hp_admission_position_pu": 0.01 if tripped else 0.8,
                "ip_admission_position_pu": 0.01 if tripped else 0.8,
                "lp_admission_position_pu": 0.01 if tripped else 1.0,
                "hp_bypass_position_pu": 1.0 if tripped else 0.0,
                "lp_bypass_position_pu": 1.0 if tripped else 0.0,
                "hp_spray_position_pu": 1.0 if tripped else 0.0,
                "lp_spray_position_pu": 1.0 if tripped else 0.0,
                "gtg_power_mw": 0.0 if tripped else 160.0,
                "gtg_speed_rpm": 3500.0 if tripped else 3600.0,
            })
            return values

        passing_rows = [row(0.1, False), row(5.0, True), row(35.0, True)]
        report = validate_lp_bfp(passing_rows, 0.2, 30.0)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(lp_bfp_closed_loop_complete(row(5.0, True)))
        self.assertEqual(report["termination_reason"], "GT_TRIP_PLUS_30_SECONDS")
        self.assertEqual(report["post_gt_trip_observation_s"], 30.0)
        events = build_native_events(passing_rows, 0.2)
        self.assertEqual(
            {event["canonical_tag"] for event in events},
            {spec.tag for spec in EVENT_SPECS},
        )
        bad = validate_lp_bfp([row(0.1, False), row(5.0, False)], 0.2, 30.0)
        self.assertEqual(bad["status"], "FAIL")
        self.assertFalse(lp_bfp_closed_loop_complete(row(5.0, False)))

    def test_native_adapter_owns_vcb_a02_to_pump_boundary(self) -> None:
        source = (ROOT / "scripts/patch_lp_fwp_opcua.py").read_text(encoding="utf-8")
        for name in (
            COMMAND_NODES["lp_fwp_trip_command_readback"],
            COMMAND_NODES["lp_fwp_trip_latch_readback"],
            COMMAND_NODES["vcb_a02_trip_command_readback"],
            COMMAND_NODES["vcb_a02_closed_readback"],
        ):
            self.assertIn(name, source)
        self.assertIn("TripLens_PumpPhysics.BreakerInertialPumpDrive", source)
        self.assertIn("TripLens_PumpPhysics.SpringLoadedCheckValve", source)
        self.assertIn(
            "connect(vppLPFWPHydraulicSpeedCommand, PompeAlimBP.rpm_or_mpower)",
            source,
        )
        self.assertIn("vppLPFWPHydraulicSpeedFloorRPM", source)
        self.assertIn("connect(PompeAlimBP.C2, vppLPFWPCheckValve.C1)", source)
        self.assertIn("connect(vppLPFWPCheckValve.C2, vanne_extraction.C1)", source)
        self.assertNotIn("fmuVlvCondExtractionTarget*vppLPFWPDischargeMultiplier", source)
        self.assertIn("vppLPFWPMassFlowTH = 3.6*PompeAlimBP.Q", source)

        package = (ROOT / "modelica/TripLens_PumpPhysics.mo").read_text(
            encoding="utf-8"
        )
        self.assertIn("model BreakerInertialPumpDrive", package)
        self.assertIn("model SpringLoadedCheckValve", package)
        self.assertIn("opening = noEvent(max(0, min(1, openingState)))", package)

    def test_tag_contract_has_all_63_scenario_tags(self) -> None:
        path = ROOT / "data/opcua_lp_bfp_nodes_v1.csv"
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 63)
        self.assertEqual(len({row["canonical_tag"] for row in rows}), 63)
        tags = {row["canonical_tag"]: row for row in rows}
        self.assertEqual(tags["ECMS.VCB-A02.CLOSED"]["direction"], "WRITE")
        self.assertEqual(tags["TSP.FWP-LP.SPEED_RPM"]["direction"], "READ")
        self.assertEqual(
            tags["TSP.FWP-LP.HYDRAULIC_SPEED_RPM"]["layer"],
            "NUMERICAL_ADAPTER",
        )
        self.assertEqual(
            tags["TSP.FWP-LP.DISCHARGE_CHECK_VALVE.OPEN"]["direction"], "READ"
        )
        self.assertEqual(tags["HRSG.LP.DRUM.LEVEL.LL"]["direction"], "DERIVED")

    def test_workflow_builds_and_runs_lp_scenario(self) -> None:
        workflow = (ROOT / ".github/workflows/run-native-opcua-ecms.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("-embeddedServer=opc-ua", workflow)
        self.assertIn('LIVE_STOP_TIME_S: "120"', workflow)
        self.assertIn('LIVE_STEP_SIZE_S: "0.04"', workflow)
        self.assertIn('LIVE_COMMAND_TIME_S: "20"', workflow)
        self.assertIn('LIVE_POST_GT_TRIP_S: "30"', workflow)
        self.assertIn("--intervals 3000", workflow)
        self.assertNotIn("scripts/patch_fmu_valve_controls.py", workflow)
        self.assertIn("scripts/patch_lp_fwp_opcua.py", workflow)
        self.assertIn("scripts/patch_all_fwp_check_valves.py", workflow)
        self.assertIn("modelica/TripLens_PumpPhysics.mo", workflow)
        build = (ROOT / "modelica/build_native_opcua.mos.tpl").read_text(
            encoding="utf-8"
        )
        self.assertIn('loadFile("/workspace/modelica/TripLens_PumpPhysics.mo")', build)
        self.assertIn("--scenario lp-bfp-trip", workflow)
        self.assertIn('--command-time "$LIVE_COMMAND_TIME_S"', workflow)
        self.assertIn('--post-gt-trip-seconds "$LIVE_POST_GT_TRIP_S"', workflow)
        self.assertIn("-s=ida", workflow)
        self.assertIn("-nls=kinsol", workflow)
        self.assertIn('docker rm -f "$native_container"', workflow)
        self.assertIn('"vppVCBA02ClosedNative"', workflow)
        self.assertNotIn("live_fmu_gateway.py", workflow)

    def test_client_uses_stable_native_step_nodes(self) -> None:
        source = (ROOT / "scripts/native_ecms_opcua_client.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ua.NodeId(10000, 0)", source)
        self.assertIn("ua.NodeId(10004, 0)", source)
        self.assertIn("motor_feeder_state", source)
        self.assertIn("breaker_open_delay_ms=80", source)
        self.assertIn("ua.VariantType.Double", source)


if __name__ == "__main__":
    unittest.main()
