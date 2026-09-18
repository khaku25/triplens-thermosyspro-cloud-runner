import test from 'node:test';
import assert from 'node:assert/strict';
import {buildDraftRows, REPORT_SECTIONS} from '../apps/web/lib/analysisClient.mjs';

const analysis={
  verification_gate:'HOLD',
  primary_cause:{claim:'외부 GT Trip 입력 후보',status:'CANDIDATE',evidence_ids:['R1'],related_tags:['vppExternalTripCommandNative'],model_time_s:48.4},
  direct_trigger:{claim:'GT Trip Latch 동작',status:'CANDIDATE',evidence_ids:['E1'],related_tags:['vppGTTripLatch'],model_time_s:48.44},
  critical_events:[{claim:'GT Trip Latch',status:'OBSERVED',evidence_ids:['E1'],related_tags:['vppGTTripLatch'],model_time_s:48.44}],
  propagation:[{claim:'52GT 차단기 개방',status:'OBSERVED',evidence_ids:['E3'],related_tags:['vpp52GTClosed'],model_time_s:48.52}],
  causal_chain:[{claim:'외부 입력 → GT Latch → 52GT Open',status:'CANDIDATE',evidence_ids:['R1','E1','E3'],related_tags:['vppExternalTripCommandNative','vppGTTripLatch','vpp52GTClosed'],model_time_s:48.44}],
  counter_evidence:[{claim:'다른 등록 원인은 현재 조회 근거에서 확인되지 않음',status:'OBSERVED',evidence_ids:['E1'],related_tags:['vppGTTripLatch'],model_time_s:48.44}],
  additional_evidence_required:['운전 일지에서 외부 Trip 입력 경위를 확인'],
  review_recommendations:['명령 입력 경위와 보호동작 기록을 담당자가 검토']
};
const envelope={
  events:[
    {event_id:'E1',event_class:'PROTECTION',equipment:'GT',tag:'TRIP_LATCH',source_node:'vppGTTripLatch',model_time_s:48.44,message:'GT Trip Latch'},
    {event_id:'E3',event_class:'PROTECTION',equipment:'52GT',tag:'BREAKER_OPEN',source_node:'vpp52GTClosed',model_time_s:48.52,message:'52GT Breaker Open'}
  ],
  analysis
};

test('report draft uses exactly the nine industrial report sections',()=>{
  const rows=buildDraftRows(envelope);
  assert.deepEqual([...new Set(rows.map(r=>r.section))],REPORT_SECTIONS);
});

test('causal fields are placed inside 발생 원인, not top-level AI labels',()=>{
  const rows=buildDraftRows(envelope);
  const causeRows=rows.filter(r=>r.section==='발생 원인');
  assert.ok(causeRows.some(r=>r.item==='선행 원인'));
  assert.ok(causeRows.some(r=>r.item==='직접 Trip 원인'));
  assert.ok(causeRows.some(r=>r.item.startsWith('파급 과정')));
  assert.ok(causeRows.some(r=>r.item.startsWith('인과관계 요약')));
  for(const forbidden of ['Primary Cause','Direct Trigger','Propagation','Causal Chain','Critical Events']){
    assert.equal(rows.some(r=>r.section===forbidden),false);
  }
});

test('critical events, chronology, uncertainty, recommendations and evidence are placed semantically',()=>{
  const rows=buildDraftRows(envelope);
  assert.ok(rows.some(r=>r.section==='장애 현상' && r.item.startsWith('Critical Event')));
  assert.ok(rows.some(r=>r.section==='시간대별 조치사항' && r.item.startsWith('SOE')));
  assert.ok(rows.some(r=>r.section==='추정 원인 및 미확인 사항' && r.item.startsWith('반대 근거')));
  assert.ok(rows.some(r=>r.section==='추정 원인 및 미확인 사항' && r.item.startsWith('추가 확인')));
  assert.ok(rows.some(r=>r.section==='재발방지 대책 — 검토 권고사항'));
  assert.ok(rows.some(r=>r.section==='증거자료' && r.evidence_ids.includes('E1')));
});
