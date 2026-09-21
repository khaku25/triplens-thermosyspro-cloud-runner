const populated=value=>value!==undefined&&value!==null&&String(value).trim()!=='';

export function eventIdentity(event={}){
  return String(event.evidence_id||event.event_id||'');
}

export function preferredSourceTag(event={}){
  return String(event.source_node||event.canonical_tag||event.tag||'');
}

export function mergeEvents(uploaded=[],enriched=[]){
  const events=new Map();
  const put=(event,index,origin)=>{
    const identity=eventIdentity(event);
    const key=identity||`${origin}:${index}`;
    const existing=events.get(key);
    events.set(key,existing?{...existing,...event}:{...event});
  };
  uploaded.forEach((event,index)=>put(event,index,'uploaded'));
  enriched.forEach((event,index)=>put(event,index,'enriched'));
  return [...events.values()].sort((left,right)=>{
    const leftTime=left.model_time_s===null||left.model_time_s===undefined||String(left.model_time_s).trim()===''?NaN:Number(left.model_time_s);
    const rightTime=right.model_time_s===null||right.model_time_s===undefined||String(right.model_time_s).trim()===''?NaN:Number(right.model_time_s);
    const a=Number.isFinite(leftTime)?leftTime:Infinity;
    const b=Number.isFinite(rightTime)?rightTime:Infinity;
    return a-b;
  });
}

export function mergeEvidenceCatalog(events=[],retrieved=[]){
  const catalog=new Map();
  for(const event of events){
    const evidence_id=eventIdentity(event);
    if(!evidence_id)continue;
    catalog.set(evidence_id,{...event,evidence_id,source_kind:'EVENT'});
  }
  for(const evidence of retrieved){
    const evidence_id=String(evidence?.evidence_id||evidence?.event_id||'');
    if(!evidence_id)continue;
    const existing=catalog.get(evidence_id);
    catalog.set(evidence_id,existing?{...existing,...evidence,evidence_id}:{...evidence,evidence_id});
  }
  return [...catalog.values()];
}

const evidenceIds=value=>String(value||'').split(';').map(id=>id.trim()).filter(populated);

export function validateReportReferences(rows=[]){
  const available=new Set();
  for(const row of rows){
    if(row?.section==='증거자료')for(const id of evidenceIds(row.evidence_ids))available.add(id);
  }
  const missing=[];
  const seen=new Set();
  for(const row of rows){
    if(row?.section==='증거자료')continue;
    for(const id of evidenceIds(row?.evidence_ids)){
      if(!available.has(id)&&!seen.has(id)){
        seen.add(id);
        missing.push(id);
      }
    }
  }
  return {valid:missing.length===0,missing};
}
