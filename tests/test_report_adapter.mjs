import test from 'node:test';
import assert from 'node:assert/strict';
import {buildDraftRows,draftCSV,parseCSV,REPORT_SECTIONS} from '../apps/web/lib/analysisClient.mjs';
import exporter from '../apps/web/lib/reportExporter.cjs';
import {buildWorkspaceExportReport,recoveryReportRows,applyRecoveryRows} from '../apps/web/lib/reportAdapter.mjs';

const events=[{event_id:'E1',evidence_id:'E1',model_time_s:48.44,message:'GT TRIP LATCH ACTIVE',source_node:'vppGTTripLatch',tag:'TRIP_LATCH',source:'DCS'}];
const catalog=[{evidence_id:'E1',source_kind:'EVENT',model_time_s:48.44,source_node:'vppGTTripLatch',tag:'TRIP_LATCH',canonical_tag:'GT.TRIP.LATCH'}];
const analysis={
  verification_gate:'PASS',
  critical_events:[{claim:'GT latch',status:'CONFIRMED',evidence_ids:['E1'],related_tags:['vppGTTripLatch'],model_time_s:48.44,evidence_verified:true}],
  primary_cause:{claim:'external command',status:'CONFIRMED',evidence_ids:['E1'],related_tags:['vppGTTripLatch'],model_time_s:48.4,evidence_verified:true},
  direct_trigger:{claim:'GT latch',status:'CONFIRMED',evidence_ids:['E1'],related_tags:['vppGTTripLatch'],model_time_s:48.44,evidence_verified:true},
  propagation:[],causal_chain:[],counter_evidence:[],additional_evidence_required:[],review_recommendations:[],
};
const recovery={
  status:'RECOVERED',
  recovered_at:'2026-09-20T09:30:00Z',
  operator:'Lee',
  actions:'현장 점검 및 보호계전기 복귀 확인',
  restart_conditions:'진동·윤활유압 정상 확인 후 재기동',
  evidence_ids:['E1'],
  approver:'Kim',
  approved_at:'',
};

function exportReport(recoveryValue=recovery){
  const reportRows=buildDraftRows({events,evidence_catalog:catalog,analysis});
  return buildWorkspaceExportReport({
    result:{run_id:'RUN-1',data_digest:'abc'},analysis,events,catalog,reportRows,recovery:recoveryValue,
    eventFileName:'EVENT.csv',rawFileName:'RAW.csv',
  });
}

test('recovery rows replace placeholders while preserving all ten human report sections', () => {
  const base=buildDraftRows({events,evidence_catalog:catalog,analysis});
  const recoveryRows=recoveryReportRows(recovery);
  const rows=applyRecoveryRows(base,recovery);
  assert.deepEqual([...new Set(rows.map(row=>row.section))],REPORT_SECTIONS);
  assert.equal(recoveryRows.length,4);
  assert.ok(rows.some(row=>row.section==='운전원·정비 조치사항'&&row.item==='실제 수행 조치'&&row.content===recovery.actions));
  assert.ok(rows.some(row=>row.section==='조치 결과 및 복구 판정'&&row.item==='재기동 조건'&&row.content===recovery.restart_conditions));
  assert.equal(rows.some(row=>row.content==='복구·조치 기록 입력 대기'),false);
});

test('workspace export projects the authoritative recovery record and reports reference integrity', () => {
  const out=exportReport();
  assert.equal(out.recovery_actions,recovery.actions);
  assert.equal(out.recovered_at,recovery.recovered_at);
  assert.equal(out.recovery_operator,recovery.operator);
  assert.equal(out.restart_conditions,recovery.restart_conditions);
  assert.equal(out.recovery_approver,recovery.approver);
  assert.equal(out.recovery_approved_at,recovery.approved_at);
  assert.equal(out.recovery_workflow,'APPROVAL_PENDING');
  assert.deepEqual(out.reference_integrity,{valid:true,missing:[]});
  assert.equal(out.report_rows.some(row=>row.section==='증거자료'&&row.evidence_ids.includes('E1')),true);
});

test('cause PASS cannot review a document until recovery is explicitly approved', () => {
  assert.equal(exportReport().document_state,'DRAFT');
  const approved={...recovery,approved_at:'2026-09-20T10:00:00Z'};
  const out=exportReport(approved);
  assert.equal(out.document_state,'REVIEWED');
  assert.equal(out.verification_gate,'PASS');
  assert.equal(out.recovery_workflow,'APPROVED');
});

test('approved recovery appears consistently in PDF, report CSV and PINPOINT', () => {
  const approved={...recovery,approved_at:'2026-09-20T10:00:00Z'};
  const out=exportReport(approved);
  const html=exporter.buildReportHtml(out);
  const csv=draftCSV(out.report_rows);
  const pinpoint=exporter.buildPinpointCsv(out);
  for(const value of [approved.actions,approved.operator,approved.restart_conditions,approved.approver,approved.approved_at,approved.recovered_at]){
    for(const output of [html,csv,pinpoint])assert.ok(output.includes(value),`missing ${value} from export`);
  }
  assert.doesNotMatch(html,/E1/);
  for(const output of [csv,pinpoint])assert.ok(output.includes('E1'),'missing E1 from detailed export');
  const recoveryRows=parseCSV(pinpoint).records.filter(row=>row.causal_stage==='RECOVERY');
  assert.ok(recoveryRows.length>=4);
  assert.ok(recoveryRows.every(row=>row.recovery_status==='RECOVERED'));
  assert.ok(recoveryRows.some(row=>row.event_id==='E1'&&row.canonical_tag==='GT.TRIP.LATCH'));
  assert.ok(recoveryRows.some(row=>row.disposition==='APPROVED'));
});

test('unresolved recovery evidence is included in the workspace integrity result', () => {
  const out=exportReport({...recovery,evidence_ids:['E1','NOPE']});
  assert.deepEqual(out.reference_integrity,{valid:false,missing:['NOPE']});
  assert.deepEqual(out.recovery_validation.missing_evidence,['NOPE']);
});

test('complete PARTIAL and NOT_RECOVERED records do not report restart conditions as missing', () => {
  const values=[
    {...recovery,status:'PARTIAL',restart_conditions:''},
    {status:'NOT_RECOVERED',operator:'Lee',actions:'정비 인계',restart_conditions:'',evidence_ids:['E1']},
  ];
  for(const value of values){
    const restart=recoveryReportRows(value).find(row=>row.item==='재기동 조건');
    assert.equal(restart.content,'해당 없음');
    assert.doesNotMatch(restart.content,/입력 대기/);
  }
});
