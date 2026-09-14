#!/usr/bin/env python3
"""Offline proof of the Dual Log schema, separation, and two-input analyzer."""

from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
from pathlib import Path


EVENT_FIELDS = (
    "event_id", "event_sequence", "session_id", "incident_id", "model_time_s",
    "wall_time_utc", "priority", "event_class", "equipment", "tag", "state",
    "value", "unit", "message", "source", "acknowledged",
)
RAW_META = (
    "record_sequence", "session_id", "incident_id", "model_time_s",
    "wall_time_utc", "quality",
)
RAW_TAGS = (
    "vppLPFWPTripPushbuttonNative", "vppLPFWPTripCommandNative",
    "vppLPFWPTripLatchNative", "vppVCBA02TripCommandNative",
    "vppECMSVCBA02Closed", "vppLPFWPSpeedRPM", "vppLPFWPMassFlowTH",
    "vppLPDrumLevelM", "vppLPDrumPressurePa", "vppVlvHPFWCVCmd",
    "LP_BFP_TRIP_PB", "LP_BFP_TRIP_CMD", "LP_BFP_TRIP_LATCH",
    "VCB_A02_TRIP_CMD", "VCB_A02_OPEN_CMD", "VCB_A02_CLOSE_CMD",
    "VCB_A02_CLOSED", "LP_BFP_SPEED_RPM", "LP_FW_FLOW_TH",
)

