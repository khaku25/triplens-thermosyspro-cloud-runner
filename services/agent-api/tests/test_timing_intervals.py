import sys
import tempfile
import unittest
from pathlib import Path
SERVICE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVICE))
from test_live_integration import make_fixture
import bridge
from triplens.analysis_contract import normalize_analysis

class TimingIntervalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.event,self.raw=make_fixture(Path(self.temp.name));self.store=bridge.build_store(self.event,self.raw);self.store.search_events()
    def tearDown(self):self.temp.cleanup()
    def test_raw_bracket_is_not_backdated_to_zero_sample(self):
        series=self.store.get_tag_series('vppExternalTripCommandNative',48,49)
        ids=series['transition_evidence'][0]['evidence_ids']
        out=normalize_analysis({'primary_cause':{'claim':'외부 입력 상승을 관측한 원인 후보','status':'CANDIDATE','evidence_ids':ids,'related_tags':['vppExternalTripCommandNative'],'model_time_s':None,'time_interval_s':[48,48.4]},'direct_trigger':{'claim':'GT latch','evidence_ids':['E-1'],'related_tags':['vppGTTripLatch'],'model_time_s':48.44}},self.store)
        self.assertIsNone(out['primary_cause']['model_time_s'])
        self.assertEqual(out['primary_cause']['time_interval_s'],[48,48.4])
        self.assertEqual(out['primary_cause']['status'],'CANDIDATE')
    def test_overlap_remains_candidate_with_explicit_hold_reason(self):
        series=self.store.get_tag_series('vppExternalTripCommandNative',48,49)
        ids=[series['points'][0]['evidence_id'],series['points'][-1]['evidence_id']]
        out=normalize_analysis({'primary_cause':{'claim':'상승 원인 후보','status':'CANDIDATE','evidence_ids':ids,'related_tags':['vppExternalTripCommandNative'],'model_time_s':None,'time_interval_s':[48,49]},'direct_trigger':{'claim':'latch','evidence_ids':['E-1'],'related_tags':['vppGTTripLatch'],'model_time_s':48.44}},self.store)
        self.assertEqual(out['primary_cause']['status'],'CANDIDATE')
        self.assertEqual(out['verification_gate'],'HOLD')
        self.assertTrue(any('시간' in x for x in out['verification_notes']))

if __name__=='__main__':unittest.main()
