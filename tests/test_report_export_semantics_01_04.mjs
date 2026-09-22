import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';

const require=createRequire(import.meta.url);
const exporter=require('../webapp/triplens_report_export.js');

const baseReport={
  run_id:'RUN-SEMANTIC-REGRESSION',
  verification_gate:'PASS',
  metadata:{event_file:'EVENT.csv',raw_file:'RAW.csv'},
  incident_summary:'설비 보호동작과 후속 공정 변화가 관측되었습니다.',
  critical_events:[{
    claim:'48.44초에 GT 트립 래치가 동작했습니다.',
    status:'OBSERVED',
    evidence_ids:['EV-TRIP'],
    related_tags:['vppGTTripLatch'],
    model_time_s:48.44,
    wall_time_utc:'2026-09-15T14:52:04.212+00:00',
  }],
  primary_cause:{claim:'외부 트립 입력',status:'CANDIDATE',evidence_ids:['RAW-CMD']},
  direct_trigger:{claim:'GT 트립 래치 동작',status:'OBSERVED',evidence_ids:['EV-TRIP'],related_tags:['vppGTTripLatch']},
  propagation:[],
  chronological_events:[],
  report_rows:[],
};

function propagationText(html){
  return html.match(/<b>파급 결과 \(Propagation\)<\/b><div><strong>(.*?)<\/strong>/)?.[1]||'';
}

test('multi-signal GT propagation keeps flow and temperature meaning without duplicate shorthand',()=>{
  const html=exporter.buildReportHtml({
    ...baseReport,
    propagation:[
      {
        claim:'터빈 트립 직후 48.72s에 GT 배기가스 유량 저하(FLOW_LOW, 1501.18 t/h) 경보가 발생하였으며, 48.92s에 배기가스 온도 저하 경보(667.03 K)가 발생하였습니다.',
        status:'OBSERVED',evidence_ids:['EV-FLOW','EV-TEMP'],
        related_tags:['GT EXHAUST::FLOW_LOW','vppGTExhaustMassFlowTH','GT EXHAUST::TEMPERATURE_LOW','vppGTExhaustTemperatureK'],
      },
      {
        claim:'49.12s ~ 50.36s 구간에서 고압(HP), 중압(IP), 저압(LP) 터빈의 증기 유량 저하 및 극저하(FLOW_LOW, FLOW_LOW_LOW) 경보가 순차적으로 발생하였습니다.',
        status:'OBSERVED',evidence_ids:['EV-HP','EV-IP','EV-LP'],
        related_tags:['vppHPTurbineSteamFlowTH','vppIPTurbineSteamFlowTH','vppLPTurbineSteamFlowTH','vppGTExhaustMassFlowTH'],
      },
    ],
  });
  const text=propagationText(html);
  assert.match(text,/GT 배기가스 유량 저하/);
  assert.match(text,/배기가스 온도 저하/);
  assert.match(text,/고압\(HP\).*중압\(IP\).*저압\(LP\)/);
  assert.doesNotMatch(text,/GT 배기유량 LOW → GT 배기유량 LOW/);
});

test('multi-train steam-flow propagation retains both LP and IP observations',()=>{
  const html=exporter.buildReportHtml({
    ...baseReport,
    propagation:[{
      claim:'저압 터빈 증기 유량(vppLPTurbineSteamFlowTH) 및 중압 터빈 증기 유량(vppIPTurbineSteamFlowTH)이 감소하면서 49.6초부터 50.52초 사이에 저유량 및 극저유량 알람이 순차적으로 발생했습니다.',
      status:'OBSERVED',evidence_ids:['EV-LP','EV-IP'],
      related_tags:['vppLPTurbineSteamFlowTH','vppIPTurbineSteamFlowTH'],
    }],
  });
  const text=propagationText(html);
  assert.match(text,/저압 터빈 증기 유량/);
  assert.match(text,/중압 터빈 증기 유량/);
  assert.doesNotMatch(text,/^IP 터빈 증기유량 LOW$/);
});

test('sample uncertainty remains a grammatical second clause',()=>{
  const claim='외부 ST 트립 명령(vppExternalSTTripCommandNative)이 47.92초와 49.0초 사이 표본 구간에서 0.0에서 1.0으로 인가되었습니다. 표본 간격에 따른 시간적 불확실성이 존재합니다.';
  const html=exporter.buildReportHtml({
    ...baseReport,
    incident_summary:claim,
    critical_events:[{claim,status:'CANDIDATE',evidence_ids:['RAW:21:cmd','RAW:22:cmd'],related_tags:['vppExternalSTTripCommandNative'],time_interval_s:[47.92,49]}],
  });
  const summary=html.match(/<tr><th>장애 요약<\/th><td>(.*?)<\/td>/)?.[1]||'';
  assert.doesNotMatch(summary,/인가\s+표본 간격/);
  assert.match(summary,/표본 간격에 따른 시간적 불확실성/);
});