def load_analyzer(path: Path):
    spec = importlib.util.spec_from_file_location("dual_analyzer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load analyzer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    analyzer = load_analyzer(root / "scripts" / "triplens_dual_log_analyzer.py")
    live_verifier = load_analyzer(Path(__file__).with_name("verify_dual_log_live.py"))
    command_event_tags = set(live_verifier.COMMAND_EVENT_TAGS)
    incident = "INCIDENT_20260914_120000_000"
    with tempfile.TemporaryDirectory(prefix="triplens-dual-log-") as temporary:
        folder = Path(temporary)
        event_path = folder / "EVENT.csv"
        raw_path = folder / "RAW.csv"
        event_rows = [
            {
                "event_id": "E1", "event_sequence": 1, "session_id": "S1",
                "incident_id": incident, "model_time_s": 100.0,
                "wall_time_utc": "2026-09-14T00:13:04.100+00:00",
                "priority": "HIGH", "event_class": "OPERATOR_ACTION",
                "equipment": "LP BFP", "tag": "LP_BFP_TRIP_PB", "state": "PRESSED",
                "value": 1, "unit": "BOOL", "message": "LP BFP TRIP PB PRESSED",
                "source": "OPERATOR", "acknowledged": False,
            },
            {
                "event_id": "E2", "event_sequence": 2, "session_id": "S1",
                "incident_id": incident, "model_time_s": 101.2,
                "wall_time_utc": "2026-09-14T00:13:05.200+00:00",
                "priority": "HIGH", "event_class": "ALARM", "equipment": "LP FEEDWATER",
                "tag": "FLOW_LOW", "state": "ACTIVE", "value": 290.0, "unit": "t/h",
                "message": "LP FW FLOW LOW ALARM", "source": "OPENMODELICA_PHYSICS",
                "acknowledged": False,
            },
            {
                "event_id": "E3", "event_sequence": 3, "session_id": "S1",
                "incident_id": incident, "model_time_s": 100.4,
                "wall_time_utc": "2026-09-14T00:13:04.400+00:00",
                "priority": "HIGH", "event_class": "PROTECTION", "equipment": "VCB-A02",
                "tag": "BREAKER_OPEN", "state": "ACTIVE", "value": 0, "unit": "BOOL",
                "message": "VCB-A02 OPEN", "source": "OPENMODELICA_PHYSICS",
                "acknowledged": False,
            },
            {
                "event_id": "E4", "event_sequence": 4, "session_id": "S1",
                "incident_id": incident, "model_time_s": 100.4,
                "wall_time_utc": "2026-09-14T00:13:04.401+00:00",
                "priority": "HIGH", "event_class": "PROTECTION", "equipment": "LP BFP",
                "tag": "MOTOR_DEENERGIZED", "state": "ACTIVE", "value": 0,
                "unit": "BOOL", "message": "LP BFP MOTOR DEENERGIZED",
                "source": "OPENMODELICA_PHYSICS", "acknowledged": False,
            },
            {
                "event_id": "E5", "event_sequence": 5, "session_id": "S1",
                "incident_id": incident, "model_time_s": 100.5,
                "wall_time_utc": "2026-09-14T00:13:04.500+00:00",
                "priority": "HIGH", "event_class": "ALARM", "equipment": "LP BFP",
                "tag": "RUNNING_LOST", "state": "ACTIVE", "value": 0, "unit": "BOOL",
                "message": "LP BFP RUNNING LOST", "source": "OPENMODELICA_PHYSICS",
                "acknowledged": False,
            },
            {
                "event_id": "E6", "event_sequence": 6, "session_id": "S1",
                "incident_id": incident, "model_time_s": 101.0,
                "wall_time_utc": "2026-09-14T00:13:05.000+00:00",
                "priority": "HIGH", "event_class": "ALARM", "equipment": "LP BFP",
                "tag": "SPEED_PROVEN_LOST", "state": "ACTIVE", "value": 0,
                "unit": "BOOL", "message": "LP BFP SPEED PROVEN LOST",
                "source": "OPENMODELICA_PHYSICS", "acknowledged": False,
            },
            {
                "event_id": "E7", "event_sequence": 7, "session_id": "S1",
                "incident_id": incident, "model_time_s": 101.5,
                "wall_time_utc": "2026-09-14T00:13:05.500+00:00",
                "priority": "MEDIUM", "event_class": "ALARM", "equipment": "LP BFP NRV",
                "tag": "CHECK_VALVE_CLOSED", "state": "ACTIVE", "value": 0,
                "unit": "BOOL", "message": "LP BFP CHECK VALVE CLOSED",
                "source": "OPENMODELICA_PHYSICS", "acknowledged": False,
            },
        ]
        raw_rows = []
        samples = (
            (99.0, 0, 0, 0, 1, 3600, 620),
            (100.1, 1, 0, 0, 1, 3590, 618),
            (100.2, 1, 1, 0, 1, 3500, 600),
            (100.3, 1, 1, 1, 1, 3300, 560),
            (100.4, 1, 1, 1, 0, 3000, 500),
            (103.0, 0, 1, 1, 0, 1000, 250),
        )
        for sequence, (model_time, trip_cmd, latch, vcb_trip, closed, speed, flow) in enumerate(samples, 1):
            raw_rows.append({
                "record_sequence": sequence, "session_id": "S1", "incident_id": incident,
                "model_time_s": model_time,
                "wall_time_utc": f"2026-09-14T00:13:{sequence:02d}.000+00:00", "quality": "GOOD",
                "vppLPFWPTripPushbuttonNative": 1 if sequence in {2, 3, 4} else 0,
                "vppLPFWPTripCommandNative": trip_cmd,
                "vppLPFWPTripLatchNative": latch,
                "vppVCBA02TripCommandNative": vcb_trip,
                "vppECMSVCBA02Closed": closed,
                "vppLPFWPSpeedRPM": speed,
                "vppLPFWPMassFlowTH": flow,
                "vppLPDrumLevelM": 1.8 - 0.02 * sequence,
                "vppLPDrumPressurePa": 1.0e6,
                "vppVlvHPFWCVCmd": 0.8,
                "LP_BFP_TRIP_PB": 1 if sequence in {2, 3, 4} else 0,
                "LP_BFP_TRIP_CMD": trip_cmd, "LP_BFP_TRIP_LATCH": latch,
                "VCB_A02_TRIP_CMD": vcb_trip,
                "VCB_A02_OPEN_CMD": max(1 - closed, vcb_trip),
                "VCB_A02_CLOSE_CMD": closed * (1 - vcb_trip),
                "VCB_A02_CLOSED": closed, "LP_BFP_SPEED_RPM": speed,
                "LP_FW_FLOW_TH": flow,
            })
        write_csv(event_path, EVENT_FIELDS, event_rows)
        write_csv(raw_path, RAW_META + RAW_TAGS, raw_rows)
        result = analyzer.analyze_dual_logs(event_path, raw_path)

        forbidden = {"scenario_id", "root_cause", "fault_injection", "fault_preset"}
        if forbidden.intersection(EVENT_FIELDS) or forbidden.intersection(RAW_META + RAW_TAGS):
            raise RuntimeError("forbidden metadata present")
        if any(row["event_class"] == "COMMAND" for row in event_rows):
            raise RuntimeError("general command leaked into EVENT")
        if any(row["tag"] in command_event_tags for row in event_rows):
            raise RuntimeError("command tag leaked into EVENT")
        expected_visible = {
            "LP_BFP_TRIP_PB", "BREAKER_OPEN", "MOTOR_DEENERGIZED",
            "RUNNING_LOST", "SPEED_PROVEN_LOST", "CHECK_VALVE_CLOSED", "FLOW_LOW",
        }
        if not expected_visible.issubset({row["tag"] for row in event_rows}):
            raise RuntimeError("physical alarm/protection event was removed from EVENT")
        if expected_visible.intersection(command_event_tags):
            raise RuntimeError("live verifier misclassifies visible Alarm/Protection events")
        required_raw_only = {
            "TRIP_CMD", "VCB_TRIP_CMD", "BREAKER_COMMAND", "OPEN_CMD", "CLOSE_CMD",
            "LP_BFP_TRIP_CMD", "LP_BFP_TRIP_LATCH", "VCB_A02_TRIP_CMD",
            "VCB_A02_OPEN_CMD", "VCB_A02_CLOSE_CMD",
        }
        if not required_raw_only.issubset(command_event_tags):
            raise RuntimeError("live verifier command-tag rejection contract incomplete")
        if not all(name in RAW_TAGS for name in (
            "vppLPFWPTripCommandNative", "vppLPFWPTripLatchNative",
            "vppVCBA02TripCommandNative", "vppECMSVCBA02Closed",
        )):
            raise RuntimeError("RAW protection chain incomplete")
        if result.get("status") != "PASS":
            raise RuntimeError(json.dumps(result, ensure_ascii=False))
        if not result.get("event_input_read") or not result.get("raw_input_read"):
            raise RuntimeError("analyzer did not prove both inputs")
        print(json.dumps({
            "status": "PASS", "event_csv": True, "raw_csv": True,
            "event_command_rows": 0, "raw_chain": True,
            "dual_input_analysis": True,
        }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
