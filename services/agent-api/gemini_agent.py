"""Bounded Gemini tool loop. No precomputed causal decisions or hidden answers."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from triplens.agent_tools import AgentToolSession
from triplens.analysis_contract import ANALYSIS_SCHEMA, normalize_analysis

SERVICE_ROOT=Path(__file__).resolve().parent
DEFAULT_MODEL='gemini-3.8-flash'

def declaration(name,description,properties,required=()):
    return {'type':'function','name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':list(required)}}
STR={'type':'string'}; NUM={'type':'number'}; INT={'type':'integer'}; TAGS={'type':'array','items':STR}
TOOL_DECLARATIONS=[
 declaration('search_events','Search actual EVENT records; original and exact mapped source identities are returned. A limited result is not proof that other events do not exist.',{'query':STR,'equipment':STR,'event_class':STR,'tags':TAGS,'limit':INT}),
 declaration('get_event_window','Chronological EVENT near a model-time center; each side <=10s, max30 rows.',{'center_time_s':NUM,'before_s':NUM,'after_s':NUM,'limit':INT},['center_time_s']),
 declaration('get_raw_window','Read <=8 exact inventory tags over <=20s. Every returned value has a RAW Evidence ID. Never guess tag names.',{'tags':TAGS,'start_time_s':NUM,'end_time_s':NUM,'max_rows':INT},['tags','start_time_s','end_time_s']),
 declaration('get_tag_series','Read one exact RAW tag. Includes extrema, bounded points, and binary transition bracketing samples with IDs.',{'tag':STR,'start_time_s':NUM,'end_time_s':NUM,'max_points':INT},['tag','start_time_s','end_time_s']),
 declaration('get_logic_context','Exact source tag or equipment::event tag lookup. Returns registered upstream tags to query in RAW. VERIFIED here means registration only, not incident causality.',{'tags':TAGS,'limit':INT},['tags']),
 declaration('get_equipment_state','Read equipment events and explicit RAW states near model time; stale nearest samples are marked.',{'equipment':STR,'at_time_s':NUM,'tags':TAGS},['equipment','at_time_s'])]

def _system_prompt():
    return (SERVICE_ROOT/'triplens'/'hybrid_agent_prompt.md').read_text(encoding='utf-8')

def _json_from_text(value):
    candidate=(value or '').strip()
    if candidate.startswith('```'):
        candidate='\n'.join(candidate.splitlines()[1:-1])
    raw=json.loads(candidate)
    if not isinstance(raw,dict): raise ValueError('Gemini output must be an object')
    return raw

def fail_closed_contract(raw=None):
    """Compatibility entry point: no ledger => no engineering confirmation."""
    return normalize_analysis(raw)

def evidence_ids(value):
    ids=[]
    if isinstance(value,dict):
        if isinstance(value.get('evidence_id'),str): ids.append(value['evidence_id'])
        for key,v in value.items():
            if key=='evidence_ids': ids.extend(v.values() if isinstance(v,dict) else v if isinstance(v,list) else [])
            else: ids.extend(evidence_ids(v))
    elif isinstance(value,list):
        for v in value: ids.extend(evidence_ids(v))
    return list(dict.fromkeys(x for x in ids if isinstance(x,str)))

def run_gemini_analysis(store,*,run_id,data_digest,model=None,client=None):
    if client is None:
        key=os.getenv('GEMINI_API_KEY','').strip()
        if not key: raise RuntimeError('GEMINI_API_KEY is not configured')
        from google import genai
        client=genai.Client(api_key=key,http_options={'timeout':45000})
    model_name=model or os.getenv('TRIPLENS_GEMINI_MODEL',DEFAULT_MODEL)
    session=AgentToolSession(store)
    bootstrap=store.build_agent_bootstrap(run_id=run_id,data_digest=data_digest)
    history=[{'type':'user_input','content':[{'type':'text','text':'한국어로 분석하세요. 아래는 입력에서 확인한 조회 안내이며 정답이 아닙니다. '+json.dumps(bootstrap,ensure_ascii=False)}]}]
    trace=[]; usage=[]; started=time.monotonic(); corrected=False
    for turn in range(10):
        if time.monotonic()-started>210: raise TimeoutError('Agent analysis deadline exceeded')
        kwargs={'model':model_name,'store':False,'input':history,'system_instruction':_system_prompt(),
                'response_format':{'type':'text','mime_type':'application/json','schema':ANALYSIS_SCHEMA}}
        if session.calls_used<session.max_calls: kwargs['tools']=TOOL_DECLARATIONS
        result=client.interactions.create(**kwargs)
        for step in result.steps: history.append(step.model_dump())
        u=getattr(result,'usage',None)
        if u is not None: usage.append(u.model_dump() if hasattr(u,'model_dump') else u if isinstance(u,dict) else {})
        calls=[s for s in result.steps if s.type=='function_call']
        if not calls:
            raw=_json_from_text(result.output_text)
            successful={t['name'] for t in trace if t['status']=='OK'}
            needed=not(successful&{'get_raw_window','get_tag_series','get_equipment_state'}) or 'get_logic_context' not in successful
            if needed and session.calls_used<session.max_calls and not corrected:
                corrected=True
                history.append({'type':'user_input','content':[{'type':'text','text':'조회가 불충분합니다. 원인을 단정하거나 없다고 결론내리기 전에 등록된 Logic upstream 태그와 실제 RAW 표본을 조회하세요. 도구로 확인되지 않은 항목은 UNKNOWN으로 남기세요.'}]})
                continue
            output=normalize_analysis(raw,store,trace)
            output['agent_execution']={'model':model_name,'tool_calls_used':session.calls_used,'tool_budget':8,'model_turns':turn+1,'duration_ms':round((time.monotonic()-started)*1000),'usage':usage,'causal_decision_author':'GEMINI','reference_verifier':'PYTHON'}
            return output
        # Every function call, including denied over-budget calls, gets a result.
        for call in calls:
            arguments=dict(call.arguments or {}); t0=time.monotonic(); executed=False
            if session.calls_used>=session.max_calls:
                value={'status':'BUDGET_EXHAUSTED','message':'Return UNKNOWN for unsupported claims.'}; status='BUDGET_EXHAUSTED'
            else:
                executed=True
                try:
                    value=session.call(call.name,arguments); status='OK'
                    if call.name in {'get_raw_window','get_tag_series','get_equipment_state'} and not evidence_ids(value): status='NO_EVIDENCE'
                    if call.name=='get_logic_context' and not value.get('items'): status='NO_EVIDENCE'
                except (ValueError,TypeError,KeyError,RuntimeError) as exc:
                    # No arbitrary exception text, credentials or model thoughts in diagnostics.
                    value={'status':'TOOL_ERROR','error_type':type(exc).__name__,'message':'도구 인자 또는 조회 범위를 확인하세요.'}; status='TOOL_ERROR'
            ids=evidence_ids(value)
            trace.append({'name':call.name,'arguments':arguments,'status':status,'executed':executed,
                          'evidence_ids':ids,'evidence_count':len(ids),'duration_ms':round((time.monotonic()-t0)*1000)})
            history.append({'type':'function_result','name':call.name,'call_id':call.id,'result':[{'type':'text','text':json.dumps(value,ensure_ascii=False,allow_nan=False)}]})
    output=normalize_analysis({'additional_evidence_required':['모델 왕복 횟수 한도에 도달했습니다.']},store,trace)
    output['agent_execution']={'model':model_name,'tool_calls_used':session.calls_used,'tool_budget':8,'model_turns':10,'causal_decision_author':'GEMINI'}
    return output
