"""Canonical output contract: reference checks are NOT engineering proof.
Python never creates a causal claim or accepts AI self-confirmation.
"""
from __future__ import annotations
import math
VERSION='GROUNDED_ANALYSIS_V3'
STATUSES={'CONFIRMED','CANDIDATE','OBSERVED','UNKNOWN'}
LIST_FIELDS=('critical_events','propagation','causal_chain','counter_evidence')
CLAIM_SCHEMA={'type':'object','properties':{
 'status':{'type':'string','enum':['CANDIDATE','OBSERVED','UNKNOWN']},
 'claim':{'type':'string','description':'한국어 설명. 관측과 추론을 구분하고 운전 조작 지시를 쓰지 마세요.'},
 'evidence_ids':{'type':'array','items':{'type':'string'}},'related_tags':{'type':'array','items':{'type':'string'}},
 'model_time_s':{'type':['number','null']},
 'time_interval_s':{'type':['array','null'],'items':{'type':'number'},'minItems':2,'maxItems':2},
 'ai_confidence':{'type':['number','null'],'minimum':0,'maximum':1}},
 'required':['status','claim','evidence_ids','related_tags','model_time_s','time_interval_s','ai_confidence'],'additionalProperties':False}
ANALYSIS_SCHEMA={'type':'object','properties':{
 **{name:{'type':'array','items':CLAIM_SCHEMA} for name in LIST_FIELDS},'primary_cause':CLAIM_SCHEMA,'direct_trigger':CLAIM_SCHEMA,
 'additional_evidence_required':{'type':'array','items':{'type':'string'}},'review_recommendations':{'type':'array','items':{'type':'string'}}},
 'required':[*LIST_FIELDS,'primary_cause','direct_trigger','additional_evidence_required','review_recommendations'],'additionalProperties':False}

def as_list(v):return [] if v is None or v=='' else v if isinstance(v,list) else [v]
def strings(v):return list(dict.fromkeys(str(x).strip() for x in as_list(v) if isinstance(x,(str,int,float)) and str(x).strip()))
def number(v):
    if v is None or v=='' or isinstance(v,bool):return None
    try:n=float(v)
    except (ValueError,TypeError):return None
    return n if math.isfinite(n) else None

def text(v):
    if isinstance(v,str):return v.strip()
    if not isinstance(v,dict):return ''
    for key in ('claim','description','finding','text','reason','item'):
        if isinstance(v.get(key),str) and v[key].strip():return v[key].strip()
    return ''

def normalize_claim(value,stage,store=None):
    src=value if isinstance(value,dict) else {'claim':text(value)}
    ids=strings(src.get('evidence_ids') or src.get('evidence_id') or src.get('event_id'))
    for e in as_list(src.get('evidence')):
        if isinstance(e,dict):ids+=strings(e.get('evidence_id') or e.get('event_id'))
    ids=list(dict.fromkeys(ids));tags=strings(src.get('related_tags') or src.get('tags') or src.get('tag'))
    when=number(src.get('model_time_s'))
    if when is None:when=number(src.get('recorded_time',src.get('aligned_time_s')))
    wall=str(src.get('wall_time_utc') or '');legacy=src.get('recorded_time')
    if not wall and isinstance(legacy,str) and 'T' in legacy:wall=legacy
    interval=src.get('time_interval_s')
    interval=[number(x) for x in interval] if isinstance(interval,list) and len(interval)==2 else None
    if interval and (None in interval or interval[0]>interval[1]):interval=None
    notes=[];refs=[];valid_ids=[]
    if store:
        catalog={x['evidence_id']:x for x in store.evidence_catalog()}
        for eid in ids:
            if eid in catalog:refs.append(catalog[eid]);valid_ids.append(eid)
            else:notes.append(f'미조회 또는 존재하지 않는 근거 ID: {eid}')
    else:valid_ids=ids
    if not ids:notes.append('근거 ID 미연결')
    actual_tags={t for r in refs for t in [r.get('tag'),r.get('source_node'),r.get('original_tag'),r.get('canonical_tag'),r.get('lookup_key')] if t}
    if store:
        invalid=[t for t in tags if t not in actual_tags]
        if invalid:notes.append('인용 근거에 없는 태그: '+', '.join(invalid))
        tags=list(dict.fromkeys(r.get('source_node') or r.get('tag') for r in refs if r.get('source_node') or r.get('tag')))
    times=sorted({r['model_time_s'] for r in refs if number(r.get('model_time_s')) is not None})
    if interval and times:
        if not all(any(abs(t-x)<1e-6 for x in times) for t in interval):
            notes.append('주장한 시간구간과 인용 표본의 시각 불일치');interval=None
        else:when=None
    if times:
        if when is None and not interval and len(times)==1:when=times[0]
        elif when is not None and not any(abs(when-t)<1e-6 for t in times):notes.append('AI 시각과 인용 근거 시각 불일치');when=times[0]
        if not wall:wall=next((r.get('wall_time_utc','') for r in refs if r.get('model_time_s')==when),'')
    confidence=number(src.get('ai_confidence',src.get('confidence')))
    if confidence is not None and not 0<=confidence<=1:confidence=None
    status=str(src.get('status',src.get('disposition',''))).upper()
    if status not in STATUSES:status='CANDIDATE' if stage in {'primary_cause','direct_trigger'} else 'OBSERVED'
    if status=='CONFIRMED':status='CANDIDATE' if stage in {'primary_cause','direct_trigger'} else 'OBSERVED'
    if not valid_ids or notes:status='UNKNOWN'
    if stage in {'primary_cause','direct_trigger'} and status=='OBSERVED':status='CANDIDATE'
    claim=text(src)
    if not claim:claim='설명 미제공';notes.append('설명 미제공');status='UNKNOWN'
    if stage=='primary_cause' and not valid_ids:claim='선행 원인을 뒷받침하는 조회 근거가 부족합니다. 원인은 미확인입니다.'
    logic_ids=list(dict.fromkeys(i for r in refs for i in r.get('logic_ids',[])))
    logic_ok=bool(store and tags and all(store.logic_matches([t]) for t in tags))
    return {'stage':stage,'status':status,'claim':claim,'description':claim,'evidence_ids':valid_ids,'related_tags':tags,
            'original_tags':list(dict.fromkeys(r.get('original_tag') or r.get('tag') for r in refs if r.get('original_tag') or r.get('tag'))),
            'model_time_s':when,'time_interval_s':interval,'evidence_time_range_s':[times[0],times[-1]] if times else None,
            'recorded_time':str(when) if when is not None else '','wall_time_utc':wall,'ai_confidence':confidence,'ai_proposed_status':src.get('status',''),
            'logic_master_status':'VERIFIED' if logic_ok else 'NOT_VERIFIED','logic_verification_scope':'REGISTRATION_ONLY','logic_ids':logic_ids,
            'evidence_verified':bool(store and valid_ids and not notes),'review_required':True,'verification_notes':notes}

