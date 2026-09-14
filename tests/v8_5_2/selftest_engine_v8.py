#!/usr/bin/env python3
"""Offline contract tests for the V8 collector/dashboard snapshot."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import tempfile
from pathlib import Path
from types import SimpleNamespace


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("trip_engine_v8", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeVariant:
    def __init__(self, value, variant_type):
        self.Value = value
        self.VariantType = variant_type


class FakeUA:
    class VariantType:
        Double = "Double"
        Boolean = "Boolean"

    Variant = FakeVariant


class FakeNode:
    def __init__(self, value):
        self.value = value
        self.writes = []

    def get_value(self):
        return self.value

    def set_value(self, variant):
        self.writes.append(variant)
        self.value = variant.Value


class FakeLive:
    @staticmethod
    def scalar(value):
        return value


def test_snapshot(module) -> None:
    engine = object.__new__(module.AlarmEngine)
    engine.alarm_rules = [
        {"source_node": "vppLPDrumLevelM", "unit": "m"},
    ]
    engine.last_historian_values = {"vppLPDrumLevelM": 1.70}
    engine.last_model_time = 42.0
    raw = {name: 0.0 for name in module.PROTECTION_REQUIRED_NODES}
    raw.update({
        "time": 42.0,
        "vppLPDrumLevelM": 1.54,
        "vppVlvHPFWCVOpening": 0.8,
        "vppLPFWPSpeedRPM": 3600.0,
        "vppCauseLPDrumLL": 1.0,
        "vppGTTripRequest": 1.0,
        "vppGTTripLatch": 1.0,
        "vpp52GTTripCmd": 1.0,
        "vpp52GTClosed": 0.0,
    })
    module.AlarmEngine.update_live_snapshot_rows(engine, raw)
    if len(engine.historian_rows) != len(raw):
        raise AssertionError("full numeric historian was not published")
    if len(engine.protection_matrix) != 9:
        raise AssertionError("common trip matrix must expose 9 causes")
    lp_ll = next(row for row in engine.protection_matrix if row["cause"] == "LP_DRUM_LL")
    if not lp_ll["active"] or lp_ll["domain"] != "GT+ST":
        raise AssertionError("LP drum LL matrix route is wrong")
    expected_chains = {"GT", "ST", "HP FWP", "IP FWP"}
    if {row["domain"] for row in engine.protection_chain} != expected_chains:
        raise AssertionError("GT/ST/HP FWP/IP FWP protection chains are incomplete")
    gt = next(row for row in engine.protection_chain if row["domain"] == "GT")
    if gt["state"] != "OPEN" or gt["request"] != 1.0:
        raise AssertionError("GT chain values do not reflect RAW")
    level = next(row for row in engine.historian_rows if row["name"] == "vppLPDrumLevelM")
    if level["group"] != "Process" or level["unit"] != "m" or not level["changed"]:
        raise AssertionError("historian metadata/change flag is wrong")
    valve = next(row for row in engine.historian_rows if row["name"] == "vppVlvHPFWCVOpening")
    if valve["group"] != "Valve" or valve["kind"] != "Analog":
        raise AssertionError("functional historian grouping is wrong")
    encoded = json.dumps(module.json_primitive({
        "rows": engine.historian_rows,
        "nan": math.nan,
        "path": Path("x"),
    }), allow_nan=False)
    if '"nan": ""' not in encoded:
        raise AssertionError("non-finite values are not JSON-safe")


def test_model_time_alarm_delay(module) -> None:
    engine = object.__new__(module.AlarmEngine)
    rule = {
        "rule_id": "DELAYED_LOW",
        "event_class": "ALARM",
        "priority": "HIGH",
        "equipment": "TEST",
        "tag": "LOW",
        "source_node": "value",
        "active_when": "LOW",
        "active_threshold": 5.0,
        "return_threshold": 6.0,
        "delay_s": 0.5,
        "unit": "m",
        "active_message": "ACTIVE",
        "return_message": "RETURN",
    }
    engine.alarm_rules = [rule]
    engine.rule_baselines = {}
    engine.rule_conditions = {}
    engine.rule_pending_since = {}
    engine.rule_reported_active = set()
    engine.alarm_coverage = [{"state": "BASELINING", "pending_s": 0.0}]
    emitted = []
    engine.add_event = lambda *args, **kwargs: emitted.append((args, kwargs))
    engine.last_model_time = 0.0
    engine.evaluate_registry({"value": 10.0})
    engine.last_model_time = 1.0
    engine.evaluate_registry({"value": 4.0})
    engine.last_model_time = 1.49
    engine.evaluate_registry({"value": 4.0})
    if emitted or engine.alarm_coverage[0]["state"] != "PENDING":
        raise AssertionError("alarm asserted before model-time delay elapsed")
    engine.last_model_time = 1.50
    engine.evaluate_registry({"value": 4.0})
    engine.last_model_time = 2.0
    engine.evaluate_registry({"value": 7.0})
    if len(emitted) != 2 or emitted[0][0][4] != "ACTIVE" or emitted[1][0][4] != "RETURN":
        raise AssertionError("delayed ACTIVE/RETURN transition failed")


def test_watchdog(module) -> None:
    engine = object.__new__(module.AlarmEngine)
    nodes = {
        "run": FakeNode(False),
        "real_time_factor": FakeNode(0.0),
        "enable_stop_time": FakeNode(True),
        "model_time": FakeNode(100.0),
    }
    engine.args = SimpleNamespace(
        watchdog_cooldown_s=10.0,
        watchdog_stall_s=3.0,
        watchdog_keep_stop_time=False,
        real_time_factor=1.0,
    )
    engine.live = FakeLive()
    engine.ua = FakeUA
    engine.runtime_control_nodes = nodes
    engine.watchdog_enabled = True
    engine.watchdog_supported = True
    engine.watchdog_state = "FROZEN"
    engine.watchdog_last_result = "NEVER"
    engine.watchdog_error = ""
    engine.watchdog_attempt_count = 0
    engine.watchdog_success_count = 0
    engine.watchdog_last_attempt_monotonic = -math.inf
    engine.watchdog_last_attempt_utc = ""
    engine.watchdog_resume_reference_time = None
    engine.last_model_time = 100.0
    engine.model_time_stalled_s = 4.0
    engine.internal_audit = lambda *args, **kwargs: None
    if not engine.resume_runtime(force=True):
        raise AssertionError("manual runtime resume was not sent")
    if nodes["run"].value is not True or nodes["enable_stop_time"].value is not False:
        raise AssertionError("watchdog did not set Run/stopTime controls")
    if nodes["real_time_factor"].value != 1.0:
        raise AssertionError("watchdog real-time factor is wrong")
    if nodes["model_time"].writes:
        raise AssertionError("watchdog must never write/fake model time")
    engine.observed_model_time = 100.0
    engine.model_time_changed_wall = 0.0
    engine.observe_model_time(101.0)
    if engine.watchdog_success_count != 1 or engine.watchdog_last_result != "RESUMED":
        raise AssertionError("watchdog resume success was not observed")


def test_pump_operator_controls(module) -> None:
    engine = object.__new__(module.AlarmEngine)
    writes = []
    waits = []
    engine.write_input = lambda name, value: writes.append((name, value)) or value
    engine.wait_chain = lambda expected, timeout_s=30.0: waits.append(dict(expected))

    engine.execute_pump_trip("HP")
    hp = module.PUMP_CONTROL_SIGNALS["HP"]
    if writes != [(hp["trip_pb"], 1.0), (hp["trip_pb"], 0.0)]:
        raise AssertionError("HP trip PB is not a safe momentary pulse")
    if waits != [{
        hp["trip_cmd"]: 1.0,
        hp["latch"]: 1.0,
        hp["breaker_trip_cmd"]: 1.0,
        hp["breaker_closed"]: 0.0,
    }]:
        raise AssertionError("HP trip chain proof is incomplete")

    writes.clear()
    engine.wait_chain = lambda expected, timeout_s=30.0: (_ for _ in ()).throw(RuntimeError("proof failed"))
    try:
        engine.execute_pump_trip("LP")
    except RuntimeError:
        pass
    else:
        raise AssertionError("failed trip proof did not propagate")
    lp = module.PUMP_CONTROL_SIGNALS["LP"]
    if writes != [(lp["trip_pb"], 1.0), (lp["trip_pb"], 0.0)]:
        raise AssertionError("failed trip proof left the LP PB asserted")

    writes.clear()
    waits.clear()
    engine.wait_chain = lambda expected, timeout_s=30.0: waits.append(dict(expected))
    engine.execute_pump_reset("IP")
    ip = module.PUMP_CONTROL_SIGNALS["IP"]
    expected_writes = [
        (ip["trip_pb"], 0.0),
        (ip["breaker_command"], 0.0),
        (ip["reset_pb"], 1.0),
        (ip["reset_pb"], 0.0),
        (ip["breaker_command"], 1.0),
    ]
    if writes != expected_writes:
        raise AssertionError(f"IP safe reset/reclose order is wrong: {writes}")
    if waits != [
        {ip["breaker_closed"]: 0.0},
        {ip["trip_cmd"]: 0.0, ip["latch"]: 0.0, ip["breaker_trip_cmd"]: 0.0},
        {ip["breaker_closed"]: 1.0},
    ]:
        raise AssertionError("IP reset chain proof is incomplete")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    module = load_module(args.engine)
    rules = module.load_alarm_registry(args.registry)
    if len(rules) != 67:
        raise AssertionError(f"plant-wide registry must retain 67 rules, got {len(rules)}")
    test_snapshot(module)
    test_model_time_alarm_delay(module)
    test_watchdog(module)
    test_pump_operator_controls(module)
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "snapshot.json"
        module.atomic_json(target, {"nan": math.nan, "ok": True})
        loaded = json.loads(target.read_text(encoding="utf-8"))
        if loaded != {"nan": "", "ok": True}:
            raise AssertionError("atomic strict JSON conversion failed")
    result = {
        "status": "PASS",
        "alarm_rules": len(rules),
        "historian_rows": "FULL",
        "protection_matrix_causes": 9,
        "protection_chains": 4,
        "alarm_delay_clock": "MODEL_TIME",
        "watchdog_model_time_writes": 0,
        "manual_resume_action": "RESUME_RUNTIME",
        "operator_pump_trains": list(module.PUMP_CONTROL_SIGNALS),
        "safe_reset_sequence": True,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
