# ---------------------------------------------------------------------------
# CODE READING GUIDE
# File role: OpenAI adapter for the existing TripLens read-only analysis contract.
# Read in this order: request/response adapter -> bounded evidence-tool loop -> normalization.
# Tool results and final claims still pass through the shared Python reference checks.
# ---------------------------------------------------------------------------
"""Bounded OpenAI Responses API tool loop using TripLens evidence controls."""
from __future__ import annotations

import copy
import json
import os
import time
from urllib.request import Request, urlopen

from gemini_agent import TOOL_DECLARATIONS, _system_prompt, evidence_ids
from triplens.agent_tools import AgentToolSession
from triplens.analysis_contract import ANALYSIS_SCHEMA,normalize_analysis
from triplens.citation_support import citation_feedback,REPAIR_INSTRUCTION

DEFAULT_MODEL='gpt-5.6-luna'
RESPONSES_URL='https://api.openai.com/v1/responses'


class _ResponsesEndpoint:
    def __init__(self,client):self._client=client
    def create(self,**payload):return self._client.create_response(payload)


class OpenAIResponsesClient:
    """Small standard-library HTTP client for the Responses endpoint."""
    def __init__(self,api_key,timeout=45):
        self.api_key=api_key
        self.timeout=timeout
        self.responses=_ResponsesEndpoint(self)

    def create_response(self,payload):
        request=Request(
            RESPONSES_URL,
            data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8'),
            headers={'Authorization':f'Bearer {self.api_key}','Content-Type':'application/json'},
            method='POST',
        )
        with urlopen(request,timeout=self.timeout) as response:
            value=json.loads(response.read().decode('utf-8'))
        if not isinstance(value,dict):raise ValueError('OpenAI response must be an object')
        return value


def _json_from_text(value):
    candidate=str(value or '').strip()
    if candidate.startswith('```'):candidate='\n'.join(candidate.splitlines()[1:-1])
    raw=json.loads(candidate)
    if not isinstance(raw,dict):raise ValueError('OpenAI output must be an object')
    return raw


def _response_text(response):
    direct=response.get('output_text')
    if isinstance(direct,str) and direct.strip():return direct
    pieces=[]
    for item in response.get('output') or []:
        if not isinstance(item,dict) or item.get('type')!='message':continue
        for content in item.get('content') or []:
            if isinstance(content,dict) and content.get('type') in {'output_text','text'}:
                if isinstance(content.get('text'),str):pieces.append(content['text'])
    return '\n'.join(pieces)


def _create_response(client,model,history,*,tools_enabled):
    payload={
        'model':model,
        'store':False,
        'instructions':_system_prompt(),
        'input':history,
        'text':{'format':{'type':'json_schema','name':'triplens_analysis','schema':ANALYSIS_SCHEMA,'strict':True}},
    }
    if tools_enabled:
        payload['tools']=[{**tool,'strict':False} for tool in TOOL_DECLARATIONS]
    return client.responses.create(**payload)


