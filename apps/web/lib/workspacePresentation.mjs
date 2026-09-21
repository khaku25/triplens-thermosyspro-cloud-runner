const list=value=>Array.isArray(value)?value:[];

const modelSeconds=value=>{
  if(value===null||value===undefined||String(value).trim()==='')return null;
  const number=Number(value);
  return Number.isFinite(number)?number:null;
};

const sourceTags=item=>new Set(list(item?.related_tags||item?.tags).map(value=>String(value||'').trim()).filter(Boolean));

export function analysisDisplayData({result}={}){
  if(!result)return {events:[],catalog:[]};
  return {
    events:list(result.events),
    catalog:list(result.evidence_catalog),
  };
}

export function inputStatus({ready=false,busy=false,complete=false,eventRows=0,rawTagCount=0}={}){
  if(busy)return {title:'사고 기록을 분석하고 있습니다…',detail:''};
  if(complete)return {title:'분석 완료',detail:'핵심 원인 및 파급 과정 확인'};
  if(ready)return {title:'분석 입력 준비 완료',detail:`EVENT.csv ${eventRows}건 · RAW.csv ${rawTagCount}개 태그`};
  return {title:'Dual Log 대기',detail:'EVENT.csv와 RAW.csv를 선택해 주세요.'};
}

export function summarizeEvidence(values,limit=5){
  const unique=[...new Set(list(values).map(value=>String(value??'').trim()).filter(Boolean))];
  const cap=Math.max(3,Math.min(5,Number(limit)||5));
  return {visible:unique.slice(0,cap),hidden:unique.slice(cap),hiddenCount:Math.max(0,unique.length-cap)};
}

export function displayEventTime(item={}){
  const wall=String(item?.wall_time_utc||item?.recorded_wall_time||'').trim();
  const clock=wall.match(/T(\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?)/)?.[1]||'';
  const seconds=modelSeconds(item?.model_time_s??item?.recorded_time);
  const model=seconds===null?'':`T+${seconds.toFixed(3)} s`;
  return clock?{primary:clock,secondary:model}:{primary:model||'시각 미확인',secondary:''};
}

export function operatorSummary(item={},stage=''){
  const tags=sourceTags(item);
  const source=String(item?.claim||item?.message||item?.description||'');
  const state=String(item?.state||'').toUpperCase();
  const rawValue=item?.value;
  const numericValue=rawValue===null||rawValue===undefined||String(rawValue).trim()===''?null:Number(rawValue);
  const active=/ACTIVE|TRIPPED|LATCHED/.test(state)||rawValue===true||numericValue===1||/ACTIVE|동작|작동|인가/.test(source);
  const opened=/OPEN|TRIPPED/.test(state)||numericValue===0||/\bOPEN\b|개방|개로/.test(source);
  const low=/LOW|ALARM/.test(state)||/\bLOW(?:_LOW)?\b|저하|저유량|저온|하한|\bLL\b/i.test(source);
  if(stage==='primary'&&tags.has('vppExternalTripCommandNative'))return '외부 Trip Command 입력';
  if(stage==='direct'&&active&&tags.has('vppGTTripLatch')&&tags.has('vppSTTripLatchPublished'))return 'GT·ST Trip Latch 동시 동작';
  if(stage==='direct'&&active&&tags.has('vppGTTripLatch'))return 'GT Trip Latch 동작';
  if(stage==='direct'&&active&&tags.has('vppSTTripLatchPublished'))return 'ST Trip Latch 동작';

  const mapped=[
    ['vpp52GTClosed','52GT 차단기 OPEN',opened],
    ['vpp52STClosed','52ST 차단기 OPEN',opened],
    ['vppGTExhaustMassFlowTH','GT 배기유량 LOW',low],
    ['vppGTExhaustTemperatureK','GT 배기온도 LOW',low],
    ['vppHPTurbineSteamFlowTH','HP 터빈 증기유량 LOW',low],
    ['vppIPTurbineSteamFlowTH','IP 터빈 증기유량 LOW',low],
    ['vppLPTurbineSteamFlowTH','LP 터빈 증기유량 LOW',low],
  ].find(([tag,,confirmed])=>confirmed&&tags.has(tag));
  if(mapped)return mapped[1];

  return source
    .replace(/model_time_s\s*=?\s*\d+(?:\.\d+)?\s*초에\s*/gi,'')
    .replace(/\((?:vpp[A-Za-z0-9_.-]+)\)/g,'')
    .replace(/\b(?:태그\s+)?vpp[A-Za-z0-9_.-]+(?:가|이|는|은)?\b/g,'')
    .replace(/1(?:\.0)?\s*\(ACTIVE\)(?:으로)?/gi,'ACTIVE')
    .replace(/개로\s*\(0(?:\.0)?\)\s*됨/g,'개방')
    .replace(/\s+/g,' ')
    .replace(/\s+([,.])/g,'$1')
    .trim();
}

