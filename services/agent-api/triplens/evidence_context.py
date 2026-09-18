"""Read-only integration for the existing six tools; never selects a cause.

Registry links are identity metadata, not causal answers. Only exact identities
and actually supplied samples can become evidence. Original files are immutable.
"""
from __future__ import annotations
import csv
import re
from collections import Counter,defaultdict
from pathlib import Path
from .agent_tools import EvidenceStore,RAW_META_COLUMNS,FORBIDDEN,_event_public,_finite,_clamp_int
META=RAW_META_COLUMNS|{'time'}
VERSION='V8_EVIDENCE_INTEGRATION_V3'

def parts(value):return [x.strip() for x in re.split(r'[;,|]',str(value or '')) if x.strip()]
def finite_time(value):
    number=_finite(value)
    if number is None:raise ValueError('model_time_s는 유한한 숫자여야 합니다.')
    return number

def read_checked(path,kind):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f,strict=True);fields=reader.fieldnames or []
        normalized=[re.sub(r'[^a-z0-9]+','_',x.strip().lower()).strip('_') for x in fields]
        if len(fields)!=len(set(fields)) or len(normalized)!=len(set(normalized)):raise ValueError(f'{kind}: 중복 CSV 열 이름')
        blocked=set(normalized)&(FORBIDDEN|{'test_audit','expected_answer','fault_injection_metadata'})
        if blocked:raise ValueError(f'{kind}: 금지된 정답 메타데이터 열: {sorted(blocked)}')
        required={'model_time_s'}|({'event_id','event_class','equipment','tag'} if kind=='EVENT' else {'record_sequence'})
        if required-set(fields):raise ValueError(f'{kind}: 필수 열 누락: {sorted(required-set(fields))}')
        rows=list(reader)
    for row in rows:
        if None in row or any(v is None for v in row.values()):raise ValueError(f'{kind}: CSV 열 수 불일치')
        finite_time(row['model_time_s'])
        if kind=='EVENT':
            seq=row.get('event_sequence','0') or '0'
            if _finite(seq) is None or float(seq)!=int(float(seq)):raise ValueError('EVENT: 잘못된 event_sequence')
        elif _finite(row.get('record_sequence')) is None:raise ValueError('RAW: 잘못된 record_sequence')
    ids=[r.get('event_id') for r in rows] if kind=='EVENT' else [r.get('record_sequence') for r in rows]
    if len(ids)!=len(set(ids)) or any(not x for x in ids):raise ValueError(f'{kind}: 근거 식별자 중복 또는 누락')
    return fields,rows

