const STATUS = Object.freeze({
  SATISFIED:'SATISFIED',
  BLOCKED:'BLOCKED',
  DATA_MISSING:'DATA_MISSING',
});

export const READINESS_STATUS = STATUS;

export const RECOVERY_READINESS_GROUPS = Object.freeze([
  Object.freeze({
    id:'gt-start',
    label:'GT START PERMISSIVES',
    affects:Object.freeze(['GT']),
    conditions:Object.freeze([
      Object.freeze({id:'gt-trip-latch',label:'GT Trip Latch Clear',aliases:['vppGTTripLatch','GT.TRIP.LATCH','GT_TRIP_LATCH'],expected:false,logic_id:'PROT-GT-LATCH'}),
      Object.freeze({id:'gt-trip-request',label:'GT Trip Request Clear',aliases:['vppGTTripRequest','GT.TRIP.REQUEST','GT_TRIP_REQUEST'],expected:false,logic_id:'PROT-GT-REQUEST'}),
      Object.freeze({id:'52gt-open',label:'52GT Field Breaker Open',aliases:['vpp52GTClosed','vppECMS52GTClosed','ECMS.52GT.CLOSED'],expected:false,logic_id:'SEQ-52GT-OPEN'}),
    ]),
  }),
  Object.freeze({
    id:'st-start',
    label:'ST START PERMISSIVES',
    affects:Object.freeze(['ST']),
    conditions:Object.freeze([
      Object.freeze({id:'st-trip-latch',label:'ST Trip Latch Clear',aliases:['vppSTTripLatchPublished','ST.TRIP.LATCH','ST_TRIP_LATCH'],expected:false,logic_id:'PROT-ST-LATCH'}),
      Object.freeze({id:'st-trip-request',label:'ST Trip Request Clear',aliases:['vppSTTripRequest','ST.TRIP.REQUEST','ST_TRIP_REQUEST'],expected:false,logic_id:'PROT-ST-REQUEST'}),
      Object.freeze({id:'52st-open',label:'52ST Breaker Open',aliases:['vpp52STClosed','vppECMS52STClosed','ECMS.52ST.CLOSED'],expected:false,logic_id:'SEQ-52ST-OPEN'}),
    ]),
  }),
  Object.freeze({
    id:'hrsg',
    label:'HRSG PROTECTION',
    affects:Object.freeze(['GT','ST']),
    conditions:Object.freeze([
      Object.freeze({id:'hp-drum-hh',label:'HP Drum HH Clear',aliases:['vppHPDrumHHRaw','HRSG.HP.DRUM.LEVEL.HH'],expected:false,logic_id:'PROT-HP-DRUM-HH'}),
      Object.freeze({id:'hp-drum-ll',label:'HP Drum LL Clear',aliases:['vppHPDrumLLRaw','HRSG.HP.DRUM.LEVEL.LL'],expected:false,logic_id:'PROT-HP-DRUM-LL'}),
      Object.freeze({id:'ip-drum-hh',label:'IP Drum HH Clear',aliases:['vppIPDrumHHRaw','HRSG.IP.DRUM.LEVEL.HH'],expected:false,logic_id:'PROT-IP-DRUM-HH'}),
      Object.freeze({id:'ip-drum-ll',label:'IP Drum LL Clear',aliases:['vppIPDrumLLRaw','HRSG.IP.DRUM.LEVEL.LL'],expected:false,logic_id:'PROT-IP-DRUM-LL'}),
      Object.freeze({id:'lp-drum-hh',label:'LP Drum HH Clear',aliases:['vppLPDrumHHRaw','HRSG.LP.DRUM.LEVEL.HH'],expected:false,logic_id:'PROT-LP-DRUM-HH'}),
      Object.freeze({id:'lp-drum-ll',label:'LP Drum LL Clear',aliases:['vppLPDrumLLRaw','HRSG.LP.DRUM.LEVEL.LL'],expected:false,logic_id:'PROT-LP-DRUM-LL'}),
    ]),
  }),
  Object.freeze({
    id:'feedwater',
    label:'FEEDWATER',
    affects:Object.freeze(['GT','ST']),
    conditions:Object.freeze([
      Object.freeze({id:'hp-fwp-trip-latch',label:'HP BFP Trip Latch Clear',aliases:['vppHPFWPTripLatchNative','vppHPFWPTripLatch','FWP_HP.TRIP_LATCH'],expected:false,logic_id:'CMD-FWP-HP-TRIP'}),
      Object.freeze({id:'ip-fwp-trip-latch',label:'IP BFP Trip Latch Clear',aliases:['vppIPFWPTripLatchNative','vppIPFWPTripLatch','FWP_IP.TRIP_LATCH'],expected:false,logic_id:'CMD-FWP-IP-TRIP'}),
      Object.freeze({id:'lp-fwp-trip-latch',label:'LP BFP Trip Latch Clear',aliases:['vppLPFWPTripLatchNative','vppLPFWPTripLatch','FWP_LP.TRIP_LATCH'],expected:false,logic_id:'CMD-FWP-LP-TRIP'}),
    ]),
  }),
]);

