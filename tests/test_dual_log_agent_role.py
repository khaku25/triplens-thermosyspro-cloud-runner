import csv
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import triplens_dual_log_analyzer as analyzer  # noqa: E402

EVENT_FIELDS = [
    "event_id","event_sequence","session_id","incident_id","model_time_s","wall_time_utc",
    "priority","event_class","equipment","tag","state","value","unit","message","source","acknowledged",
]
LP_RAW_FIELDS = [
    "record_sequence","session_id","incident_id","model_time_s","wall_time_utc","collector_quality",
    "vppLPFWPTripCommandNative","vppLPFWPTripLatchNative","vppVCBA02TripCommandNative",
    "vppECMSVCBA02Closed","vppLPFWPSpeedRPM","vppLPFWPMassFlowTH","vppLPDrumLevelM",
]
GT_RAW_FIELDS = [
    "record_sequence","session_id","incident_id","model_time_s","wall_time_utc","collector_quality",
    "vppGTTripCmd","vppGTTripRequest","vppGTTripLatch","vppSTTripRequest","vppSTTripLatchPublished",
    "vpp52GTTripCmd","vpp52GTClosed","vpp52STTripCmd","vpp52STClosed",
    "vppGTExhaustMassFlowTH","vppGTExhaustTemperatureK",
]


