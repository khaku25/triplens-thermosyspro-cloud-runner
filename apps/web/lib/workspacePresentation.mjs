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

function semanticTagSummary(tags,stage=''){
  const joined=[...tags].join(' ');
  if(stage==='primary'&&/vppExternal(?:ST)?TripCommandNative/.test(joined))return /ExternalSTTripCommandNative/.test(joined)?'외부 ST Trip Command 입력':'외부 GT Trip Command 입력';
  if(stage==='primary'&&/vppCause(?:GT|ST)?BreakerOpenWhileRunning/.test(joined)){
    const unit=/vppCauseSTBreakerOpenWhileRunning/.test(joined)?'ST':/vppCauseGTBreakerOpenWhileRunning/.test(joined)?'GT':'';
    return unit?unit+' 운전 중 차단기 개로 원인 활성화됨':'운전 중 차단기 개로 원인 활성화됨';
  }
  if(stage==='primary'&&/vppECMS52(?:GT|ST)ClosedCommandNative/.test(joined)){
    const unit=/vppECMS52STClosedCommandNative/.test(joined)?'ST':'GT';
    return '52'+unit+' 차단기 투입 명령 해제';
  }
  if(stage==='direct'&&/vpp(?:GT|ST)TripLatch(?:Published)?/.test(joined)){
    const gt=/vppGTTripLatch/.test(joined);
    const st=/vppSTTripLatch/.test(joined);
    if(gt&&st)return 'GT·ST Trip Latch 동시 동작';
    if(gt)return 'GT Trip Latch 동작';
    if(st)return 'ST Trip Latch 동작';
  }
  if(stage==='primary'&&/BreakerOpenWhileRunning/.test(joined))return '운전 중 차단기 개로 원인 활성화됨';
  return '';
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
  const semantic=semanticTagSummary(tags,stage);
  if(semantic)return semantic;

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

  return operatorPhrase(source
    .replace(/model_time_s\s*=?\s*\d+(?:\.\d+)?\s*초에\s*/gi,'')
    .replace(/\((?:vpp[A-Za-z0-9_.-]+)\)/g,'')
    .replace(/\b(?:태그\s+)?vpp[A-Za-z0-9_.-]+(?:가|이|는|은)?\b/g,'')
    .replace(/1(?:\.0)?\s*\(ACTIVE\)(?:으로)?/gi,'ACTIVE')
    .replace(/개로\s*\(0(?:\.0)?\)\s*됨/g,'개방')
    .replace(/\s+/g,' ')
    .replace(/\s+([,.])/g,'$1')
    .trim());
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


export function operatorPhrase(value,limit=180){
  let text=String(value??'').trim();
  if(!text)return '';
  const gtStLatch=/((가스\s*터빈|GT).*트립\s*래치.*(증기\s*터빈|ST).*트립\s*래치|(증기\s*터빈|ST).*트립\s*래치.*(가스\s*터빈|GT).*트립\s*래치)/i.test(text);
  if(gtStLatch&&/(활성|동작|작동|ACTIVE|LATCH)/i.test(text))return 'GT·ST Trip Latch 동시 동작';
  if(/외부\s*(?:GT\s*)?(?:Trip|트립)\s*(?:Command|명령).*(?:입력|인가|관측)/i.test(text))return '외부 Trip Command 입력';

  text=text
    .replace(/model_time_s\s*=?\s*\d+(?:\.\d+)?\s*초에\s*/gi,'')
    .replace(/^\s*\d+(?:\.\d+)?\s*초에\s*/,'')
    .replace(/RAW\s*변화\s*시간구간이\s*Direct Trigger\s*시각과\s*겹칩니다\.?/gi,'RAW 변화구간 · Direct Trigger 시각 중첩')
    .replace(/선후관계는\s*표본만으로\s*확정할\s*수\s*없습니다\.?/g,'선후관계 미확정')
    .replace(/선후관계를\s*확정할\s*수\s*없습니다\.?/g,'선후관계 미확정')
    .replace(/확인되지\s*않았습니다\.?/g,'미확인')
    .replace(/완료되지\s*않았습니다\.?/g,'미완료')
    .replace(/조회가\s*미확인/g,'조회 미확인')
    .replace(/확인(?:이)?\s*필요합니다\.?/g,'확인 필요')
    .replace(/확인해야\s*합니다\.?/g,'확인 필요')
    .replace(/검토해야\s*합니다\.?/g,'검토 필요')
    .replace(/확정할\s*수\s*없습니다\.?/g,'미확정')
    .replace(/판단할\s*수\s*없습니다\.?/g,'판단 불가')
    .replace(/알\s*수\s*없습니다\.?/g,'미확인')
    .replace(/활성화되었습니다\.?/g,'활성')
    .replace(/동작되었습니다\.?/g,'동작')
    .replace(/작동(?:하였|했)습니다\.?/g,'동작')
    .replace(/관측되었습니다\.?/g,'관측')
    .replace(/기록되었습니다\.?/g,'기록')
    .replace(/입력되었습니다\.?/g,'입력')
    .replace(/인가되었습니다\.?/g,'인가')
    .replace(/없습니다\.?/g,'없음')
    .replace(/있습니다\.?/g,'있음')
    .replace(/입니다\.?$/g,'')
    .replace(/합니다\.?$/g,'')
    .replace(/\.\s+/g,' · ')
    .replace(/[.]$/,'')
    .replace(/\s+/g,' ')
    .replace(/\s+([,])/g,'$1')
    .trim();
  return text.length>limit?text.slice(0,limit).trimEnd()+'…':text;
}

function reviewTitle(value){
  const text=String(value??'');
  if(/(발신|출처|감사\s*로그)/.test(text)&&/(Trip|트립|외부)/i.test(text))return '외부 Trip Command 발신 경로';
  if(/하드웨어\s*접점|통신\s*링크|전송\s*라인/.test(text))return '신호 경로 건전성';
  if(/시간구간|선후관계|겹칩|겹칩니다|중첩|시각/.test(text))return '시각 선후관계';
  if(/운전원.*조작|조작\s*이벤트|ESD|E-Stop/i.test(text))return '운전 조작이력';
  if(/노이즈|단선|단락/.test(text))return '입력 신호 건전성';
  if(/보호계전|계전|보호동작/.test(text))return '보호동작 기록';
  if(/로직|logic/i.test(text))return '등록 로직 대조';
  const phrase=operatorPhrase(text,44);
  return phrase.split(' · ')[0].replace(/\s*확인 필요$/,'').replace(/\s*검토 필요$/,'').trim()||'추가 확인 항목';
}

export function operatorReviewItems(analysis={}){
  const entries=[
    ...list(analysis?.additional_evidence_required).map(value=>({value,kind:'required',status:'확인 필요'})),
    ...list(analysis?.review_recommendations).map(value=>({value,kind:'review',status:'담당자 검토'})),
  ];
  const seen=new Set();
  return entries.map(({value,kind,status})=>{
    const raw=typeof value==='string'?value:String(value?.claim||value?.text||value?.description||'');
    const tags=[...new Set(raw.match(/vpp[A-Za-z0-9_.-]+/g)||[])];
    const cleaned=raw
      .replace(/\((vpp[A-Za-z0-9_.-]+)\)/g,'')
      .replace(/\b(?:태그\s+)?vpp[A-Za-z0-9_.-]+(?:가|이|는|은)?\b/g,'')
      .replace(/\s+/g,' ')
      .trim();
    const title=reviewTitle(raw);
    let detail=operatorPhrase(cleaned,170);
    if(detail===title)detail='';
    const key=(title+'|'+detail).toLowerCase();
    if(seen.has(key))return null;
    seen.add(key);
    return {title,detail,status,kind,tags};
  }).filter(Boolean);
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
    'vppGTTripLatchPublished':'GT Trip Latch',
    'vppSTTripLatch':'ST Trip Latch',
    'vpp52GTClosedCommandNative':'52GT 투입 명령',
    'vpp52STClosedCommandNative':'52ST 투입 명령',
    'vppCauseBreakerOpenWhileRunning':'운전 중 차단기 개로 원인',
      'vppECMS52GTClosedCommandNative':'52GT 투입 명령',
      'vppECMS52STClosedCommandNative':'52ST 투입 명령',
      'vppCauseGTBreakerOpenWhileRunning':'GT 운전 중 차단기 개로 원인',
      'vppCauseSTBreakerOpenWhileRunning':'ST 운전 중 차단기 개로 원인',
      'vppGTExhaustMassFlowTH':'GT 배기유량',
      'vppGTExhaustTemperatureK':'GT 배기온도',
      'vppHPTurbineSteamFlowTH':'HP 터빈 증기유량',
  };
  if(exact[tag])return exact[tag];
  return tag.replace(/^vpp/,'').replace(/([a-z0-9])([A-Z])/g,'$1 $2').replace(/[._]+/g,' ').trim();
}