const clean = value => String(value ?? '').trim();
const keyToken = value => clean(value).toLowerCase().replace(/[^a-z0-9]/g,'');

function booleanValue(value){
  if(typeof value === 'boolean') return value;
  if(typeof value === 'number' && Number.isFinite(value)) return value !== 0;
  const source = clean(value).toLowerCase();
  if(!source) return null;
  if(['true','on','active','closed','yes'].includes(source)) return true;
  if(['false','off','inactive','open','no'].includes(source)) return false;
  const numeric = Number(source);
  return Number.isFinite(numeric) ? numeric !== 0 : null;
}

function sourceKey(records, aliases){
  const keys = [...new Set(records.flatMap(row => Object.keys(row || {})))];
  const normalized = keys.map(key => ({key,token:keyToken(key)}));
  const targets = aliases.map(keyToken).filter(Boolean);
  for(const target of targets){
    const exact = normalized.find(item => item.token === target);
    if(exact) return exact.key;
  }
  for(const target of targets){
    const suffix = normalized.find(item => item.token.endsWith(target));
    if(suffix) return suffix.key;
  }
  return '';
}

function latestValue(records, aliases){
  const key = sourceKey(records, aliases);
  if(!key) return {found:false,key:'',value:null,time:''};
  for(let index=records.length-1; index>=0; index--){
    const row = records[index] || {};
    const raw = row[key];
    if(raw === '' || raw === null || raw === undefined) continue;
    return {
      found:true,
      key,
      value:raw,
      time:clean(row.model_time_s ?? row.time_s ?? row.time ?? ''),
      row_index:index,
    };
  }
  return {found:false,key,value:null,time:''};
}

function aggregate(items){
  if(items.some(item => item.status === STATUS.BLOCKED)) return STATUS.BLOCKED;
  if(items.some(item => item.status === STATUS.DATA_MISSING)) return STATUS.DATA_MISSING;
  return STATUS.SATISFIED;
}

export function evaluateReadinessCondition(records, condition, affects=[]){
  const observed = latestValue(records, condition.aliases || []);
  if(!observed.found){
    return {...condition,affects,status:STATUS.DATA_MISSING,source_key:observed.key,raw_value:null,model_time_s:''};
  }
  const value = booleanValue(observed.value);
  if(value === null){
    return {...condition,affects,status:STATUS.DATA_MISSING,source_key:observed.key,raw_value:observed.value,model_time_s:observed.time};
  }
  const status = value === Boolean(condition.expected) ? STATUS.SATISFIED : STATUS.BLOCKED;
  return {...condition,affects,status,source_key:observed.key,raw_value:observed.value,model_time_s:observed.time};
}

export function deriveRecoveryReadiness(records=[]){
  const source = Array.isArray(records) ? records : [];
  const groups = RECOVERY_READINESS_GROUPS.map(group => {
    const conditions = group.conditions.map(condition => evaluateReadinessCondition(source,condition,group.affects));
    return {...group,conditions,status:aggregate(conditions)};
  });
  const byId=Object.fromEntries(groups.map(group=>[group.id,group]));
  const bopHrsg={
    id:'bop-hrsg',
    label:'BOP / HRSG READY TO START',
    status:aggregate([byId.hrsg,byId.feedwater]),
    dependencies:[byId.hrsg,byId.feedwater],
  };
  const gt={
    id:'gt-ready',
    label:'GT READY TO START',
    status:aggregate([byId['gt-start'],bopHrsg]),
    dependencies:[byId['gt-start'],bopHrsg],
  };
  const st={
    id:'st-ready',
    label:'ST READY TO START',
    status:aggregate([byId['st-start'],bopHrsg]),
    dependencies:[byId['st-start'],bopHrsg],
  };
  const trains=[gt,st];
  const status=aggregate(trains);
  const conditions=groups.flatMap(group=>group.conditions);
  const satisfied=conditions.filter(item=>item.status===STATUS.SATISFIED).length;
  const blocked=conditions.filter(item=>item.status===STATUS.BLOCKED);
  const missing=conditions.filter(item=>item.status===STATUS.DATA_MISSING);
  return {
    status,
    ready:status===STATUS.SATISFIED,
    trains,
    bop_hrsg:bopHrsg,
    groups,
    total:conditions.length,
    satisfied,
    blocked_count:blocked.length,
    missing_count:missing.length,
    blockers:blocked,
    missing,
  };
}
