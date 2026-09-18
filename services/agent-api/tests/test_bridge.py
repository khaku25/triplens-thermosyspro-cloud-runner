from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
import sys
from pathlib import Path


SERVICE = Path(__file__).resolve().parents[1]
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))
spec = importlib.util.spec_from_file_location("bridge", SERVICE / "bridge.py")
assert spec and spec.loader
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


EVENT_FIELDS = [
    "event_id","event_sequence","session_id","incident_id","model_time_s","wall_time_utc",
    "priority","event_class","equipment","tag","state","value","unit","message","source","acknowledged",
]
RAW_FIELDS = [
    "record_sequence","session_id","incident_id","model_time_s","wall_time_utc","collector_quality",
    "vppLPFWPTripCommandNative","vppLPFWPTripLatchNative","vppVCBA02TripCommandNative",
    "vppECMSVCBA02Closed","vppLPFWPSpeedRPM","vppLPFWPMassFlowTH","vppLPDrumLevelM",
]


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class BridgeTest(unittest.TestCase):
    def test_public_contract_tracks_live_current_v8_sot(self):
        contract = bridge.public_contract()
        self.assertEqual(contract["python_role"], "EVIDENCE_PROVIDER_AND_VERIFIER")
        self.assertEqual(contract["decision_authority"], "GEMINI_AGENT")
        self.assertEqual(contract["logic_summary"]["live_rules"], 53)
        self.assertEqual(contract["logic_summary"]["alarm"], 28)
        self.assertEqual(contract["logic_summary"]["protection"], 17)
        self.assertEqual(contract["logic_summary"]["commands"], 6)
        self.assertEqual(contract["logic_summary"]["physical_response"], 2)
        self.assertEqual(contract["live_tag_allowlist_count"], 603)
        self.assertEqual(contract["current_v8_counts"]["live_tags"], 603)
        self.assertEqual(contract["current_v8_counts"]["logic_rules"], 53)
        self.assertEqual(contract["version"], "CURRENT_V8_LIVE_SOT_V1")
        self.assertTrue((SERVICE / "triplens" / "current_v8" / "live_logic_runtime.csv").exists())
        self.assertTrue((SERVICE / "triplens" / "current_v8" / "live_tag_allowlist.csv").exists())
        self.assertTrue((SERVICE / "triplens" / "current_v8" / "live_validation_manifest.json").exists())

    def test_runtime_logic_is_fail_closed_against_live_allowlist(self):
        rows = bridge.runtime_logic_rows()
        self.assertEqual(len(rows), 53)
        allow = bridge.live_tag_allowlist()
        self.assertEqual(len(allow), 603)
        for row in rows:
            linked = [
                part.strip()
                for part in str(row.get("linked_tag_ids", "")).replace(",", ";").split(";")
                if part.strip()
            ]
            for tag in linked:
                if tag.startswith("vpp"):
                    self.assertIn(tag, allow)

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
            base={"session_id":"S","incident_id":"I","wall_time_utc":"","collector_quality":"GOOD"}
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

            known = store.get_logic_context(["vppLPFWPTripCommandNative"])
            self.assertEqual(known["status"], "VERIFIED")
            self.assertTrue(known["items"])
            unknown = store.get_logic_context(["vppDefinitelyNotARealCurrentTag"])
            self.assertEqual(unknown["status"], "PARTIAL_OR_UNREGISTERED")
            self.assertEqual(unknown["items"], [])
            self.assertEqual(unknown["unregistered_tags"], ["vppDefinitelyNotARealCurrentTag"])


if __name__ == "__main__":
    unittest.main()