def write(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class DualLogAgentRoleTest(unittest.TestCase):
    def test_python_exposes_candidates_but_reserves_causal_decisions_for_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = root / "EVENT.csv"
            raw = root / "RAW.csv"
            write(event, EVENT_FIELDS, [{
                "event_id":"E1","event_sequence":1,"session_id":"S","incident_id":"I","model_time_s":1,
                "wall_time_utc":"","priority":"HIGH","event_class":"ALARM","equipment":"LP BFP",
                "tag":"SPEED_PROVEN_LOST","state":"ACTIVE","value":0,"unit":"BOOL",
                "message":"speed proven lost","source":"SIM","acknowledged":False,
            }])
            base={"session_id":"S","incident_id":"I","wall_time_utc":"","collector_quality":"GOOD"}
            write(raw, LP_RAW_FIELDS, [
                {**base,"record_sequence":1,"model_time_s":0,"vppLPFWPTripCommandNative":0,
                 "vppLPFWPTripLatchNative":0,"vppVCBA02TripCommandNative":0,"vppECMSVCBA02Closed":1,
                 "vppLPFWPSpeedRPM":3600,"vppLPFWPMassFlowTH":600,"vppLPDrumLevelM":1.8},
                {**base,"record_sequence":2,"model_time_s":2,"vppLPFWPTripCommandNative":1,
                 "vppLPFWPTripLatchNative":1,"vppVCBA02TripCommandNative":1,"vppECMSVCBA02Closed":0,
                 "vppLPFWPSpeedRPM":1000,"vppLPFWPMassFlowTH":200,"vppLPDrumLevelM":1.7},
            ])
            out = analyzer.analyze_dual_logs(event, raw)
            self.assertEqual(out["readiness_version"], "GENERIC_DUAL_LOG_EVIDENCE_V2")
            self.assertEqual(out["analysis_role"], "EVIDENCE_PROVIDER_ONLY")
            self.assertEqual(out["decision_authority"], "GEMINI_AGENT")
            self.assertEqual(out["status_scope"], "EVIDENCE_READINESS_ONLY")
            self.assertEqual(out["decision_fields_generated_by_python"], [])
            self.assertIn("protection_chain_candidates", out["candidate_evidence"])
            self.assertIn("raw_transition_candidates", out["candidate_evidence"])
            self.assertIn("process_response_candidates", out["candidate_evidence"])
            for key in ("primary_cause","direct_trigger","critical_events","propagation","causal_chain"):
                self.assertNotIn(key, out)

    def test_gt_direct_trip_readiness_is_generic_and_has_no_lp_bfp_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = root / "EVENT.csv"
            raw = root / "RAW.csv"
            events = [
                {
                    "event_id":"GT-1","event_sequence":1,"session_id":"S","incident_id":"GT-I",
                    "model_time_s":30.0,"wall_time_utc":"","priority":"CRITICAL",
                    "event_class":"OPERATOR_ACTION","equipment":"GTG","tag":"GT.TRIP.CMD",
                    "state":"ACTIVE","value":1,"unit":"BOOL","message":"GT Trip command asserted",
                    "source":"DCS1","acknowledged":False,
                },
                {
                    "event_id":"GT-2","event_sequence":2,"session_id":"S","incident_id":"GT-I",
                    "model_time_s":30.0,"wall_time_utc":"","priority":"CRITICAL",
                    "event_class":"PROTECTION","equipment":"GTG","tag":"GT.TRIP.REQUEST",
                    "state":"ACTIVE","value":1,"unit":"BOOL","message":"GT Trip request active",
                    "source":"ECMS","acknowledged":False,
                },
                {
                    "event_id":"GT-3","event_sequence":3,"session_id":"S","incident_id":"GT-I",
                    "model_time_s":30.055,"wall_time_utc":"","priority":"CRITICAL",
                    "event_class":"PROTECTION","equipment":"86GT","tag":"86GT.OPERATE",
                    "state":"ACTIVE","value":1,"unit":"BOOL","message":"86GT lockout operated",
                    "source":"ECMS","acknowledged":False,
                },
                {
                    "event_id":"GT-4","event_sequence":4,"session_id":"S","incident_id":"GT-I",
                    "model_time_s":30.080,"wall_time_utc":"","priority":"CRITICAL",
                    "event_class":"PROTECTION","equipment":"52GT","tag":"ECMS.52GT.CLOSED",
                    "state":"OPEN","value":0,"unit":"BOOL","message":"52GT breaker open feedback",
                    "source":"ECMS","acknowledged":False,
                },
            ]
            write(event, EVENT_FIELDS, events)
            base={"session_id":"S","incident_id":"GT-I","wall_time_utc":"","collector_quality":"GOOD"}
            write(raw, GT_RAW_FIELDS, [
                {**base,"record_sequence":1,"model_time_s":29.0,
                 "vppGTTripCmd":0,"vppGTTripRequest":0,"vppGTTripLatch":0,
                 "vppSTTripRequest":0,"vppSTTripLatchPublished":0,
                 "vpp52GTTripCmd":0,"vpp52GTClosed":1,"vpp52STTripCmd":0,"vpp52STClosed":1,
                 "vppGTExhaustMassFlowTH":2185.2,"vppGTExhaustTemperatureK":893.75},
                {**base,"record_sequence":2,"model_time_s":30.0,
                 "vppGTTripCmd":1,"vppGTTripRequest":1,"vppGTTripLatch":0,
                 "vppSTTripRequest":1,"vppSTTripLatchPublished":0,
                 "vpp52GTTripCmd":0,"vpp52GTClosed":1,"vpp52STTripCmd":0,"vpp52STClosed":1,
                 "vppGTExhaustMassFlowTH":2185.2,"vppGTExhaustTemperatureK":893.75},
                {**base,"record_sequence":3,"model_time_s":30.055,
                 "vppGTTripCmd":1,"vppGTTripRequest":1,"vppGTTripLatch":1,
                 "vppSTTripRequest":1,"vppSTTripLatchPublished":1,
                 "vpp52GTTripCmd":1,"vpp52GTClosed":1,"vpp52STTripCmd":1,"vpp52STClosed":1,
                 "vppGTExhaustMassFlowTH":2100.0,"vppGTExhaustTemperatureK":880.0},
                {**base,"record_sequence":4,"model_time_s":30.1,
                 "vppGTTripCmd":1,"vppGTTripRequest":1,"vppGTTripLatch":1,
                 "vppSTTripRequest":1,"vppSTTripLatchPublished":1,
                 "vpp52GTTripCmd":1,"vpp52GTClosed":0,"vpp52STTripCmd":1,"vpp52STClosed":0,
                 "vppGTExhaustMassFlowTH":1800.0,"vppGTExhaustTemperatureK":820.0},
            ])

            out = analyzer.analyze_dual_logs(event, raw)
            self.assertEqual(out["status"], "PASS")
            self.assertTrue(out["coverage"]["event_chronology_ready"])
            self.assertTrue(out["coverage"]["raw_timeseries_ready"])
            self.assertGreater(out["coverage"]["raw_digital_transitions"], 0)
            self.assertGreater(out["coverage"]["raw_process_changes"], 0)
            rendered = str(out)
            self.assertNotIn("LP_BFP", rendered)
            self.assertNotIn("LP BFP", rendered)
            roles = {
                item["candidate_role"]
                for item in out["candidate_evidence"]["protection_chain_candidates"]
            }
            self.assertIn("TRIP_REQUEST", roles)
            self.assertIn("PROTECTION_ACTUATION", roles)
            self.assertIn("STATE_FEEDBACK", roles)

    def test_waiting_state_keeps_agent_role_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = root / "EVENT.csv"
            raw = root / "RAW.csv"
            write(event, EVENT_FIELDS, [])
            write(raw, LP_RAW_FIELDS, [])
            out = analyzer.analyze_dual_logs(event, raw)
            self.assertEqual(out["status"], "WAITING")
            self.assertEqual(out["readiness_version"], "GENERIC_DUAL_LOG_EVIDENCE_V2")
            self.assertEqual(out["analysis_role"], "EVIDENCE_PROVIDER_ONLY")
            self.assertEqual(out["decision_authority"], "GEMINI_AGENT")
            self.assertEqual(out["decision_fields_generated_by_python"], [])


if __name__ == "__main__":
    unittest.main()
