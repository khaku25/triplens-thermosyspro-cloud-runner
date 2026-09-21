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

test('PDF report HTML follows the concise operator report structure', () => {
  const html = exporter.buildReportHtml(report);
  for (const text of ['설비 고장 분석보고서','1. 사고 개요','2. 발생 원인','직접 보호동작','3. 시간순 사고 경위','4. 복구조치 및 확인사항','EVENT.csv','RAW.csv']) assert.match(html,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  for (const text of ['Verification Gate','AI Confidence','CANDIDATE','(초안)','근거 ID','관련 태그']) assert.doesNotMatch(html,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  assert.match(html,/overflow:visible!important/);
  assert.match(html,/max-height:none!important/);
  assert.doesNotMatch(html,/T\+0\.000 s/);
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

test('internal verification state is not shown as unfinished report copy', () => {
  const html = exporter.buildReportHtml(report);
  assert.match(html,/설비 고장 분석보고서/);
  assert.doesNotMatch(html,/초안|Verification Gate|HOLD|검증 미완료/);
  assert.doesNotMatch(html,/Root Cause Confirmed/);
  assert.doesNotMatch(html,/>최종 확정</);
});

test('concise PDF preserves editable summary and direct-trigger wording', () => {
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
  assert.doesNotMatch(html,/Dual Log evidence preserved/);
});

test('workspace PDF projects ten-section source rows into four concise operator sections', () => {
  const workspaceSections = [
    '개요','사고 발생 전 운전 현황','장애 현상','시간대별 사건·자동동작(SOE)','발생 원인',
    '운전원·정비 조치사항','조치 결과 및 복구 판정','추정 원인 및 미확인 사항',
    '재발방지 대책 — 검토 권고사항','증거자료',
  ];
  const workspaceHtml=exporter.buildReportHtml({...report,report_rows:workspaceSections.map(section=>({section,item:'검토',content:'내용'}))});
  assert.match(workspaceHtml,/4\. 복구조치 및 확인사항/);
  assert.match(workspaceHtml,/내용/);
  assert.doesNotMatch(workspaceHtml,/10\. 증거자료|근거 ID|관련 태그/);

  const legacyHtml=exporter.buildReportHtml({...report,report_rows:[{section:'개요',item:'검토',content:'내용'}]});
  assert.match(legacyHtml,/4\. 복구조치 및 확인사항/);
  assert.doesNotMatch(legacyHtml,/9\. 증거자료|10\. 증거자료/);
});

test('legacy failure-report CSV neutralizes spreadsheet formulas without changing eight columns', () => {
  const csv=exporter.buildFailureReportCsv({...report,incident_summary:'=HYPERLINK("https://example.invalid")'});
  assert.match(csv,/'=HYPERLINK/);
  assert.doesNotMatch(csv,/개요,장애 요약,=HYPERLINK/);
  const summaryLine=csv.split('\r\n').find(line=>line.includes('HYPERLINK'));
  assert.equal(summaryLine.match(/,/g).length,7);
});

test('workspace document state keeps the same finished report title', () => {
  const reportRows=[{section:'운전원·정비 조치사항',item:'실제 수행 조치',content:'점검 완료'}];
  const draft=exporter.buildReportHtml({...report,verification_gate:'PASS',document_state:'DRAFT',report_rows:reportRows});
  assert.match(draft,/설비 고장 분석보고서/);
  assert.doesNotMatch(draft,/설비 고장 분석보고서 \(초안\)|설비 고장 분석보고서 \(검토본\)/);
  const reviewed=exporter.buildReportHtml({...report,verification_gate:'PASS',document_state:'REVIEWED',report_rows:reportRows});
  assert.match(reviewed,/설비 고장 분석보고서/);
  assert.doesNotMatch(reviewed,/설비 고장 분석보고서 \(초안\)|설비 고장 분석보고서 \(검토본\)/);
});

test('default PDF is a concise operator report without developer metadata or raw evidence columns', () => {
  const operatorReport={
    ...report,
    metadata:{
      ...report.metadata,
      data_digest:'secret-digest',
      analysis_engine:'Gemini Tool Analysis',
    },
    primary_cause:{
      ...report.primary_cause,
      claim:'외부 트립 명령 태그 vppExternalTripCommandNative가 47.92초와 48.92초 사이에서 인가됨.',
      related_tags:['vppExternalTripCommandNative'],
    },
    direct_trigger:{
      ...report.direct_trigger,
      claim:'model_time_s 48.44초에 GT TRIP LATCH(vppGTTripLatch) 및 ST TRIP LATCH(vppSTTripLatchPublished)가 1.0(ACTIVE)으로 동시에 작동함.',
      related_tags:['vppGTTripLatch','vppSTTripLatchPublished'],
    },
    chronological_events:Array.from({length:12},(_,index)=>({
      recorded_time:48.44+index/10,
      wall_time_utc:`2026-09-15T14:52:${String(4+index).padStart(2,'0')}.213+00:00`,
      equipment:index<2?'GT':'HRSG',
      category:index<2?'PROTECTION':'ALARM',
      claim:index===0?'GT TRIP LATCH ACTIVE':index===1?'52GT BREAKER OPEN':`후속 알람 ${index}`,
      related_tags:index===0?['vppGTTripLatch']:[],
    })),
    report_rows:[],
  };
  const html=exporter.buildReportHtml(operatorReport);
  for(const text of ['사고 개요','발생 원인','직접 보호동작','시간순 사고 경위','시간','설비 / 구분','발생 내용','후속 기록 5건'])assert.match(html,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  for(const text of ['Run ID','Data Digest','Analysis Engine','근거 ID','관련 태그','model_time_s','vppGTTripLatch','secret-digest'])assert.doesNotMatch(html,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  assert.equal((html.match(/class="timeline-row"/g)||[]).length,7);
  assert.match(html,/@page\{size:A4;margin:0\}/);
});

test('detailed CSV remains available after the PDF is shortened', () => {
  const csv=exporter.buildPinpointCsv(report);
  assert.match(csv,/event_id/);
  assert.match(csv,/ST\.TRIP\.LATCH/);
  assert.match(csv,/EV-1/);
});

test('operator PDF shortens unusually long AI prose', () => {
  const longClaim='상세 원인 설명 '.repeat(40).trim();
  const html=exporter.buildReportHtml({
    ...report,
    primary_cause:{claim:longClaim,related_tags:[]},
    report_rows:[],
  });
  assert.doesNotMatch(html,new RegExp(longClaim));
  assert.match(html,/상세 원인 설명 .*…/);
});
