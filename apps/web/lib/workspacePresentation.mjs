const list=value=>Array.isArray(value)?value:[];

const modelSeconds=value=>{
  if(value===null||value===undefined||String(value).trim()==='')return null;
  const number=Number(value);
  return Number.isFinite(number)?number:null;
};

const sourceTags=item=>new Set(list(item?.related_tags||item?.tags).map(value=>String(value||'').trim()).filter(Boolean));

const GT_LATCH_TAGS=new Set(['TRIP_LATCH','GT.TRIP.LATCH','GT_TRIP_LATCH','vppGTTripLatch']);
const ST_LATCH_TAGS=new Set(['ST.TRIP.LATCH','ST_TRIP_LATCH','vppSTTripLatchPublished']);
const TRIP_COMMAND_TAGS=new Map([
  ['vppExternalTripCommandNative',{equipment:'GT',message:'외부 GT Trip Command 입력',operator_kind:'GT_TRIP_COMMAND'}],
  ['vppExternalSTTripCommandNative',{equipment:'ST',message:'외부 ST Trip Command 입력',operator_kind:'ST_TRIP_COMMAND'}],
  ['vppCauseDirectGTTrip',{equipment:'GT',message:'GT Trip Command 입력',operator_kind:'GT_TRIP_COMMAND'}],
  ['vppCauseDirectSTTrip',{equipment:'ST',message:'ST Trip Command 입력',operator_kind:'ST_TRIP_COMMAND'}],
]);
const BREAKER_CLOSED_TAGS=new Map([
  ['vpp52GTClosed',{equipment:'52GT',message:'52GT 차단기 OPEN'}],
  ['vpp52STClosed',{equipment:'52ST',message:'52ST 차단기 OPEN'}],
]);

const sourceTag=item=>String(item?.source_node||item?.canonical_tag||item?.tag||'').trim();
const evidenceIds=item=>[...new Set([
  ...list(item?.evidence_ids),
  item?.evidence_id,
  item?.event_id,
].map(value=>String(value||'').trim()).filter(Boolean))];

function digitalActive(item={}){
  const value=item.value;
  if(value!==null&&value!==undefined&&String(value).trim()!==''){
    if(value===true)return true;
    if(value===false)return false;
    const text=String(value).trim().toUpperCase();
    if(['1','1.0','TRUE','ACTIVE'].includes(text))return true;
    if(['0','0.0','FALSE','INACTIVE'].includes(text))return false;
    return false;
  }
  return ['1','1.0','TRUE','ACTIVE'].includes(String(item.state||'').trim().toUpperCase());
}

function binarySampleValue(value){
  if(value===true||value===false)return true;
  const text=String(value??'').trim().toUpperCase();
  return ['0','0.0','1','1.0','TRUE','FALSE','ACTIVE','INACTIVE'].includes(text);
}

function recordedClock(item={}){
  const wall=String(item?.wall_time_utc||item?.recorded_wall_time||'').trim();
  return wall.match(/T(\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?)/)?.[1]||'';
}

function semanticEventState(item={}){
  const text=`${item.state||''} ${item.event_class||''} ${item.message||item.claim||''} ${item.tag||''}`.toUpperCase();
  if(/\bLOW(?:_LOW)?\b|저하|저유량|저온|하한|\bLL\b/.test(text))return 'LOW';
  if(/\bALARM\b|경보|알람/.test(text))return 'ALARM';
  const state=String(item.state||'').trim().toUpperCase();
  return state&&!['OBSERVED','UNKNOWN'].includes(state)?state:'';
}

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
  const clock=recordedClock(item);
  const seconds=modelSeconds(item?.model_time_s??item?.recorded_time);
  const model=seconds===null?'':`T+${seconds.toFixed(3)} s`;
  return clock?{primary:clock,secondary:model}:{primary:model||'시각 미확인',secondary:''};
}

export function displayAccidentTime(item={}){
  const seconds=modelSeconds(item?.model_time_s??item?.recorded_time);
  const model=seconds===null?'':`T+${seconds.toFixed(3)} s`;
  const clock=recordedClock(item);
  return model?{primary:model,secondary:clock}:{primary:clock||'시각 미확인',secondary:''};
}

