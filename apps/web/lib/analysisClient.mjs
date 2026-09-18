// Presentation only. Never derives a Primary Cause or a plant command.
export const CONTRACT_VERSION='GROUNDED_ANALYSIS_V3';
export const STATUS_TEXT={CONFIRMED:'확인',CANDIDATE:'후보',OBSERVED:'관측',UNKNOWN:'미확인'};
const list=v=>v==null?[]:Array.isArray(v)?v:[v];
const unique=v=>[...new Set(v.filter(x=>x!==null&&x!==undefined&&String(x).trim()).map(String))];
const numeric=v=>v!==''&&v!=null&&typeof v!=='boolean'&&Number.isFinite(Number(v))?Number(v):null;
export function claimText(v){if(typeof v==='string')return v;if(!v||typeof v!=='object')return '';return ['claim','description','finding','text','reason','item'].map(k=>v[k]).find(x=>typeof x==='string'&&x.trim())||'';}
export function modelTime(v){const n=numeric(v);return n===null?'시각 미확인':`${n.toFixed(3)} s`;}
export function claimTime(v){return Array.isArray(v?.time_interval_s)&&v.time_interval_s.length===2&&v.time_interval_s.every(x=>numeric(x)!==null)?`${Number(v.time_interval_s[0]).toFixed(3)} ~ ${Number(v.time_interval_s[1]).toFixed(3)} s (표본 구간)`:modelTime(v?.model_time_s);}
export function normalizeDisplayClaim(value,stage='observation',gate='HOLD'){
 const v=value&&typeof value==='object'&&!Array.isArray(value)?value:{claim:claimText(value)};
 const ids=unique(list(v.evidence_ids||v.evidence_id||v.event_id));const tags=unique(list(v.related_tags||v.tag||v.tags));
 const interval=Array.isArray(v.time_interval_s)&&v.time_interval_s.length===2&&v.time_interval_s.every(x=>numeric(x)!==null)?v.time_interval_s.map(Number):null;
 const seconds=interval?null:numeric(v.model_time_s)??numeric(v.recorded_time);
 const wall=v.wall_time_utc||(typeof v.recorded_time==='string'&&v.recorded_time.includes('T')?v.recorded_time:'');
 let status=Object.hasOwn(STATUS_TEXT,v.status)?v.status:ids.length?'OBSERVED':'UNKNOWN';
 if(!ids.length)status='UNKNOWN';if(status==='CONFIRMED'&&(gate!=='PASS'||v.evidence_verified!==true))status=['primary_cause','direct_trigger'].includes(stage)?'CANDIDATE':'OBSERVED';
 let claim=claimText(v)||'설명 미제공';
 if(interval&&!claim.includes('(표본 구간)'))claim+=` [${claimTime({time_interval_s:interval})}; 정확한 발생 시각 미확인]`;
 return {...v,stage,claim,status,evidence_ids:ids,related_tags:tags,model_time_s:seconds,time_interval_s:interval,recorded_time:seconds===null?'':String(seconds),wall_time_utc:wall,logic_master_status:v.logic_master_status||'NOT_VERIFIED',ai_confidence:numeric(v.ai_confidence)};
}
export function normalizeDisplayAnalysis(raw={}){
 const gate=raw.verification_gate==='PASS'?'PASS':'HOLD';const result={...raw,verification_gate:gate};
 for(const name of ['primary_cause','direct_trigger'])result[name]=normalizeDisplayClaim(raw[name],name,gate);
 for(const name of ['critical_events','propagation','causal_chain','counter_evidence'])result[name]=list(raw[name]).map(v=>normalizeDisplayClaim(v,name,gate));
 result.additional_evidence_required=list(raw.additional_evidence_required).map(claimText).filter(Boolean);result.review_recommendations=list(raw.review_recommendations).map(claimText).filter(Boolean);result.tool_trace=list(raw.tool_trace);result.verification_notes=list(raw.verification_notes);return result;
}
export function parseCSV(text){
 const rows=[];let row=[],cell='',quoted=false;text=String(text).replace(/^\uFEFF/,'');
 for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(c===','&&!quoted){row.push(cell);cell='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(x=>x!==''))rows.push(row);row=[];cell='';}else cell+=c;}
 if(quoted)throw new Error('CSV 따옴표가 닫히지 않았습니다.');row.push(cell);if(row.some(x=>x!==''))rows.push(row);
 const fields=rows.shift()||[];if(new Set(fields).size!==fields.length)throw new Error('CSV에 중복 열이 있습니다.');
 const records=rows.map((values,i)=>{if(values.length!==fields.length)throw new Error(`CSV ${i+2}행 열 수 불일치`);return Object.fromEntries(fields.map((k,j)=>[k,values[j]]));});return {fields,records};
}
export function summarizeEvents(records=[]){const r={rows:records.length,dcs:0,ecms:0,simulation:0,other:0,protection:0};for(const e of records){const s=String(e.source||'').toUpperCase();if(s.includes('DCS'))r.dcs++;else if(s.includes('ECMS'))r.ecms++;else if(s.includes('OPENMODELICA')||s==='SIM')r.simulation++;else r.other++;if(String(e.event_class).toUpperCase()==='PROTECTION')r.protection++;}return r;}
export const REPORT_COLUMNS=['구분','항목','내용','상태','근거 ID','관련 태그','기록 시각','비고'];
export const REPORT_SECTIONS=['개요','사고 발생 전 운전 현황','장애 현상','시간대별 조치사항','발생 원인','조치 결과','추정 원인 및 미확인 사항','재발방지 대책 — 검토 권고사항','증거자료'];
// IDs are metadata, not a ninth CSV column. Display numbering does not define identity.
function assignReportRowIds(rows){
 const identities=new Map(),occurrences=new Map();
 return rows.map(row=>{
  const tokens=v=>String(v||'').split(';').map(x=>x.trim()).filter(Boolean).sort();
  const identity=JSON.stringify([row.section,row.item.replace(/\s+\d+$/,''),row.content,tokens(row.evidence_ids),tokens(row.tags),row.time]);
  let hash=0xcbf29ce484222325n;
  for(const byte of new TextEncoder().encode(identity)){hash^=BigInt(byte);hash=BigInt.asUintN(64,hash*0x100000001b3n);}
  const base='ROW-'+hash.toString(16).padStart(16,'0');
  if(identities.has(base)&&identities.get(base)!==identity)throw new Error('보고서 행 식별자 충돌: 검토를 중단합니다.');
  identities.set(base,identity);const occurrence=(occurrences.get(base)||0)+1;occurrences.set(base,occurrence);
  return {...row,row_id:base+(occurrence>1?'-'+occurrence:'')};
 });
}
export function humanReviewNote(value){
 const s=String(value||'');
 const translations=[
  ['근거 ID 미연결','해당 주장에 연결된 원본 기록이 없어 추가 확인이 필요합니다.'],
  ['설명 미제공','분석 설명이 제공되지 않아 담당자 확인이 필요합니다.'],
  ['인용 근거에 없는 태그:','다음 신호에 대한 원본 관측과 해당 주장의 근거 연결을 확인하세요:'],
  ['미조회 또는 존재하지 않는 근거 ID:','해당 주장이 참조하는 원본 기록을 다시 확인하세요:'],
  ['주장한 시간구간과 인용 표본의 시각 불일치','서술한 관측 구간의 시작·끝 표본을 확인하고 보고서의 시간 범위를 맞춰야 합니다.'],
  ['태그별 관측 구간의 경계 표본 인용 누락:','관측 구간의 시작·끝 표본을 추가로 연결해야 하는 신호:'],
  ['AI 시각과 인용 근거 시각 불일치','분석에 적힌 시각과 원본 기록의 시각을 대조해야 합니다.'],
  ['RAW Tool 조회 성공 기록 없음','공정 시계열 조회가 확인되지 않았습니다. 원본 RAW 기록을 확인해야 합니다.'],
  ['Logic Tool 조회 성공 기록 없음','관련 로직 조회가 확인되지 않았습니다. 승인 로직 원장을 확인해야 합니다.'],
  ['Tool 오류 또는 호출 예산 소진','일부 근거 조회가 완료되지 않아 해당 항목은 추가 확인이 필요합니다.'],
  ['Primary Cause 미확인','사고의 선행 원인을 확정할 근거가 부족합니다.'],
  ['Direct Trigger 미확인','직접 보호동작을 판단할 근거를 추가 확인해야 합니다.'],
  ['Direct Trigger의 등록 로직 연결 미확인','직접 보호동작과 승인 로직의 연결을 확인해야 합니다.']
 ];
 for(const [prefix,replacement] of translations)if(s.startsWith(prefix))return replacement+s.slice(prefix.length);
 return s;
}
export function buildDraftRows(envelope){
 const a=normalizeDisplayAnalysis(envelope?.analysis||{});const rows=[];const events=[...(envelope?.events||[])].sort((x,y)=>(numeric(x.model_time_s)??Infinity)-(numeric(y.model_time_s)??Infinity));
 const add=(section,item,c,note='')=>rows.push({section,item,content:claimText(c)||'추가 확인 필요',status:c?.status||'UNKNOWN',evidence_ids:list(c?.evidence_ids).join('; '),tags:list(c?.related_tags).join('; '),time:c?.time_interval_s?claimTime(c):numeric(c?.model_time_s)===null?'':modelTime(c.model_time_s),note});
 const first=events[0];
 add('개요','발생 시각',first?{claim:modelTime(first.model_time_s),status:'OBSERVED',evidence_ids:[first.evidence_id||first.event_id],related_tags:[first.source_node||first.tag],model_time_s:first.model_time_s}:{},'최초 기록 시각 기준');
 add('사고 발생 전 운전 현황','사고 전 운전 상태',{},'사고 전 RAW 운전상태를 담당자가 검토하여 작성');
 if(a.critical_events.length)a.critical_events.forEach((c,i)=>add('장애 현상',`Critical Event ${i+1}`,c));
 else if(first)add('장애 현상','최초 기록 Event',{claim:first.message||first.tag,status:'OBSERVED',evidence_ids:[first.evidence_id||first.event_id],related_tags:[first.source_node||first.tag],model_time_s:first.model_time_s});
 else add('장애 현상','검토 상태',{},'EVENT 근거 없음');
 if(events.length)events.forEach((e,i)=>add('시간대별 조치사항',`SOE ${i+1}`,{claim:e.message||`${e.equipment||''} ${e.tag||''}`.trim(),status:'OBSERVED',evidence_ids:[e.evidence_id||e.event_id].filter(Boolean),related_tags:[e.source_node||e.tag].filter(Boolean),model_time_s:e.model_time_s},e.event_class||e.source||''));
 else add('시간대별 조치사항','검토 상태',{},'시간순 EVENT 기록 없음');
 add('발생 원인','선행 원인',a.primary_cause,'AI 후보 / 최종 확정 아님');
 add('발생 원인','직접 Trip 원인',a.direct_trigger,'등록 Logic 확인과 공학적 원인 확정은 구분');
 if(a.propagation.length)a.propagation.forEach((c,i)=>add('발생 원인',`파급 과정 ${i+1}`,c));
 else add('발생 원인','파급 과정',{},'파급 근거 추가 확인 필요');
 if(a.causal_chain.length)a.causal_chain.forEach((c,i)=>add('발생 원인',`인과관계 요약 ${i+1}`,c,'시간순 근거와 함께 검토'));
 else add('발생 원인','인과관계 요약',{},'인과관계 추가 확인 필요');
 add('조치 결과','복구 상태',{},'실제 복구·재기동 기록은 담당자 확인 필요');
 if(a.counter_evidence.length)a.counter_evidence.forEach((c,i)=>add('추정 원인 및 미확인 사항',`반대 근거 ${i+1}`,c));
 else add('추정 원인 및 미확인 사항','반대 근거',{},'반대 근거 없음으로 단정하지 않음');
 if(a.additional_evidence_required.length)a.additional_evidence_required.forEach((v,i)=>add('추정 원인 및 미확인 사항',`추가 확인 ${i+1}`,{claim:humanReviewNote(v),status:'UNKNOWN'}));
 else add('추정 원인 및 미확인 사항','추가 확인',{},'담당자 최종 검토 필요');
 const recommendations=a.review_recommendations.length?a.review_recommendations:['재발방지 대책은 운전·정비 담당자 검토 후 작성'];
 recommendations.forEach((v,i)=>add('재발방지 대책 — 검토 권고사항',`검토 권고 ${i+1}`,{claim:v,status:'CANDIDATE'},'담당자 승인 필요 / 설비 조작 명령 아님'));
 const evidence=envelope?.evidence_catalog?.length?envelope.evidence_catalog:events.map(e=>({...e,evidence_id:e.evidence_id||e.event_id,source_kind:'EVENT'}));
 if(evidence.length)evidence.forEach((e,i)=>add('증거자료',`Evidence ${i+1}`,{claim:e.message||`${e.source_kind||'EVIDENCE'} · ${e.source_node||e.tag||''}`.trim(),status:'OBSERVED',evidence_ids:[e.evidence_id||e.event_id].filter(Boolean),related_tags:[e.source_node||e.tag].filter(Boolean),model_time_s:e.model_time_s},e.source_kind||e.source||''));
 else add('증거자료','검토 상태',{},'연결된 Evidence 없음');
 return assignReportRowIds(rows);
}
export function draftCSV(rows){const safe=v=>{let s=String(v??'');if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};return '\uFEFF'+[REPORT_COLUMNS,...rows.map(r=>[r.section,r.item,r.content,r.status,r.evidence_ids,r.tags,r.time,r.note])].map(r=>r.map(safe).join(',')).join('\r\n');}
export function displayError(error){if(typeof error==='string')return error;return error?.message||error?.detail?.message||'요청이 완료되지 않았습니다.';}
const DB_NAME='triplens-v8-review';
async function db(){return new Promise((resolve,reject)=>{const r=indexedDB.open(DB_NAME,1);r.onupgradeneeded=()=>r.result.createObjectStore('session');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
export async function loadSession(){const d=await db();try{return await new Promise((resolve,reject)=>{const t=d.transaction('session');const r=t.objectStore('session').get('active');r.onsuccess=()=>resolve(r.result||null);r.onerror=()=>reject(r.error);});}finally{d.close();}}
export async function saveSession(value){const d=await db();try{await new Promise((resolve,reject)=>{const t=d.transaction('session','readwrite');t.objectStore('session').put(value,'active');t.oncomplete=resolve;t.onerror=()=>reject(t.error);});}finally{d.close();}}
