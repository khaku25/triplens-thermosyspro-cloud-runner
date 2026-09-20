import test from 'node:test';
import assert from 'node:assert/strict';
import {
  analysisDisplayData,
  inputStatus,
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
