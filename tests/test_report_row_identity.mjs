import test from 'node:test';
import assert from 'node:assert/strict';
import {buildDraftRows,draftCSV,REPORT_COLUMNS} from '../apps/web/lib/analysisClient.mjs';
const c=(claim,id)=>({claim,status:'OBSERVED',evidence_ids:[id],related_tags:['vppA'],model_time_s:1});
const env={analysis:{critical_events:[c('첫 관측','E1'),c('두번째 관측','E2')]},events:[]};
test('rows have unique IDs and same evidence row keeps identity after preceding insertion',()=>{
 const rows=buildDraftRows(env);
 assert.ok(rows.every(r=>typeof r.row_id==='string'&&r.row_id.length>0));
 assert.equal(new Set(rows.map(r=>r.row_id)).size,rows.length);
 const expanded=buildDraftRows({analysis:{critical_events:[c('추가 관측','E0'),...env.analysis.critical_events]},events:[]});
 assert.equal(rows.find(r=>r.content==='두번째 관측').row_id,expanded.find(r=>r.content==='두번째 관측').row_id);
 assert.deepEqual(rows,buildDraftRows(env));
});
test('manual edit retains row identity and eight visible CSV columns',()=>{
 const rows=buildDraftRows(env);const edited=rows.map(r=>({...r,content:'편집됨'}));
 assert.ok(rows[0].row_id);assert.equal(edited[0].row_id,rows[0].row_id);
 assert.equal(REPORT_COLUMNS.length,8);assert.equal(draftCSV(edited).split('\r\n')[0].split(',').length,8);
});
test('human report translates technical warning text without losing raw diagnostics',()=>{
 const original='인용 근거에 없는 태그: vppGTTripRequest';
 const e={analysis:{additional_evidence_required:[original],verification_notes:[original]}};
 const rows=buildDraftRows(e);
 assert.ok(!rows.some(r=>r.content.includes('인용 근거에 없는 태그:')));
 assert.ok(rows.some(r=>r.content.includes('vppGTTripRequest')));
 assert.deepEqual(e.analysis.verification_notes,[original]);
});
