"""Bounded Gemini tool loop. No precomputed causal decisions or hidden answers."""
from __future__ import annotations
import copy
import json
import os
import time
from pathlib import Path
from triplens.agent_tools import AgentToolSession
from triplens.analysis_contract import ANALYSIS_SCHEMA,normalize_analysis
from triplens.citation_support import citation_feedback, REPAIR_INSTRUCTION
SERVICE_ROOT=Path(__file__).resolve().parent
DEFAULT_MODEL='gemini-3.8-flash'

# Pricing snapshot for per-run estimation. Environment overrides keep this safe if pricing changes.
MODEL_PRICING_USD_PER_M={
    'gemini-3.8-flash': {'input':0.75,'output':3.75,'valid_through':'2026-12-31'},
}
USAGE_KEYS=('total_input_tokens','total_output_tokens','total_thought_tokens','total_cached_tokens','total_tool_use_tokens','total_tokens')

def summarize_usage(usages,model_name):
    totals={key:0 for key in USAGE_KEYS}
    for item in usages or []:
        if not isinstance(item,dict):continue
        for key in USAGE_KEYS:
            value=item.get(key,0)
            if isinstance(value,(int,float)) and not isinstance(value,bool):totals[key]+=int(value)
    pricing=MODEL_PRICING_USD_PER_M.get(model_name)
    input_override=os.getenv('TRIPLENS_GEMINI_INPUT_USD_PER_M','').strip()
    output_override=os.getenv('TRIPLENS_GEMINI_OUTPUT_USD_PER_M','').strip()
    if input_override or output_override:
        try:
            pricing={'input':float(input_override or (pricing or {}).get('input')),'output':float(output_override or (pricing or {}).get('output')),'valid_through':'ENV_OVERRIDE'}
        except (TypeError,ValueError):pricing=None
    estimated_cost_usd=None
    if pricing:
        billable_output=totals['total_output_tokens']+totals['total_thought_tokens']
        estimated_cost_usd=round((totals['total_input_tokens']*pricing['input']+billable_output*pricing['output'])/1_000_000,6)
    return {**totals,
        'billable_output_tokens':totals['total_output_tokens']+totals['total_thought_tokens'],
        'estimated_cost_usd':estimated_cost_usd,
        'pricing_usd_per_m':pricing,
        'request_count':len(usages or []),
        'estimate_note':'Estimate from Gemini usage; actual billing can differ for caching, promotions, taxes, or provider adjustments.'}

def declaration(name,description,properties,required=()):return {'type':'function','name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':list(required)}}
STR={'type':'string'};NUM={'type':'number'};INT={'type':'integer'};TAGS={'type':'array','items':STR}
TOOL_DECLARATIONS=[
 declaration('search_events','Search actual EVENT records; original and exact mapped source identities are returned. A limited result is not proof that other events do not exist.',{'query':STR,'equipment':STR,'event_class':STR,'tags':TAGS,'limit':INT}),
 declaration('get_event_window','Chronological EVENT near a model-time center; each side <=10s, max30 rows.',{'center_time_s':NUM,'before_s':NUM,'after_s':NUM,'limit':INT},['center_time_s']),
 declaration('get_raw_window','Read <=8 exact inventory tags over <=20s. Every returned value has a RAW Evidence ID. Never guess tag names.',{'tags':TAGS,'start_time_s':NUM,'end_time_s':NUM,'max_rows':INT},['tags','start_time_s','end_time_s']),
 declaration('get_tag_series','Read one exact RAW tag. Includes extrema, bounded points, and binary transition bracketing samples with IDs.',{'tag':STR,'start_time_s':NUM,'end_time_s':NUM,'max_points':INT},['tag','start_time_s','end_time_s']),
 declaration('get_logic_context','Exact source tag or equipment::event tag lookup. Returns registered upstream tags to query in RAW. VERIFIED means registration only, not incident causality.',{'tags':TAGS,'limit':INT},['tags']),
 declaration('get_equipment_state','Read equipment events and explicit RAW states near model time; stale nearest samples are marked.',{'equipment':STR,'at_time_s':NUM,'tags':TAGS},['equipment','at_time_s'])]

