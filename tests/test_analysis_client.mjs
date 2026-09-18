import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeDisplayAnalysis,parseCSV,summarizeEvents,buildDraftRows,draftCSV,modelTime,REPORT_COLUMNS,REPORT_SECTIONS} from '../apps/web/lib/analysisClient.mjs';

test('provider string and alias propagation never render as blank rows',()=>{
 const a=normalizeDisplayAnalysis({propagation:['GT 출력 감소',{description:'52GT 개방',evidence_id:'E3',tag:'vpp52GTClosed',model_time_s:48.52}]});
 assert.equal(a.propagation[0].claim,'GT 출력 감소');assert.equal(a.propagation[0].status,'UNKNOWN');assert.equal(a.propagation[1].claim,'52GT 개방');assert.deepEqual(a.propagation[1].evidence_ids,['E3']);
});
test('audit ISO strings never get an s suffix or become model time zero',()=>{
 const a=normalizeDisplayAnalysis({direct_trigger:{claim:'LATCH',recorded_time:'2026-09-15T14:52:04.212+00:00',status:'CONFIRMED',evidence_id:'E1'},verification_gate:'HOLD'});
 assert.equal(a.direct_trigger.model_time_s,null);assert.equal(a.direct_trigger.status,'CANDIDATE');assert.equal(modelTime(null),'시각 미확인');assert.equal(modelTime(0),'0.000 s');
});
test('CSV parser handles BOM, quoted multiline, comma, escaped quote and empty last cell',()=>{
 const parsed=parseCSV('\uFEFFevent_id,message,source,note\r\nE1,"line1\nline2, ""quoted""",OPENMODELICA_PHYSICS,\r\n');
 assert.equal(parsed.records.length,1);assert.equal(parsed.records[0].message,'line1\nline2, "quoted"');assert.equal(parsed.records[0].note,'');
 assert.throws(()=>parseCSV('a,a\n1,2'));assert.throws(()=>parseCSV('a,b\n1'));assert.throws(()=>parseCSV('a\n"unclosed'));
});
test('simulation events do not masquerade as ECMS events',()=>{
 const s=summarizeEvents([{source:'OPENMODELICA_PHYSICS',event_class:'PROTECTION'},{source:'DCS1'},{source:'ECMS'},{source:'unknown'}]);assert.deepEqual(s,{rows:4,dcs:1,ecms:1,simulation:1,other:1,protection:1});
});
test('draft uses fixed eight columns, nine human sections, UNKNOWN placeholders, and is safely editable',()=>{
 const envelope={events:[{event_id:'E1',tag:'TRIP_LATCH',source_node:'vppGTTripLatch',model_time_s:48.44,message:'GT LATCH'}],analysis:{verification_gate:'HOLD',primary_cause:{claim:'원인 후보',status:'CANDIDATE',evidence_ids:['R1']}}};
 const rows=buildDraftRows(envelope);assert.deepEqual([...new Set(rows.map(r=>r.section))],REPORT_SECTIONS);
 rows[0].content='=DANGEROUS()';const csv=draftCSV(rows);assert.ok(csv.startsWith('\uFEFF'));assert.ok(csv.includes("'=DANGEROUS()"));
 const parsed=parseCSV(csv);assert.deepEqual(parsed.fields,REPORT_COLUMNS);assert.ok(parsed.records.every(r=>Object.keys(r).length===8));assert.equal(envelope.events[0].message,'GT LATCH');
});
test('lists greater than five remain fully expandable',()=>{
 const source={critical_events:Array.from({length:15},(_,i)=>({claim:`사건 ${i}`,evidence_ids:[`E${i}`]}))};assert.equal(normalizeDisplayAnalysis(source).critical_events.length,15);
});
test('mandatory report semantics remain present even with empty AI lists',()=>{
 const rows=buildDraftRows({analysis:{}});
 assert.deepEqual([...new Set(rows.map(r=>r.section))],REPORT_SECTIONS);
 for(const item of ['선행 원인','직접 Trip 원인','파급 과정','인과관계 요약'])assert.ok(rows.some(r=>r.section==='발생 원인'&&r.item===item),item);
 assert.ok(rows.some(r=>r.section==='추정 원인 및 미확인 사항'&&r.item==='반대 근거'));
 assert.ok(rows.some(r=>r.section==='추정 원인 및 미확인 사항'&&r.item==='추가 확인'));
});
test('sampling intervals are visible, idempotent and not false exact timestamps',()=>{
 const source={primary_cause:{claim:'외부 입력 상승 후보',status:'CANDIDATE',evidence_ids:['RAW:1:tag','RAW:2:tag'],time_interval_s:[47.92,48.92],model_time_s:null}};
 const a=normalizeDisplayAnalysis(source);assert.match(a.primary_cause.claim,/47\.920 ~ 48\.920/);assert.equal(a.primary_cause.model_time_s,null);assert.equal(normalizeDisplayAnalysis(a).primary_cause.claim,a.primary_cause.claim);
 const row=buildDraftRows({analysis:a}).find(r=>r.section==='발생 원인'&&r.item==='선행 원인');assert.ok(row);assert.match(row.time,/표본 구간/);
});
