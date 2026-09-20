"""Regression tests for captured citation omissions and incorrect reviewer row pointers."""
import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))
from triplens import engineering_reviewer as reviewer
from triplens.analysis_contract import normalize_claim
from gemini_agent import run_gemini_analysis

class Store:
    def __init__(self):
        self.rows = [
            {'evidence_id':'R-A0','source_node':'vppA','tag':'vppA','model_time_s':47.92,'value':0,'source_kind':'RAW','logic_ids':['L1']},
            {'evidence_id':'R-A1','source_node':'vppA','tag':'vppA','model_time_s':48.92,'value':1,'source_kind':'RAW','logic_ids':['L1']},
            {'evidence_id':'R-B0','source_node':'vppB','tag':'vppB','model_time_s':47.92,'value':0,'source_kind':'RAW','logic_ids':['L1']},
            {'evidence_id':'R-B1','source_node':'vppB','tag':'vppB','model_time_s':48.92,'value':1,'source_kind':'RAW','logic_ids':['L1']},
        ]
    def evidence_catalog(self): return copy.deepcopy(self.rows)
    def logic_matches(self,tags): return [{'logic_id':'L1'}]
    def build_agent_bootstrap(self,**kwargs): return {'events':[]}

class Client:
    def __init__(self,results): self.results=iter(results);self.requests=[];self.interactions=self
    def create(self,**kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        result=next(self.results)
        if isinstance(result,Exception):raise result
        return SimpleNamespace(steps=[],output_text=json.dumps(result),usage=None)

def review_raw(**finding):
    base={'severity':'WARNING','category':'EVIDENCE','row_id':'ROW-primary','current_section':'발생 원인','expected_section':None,'finding':'해당 근거 추가 확인','evidence_ids':['R-A0']}
    base.update(finding)
    return {'review_status':'PASS','summary_ko':'검토 결과','findings':[base],'missing_required_sections':[],
        'human_review_focus':[],'content_score':4,'placement_score':4,'evidence_score':4}

def package():
    return {'report_rows':[{'row_id':'ROW-primary','section':'발생 원인','item':'선행 원인','content':'입력 상승 후보','status':'CANDIDATE'}],
        'evidence_catalog':Store().rows, 'events':[], 'analysis':{},'logic_rows':[], 'validation':{}}

class ReferenceFixTests(unittest.TestCase):
    def test_unknown_section_blocks_before_model(self):
        p=package()
        p['report_rows']=[{'row_id':f'ROW-{i}','section':section,'item':'검토','content':'검토','status':'OBSERVED'}
            for i,section in enumerate([
                '개요','사고 발생 전 운전 현황','장애 현상','시간대별 사건·자동동작(SOE)','발생 원인',
                '운전원·정비 조치사항','조치 결과 및 복구 판정','추정 원인 및 미확인 사항',
                '재발방지 대책 — 검토 권고사항','증거자료'
            ],1)]
        invalid=copy.deepcopy(p);invalid['report_rows'][0]['section']='임의 섹션';blocked=Client([review_raw()])
        with self.assertRaisesRegex(ValueError,'Unknown report section'):
            reviewer.run_engineering_review(invalid,client=blocked)
        self.assertFalse(blocked.requests)

    def test_reviewer_sees_final_analysis_not_initial_repair_draft(self):
        p=package();p['analysis']={'primary_cause':{'claim':'최종 후보'},'citation_repair':{'initial_draft':{'claim':'OLD_DRAFT_DO_NOT_REVIEW'}}}
        c=Client([review_raw()]);reviewer.run_engineering_review(p,client=c)
        self.assertNotIn('OLD_DRAFT_DO_NOT_REVIEW',json.dumps(c.requests))
    def test_wrong_section_is_quarantined_not_silently_retargeted(self):
        r=reviewer.run_engineering_review(package(),client=Client([review_raw(current_section='시간대별 조치사항')]))
        self.assertEqual(r.get('reference_validation',{}).get('status'),'HOLD')
        self.assertEqual(r['findings'],[])
        self.assertEqual(len(r.get('rejected_findings',[])),1)
        self.assertNotEqual(r['review_status'],'PASS')
    def test_legacy_row_index_alone_is_not_authoritative(self):
        raw=review_raw();raw['findings'][0].pop('row_id');raw['findings'][0]['row_index']=0
        r=reviewer.run_engineering_review(package(),client=Client([raw]))
        self.assertEqual(r['findings'],[])
    def test_unknown_evidence_and_row_id_are_rejected(self):
        for kw in ({'row_id':'ROW-fake'},{'evidence_ids':['NOT-QUERIED']}):
            r=reviewer.run_engineering_review(package(),client=Client([review_raw(**kw)]))
            self.assertEqual(r['findings'],[])
    def test_correct_reference_is_derived_locally_and_raw_response_preserved(self):
        raw=review_raw();r=reviewer.run_engineering_review(package(),client=Client([raw]))
        self.assertEqual(r.get('reference_validation',{}).get('status'),'PASS')
        self.assertEqual(r['findings'][0].get('row_index'),0)
        self.assertEqual(r.get('raw_review'),raw)
        self.assertEqual(len(r.get('reviewed_report_sha256','')),64)
    def test_changed_row_rejects_stale_review(self):
        r=reviewer.run_engineering_review(package(),client=Client([review_raw()]))
        self.assertTrue(hasattr(reviewer,'review_matches_report'),'missing snapshot validation')
        rows=package()['report_rows'];self.assertTrue(reviewer.review_matches_report(r,rows))
        rows[0]['content']='사람이 편집한 새로운 내용'
        self.assertFalse(reviewer.review_matches_report(r,rows))
    def test_duplicate_or_missing_row_ids_fail_before_model(self):
        for rows in ([package()['report_rows'][0]]*2,[{'section':'발생 원인','content':'no ID'}]):
            c=Client([review_raw()]);p=package();p['report_rows']=rows
            with self.assertRaises(ValueError):reviewer.run_engineering_review(p,client=c)
            self.assertFalse(c.requests)
    def test_literal_tag_omitted_from_related_tags_is_not_grounded(self):
        c=normalize_claim({'claim':'vppA 및 vppB 상승을 관측','evidence_ids':['R-A1'],'related_tags':['vppA']},'direct_trigger',Store())
        self.assertEqual(c['status'],'UNKNOWN')
        self.assertTrue(any('vppB' in n for n in c['verification_notes']))
    def test_interval_requires_both_endpoints_for_each_raw_tag(self):
        c=normalize_claim({'claim':'두 신호를 구간 내 관측','evidence_ids':['R-A0','R-A1','R-B0'],
            'related_tags':['vppA','vppB'],'time_interval_s':[47.92,48.92]},'counter_evidence',Store())
        self.assertEqual(c['status'],'UNKNOWN')
    def test_citation_repair_once_without_new_tools_or_python_filling(self):
        from unittest.mock import patch
        bad={'direct_trigger':{'claim':'vppA 및 vppB 상승을 관측','evidence_ids':['R-A1'],'related_tags':['vppA','vppB']}}
        good=copy.deepcopy(bad);good['direct_trigger']['evidence_ids'].append('R-B1')
        c=Client([bad,good])
        with patch('gemini_agent.AgentToolSession',return_value=SimpleNamespace(calls_used=8,max_calls=8)):
            out=run_gemini_analysis(Store(),run_id='TEST',data_digest='TEST',client=c)
        self.assertEqual(len(c.requests),2)
        self.assertNotIn('tools',c.requests[1])
        self.assertEqual(out.get('citation_repair',{}).get('attempts'),1)
        self.assertEqual(out['direct_trigger']['evidence_ids'],['R-A1','R-B1'])
        self.assertEqual(bad['direct_trigger']['evidence_ids'],['R-A1'])
        self.assertEqual(out['agent_execution']['tool_calls_used'],8)
    def test_failed_repair_stays_unknown_and_never_loops(self):
        from unittest.mock import patch
        bad={'direct_trigger':{'claim':'vppA 및 vppB 상승','evidence_ids':['R-A1'],'related_tags':['vppA','vppB']}}
        c=Client([bad,bad])
        with patch('gemini_agent.AgentToolSession',return_value=SimpleNamespace(calls_used=8,max_calls=8)):
            out=run_gemini_analysis(Store(),run_id='TEST',data_digest='TEST',client=c)
        self.assertEqual(len(c.requests),2)
        self.assertEqual(out['direct_trigger']['status'],'UNKNOWN')
        self.assertEqual(out['verification_gate'],'HOLD')

if __name__=='__main__':unittest.main()
