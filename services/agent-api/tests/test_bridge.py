from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


SERVICE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bridge", SERVICE / "bridge.py")
assert spec and spec.loader
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


EVENT_FIELDS = [
    "event_id","event_sequence","session_id","incident_id","model_time_s","wall_time_utc",
    "priority","event_class","equipment","tag","state","value","unit","message","source","acknowledged",
]
RAW_FIELDS = [
    "record_sequence","session_id","incident_id","model_time_s","wall_time_utc","quality",
    "vppLPFWPTripCommandNative","vppLPFWPTripLatchNative","vppVCBA02TripCommandNative",
    "vppECMSVCBA02Closed","vppLPFWPSpeedRPM","vppLPFWPMassFlowTH","vppLPDrumLevelM",
]


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class BridgeTest(unittest.TestCase):
    def test_public_contract_tracks_current_runtime_registry(self):
        contract = bridge.public_contract()
        self.assertEqual(contract["python_role"], "EVIDENCE_PROVIDER_AND_VERIFIER")
        self.assertEqual(contract["decision_authority"], "GEMINI_AGENT")
        self.assertEqual(contract["logic_summary"]["live_rules"], 67)
        self.assertEqual(contract["logic_summary"]["alarm"], 54)
        self.assertEqual(contract["logic_summary"]["protection"], 13)

    def test_store_exposes_six_bounded_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            event = root / "EVENT.csv"
            raw = root / "RAW.csv"
            write_csv(event, EVENT_FIELDS, [{
                "event_id":"E1","event_sequence":1,"session_id":"S","incident_id":"I","model_time_s":1,
                "wall_time_utc":"","priority":"HIGH","event_class":"ALARM","equipment":"LP BFP",
                "tag":"SPEED_PROVEN_LOST","state":"ACTIVE","value":0,"unit":"BOOL",
                "message":"LP BFP SPEED PROVEN LOST","source":"DCS","acknowledged":False,
            }])
            base={"session_id":"S","incident_id":"I","wall_time_utc":"","quality":"GOOD"}
            write_csv(raw, RAW_FIELDS, [
                {**base,"record_sequence":1,"model_time_s":0,"vppLPFWPTripCommandNative":0,
                 "vppLPFWPTripLatchNative":0,"vppVCBA02TripCommandNative":0,"vppECMSVCBA02Closed":1,
                 "vppLPFWPSpeedRPM":3600,"vppLPFWPMassFlowTH":600,"vppLPDrumLevelM":1.8},
                {**base,"record_sequence":2,"model_time_s":2,"vppLPFWPTripCommandNative":1,
                 "vppLPFWPTripLatchNative":1,"vppVCBA02TripCommandNative":1,"vppECMSVCBA02Closed":0,
                 "vppLPFWPSpeedRPM":1000,"vppLPFWPMassFlowTH":200,"vppLPDrumLevelM":1.7},
            ])
            store = bridge.build_store(event, raw)
            names = [tool["name"] for tool in store.tool_manifest()["tools"]]
            self.assertEqual(names, [
                "search_events","get_event_window","get_raw_window",
                "get_tag_series","get_logic_context","get_equipment_state",
            ])
            self.assertEqual(store.tool_manifest()["max_tool_calls_per_analysis"], 8)


if __name__ == "__main__":
    unittest.main()
