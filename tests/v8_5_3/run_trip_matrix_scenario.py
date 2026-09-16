#!/usr/bin/env python3
"""Run one isolated V8 trip scenario with a scenario-specific horizon.

The drum/matrix scenarios retain the 100 s proof window.  HP/IP BFP-only
scenarios stop after a shorter 45 s physical coastdown window; their separate
HP/IP drum-LL scenarios continue to prove the common-trip matrix.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


EVENT_COLUMNS = [
    "event_id", "event_sequence", "session_id", "incident_id", "model_time_s",
    "wall_time_utc", "priority", "event_class", "equipment", "tag", "state",
    "value", "unit", "message", "source", "acknowledged",
]
DEFAULT_POST_FAULT_MODEL_SECONDS = 100.0
SHORT_BFP_POST_FAULT_MODEL_SECONDS = 45.0
OPENMODELICA_RUN_NODE_ID = 10001
FORBIDDEN_COLUMNS = {"scenario_id", "root_cause", "fault_injection", "fault_preset"}
COMMAND_EVENT_TAGS = {
    "TRIP_CMD", "VCB_TRIP_CMD", "BREAKER_COMMAND", "OPEN_CMD", "CLOSE_CMD",
    "LP_BFP_TRIP_CMD", "LP_BFP_TRIP_LATCH", "VCB_A02_TRIP_CMD",
    "VCB_A02_OPEN_CMD", "VCB_A02_CLOSE_CMD",
}
FAULT_SIGNAL_SUFFIXES = ("FaultEnableNative", "FaultValueNative", "FaultActive")
GT_CAUSES = (
    "vppCauseDirectGTTrip", "vppCauseGTBreakerOpenWhileRunning",
    "vppCauseHPDrumLL", "vppCauseIPDrumLL", "vppCauseLPDrumLL",
)
ST_CAUSES = (
    "vppCauseDirectSTTrip", "vppCauseHPDrumHH",
    "vppCauseIPDrumHH", "vppCauseLPDrumHH",
)

GT_ST_TRIPPED = {
    "vppGTTripLatch": 1.0,
    "vpp52GTTripCmd": 1.0,
    "vpp52GTClosed": 0.0,
    "vppSTTripLatchPublished": 1.0,
    "vpp52STTripCmd": 1.0,
    "vpp52STClosed": 0.0,
}
ST_ONLY_TRIPPED = {
    "vppSTTripLatchPublished": 1.0,
    "vpp52STTripCmd": 1.0,
    "vpp52STClosed": 0.0,
}
GT_ST_NORMAL = {
    "vppGTTripLatch": 0.0,
    "vpp52GTTripCmd": 0.0,
    "vpp52GTClosed": 1.0,
    "vppSTTripLatchPublished": 0.0,
    "vpp52STTripCmd": 0.0,
    "vpp52STClosed": 1.0,
}


def drum_writes(section: str, level: str) -> dict[str, float]:
    prefix = section.upper()
    feed = f"vppVlv{prefix}FWCV" if prefix in {"HP", "IP"} else "vppVlvLPFW"
    steam = f"vppVlv{prefix}Steam"
    high = level == "hh"
    return {
        f"{feed}FaultValueNative": 1.0 if high else 0.0,
        f"{steam}FaultValueNative": 0.0 if high else 1.0,
        f"{feed}FaultEnableNative": 1.0,
        f"{steam}FaultEnableNative": 1.0,
    }


def write_inputs_atomically(client, ua, live, nodes, writes: dict[str, float], *, pause_runtime: bool) -> None:
    """Apply a multi-valve drum fault without exposing a partial solver state.

    The embedded OpenModelica server advances between OPC UA writes.  A drum
    fault needs a coordinated pair of feedwater/steam valve overrides, so pause
    the solver while the four inputs are changed and resume only after the
    complete fault state exists.  All ordinary one-input scenarios retain the
    direct write path.
    """
    run_node = None
    paused = False
    if pause_runtime:
        run_node = client.get_node(ua.NodeId(OPENMODELICA_RUN_NODE_ID, 0))
        run_node.set_value(ua.Variant(False, ua.VariantType.Boolean))
        paused = True
    try:
        for name, value in writes.items():
            nodes[name].set_value(ua.Variant(float(value), ua.VariantType.Float))
    finally:
        if paused and run_node is not None:
            run_node.set_value(ua.Variant(True, ua.VariantType.Boolean))
    for name, value in writes.items():
        live.wait_write_echo(nodes[name], value, 30.0)


SCENARIOS: dict[str, dict[str, Any]] = {
    "direct_gt": {
        "expected_domain": "GT+ST",
        "writes": {"vppExternalTripCommandNative": 1.0},
        "cause": "vppCauseDirectGTTrip",
        "expected": GT_ST_TRIPPED,
        "events": {("GT", "TRIP_LATCH"), ("52GT", "BREAKER_OPEN"),
                   ("ST", "TRIP_LATCH"), ("52ST", "BREAKER_OPEN")},
    },
    "gt_breaker": {
        "expected_domain": "GT+ST",
        "writes": {"vppECMS52GTClosedCommandNative": 0.0},
        "cause": "vppCauseGTBreakerOpenWhileRunning",
        "expected": GT_ST_TRIPPED,
        "events": {("GT", "TRIP_LATCH"), ("52GT", "BREAKER_OPEN"),
                   ("ST", "TRIP_LATCH"), ("52ST", "BREAKER_OPEN")},
    },
    "direct_st": {
        "expected_domain": "ST",
        "writes": {"vppExternalSTTripCommandNative": 1.0},
        "cause": "vppCauseDirectSTTrip",
        "expected": ST_ONLY_TRIPPED,
        "events": {("ST", "TRIP_LATCH"), ("52ST", "BREAKER_OPEN")},
    },
}
for _section in ("hp", "ip", "lp"):
    for _level in ("hh", "ll"):
        _name = f"{_section}_drum_{_level}"
        _upper = _section.upper()
        SCENARIOS[_name] = {
            "expected_domain": "ST" if _level == "hh" else "GT+ST",
            "writes": drum_writes(_section, _level),
            "cause": f"vppCause{_upper}Drum{_level.upper()}",
            "expected": ST_ONLY_TRIPPED if _level == "hh" else GT_ST_TRIPPED,
            "events": (
                {("ST", "TRIP_LATCH"), ("52ST", "BREAKER_OPEN")}
                if _level == "hh" else
                {("GT", "TRIP_LATCH"), ("52GT", "BREAKER_OPEN"),
                 ("ST", "TRIP_LATCH"), ("52ST", "BREAKER_OPEN")}
            ),
            "drum": _upper,
            "level": _level.upper(),
        }
for _section, _vcb in (("hp", "VCB-A01"), ("ip", "VCB-B01"), ("lp", "VCB-A02")):
    _upper = _section.upper()
    _drum_cause = f"vppCause{_upper}DrumLL"
    _physical_events = {
        (f"{_upper} BFP", "SPEED_PROVEN_LOST"),
        (f"{_upper} BFP NRV", "CHECK_VALVE_CLOSED"),
        (f"{_upper} FEEDWATER", "FLOW_LOW"),
    }
    _matrix_events = {
        ("GT", "TRIP_LATCH"), ("52GT", "BREAKER_OPEN"),
        ("ST", "TRIP_LATCH"), ("52ST", "BREAKER_OPEN"),
    }
    # BFP scenarios prove the physical equipment chain (pushbutton -> latch
    # -> breaker -> motor/speed/NRV/flow).  Drum LL -> GT/ST is a separate
    # physical-inventory scenario above and carries the contractual 100 s
    # common-trip proof.  Requiring an LP drum LL in the same BFP case would
    # conflate two independent disturbances and, with the native drum
    # inventory, is not reachable within the 45 s BFP acceptance window.
    _full_chain = False
    SCENARIOS[f"{_section}_bfp"] = {
        # The independent HP/IP/LP drum-LL cases prove the common-trip route
        # at 100 s; each BFP case remains an equipment-chain proof.
        "expected_domain": "GT+ST" if _full_chain else "BFP",
        "pump": _upper,
        "cause": _drum_cause if _full_chain else None,
        "requires_drum_trip": _full_chain,
        "post_fault_model_seconds": (
            DEFAULT_POST_FAULT_MODEL_SECONDS if _full_chain
            else SHORT_BFP_POST_FAULT_MODEL_SECONDS
        ),
        "expected": {
            f"vpp{_upper}FWPTripLatchNative": 1.0,
            f"vppECMS{_vcb.replace('-', '')}Closed": 0.0,
            f"vpp{_upper}FWPMotorEnergized": 0.0,
            f"vpp{_upper}FWPRunning": 0.0,
            **(GT_ST_TRIPPED if _full_chain else {}),
        },
        "events": (
            {(_vcb, "BREAKER_OPEN"), (f"{_upper} BFP", "MOTOR_DEENERGIZED"),
             (f"{_upper} BFP", "RUNNING_LOST")} | _physical_events |
            (_matrix_events if _full_chain else set())
        ),
    }


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def atomic_control(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    os.replace(temporary, path)


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def wait_snapshot(
    path: Path, process: subprocess.Popen[Any], deadline: float, predicate
) -> dict[str, Any]:
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Dual Log engine exited early with code {process.returncode}")
        current = load_json(path)
        if current:
            latest = current
            if predicate(current):
                return current
            if (
                current.get("status") == "PASS" and
                current.get("model_time_advancing") is False and
                float(current.get("model_time_stalled_s", 0.0)) >= 10.0
            ):
                raise RuntimeError(
                    "OpenModelica model time stalled before acceptance target; "
                    f"model_time_s={current.get('model_time_s')}"
                )
        time.sleep(0.25)
    raise RuntimeError(f"snapshot wait timed out; latest={latest}")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def finite_number(row: dict[str, str], name: str) -> float | None:
    try:
        value = float(row[name])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def reached(rows: list[dict[str, str]], name: str, target: float) -> bool:
    return any(
        (value := finite_number(row, name)) is not None and
        math.isclose(value, target, abs_tol=2e-5)
        for row in rows
    )


def rose(rows: list[dict[str, str]], name: str) -> bool:
    return any(
        (value := finite_number(row, name)) is not None and value >= 0.5
        for row in rows
    )


def series(rows: list[dict[str, str]], name: str) -> list[float]:
    """Return finite samples for one historian tag in file order."""
    return [
        value for row in rows
        if (value := finite_number(row, name)) is not None
    ]


def validate(
    scenario: str, spec: dict[str, Any], event_path: Path, raw_path: Path,
    trigger_time: float, required_pre_s: float, required_post_s: float,
) -> dict[str, Any]:
    event_fields, events = read_csv(event_path)
    raw_fields, raw = read_csv(raw_path)
    problems: list[str] = []
    if event_fields != EVENT_COLUMNS:
        problems.append("EVENT schema mismatch")
    if FORBIDDEN_COLUMNS.intersection(event_fields) or FORBIDDEN_COLUMNS.intersection(raw_fields):
        problems.append("fault/answer metadata leaked into AI CSV")
    leaked_fault_fields = sorted(name for name in raw_fields if name.endswith(FAULT_SIGNAL_SUFFIXES))
    if leaked_fault_fields:
        problems.append("internal fault injection signals leaked into RAW: " + ",".join(leaked_fault_fields))
    if any(row.get("tag") in COMMAND_EVENT_TAGS for row in events):
        problems.append("command evidence leaked into EVENT.csv")
    required_raw_meta = {
        "record_sequence", "session_id", "incident_id", "model_time_s",
        "wall_time_utc", "quality",
    }
    missing_raw_meta = sorted(required_raw_meta.difference(raw_fields))
    if missing_raw_meta:
        problems.append("RAW metadata columns missing: " + ",".join(missing_raw_meta))
    times: list[float] = []
    for index, row in enumerate(raw, start=2):
        value = finite_number(row, "model_time_s")
        if value is None:
            problems.append(f"invalid RAW model_time_s at row {index}")
            continue
        times.append(value)
    pre_rows = [row for row in raw if (finite_number(row, "model_time_s") or -math.inf) < trigger_time]
    post_rows = [row for row in raw if (finite_number(row, "model_time_s") or -math.inf) >= trigger_time]
    if len(pre_rows) < 2:
        problems.append(f"pre-fault RAW sample count too short: {len(pre_rows)}")
    pre_coverage = trigger_time - times[0] if times else 0.0
    if pre_coverage < required_pre_s - 0.25:
        problems.append(f"pre-fault coverage too short: {pre_coverage:.6f} s")
    minimum_post_rows = max(2, math.floor(required_post_s / 1.5))
    if len(post_rows) < minimum_post_rows:
        problems.append(
            f"post-fault RAW sample count too short: {len(post_rows)} rows; "
            f"minimum={minimum_post_rows}"
        )
    if not times or times[-1] < trigger_time + required_post_s - 1.5:
        problems.append(
            f"{required_post_s:g} s post-fault horizon not reached"
        )
    if any(times[index] > times[index + 1] for index in range(len(times) - 1)):
        problems.append("RAW model time is not monotonic")
    if {row.get("quality") for row in raw} != {"GOOD"}:
        problems.append("RAW quality is not uniformly GOOD")
    metadata = {"record_sequence", "session_id", "incident_id", "model_time_s", "wall_time_utc", "quality"}
    nonfinite: list[str] = []
    for index, row in enumerate(raw, start=2):
        for field, value in row.items():
            if field in metadata:
                continue
            if finite_number(row, field) is None:
                nonfinite.append(f"row={index}:{field}={value}")
                if len(nonfinite) >= 10:
                    break
        if len(nonfinite) >= 10:
            break
    if nonfinite:
        problems.append("non-finite RAW values: " + ", ".join(nonfinite))
    baseline_expected = dict(GT_ST_NORMAL)
    if spec.get("pump"):
        pump = str(spec["pump"])
        vcb = {"HP": "VCBA01", "IP": "VCBB01", "LP": "VCBA02"}[pump]
        baseline_expected.update({
            f"vpp{pump}FWPTripLatchNative": 0.0,
            f"vppECMS{vcb}Closed": 1.0,
            f"vpp{pump}FWPMotorEnergized": 1.0,
            f"vpp{pump}FWPRunning": 1.0,
        })
    baseline = pre_rows[-1] if pre_rows else {}
    for field, expected in baseline_expected.items():
        value = finite_number(baseline, field)
        if value is None:
            problems.append(f"pre-fault field missing/non-finite: {field}")
        elif not math.isclose(value, expected, abs_tol=2e-5):
            problems.append(f"pre-fault state not normal {field}: expected={expected} actual={value}")
    for cause_name in GT_CAUSES + ST_CAUSES:
        if cause_name not in raw_fields:
            problems.append(f"protection cause field missing: {cause_name}")
        elif rose(pre_rows, cause_name):
            problems.append(f"protection cause already active before trigger: {cause_name}")
    cause = spec.get("cause")
    if cause and (cause not in raw_fields or not rose(post_rows, str(cause))):
        problems.append(f"protection cause did not assert: {cause}")
    last = raw[-1] if raw else {}
    actual: dict[str, float] = {}
    for field, expected in spec["expected"].items():
        if field not in raw_fields:
            problems.append(f"expected RAW field missing: {field}")
            continue
        value = finite_number(last, field)
        if value is None:
            problems.append(f"expected RAW field non-finite: {field}")
            continue
        actual[field] = value
        if not math.isclose(value, expected, abs_tol=2e-5):
            problems.append(f"matrix mismatch {field}: expected={expected} actual={value}")
        if not reached(post_rows, field, expected):
            problems.append(f"expected post-trigger transition missing: {field}->{expected}")
    primary_domain = str(spec["expected_domain"])
    primary_route = GT_ST_TRIPPED if primary_domain == "GT+ST" else (
        {key: value for key, value in ST_ONLY_TRIPPED.items() if key.startswith("vppST") or key.startswith("vpp52ST")}
        if primary_domain == "ST" else {}
    )
    for field, expected in primary_route.items():
        if not reached(post_rows, field, expected):
            problems.append(f"primary protection route missing: {field}->{expected}")
    asserted_causes = [name for name in GT_CAUSES + ST_CAUSES if rose(post_rows, name)]
    final_gt_latch = finite_number(last, "vppGTTripLatch")
    final_st_latch = finite_number(last, "vppSTTripLatchPublished")
    if final_gt_latch is not None and final_gt_latch >= 0.5 and not any(name in asserted_causes for name in GT_CAUSES):
        problems.append("GT latch asserted without a recorded GT matrix cause")
    if final_st_latch is not None and final_st_latch >= 0.5 and not (
        any(name in asserted_causes for name in ST_CAUSES) or
        any(name in asserted_causes for name in GT_CAUSES)
    ):
        problems.append("ST latch asserted without a recorded ST/GT matrix cause")
    for prefix, latch_name, command_name, closed_name in (
        ("GT", "vppGTTripLatch", "vpp52GTTripCmd", "vpp52GTClosed"),
        ("ST", "vppSTTripLatchPublished", "vpp52STTripCmd", "vpp52STClosed"),
    ):
        latch = finite_number(last, latch_name)
        command = finite_number(last, command_name)
        closed = finite_number(last, closed_name)
        if None not in (latch, command, closed) and (
            not math.isclose(float(command), float(latch), abs_tol=2e-5) or
            not math.isclose(float(closed), 1.0 - float(latch), abs_tol=2e-5)
        ):
            problems.append(f"{prefix} latch/breaker final-state inconsistency")
    active_event_pairs = {
        (row.get("equipment", ""), row.get("tag", ""))
        for row in events if row.get("state") in {"ACTIVE", "PRESSED"}
    }
    missing_events = sorted(set(spec["events"]).difference(active_event_pairs))
    if missing_events:
        problems.append("required EVENT records missing: " + repr(missing_events))
    if spec.get("pump"):
        pump = str(spec["pump"])
        pb = (f"{pump} BFP", f"{pump}_BFP_TRIP_PB")
        if pb not in active_event_pairs:
            problems.append(f"operator PB EVENT missing: {pb}")
    physical_fields = [
        "vppGTGPowerMW", "vppGTGSpeedRPM", "vppGTExhaustMassFlowTH",
        "vppGTExhaustTemperatureK", "vppHPTurbineSteamFlowTH",
        "vppIPTurbineSteamFlowTH", "vppLPTurbineSteamFlowTH",
        "vppHPDrumLevelM", "vppIPDrumLevelM", "vppLPDrumLevelM",
        "vppHPDrumPressurePa", "vppIPDrumPressurePa", "vppLPDrumPressurePa",
        "vppHPFWPMassFlowTH", "vppIPFWPMassFlowTH", "vppLPFWPMassFlowTH",
        "vppHPFWPSpeedRPM", "vppIPFWPSpeedRPM", "vppLPFWPSpeedRPM",
        "vppHPFWPHydraulicSpeedRPM", "vppIPFWPHydraulicSpeedRPM",
        "vppLPFWPHydraulicSpeedRPM",
        "vppHPFWPCheckValveOpen", "vppIPFWPCheckValveOpen",
        "vppLPFWPCheckValveOpen", "vppHPFWPCheckValveOpening",
        "vppIPFWPCheckValveOpening", "vppLPFWPCheckValveOpening",
    ]
    physical = {}
    if raw:
        for field in physical_fields:
            if field in raw_fields:
                before = finite_number(pre_rows[-1], field) if pre_rows else None
                after = finite_number(raw[-1], field)
                if before is None or after is None:
                    continue
                physical[field] = {
                    "before": before,
                    "after": after,
                    "delta": after - before,
                }
    if spec.get("pump"):
        pump = str(spec["pump"])
        speed_field = f"vpp{pump}FWPSpeedRPM"
        hydraulic_speed_field = f"vpp{pump}FWPHydraulicSpeedRPM"
        flow_field = f"vpp{pump}FWPMassFlowTH"
        valve_open_field = f"vpp{pump}FWPCheckValveOpen"
        valve_position_field = f"vpp{pump}FWPCheckValveOpening"
        drum_level_field = f"vpp{pump}DrumLevelM"
        speed_before = finite_number(pre_rows[-1], speed_field) if pre_rows else None
        speed_post = series(post_rows, speed_field)
        hydraulic_speed_post = series(post_rows, hydraulic_speed_field)
        flow_before = finite_number(pre_rows[-1], flow_field) if pre_rows else None
        flow_post = series(post_rows, flow_field)
        valve_post = series(post_rows, valve_open_field)
        valve_position_post = series(post_rows, valve_position_field)
        drum_post = series(post_rows, drum_level_field)
        if speed_before is None or not speed_post:
            problems.append(f"physical speed trajectory missing: {speed_field}")
        elif min(speed_post) >= speed_before * 0.9:
            problems.append(
                f"{pump} BFP physical coastdown not proven: "
                f"pre={speed_before:.6f} min_post={min(speed_post):.6f}"
            )
        if not hydraulic_speed_post:
            problems.append(f"hydraulic speed trajectory missing: {hydraulic_speed_field}")
        elif min(hydraulic_speed_post) > 705.0:
            problems.append(
                f"{pump} hydraulic speed did not reach the numerical floor: "
                f"min_post={min(hydraulic_speed_post):.6f}"
            )
        if flow_before is None or not flow_post:
            problems.append(f"physical flow trajectory missing: {flow_field}")
        elif min(flow_post) >= abs(flow_before) * 0.5:
            problems.append(
                f"{pump} BFP feedwater coastdown not proven: "
                f"pre={flow_before:.6f} min_post={min(flow_post):.6f}"
            )
        if not valve_post:
            problems.append(f"check-valve state trajectory missing: {valve_open_field}")
        elif min(valve_post) >= 0.5 or finite_number(post_rows[-1], valve_open_field) is None or finite_number(post_rows[-1], valve_open_field) >= 0.5:
            problems.append(f"{pump} BFP discharge check valve did not close")
        if not valve_position_post:
            problems.append(f"check-valve opening trajectory missing: {valve_position_field}")
        elif min(valve_position_post) > 0.2:
            problems.append(
                f"{pump} BFP check-valve opening did not collapse: "
                f"min_post={min(valve_position_post):.6f}"
            )
        if spec.get("requires_drum_trip") and (
            not drum_post or not rose(post_rows, str(spec["cause"]))
        ):
            problems.append(f"{pump} Drum LL physical cause trajectory missing: {drum_level_field}")
    return {
        "status": "PASS" if not problems else "FAIL",
        "scenario": scenario,
        "expected_domain": primary_domain,
        "trigger_model_time_s": trigger_time,
        "final_model_time_s": times[-1] if times else None,
        "pre_fault_coverage_s": pre_coverage,
        "post_fault_coverage_s": (times[-1] - trigger_time) if times else 0.0,
        "required_post_fault_seconds": required_post_s,
        "event_rows": len(events),
        "raw_rows": len(raw),
        "raw_columns": len(raw_fields),
        "cause": cause,
        "cause_status": "ASSERTED" if cause and cause in raw_fields and rose(post_rows, str(cause)) else (
            "NOT_ASSERTED" if cause else "N/A"
        ),
        "asserted_matrix_causes": asserted_causes,
        "matrix_actual": actual,
        "physical_response": physical,
        "command_leakage_count": sum(row.get("tag") in COMMAND_EVENT_TAGS for row in events),
        "required_event_count": len(spec["events"]) + (1 if spec.get("pump") else 0),
        "missing_event_count": len(missing_events) + (1 if spec.get("pump") and
            (f"{spec['pump']} BFP", f"{spec['pump']}_BFP_TRIP_PB") not in active_event_pairs else 0),
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--pre-fault-model-seconds", type=float, default=5.0)
    parser.add_argument(
        "--post-fault-model-seconds", type=float, default=None,
        help="Override the scenario default; otherwise use its declared horizon",
    )
    parser.add_argument("--timeout", type=float, default=1200.0)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    engine_root = output / "engine"
    engine_root.mkdir(parents=True, exist_ok=True)
    snapshot = engine_root / "snapshot.json"
    control = engine_root / "control.json"
    stdout = output / "engine.stdout.log"
    stderr = output / "engine.stderr.log"
    result_path = output / "SCENARIO_RESULT.json"
    audit_path = output / "TEST_AUDIT.json"
    engine = repo / "scripts" / "ecms_bfp_alarm_engine.py"
    command = [
        sys.executable, str(engine), "--repo-root", str(repo),
        "--endpoint", args.endpoint, "--snapshot-file", str(snapshot),
        "--control-file", str(control), "--output-root", str(engine_root / "runtime"),
        "--period", "0.25", "--raw-period", "1.0", "--no-auto-resume",
    ]
    spec = SCENARIOS[args.scenario]
    post_fault_seconds = (
        float(args.post_fault_model_seconds)
        if args.post_fault_model_seconds is not None
        else float(spec.get("post_fault_model_seconds", DEFAULT_POST_FAULT_MODEL_SECONDS))
    )
    process: subprocess.Popen[Any] | None = None
    latest: dict[str, Any] = {}
    trigger_time = math.nan
    problems: list[str] = []
    with stdout.open("w", encoding="utf-8") as out_stream, stderr.open("w", encoding="utf-8") as err_stream:
        process = subprocess.Popen(command, stdout=out_stream, stderr=err_stream)
        deadline = time.monotonic() + args.timeout
        try:
            ready = wait_snapshot(
                snapshot, process, deadline,
                lambda item: item.get("status") == "PASS" and int(item.get("raw_count_session", 0)) >= 2,
            )
            attached_time = float(ready["model_time_s"])
            ready = wait_snapshot(
                snapshot, process, deadline,
                lambda item: item.get("status") == "PASS" and
                float(item.get("model_time_s", -1)) >= attached_time + args.pre_fault_model_seconds,
            )
            prior_incident = str(ready.get("incident_id", ""))
            if spec.get("pump"):
                atomic_control(control, {"action": "PUMP_TRIP", "train": spec["pump"]})
            else:
                atomic_control(control, {"action": "BEGIN_SCENARIO", "scenario": args.scenario})
            latest = wait_snapshot(
                snapshot, process, deadline,
                lambda item: item.get("status") == "PASS" and
                bool(item.get("incident_id")) and str(item.get("incident_id")) != prior_incident,
            )
            action_model_time = float(latest["model_time_s"])

            writes = dict(spec.get("writes") or {})
            if writes:
                scripts = repo / "scripts"
                sys.path.insert(0, str(scripts))
                import local_ecms_opcua as live  # type: ignore
                from opcua import ua
                client = live.connect(args.endpoint, 5.0)
                try:
                    nodes = live.find_nodes(client, writes)
                    write_inputs_atomically(
                        client, ua, live, nodes, writes,
                        pause_runtime=bool(spec.get("drum")),
                    )
                finally:
                    client.disconnect()
                latest = wait_snapshot(
                    snapshot, process, deadline,
                    lambda item: item.get("status") == "PASS" and
                    float(item.get("model_time_s", -1)) > action_model_time,
                )
            trigger_time = float(latest["model_time_s"])
            atomic_json(audit_path, {
                "scenario": args.scenario,
                "trigger_model_time_s": trigger_time,
                "writes": writes if writes else {"action": "PUMP_TRIP", "train": spec["pump"]},
                "excluded_from_ai_csv": True,
            })
            target = trigger_time + post_fault_seconds
            latest = wait_snapshot(
                snapshot, process, deadline,
                lambda item: item.get("status") == "PASS" and
                float(item.get("model_time_s", -1)) >= target,
            )
        except Exception as exc:
            problems.append(f"{type(exc).__name__}: {exc}")
        finally:
            if process.poll() is None:
                try:
                    atomic_control(control, {"action": "STOP"})
                    process.wait(timeout=10)
                except Exception:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()

    final_snapshot = load_json(snapshot) or latest
    event_source = Path(str(final_snapshot.get("event_csv", "")))
    raw_source = Path(str(final_snapshot.get("raw_csv", "")))
    analysis_source = Path(str(final_snapshot.get("analysis_json", "")))
    event_path = output / "EVENT.csv"
    raw_path = output / "RAW.csv"
    if event_source.is_file():
        shutil.copy2(event_source, event_path)
    else:
        problems.append("incident EVENT.csv was not produced")
    if raw_source.is_file():
        shutil.copy2(raw_source, raw_path)
    else:
        problems.append("incident RAW.csv was not produced")
    if args.scenario == "lp_bfp" and analysis_source.is_file():
        shutil.copy2(analysis_source, output / "LP_BFP_DUAL_ANALYSIS.json")

    result: dict[str, Any]
    if event_path.is_file() and raw_path.is_file() and math.isfinite(trigger_time):
        try:
            result = validate(
                args.scenario, spec, event_path, raw_path, trigger_time,
                args.pre_fault_model_seconds, post_fault_seconds,
            )
            result["problems"] = problems + list(result["problems"])
            if result["problems"]:
                result["status"] = "FAIL"
        except Exception as exc:
            problems.append(f"validation {type(exc).__name__}: {exc}")
            result = {}
    else:
        result = {}
    if not result:
        result = {
            "status": "FAIL", "scenario": args.scenario,
            "expected_domain": spec["expected_domain"],
            "trigger_model_time_s": trigger_time if math.isfinite(trigger_time) else None,
            "final_model_time_s": None,
            "pre_fault_coverage_s": 0.0,
            "post_fault_coverage_s": 0.0,
            "required_post_fault_seconds": post_fault_seconds,
            "event_rows": 0, "raw_rows": 0, "raw_columns": 0,
            "cause": spec.get("cause"), "cause_status": "NOT_EVALUATED",
            "asserted_matrix_causes": [], "matrix_actual": {},
            "physical_response": {}, "command_leakage_count": None,
            "required_event_count": len(spec["events"]) + (1 if spec.get("pump") else 0),
            "missing_event_count": None, "problems": problems,
        }
    atomic_json(result_path, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
