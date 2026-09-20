import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const exporter = require('../webapp/triplens_report_export.js');

const report = {
  title: 'TripLens Incident Analysis Report',
  run_id: 'RUN-TEST-001',
  verification_gate: 'HOLD',
  metadata: { run_id: 'RUN-TEST-001', event_file: 'EVENT.csv', raw_file: 'RAW.csv' },
  incident_summary: 'Dual Log evidence preserved',
  critical_events: [{ claim: 'ST Trip latch active', disposition: 'CONFIRMED', evidence: [{ source_system:'DCS1', event_id:'EV-1', original_time:'48.440', aligned_time:'48.440', equipment:'ST', event_tag:'TRIP_LATCH', canonical_tag:'ST.TRIP.LATCH', value:1, unit:'BOOL', state:'ACTIVE', evidence_role:'TRIGGER', mapping_status:'EVENT_RULE' }] }],
  primary_cause: { claim:'Cause candidate', disposition:'CANDIDATE', evidence_ids:['RAW-017'], related_tags:['ST.SPEED'], recorded_time:'48.200', ai_confidence:0.84, logic_master_status:'NOT_VERIFIED', review_required:true },
  direct_trigger: { claim:'ST Trip latch', status:'CONFIRMED', evidence_ids:['EV-1'], related_tags:['ST.TRIP.LATCH'], recorded_time:'48.440', logic_master_status:'VERIFIED' },
  propagation: [{ claim:'52ST open -> secondary alarms', status:'OBSERVED', evidence_ids:['EV-2'], related_tags:['52ST'], recorded_time:'48.610' }],
  causal_chain: ['ST Trip latch', '52ST breaker open'],
  key_evidence: [{ source:'EVENT.csv', tag:'TRIP_LATCH' }],
  recovery_check: 'Not fully recovered',
  gemini_analysis: 'Additional engineering review text',
  counter_evidence: ['No independent mechanical-failure evidence'],
  additional_evidence_required: ['Protection relay record'],
  recommendations: [{ claim:'보호 설정 검토', evidence_ids:['EV-1'] }],
  chronological_events: Array.from({length:12},(_,i)=>({ recorded_time:String(48+i/10), category:'SOE', claim:`Chronology ${i+1}`, status:'OBSERVED', evidence_ids:[`SEQ-${i+1}`], related_tags:[`TAG_${i+1}`] })),
};

test('PDF report HTML follows the industrial v2 report structure', () => {
  const html = exporter.buildReportHtml(report);
  for (const text of ['설비 고장 분석보고서 (초안)','1. 개요','3. 장애 현상','4. 시간대별 조치사항','5. 발생 원인','선행 원인','Primary Cause','직접 Trip 원인','Direct Trigger','파급 과정','Propagation','EVENT.csv','RAW.csv','검증 미완료']) assert.match(html,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  assert.match(html,/overflow:visible!important/);
  assert.match(html,/max-height:none!important/);
  assert.doesNotMatch(html,/>Gemini Analysis</);
});

test('PINPOINT CSV keeps canonical evidence and review state', () => {
  const csv = exporter.buildPinpointCsv(report);
  assert.match(csv,/^run_id,pinpoint_rank,causal_stage,claim,disposition,/);
  assert.match(csv,/RUN-TEST-001/);
  assert.match(csv,/ST\.TRIP\.LATCH/);
  assert.match(csv,/TRIP_LATCH/);
  assert.match(csv,/CONFIRMED/);
  assert.match(csv,/CANDIDATE/);
});

test('failure report CSV uses the fixed v2 columns and evidence-linked sections', () => {
  const csv = exporter.buildFailureReportCsv(report);
  assert.match(csv,/^구분,항목,내용,상태,근거 ID,관련 태그,기록 시각,비고/);
  for (const text of ['Primary Cause','Direct Trigger','Propagation','Critical Events']) assert.match(csv,new RegExp(text));
  assert.match(csv,/EV-1/);
  assert.equal((csv.match(/Chronology /g)||[]).length,12);
});

test('verification HOLD keeps report output as draft and never presents final-confirmed wording', () => {
  const html = exporter.buildReportHtml(report);
  assert.match(html,/고장 분석보고서 \(초안\)|검증 미완료/);
  assert.doesNotMatch(html,/Root Cause Confirmed/);
  assert.doesNotMatch(html,/>최종 확정</);
});

test('PDF v2 preserves the current editable report rows exactly', () => {
  const edited = {
    ...report,
    report_rows: [
      { section:'개요', item:'장애 요약', content:'운전 담당자가 수정한 최종 초안 문구', status:'OBSERVED', evidence_ids:'EV-1', tags:'ST.TRIP.LATCH', time:'48.440 s', note:'담당자 편집' },
      { section:'발생 원인', item:'직접 Trip 원인', content:'편집된 직접 Trip 원인', status:'CANDIDATE', evidence_ids:'EV-1', tags:'ST.TRIP.LATCH', time:'48.440 s', note:'최종 승인 전' },
    ],
  };
  const html = exporter.buildReportHtml(edited);
  assert.match(html,/운전 담당자가 수정한 최종 초안 문구/);
  assert.match(html,/편집된 직접 Trip 원인/);
  assert.match(html,/담당자 편집/);
  assert.doesNotMatch(html,/Dual Log evidence preserved/);
});

test('real workspace rows render all ten sections while legacy rows retain nine-section numbering', () => {
  const workspaceSections = [
    '개요','사고 발생 전 운전 현황','장애 현상','시간대별 사건·자동동작(SOE)','발생 원인',
    '운전원·정비 조치사항','조치 결과 및 복구 판정','추정 원인 및 미확인 사항',
    '재발방지 대책 — 검토 권고사항','증거자료',
  ];
  const workspaceHtml=exporter.buildReportHtml({...report,report_rows:workspaceSections.map(section=>({section,item:'검토',content:'내용'}))});
  assert.match(workspaceHtml,/6\. 운전원·정비 조치사항/);
  assert.match(workspaceHtml,/10\. 증거자료/);

  const legacyHtml=exporter.buildReportHtml({...report,report_rows:[{section:'개요',item:'검토',content:'내용'}]});
  assert.match(legacyHtml,/9\. 증거자료/);
  assert.doesNotMatch(legacyHtml,/10\. 증거자료/);
});

test('legacy failure-report CSV neutralizes spreadsheet formulas without changing eight columns', () => {
  const csv=exporter.buildFailureReportCsv({...report,incident_summary:'=HYPERLINK("https://example.invalid")'});
  assert.match(csv,/'=HYPERLINK/);
  assert.doesNotMatch(csv,/개요,장애 요약,=HYPERLINK/);
  const summaryLine=csv.split('\r\n').find(line=>line.includes('HYPERLINK'));
  assert.equal(summaryLine.match(/,/g).length,7);
});

test('workspace document state, not cause PASS alone, controls draft versus reviewed title', () => {
  const reportRows=[{section:'운전원·정비 조치사항',item:'실제 수행 조치',content:'점검 완료'}];
  const draft=exporter.buildReportHtml({...report,verification_gate:'PASS',document_state:'DRAFT',report_rows:reportRows});
  assert.match(draft,/설비 고장 분석보고서 \(초안\)/);
  assert.doesNotMatch(draft,/설비 고장 분석보고서 \(검토본\)/);
  const reviewed=exporter.buildReportHtml({...report,verification_gate:'PASS',document_state:'REVIEWED',report_rows:reportRows});
  assert.match(reviewed,/설비 고장 분석보고서 \(검토본\)/);
});
