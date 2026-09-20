const list=value=>Array.isArray(value)?value:[];

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