class GroundedEvidenceStore(EvidenceStore):
    def __init__(self,event_csv,raw_csv,logic_rows=None,*,event_registry=None,live_tags=None):
        ef,er=read_checked(event_csv,'EVENT');rf,rr=read_checked(raw_csv,'RAW')
        for key in ('session_id','incident_id'):
            es={r.get(key,'') for r in er}-{''};rs={r.get(key,'') for r in rr}-{''}
            if len(es)>1 or len(rs)>1 or (es and rs and es!=rs):raise ValueError(f'EVENT/RAW {key}가 다르거나 복수입니다. 같은 사고의 파일 쌍을 선택하세요.')
        self.live_tags=set(live_tags or []);self.registry={}
        for row in event_registry or []:
            if str(row.get('enabled','1')).lower() not in {'1','true','yes'}:continue
            key=f"{row.get('equipment','').strip()}::{row.get('tag','').strip()}";node=str(row.get('source_node','')).strip()
            if self.live_tags and node not in self.live_tags:continue
            previous=self.registry.get(key)
            self.registry[key]=row if previous is None or previous.get('source_node')==node else {}
        super().__init__(Path(event_csv),Path(raw_csv),logic_rows=logic_rows)
        self.raw_tag_inventory=[x for x in self.raw_fields if x not in META]
        if len(self.raw_tag_inventory)>2048:raise ValueError('RAW 태그 수 한도 2048 초과')
        self._served={}
        original_indices={row['record_sequence']:i for i,row in enumerate(rr,1)}
        self._raw_original={id(row):original_indices[row['record_sequence']] for row in self.raw_rows}
        self._raw_time=defaultdict(list)
        for row in self.raw_rows:self._raw_time[finite_time(row['model_time_s'])].append(row)
        self._events={r['event_id']:r for r in self.event_rows}
        self.mapping_counts=Counter(self.describe_event(r)['mapping_status'] for r in self.event_rows)
        self.validation={'status':'PASS','time_field':'model_time_s','event_rows':len(er),'visible_event_rows':len(self.event_rows),'raw_rows':len(rr),'raw_tag_count':len(self.raw_tag_inventory),'mapping_counts':dict(self.mapping_counts)}
        if self.event_rows and self.raw_rows:
            et=[finite_time(r['model_time_s']) for r in self.event_rows];rt=list(self._raw_time)
            self.validation.update(event_time_range=[min(et),max(et)],raw_time_range=[min(rt),max(rt)])
            self.validation['time_alignment']='OVERLAP' if min(max(et),max(rt))>=max(min(et),min(rt)) else 'NO_OVERLAP'
        else:self.validation['time_alignment']='INSUFFICIENT'

    def resolve_source(self,key):
        key=str(key or '').strip()
        if key in self.raw_tag_inventory or key in self.live_tags:return key
        row=self.registry.get(key)
        return str(row.get('source_node','')) if row else ''

    def logic_matches(self,tags):
        requested=set(tags);found=[]
        for row in self.logic_rows:
            values={str(row.get(k,'')).strip() for k in ('tag_id','canonical_tag','event_tag','source_node')};values.update(parts(row.get('linked_tag_ids')))
            if values&requested:found.append(row)
        return found

    def describe_event(self,row):
        item=_event_public(row);key=f"{row.get('equipment','').strip()}::{row.get('tag','').strip()}";mapped=self.registry.get(key)
        source=str(mapped.get('source_node','')) if mapped else ''
        if not source and row.get('tag') in self.live_tags:source=row['tag']
        item.update(original_tag=row.get('tag',''),lookup_key=key,source_node=source,canonical_tag=source or '',display_name=row.get('message') or key,mapping_status='EQUIPMENT_TAG_EXACT' if mapped else 'EXACT_SOURCE' if source else 'UNREGISTERED_OBSERVATION',raw_available=source in self.raw_tag_inventory,source_kind='EVENT')
        item['logic_ids']=[r.get('logic_id','') for r in self.logic_matches([source]) if source]
        return item

    def publish_event(self,row):
        item=self.describe_event(row);self._served[item['evidence_id']]=item;return item

    def search_events(self,query='',*,equipment=None,event_class=None,tags=None,limit=20):
        items=super().search_events(query,equipment=equipment,event_class=event_class,tags=tags,limit=limit)
        return [self.publish_event(self._events[x['event_id']]) for x in items]

    def get_event_window(self,center_time_s,*,before_s=5,after_s=5,limit=30):
        finite_time(center_time_s);rows=super().get_event_window(center_time_s,before_s=before_s,after_s=after_s,limit=limit)
        return [self.publish_event(self._events[x['event_id']]) for x in rows]

    def raw_evidence(self,row,tag):
        index=self._raw_original[id(row)];eid=f'RAW:{index}:{tag}';value=_finite(row.get(tag))
        result={'evidence_id':eid,'source_kind':'RAW','row_number':index,'csv_record_number':index+1,'record_sequence':row.get('record_sequence',''),'model_time_s':finite_time(row['model_time_s']),'wall_time_utc':row.get('wall_time_utc',''),'tag':tag,'source_node':tag,'value':value if value is not None else row.get(tag,''),'collector_quality':row.get('collector_quality',row.get('quality','')),'logic_ids':[x.get('logic_id','') for x in self.logic_matches([tag])],'mapping_status':'EXACT_SOURCE' if tag in self.live_tags else 'UNREGISTERED_OBSERVATION'}
        self._served[eid]=result;return result

    def get_raw_window(self,tags,start_time_s,end_time_s,*,max_rows=50):
        finite_time(start_time_s);finite_time(end_time_s);result=super().get_raw_window(tags,start_time_s,end_time_s,max_rows=max_rows);rows=[]
        for item in result['rows']:
            source=next((r for r in self._raw_time[item['model_time_s']] if all((_finite(r.get(t)) if _finite(r.get(t)) is not None else r.get(t,''))==item[t] for t in result['tags'])),None)
            ids={t:self.raw_evidence(source,t)['evidence_id'] for t in result['tags']} if source else {}
            rows.append({**item,'evidence_ids':ids})
        result['rows']=rows;result['requested_tags_truncated']=len(tags)>8
        result['effective_time_range']=[min(start_time_s,end_time_s),min(max(start_time_s,end_time_s),min(start_time_s,end_time_s)+20)]
        result['sample_warning']='표시용 균등 표본입니다. 짧은 디지털 변화 검토에는 get_tag_series transition_evidence를 사용하세요.'
        return result

    def get_tag_series(self,tag,start_time_s,end_time_s,*,max_points=50):
        start,end=sorted([finite_time(start_time_s),finite_time(end_time_s)]);result=super().get_tag_series(tag,start,end,max_points=max_points)
        if result['status']!='OK':return result
        valid=[r for r in self.raw_rows if start<=float(r['model_time_s'])<=end and _finite(r.get(tag)) is not None]
        for point in result['points']:
            row=next(r for r in self._raw_time[point['model_time_s']] if _finite(r.get(tag))==point['value'])
            point['evidence_id']=self.raw_evidence(row,tag)['evidence_id']
        transitions=[];transition_count=0
        for before,after in zip(valid,valid[1:]):
            a,b=_finite(before[tag]),_finite(after[tag])
            if a in (0,1) and b in (0,1) and a!=b:
                transition_count+=1
                if len(transitions)>=24:continue
                transitions.append({'tag':tag,'from':a,'to':b,'time_interval_s':[float(before['model_time_s']),float(after['model_time_s'])],'evidence_ids':[self.raw_evidence(before,tag)['evidence_id'],self.raw_evidence(after,tag)['evidence_id']]})
        result['transition_evidence']=transitions;result['transitions_truncated']=transition_count>24;result['transition_count']=transition_count
        if valid:
            selected=[valid[0],valid[-1],min(valid,key=lambda r:float(r[tag])),max(valid,key=lambda r:float(r[tag]))]
            result['summary']['evidence_ids']=list(dict.fromkeys(self.raw_evidence(r,tag)['evidence_id'] for r in selected))
        return result

    def get_logic_context(self,tags,*,limit=12):
        cap=_clamp_int(limit,12,12);resolved={tag:(self.resolve_source(tag) or tag) for tag in tags};all_matches=self.logic_matches(list(resolved.values()))
        unregistered=[tag for tag,node in resolved.items() if not self.logic_matches([node])];items=[]
        for row in all_matches[:cap]:
            item={k:row.get(k,'') for k in ('logic_id','logic_type','logic_name','tag_id','event_tag','source_node','condition','linked_tag_ids','output_nodes_or_tags')}
            linked=parts(row.get('linked_tag_ids'));outputs=set(parts(row.get('output_nodes_or_tags')))
            item['upstream_tags']=[t for t in linked if t not in outputs and t in self.live_tags]
            item['raw_available_tags']=[t for t in linked if t in self.raw_tag_inventory]
            item['missing_raw_tags']=[t for t in linked if t in self.live_tags and t not in self.raw_tag_inventory];items.append(item)
        return {'items':items,'unregistered_tags':unregistered,'resolved_tags':resolved,'infer_unregistered_logic':False,'status':'VERIFIED' if tags and not unregistered else 'PARTIAL_OR_UNREGISTERED','verification_scope':'REGISTRATION_ONLY_NOT_INCIDENT_CAUSAL_PROOF','truncated':len(all_matches)>cap,'total_matches':len(all_matches)}

    def get_equipment_state(self,equipment,at_time_s,*,tags=None):
        finite_time(at_time_s);out=super().get_equipment_state(equipment,at_time_s,tags=tags)
        out['events']=[self.publish_event(self._events[e['event_id']]) for e in out['events']]
        nearest=min(self.raw_rows,key=lambda r:abs(float(r['model_time_s'])-at_time_s)) if self.raw_rows else None
        age=abs(float(nearest['model_time_s'])-at_time_s) if nearest else None
        out['raw_sample_time_s']=float(nearest['model_time_s']) if nearest else None;out['raw_sample_distance_s']=age;out['raw_stale']=age is None or age>5
        out['raw_evidence_ids']={t:self.raw_evidence(nearest,t)['evidence_id'] for t in out['raw_values']} if nearest and not out['raw_stale'] else {}
        if out['raw_stale']:out['raw_values']={}
        return out

    def upstream_inventory(self):
        nodes={self.describe_event(r)['source_node'] for r in self.event_rows}-{''};reached=set(nodes)
        for _ in range(4):
            for row in self.logic_rows:
                outputs=set(parts(row.get('output_nodes_or_tags')))
                if outputs&nodes:reached.update(t for t in parts(row.get('linked_tag_ids')) if t in self.live_tags)
            if reached==nodes:break
            nodes=set(reached)
        return sorted(reached&set(self.raw_tag_inventory))

    def readiness(self):
        ready=bool(self.event_rows and len(set(self._raw_time))>=2 and self.validation['time_alignment']=='OVERLAP')
        return {'readiness_version':'GENERIC_DUAL_LOG_EVIDENCE_V2','strict_validation_version':VERSION,'status':'PASS' if ready else 'COLLECTING','status_scope':'EVIDENCE_READINESS_ONLY','analysis_role':'EVIDENCE_PROVIDER_ONLY','decision_authority':'GEMINI_AGENT','decision_fields_generated_by_python':[],'event_rows':len(self.event_rows),'raw_rows':len(self.raw_rows),'validation':self.validation,'conclusion':'조회 준비 상태이며 사고 원인 확정이 아닙니다.'}

    def build_agent_bootstrap(self,*,run_id='',data_digest=''):
        boot=super().build_agent_bootstrap(run_id=run_id,data_digest=data_digest);boot['incident_id']='OPAQUE_INCIDENT'
        boot.update(evidence_version=VERSION,validation=self.validation,evidence_readiness=self.readiness(),raw_tag_inventory=self.raw_tag_inventory,upstream_available_tags=self.upstream_inventory(),initial_events=[self.publish_event(r) for r in self.event_rows[:12]])
        boot['inventory_policy']='Names are available observations, not causes. Query samples to test hypotheses. No raw bulk values are in this bootstrap.'
        return boot

    def evidence_catalog(self):return list(self._served.values())
