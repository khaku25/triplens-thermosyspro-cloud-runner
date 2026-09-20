"""The report includes all original EVENT rows, not only the analyzer's query window."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_review_reference_fix import reviewer, package, Client, review_raw

class ReportEvidenceTests(unittest.TestCase):
    def test_ten_section_snapshot_is_accepted(self):
        p=package()
        p['report_rows']=[{'row_id':f'ROW-{i}','section':section,'item':'검토','content':'검토','status':'OBSERVED'}
            for i,section in enumerate([
                '개요','사고 발생 전 운전 현황','장애 현상','시간대별 사건·자동동작(SOE)','발생 원인',
                '운전원·정비 조치사항','조치 결과 및 복구 판정','추정 원인 및 미확인 사항',
                '재발방지 대책 — 검토 권고사항','증거자료'
            ],1)]
        client=Client([review_raw(row_id=None,current_section=None,evidence_ids=[])])
        result=reviewer.run_engineering_review(p,client=client)
        self.assertEqual(result['missing_required_sections'],[])
        self.assertEqual(len(client.requests),1)

    def test_unqueried_original_event_can_support_report_but_not_claim_analyzer_read_it(self):
        p=package();p['report_rows'][0]['evidence_ids']='E21'
        p['events']=[{'evidence_id':'E21','event_id':'E21','source_kind':'EVENT',
            'model_time_s':137.4,'tag':'PRESSURE_LOW','source_node':'vppIPDrumPressurePa','value':'2546547.257473'}]
        before=copy.deepcopy(p)
        client=Client([review_raw(evidence_ids=['E21'])])
        result=reviewer.run_engineering_review(p,client=client)
        self.assertEqual(result.get('reference_validation',{}).get('status'),'PASS')
        sent=json.loads(client.requests[0]['input'][0]['content'][0]['text'].split('\n',1)[1])
        self.assertIn('E21',{e['evidence_id'] for e in sent['evidence_catalog']})
        self.assertNotIn('E21',sent['evidence_scope']['analyzer_retrieved_evidence_ids'])
        self.assertIn('E21',sent['evidence_scope']['report_only_event_ids'])
        self.assertEqual(p,before)
    def test_unknown_report_evidence_blocks_before_paid_review(self):
        p=package();p['report_rows'][0]['evidence_ids']='E-NOT-REAL';client=Client([review_raw()])
        with self.assertRaisesRegex(ValueError,'report evidence'):
            reviewer.run_engineering_review(p,client=client)
        self.assertFalse(client.requests)
    def test_conflicting_original_event_cannot_overwrite_existing_catalog(self):
        p=package();e={'evidence_id':'E1','event_id':'E1','source_kind':'EVENT','model_time_s':1,'tag':'TRIP'}
        p['evidence_catalog'].append(e);p['events']=[{**e,'model_time_s':2}];client=Client([review_raw()])
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            reviewer.run_engineering_review(p,client=client)
        self.assertFalse(client.requests)
    def test_raw_record_cannot_be_added_as_report_only_event(self):
        p=package();p['events']=[{'event_id':'RAW:100:vppA','source_kind':'RAW','value':1}]
        client=Client([review_raw()])
        with self.assertRaisesRegex(ValueError,'EVENT'):
            reviewer.run_engineering_review(p,client=client)
        self.assertFalse(client.requests)

if __name__=='__main__':unittest.main()
