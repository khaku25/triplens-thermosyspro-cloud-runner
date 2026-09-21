import test from 'node:test';
import assert from 'node:assert/strict';
import {
  analysisDisplayData,
  compactTimeline,
  displayEventTime,
  incidentMetrics,
  inputStatus,
  operatorSummary,
  selectDetailEvidence,
  summarizeEvidence,
} from '../apps/web/lib/workspacePresentation.mjs';

test('uploaded rows stay hidden until analysis succeeds', () => {
  const uploadedEvents=[{event_id:'SESSION-OLD',tag:'TRIP_LATCH'}];
  const inspected={events:[{event_id:'SESSION-BOOTSTRAP',tag:'TRIP_LATCH'}]};
  assert.deepEqual(analysisDisplayData({result:null,uploadedEvents,inspected}),{events:[],catalog:[]});
});

test('analysis display uses only current successful result data', () => {
  const result={events:[{event_id:'SESSION-CURRENT'}],evidence_catalog:[{evidence_id:'RAW:1:vppGTTripLatch'}]};
  assert.deepEqual(analysisDisplayData({result,uploadedEvents:[{event_id:'SESSION-OLD'}],inspected:{events:[{event_id:'BOOT'}]}}),{
    events:result.events,
    catalog:result.evidence_catalog,
  });
});

test('input status follows the four operator-facing states', () => {
  assert.deepEqual(inputStatus({}),{title:'Dual Log 대기',detail:'EVENT.csv와 RAW.csv를 선택해 주세요.'});
  assert.deepEqual(inputStatus({ready:true,eventRows:21,rawTagCount:693}),{title:'분석 입력 준비 완료',detail:'EVENT.csv 21건 · RAW.csv 693개 태그'});
  assert.deepEqual(inputStatus({ready:true,busy:true}),{title:'사고 기록을 분석하고 있습니다…',detail:''});
  assert.deepEqual(inputStatus({ready:true,complete:true}),{title:'분석 완료',detail:'핵심 원인 및 파급 과정 확인'});
});

test('default evidence summary exposes at most five unique tags', () => {
  const summary=summarizeEvidence(['A','B','A','C','D','E','F'],5);
  assert.deepEqual(summary.visible,['A','B','C','D','E']);
  assert.deepEqual(summary.hidden,['F']);
  assert.equal(summary.hiddenCount,1);
});

test('operator time uses recorded clock time first and keeps model time secondary', () => {
  assert.deepEqual(displayEventTime({
    wall_time_utc:'2026-09-15T14:52:04.213+00:00',
    model_time_s:48.44,
  }),{primary:'14:52:04.213',secondary:'T+48.440 s'});
  assert.deepEqual(displayEventTime({model_time_s:48.52}),{primary:'T+48.520 s',secondary:''});
  assert.deepEqual(displayEventTime({recorded_time:''}),{primary:'시각 미확인',secondary:''});
});

test('operator summaries remove raw field names and source tags from core trip events', () => {
  assert.equal(operatorSummary({
    claim:'외부 트립 명령 태그 vppExternalTripCommandNative가 47.92초와 48.92초 사이에서 인가됨.',
    related_tags:['vppExternalTripCommandNative'],
  },'primary'),'외부 Trip Command 입력');
  assert.equal(operatorSummary({
    claim:'model_time_s 48.44초에 GT TRIP LATCH(vppGTTripLatch) 및 ST TRIP LATCH(vppSTTripLatchPublished) 보호 기능이 1.0(ACTIVE)으로 동시에 작동함.',
    related_tags:['vppGTTripLatch','vppSTTripLatchPublished'],
  },'direct'),'GT·ST Trip Latch 동시 동작');
  assert.equal(operatorSummary({
    claim:'model_time_s 48.520005초에 52GT 차단기(vpp52GTClosed)가 개로(0.0)됨.',
    related_tags:['vpp52GTClosed'],
  },'propagation'),'52GT 차단기 OPEN');
});

test('operator timeline is chronological and exposes only seven primary rows', () => {
  const events=Array.from({length:10},(_,index)=>({
    event_id:`E-${index}`,
    model_time_s:50-index,
    message:`EVENT ${index}`,
  }));
  const timeline=compactTimeline(events,7);
  assert.equal(timeline.visible.length,7);
  assert.equal(timeline.hiddenCount,3);
  assert.deepEqual(timeline.visible.map(item=>item.model_time_s),[41,42,43,44,45,46,47]);
});

test('incident metrics replace empty source counters with accident-centered values', () => {
  const metrics=incidentMetrics([
    {wall_time_utc:'2026-09-15T14:52:04.213+00:00',model_time_s:48.44,event_class:'PROTECTION'},
    {model_time_s:48.52,event_class:'PROTECTION'},
    {model_time_s:48.72,event_class:'ALARM'},
  ]);
  assert.deepEqual(metrics,{firstTime:'14:52:04.213',protection:2,alarms:1});
});

test('claim detail selects only cited evidence and never expands the full tag history', () => {
  const catalog=[
    {evidence_id:'ACTIVE',source_node:'vppSTTripLatchPublished',model_time_s:48.44,value:1},
    {evidence_id:'BASELINE-1',source_node:'vppSTTripLatchPublished',model_time_s:40.92,value:0},
    {evidence_id:'BASELINE-2',source_node:'vppSTTripLatchPublished',model_time_s:41.92,value:0},
  ];
  const claimRows=selectDetailEvidence(catalog,{kind:'claim',evidenceIds:['ACTIVE'],tags:['vppSTTripLatchPublished']});
  assert.deepEqual(claimRows.map(row=>row.evidence_id),['ACTIVE']);
  const tagRows=selectDetailEvidence(catalog,{kind:'tag',value:'vppSTTripLatchPublished'});
  assert.deepEqual(tagRows.map(row=>row.evidence_id),['BASELINE-1','BASELINE-2','ACTIVE']);
});