def normalize_analysis(raw=None,store=None,trace=None):
    src=raw if isinstance(raw,dict) else {}
    out={name:[normalize_claim(x,name,store) for x in as_list(src.get(name))] for name in LIST_FIELDS}
    for name in ('primary_cause','direct_trigger'):out[name]=normalize_claim(src.get(name,{}),name,store)
    out['additional_evidence_required']=[text(x) for x in as_list(src.get('additional_evidence_required')) if text(x)]
    out['review_recommendations']=[text(x) for x in as_list(src.get('review_recommendations')) if text(x)]
    all_claims=[out['primary_cause'],out['direct_trigger'],*[x for name in LIST_FIELDS for x in out[name]]]
    issues=[note for c in all_claims for note in c['verification_notes']];trigger=out['direct_trigger'];cause=out['primary_cause']
    if trigger['model_time_s'] is not None:
        interval=cause.get('time_interval_s')
        if interval and interval[0]>trigger['model_time_s']+1e-6:
            cause['status']='UNKNOWN';issues.append('선행 원인 표본 시간구간이 Direct Trigger보다 늦습니다.')
        elif interval and interval[1]>=trigger['model_time_s']-1e-6:
            issues.append('RAW 변화 시간구간이 Direct Trigger 시각과 겹칩니다. 선후관계는 표본만으로 확정할 수 없습니다.')
        if cause['model_time_s'] is not None and cause['model_time_s']>trigger['model_time_s']+1e-6:
            cause['status']='UNKNOWN';issues.append('선행 원인 시각이 Direct Trigger보다 늦습니다.')
        for item in out['propagation']:
            if item['model_time_s'] is not None and item['model_time_s']<trigger['model_time_s']-1e-6:
                item['status']='UNKNOWN';item['verification_notes'].append('Direct Trigger 이전 관측: 파급 분류 검토 필요');issues.append('파급 항목의 시간 선후관계 불일치')
    traces=trace or [];successful={t.get('name') for t in traces if t.get('status')=='OK'}
    has_raw=any(t.get('status')=='OK' and t.get('raw_evidence_count',0)>0 for t in traces);has_logic='get_logic_context' in successful
    if not has_raw:issues.append('RAW Tool 조회 성공 기록 없음')
    if not has_logic:issues.append('Logic Tool 조회 성공 기록 없음')
    if any(t.get('status')!='OK' for t in traces):issues.append('Tool 오류 또는 호출 예산 소진')
    if cause['status']=='UNKNOWN':issues.append('Primary Cause 미확인')
    if trigger['status']=='UNKNOWN':issues.append('Direct Trigger 미확인')
    if not trigger['logic_ids']:issues.append('Direct Trigger의 등록 로직 연결 미확인')
    gate='PASS' if store and has_raw and has_logic and not issues and all(c['evidence_verified'] for c in all_claims) else 'HOLD'
    out.update(output_contract_version=VERSION,verification_gate=gate,verification_scope='REFERENCE_AND_CHRONOLOGY_CHECKS_NOT_ENGINEERING_CAUSAL_PROOF',verification_notes=list(dict.fromkeys(issues)),tool_trace=traces,finality={'can_mark_final_confirmed':False,'output_label':'고장보고서 초안','human_approval_required':True})
    if issues:out['additional_evidence_required']=list(dict.fromkeys(out['additional_evidence_required']+issues))
    return out
