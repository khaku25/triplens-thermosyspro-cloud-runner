"""Second-pass adversarial review tests; fake model tests are NOT live AI tests."""
import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
SERVICE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVICE))
from test_live_integration import make_fixture,write_csv,EVENT_FIELDS,RAW_META,TAGS
import bridge
from gemini_agent import run_gemini_analysis
from triplens.analysis_contract import normalize_analysis

class Step:
    def __init__(self,name,args,id): self.type='function_call'; self.name=name; self.arguments=args; self.id=id
    def model_dump(self): return {'type':self.type,'name':self.name,'arguments':self.arguments,'id':self.id}
class FakeClient:
    def __init__(self,responses): self.responses=iter(responses); self.requests=[]; self.interactions=self
    def create(self,**kwargs):
        self.requests.append(json.loads(json.dumps(kwargs)))
        return next(self.responses)
def calls(*steps): return SimpleNamespace(steps=list(steps),output_text='',usage=None)
def answer(raw): return SimpleNamespace(steps=[],output_text=json.dumps(raw),usage=None)

class ReviewGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.event,self.raw=make_fixture(self.root);self.store=bridge.build_store(self.event,self.raw)
    def tearDown(self): self.temp.cleanup()

    def test_reference_check_rejects_fabricated_evidence(self):
        out=normalize_analysis({'primary_cause':{'claim':'GT 원인이라고 가정','status':'CONFIRMED','evidence_ids':['MADE_UP'],'related_tags':['vppExternalTripCommandNative']}},self.store)
        self.assertEqual(out['primary_cause']['status'],'UNKNOWN')
        self.assertEqual(out['primary_cause']['evidence_ids'],[])
        self.assertFalse(out['finality']['can_mark_final_confirmed'])

    def test_registered_tag_not_in_cited_evidence_is_not_grounded(self):
        self.store.search_events()
        out=normalize_analysis({'direct_trigger':{'claim':'latch','evidence_ids':['E-1'],'related_tags':['vpp52STClosed'],'model_time_s':48.44}},self.store)
        self.assertEqual(out['direct_trigger']['status'],'UNKNOWN')

    def test_readiness_rejects_disjoint_time_ranges(self):
        with self.raw.open(encoding='utf-8-sig',newline='') as f:
            r=csv.DictReader(f);fields=r.fieldnames;rows=list(r)
        for row in rows: row['model_time_s']=float(row['model_time_s'])+1000
        write_csv(self.raw,fields,rows)
        self.assertEqual(bridge.build_store(self.event,self.raw).readiness()['status'],'COLLECTING')

    def test_mismatched_session_rejected(self):
        self.raw.write_text(self.raw.read_text(encoding='utf-8-sig').replace('S-REGRESSION','OTHER-SESSION'),encoding='utf-8')
        with self.assertRaises(ValueError): bridge.build_store(self.event,self.raw)

    def test_raw_original_csv_row_survives_time_sort(self):
        with self.raw.open(encoding='utf-8-sig',newline='') as f:
            r=csv.DictReader(f);fields=r.fieldnames;rows=list(r)
        rows=list(reversed(rows));write_csv(self.raw,fields,rows)
        store=bridge.build_store(self.event,self.raw)
        sample=store.get_tag_series('vppExternalTripCommandNative',48,48)['points'][0]
        evidence=next(e for e in store.evidence_catalog() if e['evidence_id']==sample['evidence_id'])
        self.assertEqual(evidence['row_number'],8)
        self.assertEqual(evidence['record_sequence'],'1')

    def test_same_timestamp_does_not_silently_replace_raw_sample(self):
        with self.raw.open(encoding='utf-8-sig',newline='') as f:
            r=csv.DictReader(f);fields=r.fieldnames;rows=list(r)
        extra=dict(rows[0],record_sequence='99',vppExternalTripCommandNative='1')
        rows.insert(1,extra);write_csv(self.raw,fields,rows)
        store=bridge.build_store(self.event,self.raw)
        points=store.get_tag_series('vppExternalTripCommandNative',48,48)['points']
        self.assertEqual(len(points),2)
        self.assertNotEqual(points[0]['evidence_id'],points[1]['evidence_id'])

    def test_files_are_immutable_after_all_tools(self):
        before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.event,self.raw)]
        self.store.search_events();self.store.get_event_window(48.44)
        self.store.get_raw_window(TAGS[:8],48,49)
        self.store.get_tag_series(TAGS[0],48,50)
        self.store.get_logic_context(['GT::TRIP_LATCH'])
        self.store.get_equipment_state('GT',48.44,tags=TAGS[:2])
        after=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.event,self.raw)]
        self.assertEqual(before,after)

    def test_equipment_event_only_is_not_raw_inspection(self):
        client=FakeClient([
            calls(Step('get_equipment_state',{'equipment':'GT','at_time_s':48.44},'A'),Step('get_logic_context',{'tags':['GT::TRIP_LATCH']},'B')),
            answer({}),
            calls(Step('get_tag_series',{'tag':TAGS[0],'start_time_s':48,'end_time_s':49},'C')),
            answer({})])
        output=run_gemini_analysis(self.store,run_id='TEST',data_digest='TEST',client=client)
        self.assertEqual(len(client.requests),4)
        trace=output['tool_trace']
        self.assertEqual(trace[0].get('raw_evidence_count'),0)
        self.assertGreater(trace[2].get('raw_evidence_count',0),0)

    def test_ninth_tool_call_gets_denied_result_and_never_executes(self):
        client=FakeClient([calls(*(Step('search_events',{'limit':1},str(i)) for i in range(9))),answer({})])
        output=run_gemini_analysis(self.store,run_id='TEST',data_digest='TEST',client=client)
        self.assertEqual(output['agent_execution']['tool_calls_used'],8)
        self.assertEqual(sum(t['executed'] for t in output['tool_trace']),8)
        self.assertEqual(output['tool_trace'][-1]['status'],'BUDGET_EXHAUSTED')
        results=[v for v in client.requests[-1]['input'] if v.get('type')=='function_result']
        self.assertEqual(len(results),9)
        self.assertNotIn('tools',client.requests[-1])
        self.assertEqual(output['verification_gate'],'HOLD')

    def test_structured_schema_and_korean_instructions_sent_to_model(self):
        client=FakeClient([answer({}),answer({})])
        output=run_gemini_analysis(self.store,run_id='TEST',data_digest='TEST',client=client)
        request=client.requests[0]
        self.assertIn('Korean',request['system_instruction'])
        self.assertIn('schema',request['response_format'])
        self.assertFalse(request['store'])
        self.assertEqual(output['verification_gate'],'HOLD')

if __name__=='__main__':unittest.main()