export function compactTimeline(events=[],limit=7){
  const sorted=list(events).slice().sort((left,right)=>{
    const a=modelSeconds(left?.model_time_s);
    const b=modelSeconds(right?.model_time_s);
    if(a===null&&b===null)return 0;
    if(a===null)return 1;
    if(b===null)return -1;
    return a-b;
  });
  const cap=Math.max(1,Number(limit)||7);
  return {visible:sorted.slice(0,cap),hidden:sorted.slice(cap),hiddenCount:Math.max(0,sorted.length-cap)};
}

export function incidentMetrics(events=[]){
  const rows=list(events);
  const first=rows.slice().sort((left,right)=>{
    const a=modelSeconds(left?.model_time_s);
    const b=modelSeconds(right?.model_time_s);
    return (a??Infinity)-(b??Infinity);
  })[0];
  const firstTime=first?displayEventTime(first).primary:'—';
  return {
    firstTime:firstTime==='시각 미확인'?'—':firstTime,
    protection:rows.filter(item=>String(item?.event_class||'').toUpperCase()==='PROTECTION').length,
    alarms:rows.filter(item=>String(item?.event_class||'').toUpperCase()==='ALARM').length,
  };
}

export function selectDetailEvidence(catalog=[],detail=null){
  if(!detail)return [];
  let rows=[];
  if(detail.kind==='evidence')rows=list(catalog).filter(entry=>entry.evidence_id===detail.value);
  else if(detail.kind==='claim'){
    const ids=new Set(list(detail.evidenceIds).map(String));
    rows=list(catalog).filter(entry=>ids.has(String(entry?.evidence_id||entry?.event_id||'')));
  }else{
    rows=list(catalog).filter(entry=>[entry?.tag,entry?.source_node,entry?.canonical_tag].includes(detail.value));
  }
  return rows.slice().sort((left,right)=>(modelSeconds(left?.model_time_s)??Infinity)-(modelSeconds(right?.model_time_s)??Infinity));
}

export function conciseClaim(value,limit=180){
  const text=String(value??'').trim();
  if(text.length<=limit)return {summary:text,detail:''};
  const firstSentence=text.match(/^.*?[.!?。](?:\s|$)/)?.[0]?.trim();
  const summary=(firstSentence&&firstSentence.length<=limit?firstSentence:text.slice(0,limit).trimEnd()+'…');
  return {summary,detail:text};
}

export function friendlyTag(value){
  const tag=String(value??'').trim();
  const exact={
    'TRIP_LATCH':'Trip Latch',
    'GT.TRIP.LATCH':'GT Trip Latch',
    'GT_TRIP_LATCH':'GT Trip Latch',
    'vppGTTripLatch':'GT Trip Latch',
    'ST.TRIP.LATCH':'ST Trip Latch',
    'ST_TRIP_LATCH':'ST Trip Latch',
    'vppSTTripLatchPublished':'ST Trip Latch',
    'vppExternalTripCommandNative':'외부 GT Trip Command',
    'vppExternalSTTripCommandNative':'외부 ST Trip Command',
    'vpp52GTClosed':'52GT 차단기 상태',
    'vpp52STClosed':'52ST 차단기 상태',
  };
  if(exact[tag])return exact[tag];
  return tag.replace(/^vpp/,'').replace(/([a-z0-9])([A-Z])/g,'$1 $2').replace(/[._]+/g,' ').trim();
}
