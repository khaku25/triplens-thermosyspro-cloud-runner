const assert = require('node:assert/strict');
const reportExporter = require('./reportExporter.cjs');

const report = {
  run_id: 'RUN-DRAFT-001',
  metadata: { event_file: 'EVENT.csv', raw_file: 'RAW.csv' },
  equipment: 'GT·ST 발전설비',
  incident_time: 48.44,
  operator_analysis: {
    critical_events: [],
    primary_cause: {
      claim: '외부 Trip Command 입력',
      status: 'OBSERVED',
      model_time_s: 48.44,
    },
    direct_trigger: {
      claim: 'GT·ST Trip Latch 동시 동작',
      status: 'OBSERVED',
      model_time_s: 48.44,
    },
    causal_chain: [],
    propagation: [],
    counter_evidence: [],
  },
  chronological_events: [
    { model_time_s: 48.44, equipment: 'GT·ST', claim: 'GT·ST Trip Latch ACTIVE' },
    { model_time_s: 48.52, equipment: '52GT', claim: '52GT 차단기 OPEN' },
  ],
  recovery: {},
};

const html = reportExporter.buildReportHtml(report);

assert.match(html, /<h2>1\. 사고 개요<\/h2>/);
assert.match(html, /발생 원인/);
assert.match(html, /직접 보호동작/);
assert.match(html, /4\. 분석 결론/);
assert.doesNotMatch(html, /READ-ONLY/);
assert.doesNotMatch(html, /고장보고서 초안/);
assert.doesNotMatch(html, /복구 기록 입력 대기/);

console.log('report-draft.test.cjs: PASS');