export function sortByModelTime(items=[]){
  return list(items).slice().sort((left,right)=>(modelSeconds(left?.model_time_s??left?.recorded_time)??Infinity)-(modelSeconds(right?.model_time_s??right?.recorded_time)??Infinity));
}

export function normalizeOperatorEvents(events=[],{sampleIntervalS=0.04}={}){
  const normalized=[];
  const previousState=new Map();
  const currentEdge=new Map();
  const repeatedProcess=new Map();
  const appendEvidence=(target,item)=>{
    target.evidence_ids=[...new Set([...evidenceIds(target),...evidenceIds(item)])];
  };
  for(const item of list(events).slice().sort((left,right)=>(modelSeconds(left?.model_time_s)??Infinity)-(modelSeconds(right?.model_time_s)??Infinity))){
    const tag=sourceTag(item);
    const ids=evidenceIds(item);
    if(GT_LATCH_TAGS.has(tag)||ST_LATCH_TAGS.has(tag)){
      const active=digitalActive(item);
      const previous=previousState.get(tag);
      previousState.set(tag,active);
      if(!active){currentEdge.delete(tag);continue;}
      if(previous===true&&currentEdge.has(tag)){appendEvidence(currentEdge.get(tag),item);continue;}
      const turbine=ST_LATCH_TAGS.has(tag)?'ST':'GT';
      const event={...item,evidence_ids:ids,state:'ACTIVE',equipment:turbine,message:`${turbine} Trip Latch 동작`,operator_kind:`${turbine}_LATCH`};
      normalized.push(event);currentEdge.set(tag,event);continue;
    }
    const command=TRIP_COMMAND_TAGS.get(tag);
    if(command){
      const active=digitalActive(item);
      const previous=previousState.get(tag);
      previousState.set(tag,active);
      if(!active){currentEdge.delete(tag);continue;}
      if(previous===true&&currentEdge.has(tag)){appendEvidence(currentEdge.get(tag),item);continue;}
      if(previous!==false)continue;
      const event={...item,...command,evidence_ids:ids,state:'ACTIVE'};
      normalized.push(event);currentEdge.set(tag,event);continue;
    }
    const breaker=BREAKER_CLOSED_TAGS.get(tag);
    if(breaker){
      const value=Number(item.value);
      if(value!==0&&value!==1)continue;
      const closed=value===1;
      const previous=previousState.get(tag);
      previousState.set(tag,closed);
      if(closed){currentEdge.delete(tag);continue;}
      if(previous===false&&currentEdge.has(tag)){appendEvidence(currentEdge.get(tag),item);continue;}
      const explicitOpen=/BREAKER[_ ]?OPEN|차단기\s*(?:개방|OPEN)/i.test(`${item.event_class||''} ${item.message||''}`);
      if(previous!==true&&!explicitOpen)continue;
      const event={...item,...breaker,evidence_ids:ids,state:'OPEN',operator_kind:`${breaker.equipment}_OPEN`};
      normalized.push(event);currentEdge.set(tag,event);continue;
    }
    const semantic=semanticEventState(item);
    const previousProcess=tag&&semantic?repeatedProcess.get(tag):null;
    if(tag&&['NORMAL','CLEAR','CLEARED'].includes(semantic)){
      repeatedProcess.set(tag,{semantic,event:null});
      continue;
    }
    if(previousProcess?.semantic===semantic){
      appendEvidence(previousProcess.event,item);
      continue;
    }
    const event={...item,evidence_ids:ids};
    normalized.push(event);
    if(tag&&semantic)repeatedProcess.set(tag,{semantic,event});
  }

  const tolerance=Math.max(0,Number(sampleIntervalS)||0)+1e-9;
  const used=new Set();
  const pairedLatches=[];
  const latchRows=normalized.filter(item=>item.operator_kind==='GT_LATCH'||item.operator_kind==='ST_LATCH');
  for(let index=0;index<latchRows.length;index+=1){
    if(used.has(index))continue;
    const current=latchRows[index];
    const currentTime=modelSeconds(current.model_time_s);
    let match=-1;
    let matchDistance=Infinity;
    for(let candidate=index+1;candidate<latchRows.length;candidate+=1){
      if(used.has(candidate)||latchRows[candidate].operator_kind===current.operator_kind)continue;
      const candidateTime=modelSeconds(latchRows[candidate].model_time_s);
      if(currentTime===null||candidateTime===null)continue;
      const distance=Math.abs(currentTime-candidateTime);
      if(distance<=tolerance&&distance<matchDistance){match=candidate;matchDistance=distance;}
    }
    if(match>=0){
      const other=latchRows[match];
      const gt=current.operator_kind==='GT_LATCH'?current:other;
      const st=current.operator_kind==='ST_LATCH'?current:other;
      const gtTime=modelSeconds(gt.model_time_s);
      const stTime=modelSeconds(st.model_time_s);
      const first=gtTime<=stTime?gt:st;
      pairedLatches.push({
        ...first,
        event_id:`${gt.event_id||'GT'}+${st.event_id||'ST'}`,
        evidence_id:undefined,
        evidence_ids:[...new Set([...evidenceIds(gt),...evidenceIds(st)])],
        related_tags:['vppGTTripLatch','vppSTTripLatchPublished'],
        equipment:'GT·ST',
        state:'ACTIVE',
        message:'GT·ST Trip Latch 동시 동작',
        operator_kind:'GT_ST_LATCH',
        model_time_s:Math.min(gtTime,stTime),
      });
      used.add(index);used.add(match);
    }else{
      pairedLatches.push(current);
      used.add(index);
    }
  }
  const nonLatches=normalized.filter(item=>item.operator_kind!=='GT_LATCH'&&item.operator_kind!=='ST_LATCH');
  return [...nonLatches,...pairedLatches].sort((left,right)=>(modelSeconds(left?.model_time_s)??Infinity)-(modelSeconds(right?.model_time_s)??Infinity));
}

