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
export function buildDraftRows(envelope){
 const a=normalizeDisplayAnalysis(envelope?.analysis||{});const rows=[];
 const add=(section,item,c,note='')=>rows.push({section,item,content:claimText(c)||'추가 확인 필요',status:c?.status||'UNKNOWN',evidence_ids:list(c?.evidence_ids).join('; '),tags:list(c?.related_tags).join('; '),time:c?.time_interval_s?claimTime(c):numeric(c?.model_time_s)===null?'':modelTime(c.model_time_s),note});
 const first=(envelope?.events||[])[0];
 add('개요','발생 시각',first?{claim:modelTime(first.model_time_s),status:'OBSERVED',evidence_ids:[first.evidence_id||first.event_id],related_tags:[first.source_node||first.tag],model_time_s:first.model_time_s}:{});
 add('운전 현황','사고 전 운전 상태',{},'RAW 근거를 검토하여 담당자가 작성');
 add('장애 현상','최초 기록 Event',first?{claim:first.message||first.tag,status:'OBSERVED',evidence_ids:[first.evidence_id||first.event_id],model_time_s:first.model_time_s}:{});
 const actions=(envelope?.events||[]).filter(e=>e.event_class==='OPERATOR_ACTION');
 if(actions.length)actions.forEach((e,i)=>add('시간대별 조치사항',`기록 ${i+1}`,{claim:e.message,status:'OBSERVED',evidence_ids:[e.evidence_id||e.event_id],related_tags:[e.source_node||e.tag],model_time_s:e.model_time_s}));else add('시간대별 조치사항','확인된 조치',{},'미기록을 조치 없음으로 단정하지 않음');
 const addGroup=(key,section)=>{if(a[key].length)a[key].forEach((c,i)=>add(section,`${i+1}`,c));else add(section,'검토 상태',{},'조회 근거 또는 분석 항목 추가 확인 필요');};
 addGroup('critical_events','Critical Events');add('Primary Cause','선행 원인',a.primary_cause,'AI 후보 / 최종 확정 아님');add('Direct Trigger','직접 보호동작',a.direct_trigger,'등록 확인과 공학적 원인 확정은 구분');
 addGroup('propagation','Propagation');addGroup('causal_chain','Causal Chain');add('조치 결과','복구 상태',{},'담당자 확인 필요');addGroup('counter_evidence','반대 근거');
 a.additional_evidence_required.forEach((v,i)=>add('추가 확인 필요',`${i+1}`,{claim:v,status:'UNKNOWN'}));if(!a.additional_evidence_required.length)add('추가 확인 필요','담당자 검토',{},'검증 통과도 자동 운전 승인 아님');
 (a.review_recommendations.length?a.review_recommendations:['재발방지 대책은 운전·정비 담당자 검토 후 작성']).forEach((v,i)=>add('재발방지 대책',`검토 권고 ${i+1}`,{claim:v,status:'CANDIDATE'},'운전원 승인 필요 / 설비 조작 명령 아님'));return rows;
}
export function draftCSV(rows){const safe=v=>{let s=String(v??'');if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};return '\uFEFF'+[REPORT_COLUMNS,...rows.map(r=>[r.section,r.item,r.content,r.status,r.evidence_ids,r.tags,r.time,r.note])].map(r=>r.map(safe).join(',')).join('\r\n');}
export function displayError(error){if(typeof error==='string')return error;return error?.message||error?.detail?.message||'요청이 완료되지 않았습니다.';}
const DB_NAME='triplens-v8-review';
async function db(){return new Promise((resolve,reject)=>{const r=indexedDB.open(DB_NAME,1);r.onupgradeneeded=()=>r.result.createObjectStore('session');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
export async function loadSession(){const d=await db();try{return await new Promise((resolve,reject)=>{const t=d.transaction('session');const r=t.objectStore('session').get('active');r.onsuccess=()=>resolve(r.result||null);r.onerror=()=>reject(r.error);});}finally{d.close();}}
export async function saveSession(value){const d=await db();try{await new Promise((resolve,reject)=>{const t=d.transaction('session','readwrite');t.objectStore('session').put(value,'active');t.oncomplete=resolve;t.onerror=()=>reject(t.error);});}finally{d.close();}}
