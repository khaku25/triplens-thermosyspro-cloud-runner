"""Offline tests for the OpenAI Responses API tool loop; never calls OpenAI."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVICE))
from openai_agent import OpenAIResponsesClient,run_openai_analysis
from triplens.analysis_contract import ANALYSIS_SCHEMA


class EvidenceStore:
    event_rows=[]
    def build_agent_bootstrap(self,*,run_id,data_digest):
        return {'run_id':run_id,'data_digest':data_digest,'mode':'test-only','decision_authority':'GEMINI_AGENT'}
    def get_raw_window(self,**kwargs):
        return {'points':[{'evidence_id':'RAW:TEST:1'}]}
    def get_logic_context(self,**kwargs):
        return {'items':[{'logic_id':'LOGIC-TEST'}]}
    def evidence_catalog(self):
        return []
    def logic_matches(self,tags):
        return False


def final_analysis():
    unknown={'status':'UNKNOWN','claim':'추가 확인 필요','evidence_ids':[],'related_tags':[],
             'model_time_s':None,'time_interval_s':None,'ai_confidence':None}
    return {'critical_events':[],'propagation':[],'causal_chain':[],'counter_evidence':[],
            'primary_cause':unknown,'direct_trigger':unknown,
            'additional_evidence_required':[],'review_recommendations':[]}


class HTTPResponse:
    status=200
    def __init__(self,value):self.payload=json.dumps(value).encode()
    def read(self):return self.payload
    def __enter__(self):return self
    def __exit__(self,*_args):return False


class OpenAIAgentTests(unittest.TestCase):
    @patch.dict(os.environ,{'OPENAI_API_KEY':'offline-test-key'},clear=True)
    def test_responses_api_tool_calls_use_shared_evidence_tools_and_output_contract(self):
        requests=[]
        responses=[
            {'id':'resp_tools','output':[
                {'id':'fc_raw','type':'function_call','call_id':'call_raw','name':'get_raw_window',
                 'arguments':json.dumps({'tags':['vppTestTag'],'start_time_s':0,'end_time_s':1})},
                {'id':'fc_logic','type':'function_call','call_id':'call_logic','name':'get_logic_context',
                 'arguments':json.dumps({'tags':['vppTestTag']})},
            ],'usage':{'input_tokens':120,'output_tokens':30}},
            {'id':'resp_final','output':[{'id':'msg_final','type':'message','role':'assistant','content':[
                {'type':'output_text','text':json.dumps(final_analysis(),ensure_ascii=False)}
            ]}],'usage':{'input_tokens':180,'output_tokens':70}},
        ]

        def intercept(request,timeout=0):
            requests.append((request,json.loads(request.data)))
            body=responses[len(requests)-1]
            return HTTPResponse(body)

        with patch('openai_agent.urlopen',side_effect=intercept):
            client=OpenAIResponsesClient(api_key='offline-test-key')
            result=run_openai_analysis(EvidenceStore(),run_id='RUN-1',data_digest='HASH',client=client)

        self.assertEqual(len(requests),2)
        self.assertEqual(requests[0][0].full_url,'https://api.openai.com/v1/responses')
        self.assertEqual(requests[0][0].get_header('Authorization'),'Bearer offline-test-key')
        self.assertEqual(requests[0][1]['model'],'gpt-6-luna')
        self.assertIn('OPENAI_AGENT',requests[0][1]['input'][0]['content'][0]['text'])
        self.assertNotIn('GEMINI_AGENT',requests[0][1]['input'][0]['content'][0]['text'])
        self.assertFalse(requests[0][1]['store'])
        self.assertEqual(len(requests[0][1]['tools']),6)
        self.assertEqual(requests[0][1]['text']['format']['schema'],ANALYSIS_SCHEMA)
        self.assertTrue(any(item.get('type')=='function_call_output' for item in requests[1][1]['input']))
        self.assertEqual(result['agent_execution']['provider'],'openai')
        self.assertEqual(result['agent_execution']['model'],'gpt-6-luna')
        self.assertEqual(result['agent_execution']['tool_calls_used'],2)
        self.assertEqual(result['agent_execution']['usage'][0]['input_tokens'],120)

    @patch.dict(os.environ,{},clear=True)
    def test_missing_openai_key_fails_before_network_or_analysis(self):
        with self.assertRaisesRegex(RuntimeError,'OPENAI_API_KEY'):
            run_openai_analysis(EvidenceStore(),run_id='R',data_digest='D')


if __name__=='__main__':
    unittest.main()
