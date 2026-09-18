import csv
import tempfile
import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import triplens_dual_log_analyzer as analyzer

EVENT_FIELDS=['event_id','event_sequence','session_id','incident_id','model_time_s','wall_time_utc','priority','event_class','equipment','tag','state','value','unit','message','source','acknowledged']
RAW_FIELDS=['record_sequence','session_id','incident_id','model_time_s','wall_time_utc','quality','vppLPFWPTripCommandNative','vppLPFWPTripLatchNative','vppVCBA02TripCommandNative','vppECMSVCBA02Closed','vppLPFWPSpeedRPM','vppLPFWPMassFlowTH','vppLPDrumLevelM']

def write(path,fields,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

class DualLogAgentRoleTest(unittest.TestCase):
    def test_python_exposes_candidates_but_reserves_causal_decisions_for_agent(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); e=d/'EVENT.csv'; r=d/'RAW.csv'
            write(e,EVENT_FIELDS,[{'event_id':'E1','event_sequence':1,'session_id':'S','incident_id':'I','model_time_s':1,'wall_time_utc':'','priority':'HIGH','event_class':'ALARM','equipment':'LP BFP','tag':'SPEED_PROVEN_LOST','state':'ACTIVE','value':0,'unit':'BOOL','message':'speed proven lost','source':'SIM','acknowledged':False}])
            base={'session_id':'S','incident_id':'I','wall_time_utc':'','quality':'GOOD'}
            write(r,RAW_FIELDS,[
                {**base,'record_sequence':1,'model_time_s':0,'vppLPFWPTripCommandNative':0,'vppLPFWPTripLatchNative':0,'vppVCBA02TripCommandNative':0,'vppECMSVCBA02Closed':1,'vppLPFWPSpeedRPM':3600,'vppLPFWPMassFlowTH':600,'vppLPDrumLevelM':1.8},
                {**base,'record_sequence':2,'model_time_s':2,'vppLPFWPTripCommandNative':1,'vppLPFWPTripLatchNative':1,'vppVCBA02TripCommandNative':1,'vppECMSVCBA02Closed':0,'vppLPFWPSpeedRPM':1000,'vppLPFWPMassFlowTH':200,'vppLPDrumLevelM':1.7},
            ])
            out=analyzer.analyze_dual_logs(e,r)
            self.assertEqual(out['analysis_role'],'EVIDENCE_PROVIDER_ONLY')
            self.assertEqual(out['decision_authority'],'GEMINI_AGENT')
            self.assertEqual(out['status_scope'],'EVIDENCE_READINESS_ONLY')
            self.assertEqual(out['decision_fields_generated_by_python'],[])
            self.assertIn('protection_chain_candidates',out['candidate_evidence'])
            self.assertIn('process_response_candidates',out['candidate_evidence'])
            for key in ('primary_cause','direct_trigger','critical_events','propagation','causal_chain'):
                self.assertNotIn(key,out)

if __name__=='__main__': unittest.main()