function citedEvidence(catalog,claim){
  const ids=new Set(list(claim?.evidence_ids).map(String));
  return ids.size?list(catalog).filter(item=>ids.has(String(item?.evidence_id||item?.event_id||''))):[];
}

function claimEvidenceIds(claim){
  return new Set(list(claim?.evidence_ids).map(value=>String(value||'')).filter(Boolean));
}

function normalizedCitedEvents(catalog,claim){
  const ids=claimEvidenceIds(claim);
  if(!ids.size)return [];
  return normalizeOperatorEvents(catalog).filter(event=>evidenceIds(event).some(id=>ids.has(id)));
}

function observedFallback(item,claim){
  const fallback={...item,claim,operator_verified:false};
  delete fallback.state;
  delete fallback.value;
  delete fallback.related_tags;
  delete fallback.tags;
  return fallback;
}

function normalizedTags(event){
  if(event?.operator_kind==='GT_ST_LATCH')return ['vppGTTripLatch','vppSTTripLatchPublished'];
  if(event?.operator_kind==='GT_LATCH')return ['vppGTTripLatch'];
  if(event?.operator_kind==='ST_LATCH')return ['vppSTTripLatchPublished'];
  const tag=sourceTag(event);
  return tag?[tag]:[];
}

export function deriveOperatorAnalysis(analysis={},catalog=[]){
  const primary=analysis?.primary_cause||{};
  const direct=analysis?.direct_trigger||{};
  const primaryEvidence=citedEvidence(catalog,primary);
  const directEvidence=citedEvidence(catalog,direct);
  const primaryTags=new Set([...sourceTags(primary),...primaryEvidence.map(sourceTag).filter(Boolean)]);
  const directTags=new Set([...sourceTags(direct),...directEvidence.map(sourceTag).filter(Boolean)]);
  const primaryText=String(primary.claim||primary.message||'');
  const directText=String(direct.claim||direct.message||'');
  const commandRelated=[...TRIP_COMMAND_TAGS.keys()].some(tag=>primaryTags.has(tag))||/TRIP\s*COMMAND|트립\s*명령/i.test(primaryText);
  const latchRelated=[...GT_LATCH_TAGS,...ST_LATCH_TAGS].some(tag=>directTags.has(tag))||/TRIP\s*LATCH|트립\s*래치/i.test(directText);
  const primaryEvents=normalizedCitedEvents(catalog,primary);
  const command=primaryEvents.find(event=>String(event.operator_kind||'').endsWith('_TRIP_COMMAND'));
  const directEvents=normalizedCitedEvents(catalog,direct);
  const commandTime=modelSeconds(command?.model_time_s);
  const latch=directEvents.find(event=>{
    if(!['GT_ST_LATCH','GT_LATCH','ST_LATCH'].includes(event.operator_kind))return false;
    const time=modelSeconds(event.model_time_s);
    return commandTime===null||time===null||time>=commandTime;
  });
  const safePrimary=commandRelated
    ?command?{...primary,claim:command.message,model_time_s:command.model_time_s,evidence_ids:evidenceIds(command),related_tags:normalizedTags(command),state:'ACTIVE',value:1,operator_verified:true}:observedFallback(primary,'외부 Trip Command 신호 관측')
    :primary;
  const safeDirect=latchRelated
    ?latch?{...direct,claim:latch.message,model_time_s:latch.model_time_s,evidence_ids:evidenceIds(latch),related_tags:normalizedTags(latch),state:'ACTIVE',value:1,operator_verified:true}:observedFallback(direct,'보호동작 신호 관측')
    :direct;
  return {analysis:{...analysis,primary_cause:safePrimary,direct_trigger:safeDirect},primaryTitle:commandRelated&&!command?'사고 개시 신호':'발생 원인'};
}

