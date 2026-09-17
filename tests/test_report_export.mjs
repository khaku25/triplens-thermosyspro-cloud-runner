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
