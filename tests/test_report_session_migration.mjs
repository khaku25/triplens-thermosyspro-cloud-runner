import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {buildDraftRows,REPORT_SECTIONS,draftCSV,parseCSV} from '../apps/web/lib/analysisClient.mjs';
import {validateReportReferences} from '../apps/web/lib/reportIntegrity.mjs';
import * as adapter from '../apps/web/lib/reportAdapter.mjs';
import exporter from '../apps/web/lib/reportExporter.cjs';

// Captured with the actual baseline builder at 526cc157; not reconstructed
// from today's builder. Contains legacy hashes, nine sections and 14 evidence rows.
const fixture=JSON.parse(readFileSync(new URL('./fixtures/legacy-report-session.json',import.meta.url)));
const recovery={status:'RECOVERED',operator:'Lee',actions:'점검 완료',recovered_at:'2026-09-20T10:00',restart_conditions:'별도 운전 승인',evidence_ids:['E21'],approver:'Kim',approved_at:'2026-09-20T11:00'};
const restore=(saved)=>adapter.restoreWorkspaceReportRows(saved);

test('legacy saved session repairs 21 EVENT references, Source tags and SOE without losing matched edits',()=>{
  const saved=structuredClone(fixture);
  assert.equal(new Set(saved.reportRows.map(row=>row.section)).size,9);
  assert.equal(saved.result.evidence_catalog.length,14);
  assert.deepEqual(validateReportReferences(saved.reportRows).missing,['E15','E16','E17','E18','E19','E20','E21']);
  Object.assign(saved.reportRows.find(row=>row.item==='사고 전 운전 상태'),{content:'담당자 운전상태 기록',status:'CANDIDATE',note:'수동 검토',tags:'custom-source'});
  Object.assign(saved.reportRows.find(row=>row.item==='SOE 21'),{content:'수정한 EVENT 설명',note:'담당자 주석'});
  Object.assign(saved.reportRows.find(row=>row.item==='Evidence 2'),{content:'근거 설명 편집',note:'담당자 주석'});
  saved.recovery=recovery;
  const before=structuredClone(saved);
  const rows=restore(saved);
  assert.deepEqual(saved,before);
  assert.deepEqual([...new Set(rows.map(row=>row.section))],REPORT_SECTIONS);
  assert.equal(rows.filter(row=>row.section==='시간대별 사건·자동동작(SOE)').length,21);
  const evidence=rows.filter(row=>row.section==='증거자료');
  assert.equal(evidence.length,21);
  assert.ok(evidence.every(row=>row.tags==='vppGTTripLatch'));
  assert.deepEqual(validateReportReferences(rows),{valid:true,missing:[]});
  assert.equal(rows.find(row=>row.item==='SOE 21').content,'수정한 EVENT 설명');
  assert.equal(rows.find(row=>row.item==='SOE 21').tags,'vppGTTripLatch');
  assert.equal(rows.find(row=>row.item==='Evidence 2').content,'근거 설명 편집');
  const manual=rows.find(row=>row.item==='사고 전 운전 상태');
  assert.deepEqual(manual,before.reportRows.find(row=>row.item==='사고 전 운전 상태'));
  assert.equal(rows.find(row=>row.item==='실제 수행 조치').content,'점검 완료');
  assert.ok(!rows.some(row=>row.section==='운전원·정비 조치사항'&&/^SOE/.test(row.item)));
  assert.equal(parseCSV(draftCSV(rows)).fields.length,8);
});

test('legacy rows without IDs migrate once and keep isolated stable identities',()=>{
  const saved=structuredClone(fixture);
  saved.reportRows.forEach(row=>delete row.row_id);
  const rows=restore(saved);
  assert.equal(new Set(rows.map(row=>row.row_id)).size,rows.length);
  assert.ok(rows.every(row=>row.row_id));
  assert.deepEqual(restore({...saved,reportRows:rows}),rows);
});

test('already-current V2 edits survive restore and cache reuse, including invalid references',()=>{
  const reportRows=adapter.applyRecoveryRows(buildDraftRows(fixture.result),recovery);
  Object.assign(reportRows[0],{content:'현재 V2 편집',tags:'custom-tag',evidence_ids:'MISSING-EDIT'});
  const saved={...fixture,reportRows,recovery};
  assert.deepEqual(restore(saved),reportRows);
  // A versioned document must not silently repair a user's evidence-row edit.
  reportRows.find(row=>row.section==='증거자료').evidence_ids='CUSTOM-ID';
  assert.deepEqual(restore({...saved,reportVersion:2}),reportRows);
  assert.equal(validateReportReferences(restore({...saved,reportVersion:2})).valid,false);
});

test('unversioned ten-section partial catalog is repaired while evidence edits follow their IDs after reordering',()=>{
  const reportRows=adapter.applyRecoveryRows(buildDraftRows(fixture.result),recovery)
    .filter(row=>row.section!=='증거자료'||Number(row.evidence_ids.slice(1))<=14);
  reportRows.find(row=>row.section==='증거자료'&&row.evidence_ids==='E2').content='E2 담당자 편집';
  const saved={...fixture,reportRows,recovery,result:{...fixture.result,events:fixture.result.events.map(row=>({...row,model_time_s:22-row.model_time_s}))}};
  const rows=restore(saved);
  assert.equal(rows.filter(row=>row.section==='증거자료').length,21);
  assert.equal(rows.find(row=>row.section==='증거자료'&&row.evidence_ids==='E2').content,'E2 담당자 편집');
  assert.deepEqual(validateReportReferences(rows),{valid:true,missing:[]});
});

test('PINPOINT recovery links resolve the EVENTs restored beyond the legacy partial catalog',()=>{
  const reportRows=restore({...fixture,recovery});
  const report=adapter.buildWorkspaceExportReport({result:fixture.result,reportRows,recovery});
  const rows=exporter.pinpointRows(report).filter(row=>row.causal_stage==='RECOVERY');
  assert.ok(rows.some(row=>row.event_id==='E21'&&row.canonical_tag==='vppGTTripLatch'));
});