def _run_openai_agent(store,*,run_id,data_digest,model,client):
    model_name=model or os.getenv('TRIPLENS_OPENAI_MODEL',DEFAULT_MODEL)
    session=AgentToolSession(store)
    bootstrap=store.build_agent_bootstrap(run_id=run_id,data_digest=data_digest)
    bootstrap['decision_authority']='OPENAI_AGENT'
    history=[{'role':'user','content':[{'type':'input_text','text':'한국어로 분석하세요. 아래는 입력에서 확인한 조회 안내이며 정답이 아닙니다. '+json.dumps(bootstrap,ensure_ascii=False)}]}]
    trace=[];usage=[];started=time.monotonic();corrected=False
    for turn in range(10):
        if time.monotonic()-started>210:raise TimeoutError('Agent analysis deadline exceeded')
        response=_create_response(client,model_name,history,tools_enabled=session.calls_used<session.max_calls)
        output_items=response.get('output') or []
        if not isinstance(output_items,list):raise ValueError('OpenAI output items must be a list')
        history.extend(output_items)
        current_usage=response.get('usage')
        if isinstance(current_usage,dict):usage.append(current_usage)
        calls=[item for item in output_items if isinstance(item,dict) and item.get('type')=='function_call']
        if not calls:
            raw=_json_from_text(_response_text(response))
            successful={item['name'] for item in trace if item['status']=='OK'}
            needed=not any(item.get('raw_evidence_count',0)>0 and item['status']=='OK' for item in trace) or 'get_logic_context' not in successful
            if needed and session.calls_used<session.max_calls and not corrected:
                corrected=True
                history.append({'role':'user','content':[{'type':'input_text','text':'조회가 불충분합니다. 원인을 단정하거나 없다고 결론내리기 전에 등록된 Logic upstream 태그와 실제 RAW 표본을 조회하세요. 도구로 확인되지 않은 항목은 UNKNOWN으로 남기세요.'}]})
                continue
            feedback=citation_feedback(raw,store)
            repair={'attempts':0,'status':'NOT_NEEDED','initial_issue_count':len(feedback),'remaining_issue_count':len(feedback),
                    'scope':'MODEL_CORRECTION_OVER_ALREADY_RETRIEVED_EVIDENCE_ONLY'}
            model_turns=turn+1
            if feedback:
                repair['initial_draft']=copy.deepcopy(raw)
                repair['status']='SKIPPED_DEADLINE'
                if time.monotonic()-started<165:
                    repair['attempts']=1;model_turns+=1
                    repair_history=history+[{'role':'user','content':[{'type':'input_text','text':REPAIR_INSTRUCTION+json.dumps({'draft_to_revise':raw,'reference_feedback':feedback},ensure_ascii=False)}]}]
                    try:
                        revision=_create_response(client,model_name,repair_history,tools_enabled=False)
                        if any(isinstance(item,dict) and item.get('type')=='function_call' for item in revision.get('output') or []):
                            raise ValueError('Reference repair cannot execute tools')
                        candidate=_json_from_text(_response_text(revision))
                        if any(key not in candidate for key in raw if key in ANALYSIS_SCHEMA['properties']):
                            raise ValueError('Incomplete citation revision')
                        raw=candidate;repair['status']='MODEL_REVISED'
                        revision_usage=revision.get('usage')
                        if isinstance(revision_usage,dict):usage.append(revision_usage)
                    except Exception as exc:
                        repair['status']='REPAIR_FAILED_RETAINED_INITIAL_DRAFT';repair['error_type']=type(exc).__name__
                repair['remaining_issue_count']=len(citation_feedback(raw,store))
            output=normalize_analysis(raw,store,trace)
            output['citation_repair']=repair
            output['agent_execution']={'provider':'openai','model':model_name,'tool_calls_used':session.calls_used,'tool_budget':8,
                'model_turns':model_turns,'duration_ms':round((time.monotonic()-started)*1000),'usage':usage,
                'causal_decision_author':'OPENAI','reference_verifier':'PYTHON'}
            return output
        for call in calls:
            t0=time.monotonic()
            name=str(call.get('name') or '')
            call_id=str(call.get('call_id') or '')
            arguments_text=call.get('arguments') or '{}'
            try:
                arguments=json.loads(arguments_text) if isinstance(arguments_text,str) else arguments_text
                if not isinstance(arguments,dict):raise ValueError('Tool arguments must be an object')
            except (ValueError,TypeError,json.JSONDecodeError):
                arguments={}
                value={'status':'TOOL_ERROR','error_type':'InvalidArguments','message':'도구 인자 JSON을 확인하세요.'}
                status='TOOL_ERROR';executed=False
            else:
                executed=False
                if session.calls_used>=session.max_calls:
                    value={'status':'BUDGET_EXHAUSTED','message':'Return UNKNOWN for unsupported claims.'};status='BUDGET_EXHAUSTED'
                else:
                    executed=True
                    try:
                        value=session.call(name,arguments);status='OK'
                        if name in {'get_raw_window','get_tag_series','get_equipment_state'} and not evidence_ids(value):status='NO_EVIDENCE'
                        if name=='get_logic_context' and not value.get('items'):status='NO_EVIDENCE'
                    except (ValueError,TypeError,KeyError,RuntimeError) as exc:
                        value={'status':'TOOL_ERROR','error_type':type(exc).__name__,'message':'도구 인자 또는 조회 범위를 확인하세요.'};status='TOOL_ERROR'
            ids=evidence_ids(value)
            trace.append({'name':name,'arguments':arguments,'status':status,'executed':executed,'evidence_ids':ids,'evidence_count':len(ids),
                'raw_evidence_count':sum(eid.startswith('RAW:') for eid in ids),'duration_ms':round((time.monotonic()-t0)*1000)})
            history.append({'type':'function_call_output','call_id':call_id,'output':json.dumps(value,ensure_ascii=False,allow_nan=False)})
    output=normalize_analysis({'additional_evidence_required':['모델 왕복 횟수 한도에 도달했습니다.']},store,trace)
    output['agent_execution']={'provider':'openai','model':model_name,'tool_calls_used':session.calls_used,'tool_budget':8,
        'model_turns':10,'causal_decision_author':'OPENAI'}
    return output


def run_openai_analysis(store,*,run_id,data_digest,model=None,client=None):
    if client is None:
        key=os.getenv('OPENAI_API_KEY','').strip()
        if not key:raise RuntimeError('OPENAI_API_KEY is not configured')
        client=OpenAIResponsesClient(key)
    return _run_openai_agent(store,run_id=run_id,data_digest=data_digest,model=model or DEFAULT_MODEL,client=client)