export function groupEvidenceRows(catalog=[]){
  const sorted=list(catalog).slice().sort((left,right)=>(modelSeconds(left?.model_time_s)??Infinity)-(modelSeconds(right?.model_time_s)??Infinity));
  const valuesByTag=new Map();
  for(const item of sorted){
    const tag=sourceTag(item)||String(item?.evidence_id||item?.event_id||'');
    if(!valuesByTag.has(tag))valuesByTag.set(tag,[]);
    if(item?.value!==null&&item?.value!==undefined&&String(item.value).trim()!=='')valuesByTag.get(tag).push(item.value);
  }
  const binaryTags=new Set([...valuesByTag].filter(([,values])=>values.length&&values.every(binarySampleValue)).map(([tag])=>tag));
  const grouped=[];
  const lastByTag=new Map();
  for(const item of sorted){
    const tag=sourceTag(item)||String(item?.evidence_id||item?.event_id||'');
    let state=String(item?.state||'').trim().toUpperCase();
    if(BREAKER_CLOSED_TAGS.has(tag)&&Number(item?.value)===0)state='OPEN';
    else if(BREAKER_CLOSED_TAGS.has(tag)&&Number(item?.value)===1)state='CLOSED';
    else if(GT_LATCH_TAGS.has(tag)||ST_LATCH_TAGS.has(tag))state=digitalActive(item)?'ACTIVE':'INACTIVE';
    const signature=JSON.stringify([state,state||!binaryTags.has(tag)?null:item?.value??null]);
    const previous=lastByTag.get(tag);
    if(previous?.signature===signature){
      previous.row.evidence_ids=[...new Set([...previous.row.evidence_ids,...evidenceIds(item)])];
      previous.row.repeat_count+=1;
      previous.row.last_value=item?.value;
      continue;
    }
    const row={...item,state:state||item?.state||'',evidence_ids:evidenceIds(item),repeat_count:1,first_value:item?.value,last_value:item?.value};
    grouped.push(row);
    lastByTag.set(tag,{signature,row});
  }
  return grouped;
}

export function prioritizeEvidenceRows(rows=[],detail={},limit=200){
  const source=list(rows);
  const cap=Math.max(1,Number(limit)||200);
  if(source.length<=cap)return source.slice();
  const selected=new Set(list(detail?.evidenceIds).map(String));
  const index=source.findIndex(item=>evidenceIds(item).some(id=>selected.has(id))||selected.has(String(item?.evidence_id||item?.event_id||'')));
  if(index<0)return source.slice(0,cap);
  const start=Math.max(0,Math.min(index-Math.floor(cap/2),source.length-cap));
  return source.slice(start,start+cap);
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
  const sorted=normalizeOperatorEvents(events);
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
