import test from 'node:test';
import assert from 'node:assert/strict';
import {
  analysisDisplayData,
  compactTimeline,
  displayAccidentTime,
  displayEventTime,
  deriveOperatorAnalysis,
  groupEvidenceRows,
  incidentMetrics,
  inputStatus,
  operatorSummary,
  normalizeOperatorEvents,
  prioritizeEvidenceRows,
  selectDetailEvidence,
  sortByModelTime,
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

test('accident time uses Model Time first and keeps the recorded clock secondary', () => {
  assert.deepEqual(displayAccidentTime({
    wall_time_utc:'2026-09-15T14:52:04.213+00:00',
    model_time_s:48.44,
  }),{primary:'T+48.440 s',secondary:'14:52:04.213'});
});

test('inactive latch samples are suppressed and paired active latches become one operator event', () => {
  const rows=normalizeOperatorEvents([
    {event_id:'ST-0-A',source_node:'vppSTTripLatchPublished',model_time_s:40.92,value:0,state:'INACTIVE'},
    {event_id:'ST-0-B',source_node:'vppSTTripLatchPublished',model_time_s:41.92,value:false,state:'FALSE'},
    {event_id:'GT-1',source_node:'vppGTTripLatch',model_time_s:48.44,value:1,state:'ACTIVE'},
    {event_id:'ST-1',source_node:'vppSTTripLatchPublished',model_time_s:48.46,value:true,state:'TRUE'},
  ],{sampleIntervalS:0.04});
  assert.equal(rows.length,1);
  assert.equal(rows[0].message,'GT·ST Trip Latch 동시 동작');
  assert.equal(rows[0].state,'ACTIVE');
  assert.deepEqual(rows[0].evidence_ids,['GT-1','ST-1']);
});

test('closed-state zero is presented as breaker OPEN and repeated digital samples collapse', () => {
  const rows=normalizeOperatorEvents([
    {event_id:'GT-CLOSED',source_node:'vpp52GTClosed',model_time_s:47,value:1,state:'CLOSED'},
    {event_id:'GT-OPEN-1',source_node:'vpp52GTClosed',model_time_s:48.52,value:0},
    {event_id:'GT-OPEN-2',source_node:'vpp52GTClosed',model_time_s:48.56,value:0},
  ]);
  assert.equal(rows.length,1);
  assert.equal(rows[0].message,'52GT 차단기 OPEN');
  assert.equal(rows[0].state,'OPEN');
  assert.equal(rows[0].model_time_s,48.52);
  assert.deepEqual(rows[0].evidence_ids,['GT-OPEN-1','GT-OPEN-2']);
});

test('trip command rising edge remains separate from the following latch edge', () => {
  const rows=normalizeOperatorEvents([
    {event_id:'CMD-0',source_node:'vppExternalTripCommandNative',model_time_s:47.92,value:0},
    {event_id:'CMD-1',source_node:'vppExternalTripCommandNative',model_time_s:48.40,value:1},
    {event_id:'CMD-1-REPEAT',source_node:'vppExternalTripCommandNative',model_time_s:48.42,value:1},
    {event_id:'GT-LATCH',source_node:'vppGTTripLatch',model_time_s:48.44,value:1},
  ]);
  assert.deepEqual(rows.map(row=>row.operator_kind),['GT_TRIP_COMMAND','GT_LATCH']);
  assert.equal(rows[0].message,'외부 GT Trip Command 입력');
  assert.deepEqual(rows[0].evidence_ids,['CMD-1','CMD-1-REPEAT']);
  assert.equal(rows[1].message,'GT Trip Latch 동작');
});

test('strict digital rules reject unsupported latch values and incomplete edges', () => {
  const rows=normalizeOperatorEvents([
    {event_id:'BAD-VALUE',source_node:'vppGTTripLatch',model_time_s:40,value:2,state:'ACTIVE'},
    {event_id:'BAD-STATE',source_node:'vppSTTripLatchPublished',model_time_s:41,value:'',state:'TRIPPED'},
    {event_id:'COMMAND-WITHOUT-BASELINE',source_node:'vppExternalTripCommandNative',model_time_s:42,value:1,state:'ACTIVE'},
    {event_id:'OPEN-WITHOUT-CLOSED',source_node:'vpp52GTClosed',model_time_s:43,value:0,state:'OPEN'},
  ]);
  assert.deepEqual(rows,[]);
});

test('operator cause cards follow cited edge evidence instead of AI wording alone', () => {
  const analysis={
    primary_cause:{claim:'외부 Trip Command 입력',evidence_ids:['CMD-0','CMD-1'],related_tags:['vppExternalTripCommandNative']},
    direct_trigger:{claim:'GT·ST Trip Latch 동시 동작',evidence_ids:['GT-1','ST-0'],related_tags:['vppGTTripLatch','vppSTTripLatchPublished']},
  };
  const catalog=[
    {evidence_id:'CMD-0',source_node:'vppExternalTripCommandNative',model_time_s:48.20,value:0},
    {evidence_id:'CMD-1',source_node:'vppExternalTripCommandNative',model_time_s:48.40,value:1},
    {evidence_id:'GT-1',source_node:'vppGTTripLatch',model_time_s:48.44,value:1},
    {evidence_id:'ST-0',source_node:'vppSTTripLatchPublished',model_time_s:48.46,value:0},
  ];
  const derived=deriveOperatorAnalysis(analysis,catalog);
  assert.equal(derived.primaryTitle,'발생 원인');
  assert.equal(derived.analysis.primary_cause.claim,'외부 GT Trip Command 입력');
  assert.equal(derived.analysis.direct_trigger.claim,'GT Trip Latch 동작');

  const noEdge=deriveOperatorAnalysis({...analysis,primary_cause:{...analysis.primary_cause,evidence_ids:['CMD-1']}},catalog.filter(item=>item.evidence_id!=='CMD-0'));
  assert.equal(noEdge.primaryTitle,'사고 개시 신호');
  assert.equal(noEdge.analysis.primary_cause.claim,'외부 Trip Command 신호 관측');
  assert.equal(operatorSummary(noEdge.analysis.primary_cause,'primary'),'외부 Trip Command 신호 관측');

  const inferredFromEvidence=deriveOperatorAnalysis({
    ...analysis,
    primary_cause:{claim:'외부 명령',evidence_ids:['CMD-0','CMD-1'],related_tags:[]},
  },catalog);
  assert.equal(inferredFromEvidence.primaryTitle,'발생 원인');
  assert.equal(operatorSummary(inferredFromEvidence.analysis.primary_cause,'primary'),'외부 Trip Command 입력');

  const unsupportedLatch=deriveOperatorAnalysis({
    ...analysis,
    direct_trigger:{claim:'GT Trip Latch 동작',evidence_ids:['GT-BAD'],related_tags:[]},
  },[...catalog,{evidence_id:'GT-BAD',source_node:'vppGTTripLatch',model_time_s:48.50,value:2,state:'ACTIVE'}]);
  assert.equal(operatorSummary(unsupportedLatch.analysis.direct_trigger,'direct'),'보호동작 신호 관측');
});

test('repeated process samples cannot push a later breaker edge out of the core timeline',()=>{
  const rows=compactTimeline([
    {event_id:'GT-LATCH',source_node:'vppGTTripLatch',model_time_s:48.44,value:1,state:'ACTIVE'},
    ...Array.from({length:8},(_,index)=>({event_id:`FLOW-${index}`,source_node:'vppGTExhaustMassFlowTH',model_time_s:48.45+index/100,value:1500-index*10,state:'LOW',event_class:'ALARM',message:'GT 배기유량 LOW'})),
    {event_id:'52GT-CLOSED',source_node:'vpp52GTClosed',model_time_s:48.50,value:1,state:'CLOSED'},
    {event_id:'52GT-OPEN',source_node:'vpp52GTClosed',model_time_s:48.52,value:0,state:'OPEN'},
  ],7);
  assert.equal(rows.visible.filter(row=>row.source_node==='vppGTExhaustMassFlowTH').length,1);
  assert.ok(rows.visible.some(row=>row.operator_kind==='52GT_OPEN'));
  assert.equal(rows.visible.find(row=>row.source_node==='vppGTExhaustMassFlowTH').evidence_ids.length,8);
});

test('a process alarm that clears and recurs remains two separate edges',()=>{
  const rows=normalizeOperatorEvents([
    {event_id:'LOW-1',source_node:'vppGTExhaustMassFlowTH',model_time_s:48.7,value:1500,state:'LOW'},
    {event_id:'LOW-REPEAT',source_node:'vppGTExhaustMassFlowTH',model_time_s:48.8,value:1400,state:'LOW'},
    {event_id:'NORMAL',source_node:'vppGTExhaustMassFlowTH',model_time_s:49.0,value:1900,state:'NORMAL'},
    {event_id:'LOW-2',source_node:'vppGTExhaustMassFlowTH',model_time_s:50.0,value:1300,state:'LOW'},
  ]);
  assert.deepEqual(rows.map(row=>row.evidence_ids),[['LOW-1','LOW-REPEAT'],['LOW-2']]);
});

test('each GT and ST latch cycle is paired independently',()=>{
  const rows=normalizeOperatorEvents([
    {event_id:'GT-1',source_node:'vppGTTripLatch',model_time_s:48.44,value:1},
    {event_id:'ST-1',source_node:'vppSTTripLatchPublished',model_time_s:48.46,value:1},
    {event_id:'GT-RESET',source_node:'vppGTTripLatch',model_time_s:49.00,value:0},
    {event_id:'ST-RESET',source_node:'vppSTTripLatchPublished',model_time_s:49.00,value:0},
    {event_id:'GT-2',source_node:'vppGTTripLatch',model_time_s:50.00,value:1},
    {event_id:'ST-2',source_node:'vppSTTripLatchPublished',model_time_s:50.02,value:1},
  ],{sampleIntervalS:0.04});
  assert.deepEqual(rows.map(row=>row.operator_kind),['GT_ST_LATCH','GT_ST_LATCH']);
  assert.deepEqual(rows.map(row=>row.evidence_ids),[['GT-1','ST-1'],['GT-2','ST-2']]);
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

test('operator summaries never infer an alarm state from a tag name alone', () => {
  assert.equal(operatorSummary({
    claim:'52GT 차단기 정상 투입 상태',
    related_tags:['vpp52GTClosed'],
    value:1,
    state:'CLOSED',
  },'propagation'),'52GT 차단기 정상 투입 상태');
  assert.equal(operatorSummary({
    claim:'GT 배기온도 정상 범위',
    related_tags:['vppGTExhaustTemperatureK'],
    value:820,
    state:'NORMAL',
  },'propagation'),'GT 배기온도 정상 범위');
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

test('detailed evidence groups unchanged samples and remains ordered by Model Time',()=>{
  const rows=groupEvidenceRows([
    {evidence_id:'FLOW',source_node:'vppFlow',model_time_s:49,value:10,state:'LOW'},
    {evidence_id:'OPEN-2',source_node:'vpp52GTClosed',model_time_s:48.56,value:0,state:'OPEN'},
    {evidence_id:'OPEN-1',source_node:'vpp52GTClosed',model_time_s:48.52,value:0,state:'OPEN'},
  ]);
  assert.deepEqual(rows.map(row=>row.model_time_s),[48.52,49]);
  assert.equal(rows[0].repeat_count,2);
  assert.deepEqual(rows[0].evidence_ids,['OPEN-1','OPEN-2']);
});

test('detailed evidence groups changing analog values while the alarm state is unchanged',()=>{
  const rows=groupEvidenceRows(Array.from({length:250},(_,index)=>({
    evidence_id:`FLOW-${index}`,
    source_node:'vppGTExhaustMassFlowTH',
    model_time_s:48+index/100,
    value:1500-index,
  })));
  assert.equal(rows.length,1);
  assert.equal(rows[0].repeat_count,250);
  assert.equal(rows[0].evidence_ids.length,250);
});

test('state-less unknown binary evidence keeps value changes visible',()=>{
  const rows=groupEvidenceRows([
    {evidence_id:'D-0',source_node:'vppUnknownDigital',model_time_s:1,value:0},
    {evidence_id:'D-1',source_node:'vppUnknownDigital',model_time_s:2,value:1},
    {evidence_id:'D-1-R',source_node:'vppUnknownDigital',model_time_s:3,value:1},
  ]);
  assert.deepEqual(rows.map(row=>row.value),[0,1]);
  assert.deepEqual(rows[1].evidence_ids,['D-1','D-1-R']);
});

test('selected evidence remains rendered without breaking Model Time order',()=>{
  const rows=Array.from({length:260},(_,index)=>({evidence_id:`E-${index}`,model_time_s:index}));
  const visible=prioritizeEvidenceRows(rows,{evidenceIds:['E-230']},200);
  assert.equal(visible.length,200);
  assert.ok(visible.some(row=>row.evidence_id==='E-230'));
  assert.deepEqual(visible.map(row=>row.model_time_s),[...visible.map(row=>row.model_time_s)].sort((a,b)=>a-b));
});

test('analysis lists keep unknown Model Time after known events',()=>{
  const rows=sortByModelTime([{claim:'UNKNOWN',model_time_s:null},{claim:'LATE',model_time_s:20},{claim:'EARLY',model_time_s:10}]);
  assert.deepEqual(rows.map(row=>row.claim),['EARLY','LATE','UNKNOWN']);
});