test('tag removal preserves Korean demonstratives and leaves no dangling citation punctuation',()=>{
  const html=exporter.buildReportHtml({
    ...baseReport,
    incident_summary:'31.84초에 IP BFP 트립 이벤트가 미등록 관측 상태였으며 이 시점의 실제 RAW 신호 전이로 이어지지 않았습니다.',
    critical_events:[{
      claim:'31.84초에 IP BFP 트립 이벤트가 미등록 관측 상태였으며 이 시점의 실제 RAW 신호 전이로 이어지지 않았습니다.',
      status:'OBSERVED',evidence_ids:['EV-IP'],related_tags:['IP_BFP_TRIP_PB'],model_time_s:31.84,
      wall_time_utc:'2026-09-15T15:25:47.072+00:00',
    }],
    primary_cause:{
      claim:'IP BFP 수동 트립 신호(vppIPFWPTripPushbuttonNative)가 48.12초(RAW:21:vppIPFWPTripPushbuttonNative, 0.0)와 49.24초(RAW:22:vppIPFWPTripPushbuttonNative, 1.0) 사이에 인가되었습니다.',
      status:'CANDIDATE',evidence_ids:['RAW:21:vppIPFWPTripPushbuttonNative','RAW:22:vppIPFWPTripPushbuttonNative'],
      related_tags:['vppIPFWPTripPushbuttonNative'],
    },
    propagation:[
      {claim:'48.96초에 IP BFP 운전 상태 상실(EV-4, RUNNING_LOST, vppIPFWPRunning)이 감지되었습니다.',status:'OBSERVED',evidence_ids:['EV-4'],related_tags:['RUNNING_LOST','vppIPFWPRunning']},
      {claim:'50.28초에 IP 급수 유량 저하(EV-6, FLOW_LOW, vppIPFWPMassFlowTH, 22.02 t/h)가 발생했습니다.',status:'OBSERVED',evidence_ids:['EV-6'],related_tags:['FLOW_LOW','vppIPFWPMassFlowTH']},
      {claim:'51.21초에 역지밸브 폐쇄(EV-7, CHECK_VALVE_CLOSED, vppIPFWPCheckValveOpen)가 발생했습니다.',status:'OBSERVED',evidence_ids:['EV-7'],related_tags:['CHECK_VALVE_CLOSED','vppIPFWPCheckValveOpen']},
    ],
  });
  const firstEvent=html.match(/<tr><th>최초 Event<\/th><td>(.*?)<\/td>/)?.[1]||'';
  const primary=html.match(/<b>선행 원인 \(Primary Cause\)<\/b><div><strong>(.*?)<\/strong>/)?.[1]||'';
  const propagation=propagationText(html);
  assert.match(firstEvent,/상태였으며 이 시점/);
  assert.doesNotMatch(firstEvent,/상태였으며가 시점/);
  assert.doesNotMatch(primary,/RAW:\d+:/);
  assert.doesNotMatch(propagation,/,\s*\)|,,|\(\s*,/);
  assert.match(propagation,/\(EV-4, RUNNING_LOST\)/);
  assert.match(propagation,/\(EV-6, FLOW_LOW, 22\.02 t\/h\)/);
  assert.match(propagation,/\(EV-7, CHECK_VALVE_CLOSED\)/);
});

test('technical drum signals keep operator labels when their values follow the removed tags',()=>{
  const claim='47.48초에서 48.48초 사이에 vppIPDrumInventoryFaultFlowCommand.signal(-250.0) 및 vppIPDrumInventoryDisturbanceMassFlowTH(-900.0 t/h)로 나타나는 IP 드럼 외란 유량이 시작됨.';
  const html=exporter.buildReportHtml({
    ...baseReport,
    incident_summary:claim,
    critical_events:[{
      claim,status:'CANDIDATE',time_interval_s:[47.48,48.48],
      evidence_ids:['RAW:20:command','RAW:21:flow'],
      related_tags:['vppIPDrumInventoryFaultFlowCommand.signal','vppIPDrumInventoryDisturbanceMassFlowTH'],
    }],
  });
  const summary=html.match(/<tr><th>장애 요약<\/th><td>(.*?)<\/td>/)?.[1]||'';
  assert.match(summary,/사이에 IP 드럼 외란 유입 지령\(-250\.0\) 및 IP 드럼 외란 유량\(-900\.0 t\/h\)으로/);
  assert.doesNotMatch(summary,/사이에\(|및\(|vppIPDrum/);
});

test('Blind Test 2 scenario 08 keeps the tagged noun after a conjunction',()=>{
  const claim='48.04초와 49.04초 사이에 vppHPDrumInventoryFaultFlowCommand.signal 및 vppHPDrumInventoryDisturbanceMassFlowTH의 급증(900 t/h 교란 유입)이 발생하여 HP 드럼 내부 수위가 급격히 상승하고 압력이 증가하여 급수 체크밸브가 차단된 것이 직접적인 근원 원인으로 추정됩니다.';
  const html=exporter.buildReportHtml({
    ...baseReport,
    primary_cause:{
      claim,status:'CANDIDATE',
      evidence_ids:['RAW:21:vppHPDrumInventoryFaultFlowCommand.signal','RAW:22:vppHPDrumInventoryDisturbanceMassFlowTH'],
      related_tags:['vppHPDrumInventoryFaultFlowCommand.signal','vppHPDrumInventoryDisturbanceMassFlowTH'],
    },
  });
  const primary=html.match(/<b>선행 원인 \(Primary Cause\)<\/b><div><strong>(.*?)<\/strong>/)?.[1]||'';
  assert.match(primary,/HP 드럼 외란 유입 지령 및 HP 드럼 외란 유량의 급증/);
  assert.doesNotMatch(primary,/및의|vppHPDrum/);
});