def _system_prompt():return (SERVICE_ROOT/'triplens'/'hybrid_agent_prompt.md').read_text(encoding='utf-8')
def _json_from_text(value):
    candidate=(value or '').strip()
    if candidate.startswith('```'):candidate='\n'.join(candidate.splitlines()[1:-1])
    raw=json.loads(candidate)
    if not isinstance(raw,dict):raise ValueError('Gemini output must be an object')
    return raw

def fail_closed_contract(raw=None):return normalize_analysis(raw)

def evidence_ids(value):
    ids=[]
    if isinstance(value,dict):
        if isinstance(value.get('evidence_id'),str):ids.append(value['evidence_id'])
        for key,v in value.items():
            if key in {'evidence_ids','raw_evidence_ids'}:ids.extend(v.values() if isinstance(v,dict) else v if isinstance(v,list) else [])
            else:ids.extend(evidence_ids(v))
    elif isinstance(value,list):
        for v in value:ids.extend(evidence_ids(v))
    return list(dict.fromkeys(x for x in ids if isinstance(x,str)))

def run_gemini_analysis(store,*,run_id,data_digest,model=None,client=None):
    if client is None:
        key=os.getenv('GEMINI_API_KEY','').strip()
        if not key:raise RuntimeError('GEMINI_API_KEY is not configured')
        from google import genai
        client=genai.Client(api_key=key,http_options={'timeout':45000})
    model_name=model or os.getenv('TRIPLENS_GEMINI_MODEL',DEFAULT_MODEL);session=AgentToolSession(store)
    bootstrap=store.build_agent_bootstrap(run_id=run_id,data_digest=data_digest)
    history=[{'type':'user_input','content':[{'type':'text','text':'한국어로 분석하세요. 아래는 입력에서 확인한 조회 안내이며 정답이 아닙니다. '+json.dumps(bootstrap,ensure_ascii=False)}]}]
    trace=[];usage=[];started=time.monotonic();corrected=False
    for turn in range(10):
        if time.monotonic()-started>210:raise TimeoutError('Agent analysis deadline exceeded')
        kwargs={'model':model_name,'store':False,'input':history,'system_instruction':_system_prompt(),'response_format':{'type':'text','mime_type':'application/json','schema':ANALYSIS_SCHEMA}}
        if session.calls_used<session.max_calls:kwargs['tools']=TOOL_DECLARATIONS
        result=client.interactions.create(**kwargs)
        for step in result.steps:history.append(step.model_dump())
        u=getattr(result,'usage',None)
        if u is not None:usage.append(u.model_dump() if hasattr(u,'model_dump') else u if isinstance(u,dict) else {})
        calls=[s for s in result.steps if s.type=='function_call']
        if not calls:
            raw=_json_from_text(result.output_text);successful={t['name'] for t in trace if t['status']=='OK'}
            needed=not any(t.get('raw_evidence_count',0)>0 and t['status']=='OK' for t in trace) or 'get_logic_context' not in successful
            if needed and session.calls_used<session.max_calls and not corrected:
                corrected=True
                history.append({'type':'user_input','content':[{'type':'text','text':'조회가 불충분합니다. 원인을 단정하거나 없다고 결론내리기 전에 등록된 Logic upstream 태그와 실제 RAW 표본을 조회하세요. 도구로 확인되지 않은 항목은 UNKNOWN으로 남기세요.'}]});continue
            feedback=citation_feedback(raw,store)
            repair={'attempts':0,'status':'NOT_NEEDED','initial_issue_count':len(feedback),'remaining_issue_count':len(feedback),
                    'scope':'MODEL_CORRECTION_OVER_ALREADY_RETRIEVED_EVIDENCE_ONLY'}
            model_turns=turn+1
            if feedback:
                repair['initial_draft']=copy.deepcopy(raw)
                repair['status']='SKIPPED_DEADLINE'
                # Reserve the provider timeout inside the existing 210-second budget.
                if time.monotonic()-started<165:
                    repair['attempts']=1;model_turns+=1
                    repair_history=history+[{'type':'user_input','content':[{'type':'text','text':REPAIR_INSTRUCTION+json.dumps({'draft_to_revise':raw,'reference_feedback':feedback},ensure_ascii=False)}]}]
                    try:
                        revision=client.interactions.create(model=model_name,store=False,input=repair_history,
                            system_instruction=_system_prompt(),response_format={'type':'text','mime_type':'application/json','schema':ANALYSIS_SCHEMA})
                        if any(s.type=='function_call' for s in revision.steps):raise ValueError('Reference repair cannot execute tools')
                        candidate=_json_from_text(revision.output_text)
                        # Malformed/empty replacement cannot erase the initial draft.
                        if any(k not in candidate for k in raw if k in ANALYSIS_SCHEMA['properties']):raise ValueError('Incomplete citation revision')
                        raw=candidate
                        repair['status']='MODEL_REVISED'
                        u=getattr(revision,'usage',None)
                        if u is not None:usage.append(u.model_dump() if hasattr(u,'model_dump') else u if isinstance(u,dict) else {})
                    except Exception as exc:
                        repair['status']='REPAIR_FAILED_RETAINED_INITIAL_DRAFT';repair['error_type']=type(exc).__name__
                repair['remaining_issue_count']=len(citation_feedback(raw,store))
            output=normalize_analysis(raw,store,trace)
            output['citation_repair']=repair
            output['agent_execution']={'model':model_name,'tool_calls_used':session.calls_used,'tool_budget':8,'model_turns':model_turns,'duration_ms':round((time.monotonic()-started)*1000),'usage':usage,'usage_summary':summarize_usage(usage,model_name),'causal_decision_author':'GEMINI','reference_verifier':'PYTHON'}
            return output
        for call in calls:
            arguments=dict(call.arguments or {});t0=time.monotonic();executed=False
            if session.calls_used>=session.max_calls:value={'status':'BUDGET_EXHAUSTED','message':'Return UNKNOWN for unsupported claims.'};status='BUDGET_EXHAUSTED'
            else:
                executed=True
                try:
                    value=session.call(call.name,arguments);status='OK'
                    if call.name in {'get_raw_window','get_tag_series','get_equipment_state'} and not evidence_ids(value):status='NO_EVIDENCE'
                    if call.name=='get_logic_context' and not value.get('items'):status='NO_EVIDENCE'
                except (ValueError,TypeError,KeyError,RuntimeError) as exc:
                    value={'status':'TOOL_ERROR','error_type':type(exc).__name__,'message':'도구 인자 또는 조회 범위를 확인하세요.'};status='TOOL_ERROR'
            ids=evidence_ids(value)
            trace.append({'name':call.name,'arguments':arguments,'status':status,'executed':executed,'evidence_ids':ids,'evidence_count':len(ids),'raw_evidence_count':sum(eid.startswith('RAW:') for eid in ids),'duration_ms':round((time.monotonic()-t0)*1000)})
            history.append({'type':'function_result','name':call.name,'call_id':call.id,'result':[{'type':'text','text':json.dumps(value,ensure_ascii=False,allow_nan=False)}]})
    output=normalize_analysis({'additional_evidence_required':['모델 왕복 횟수 한도에 도달했습니다.']},store,trace)
    output['agent_execution']={'model':model_name,'tool_calls_used':session.calls_used,'tool_budget':8,'model_turns':10,'usage':usage,'usage_summary':summarize_usage(usage,model_name),'causal_decision_author':'GEMINI'}
    return output
