import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {
  DEVICE_TEST_CASES,
  evaluateDeviceCases,
  buildEvidenceLogicTargets,
  buildExportReport,
} from '../apps/web/lib/integrationTestbench.mjs';

const index = JSON.parse(fs.readFileSync(new URL('../apps/web/public/logic-assets/logic_diagram_index.json', import.meta.url)));

test('device testbench covers turbine, breaker, feedwater pump and drum units', () => {
  const equipment = new Set(DEVICE_TEST_CASES.map(item => item.equipment));
  for (const required of ['GT','ST','52GT','52ST','HP FWP','IP FWP','LP FWP','HP DRUM','IP DRUM','LP DRUM']) {
    assert.ok(equipment.has(required), `missing ${required}`);
  }
});

test('every device fixture resolves tag, expected rule and diagram page', () => {
  const results = evaluateDeviceCases(index, DEVICE_TEST_CASES);
  assert.equal(results.length, DEVICE_TEST_CASES.length);
  assert.deepEqual(results.filter(item => item.status !== 'PASS'), []);
});

test('evidence detail exposes one logic-library entry with grouped registered rules', () => {
  const targets = buildEvidenceLogicTargets({
    source_node:'vppGTTripLatch',
    tag:'TRIP_LATCH',
    logic_ids:['PROT-GT-LATCH','SEQ-52GT-OPEN'],
  });
  assert.deepEqual(targets.tags, ['vppGTTripLatch']);
  assert.deepEqual(targets.rules, ['PROT-GT-LATCH','SEQ-52GT-OPEN']);
  assert.deepEqual(targets.entry, {tag:'vppGTTripLatch',ruleCount:2});
});

test('current analysis state is adapted to report v2 without losing edits or evidence', () => {
  const analysis={
    verification_gate:'HOLD',
    critical_events:[{claim:'GT latch',status:'OBSERVED',evidence_ids:['E-1'],related_tags:['vppGTTripLatch'],model_time_s:48.44}],
    primary_cause:{claim:'external command candidate',status:'CANDIDATE',evidence_ids:['RAW:1:vppExternalTripCommandNative'],related_tags:['vppExternalTripCommandNative'],model_time_s:48.4},
    direct_trigger:{claim:'GT latch',status:'CANDIDATE',evidence_ids:['E-1'],related_tags:['vppGTTripLatch'],model_time_s:48.44},
    propagation:[],causal_chain:[],counter_evidence:[],additional_evidence_required:[],review_recommendations:[],
  };
  const events=[{event_id:'E-1',evidence_id:'E-1',model_time_s:48.44,wall_time_utc:'2026-09-15T14:52:04.213+00:00',equipment:'GT',message:'GT TRIP LATCH ACTIVE',source_node:'vppGTTripLatch',tag:'TRIP_LATCH',source:'DCS'}];
  const catalog=[{evidence_id:'E-1',source_kind:'EVENT',model_time_s:48.44,source_node:'vppGTTripLatch',tag:'TRIP_LATCH',canonical_tag:'GT.TRIP.LATCH',logic_ids:['PROT-GT-LATCH'],state:'ACTIVE'}];
  const reportRows=[{section:'개요',item:'장애 요약',content:'담당자 편집 문구',status:'OBSERVED',evidence_ids:'E-1',tags:'vppGTTripLatch',time:'48.440 s',note:'검토 중'}];
  const out=buildExportReport({result:{run_id:'RUN-1',data_digest:'abc'},analysis,events,catalog,reportRows,eventFileName:'EVENT.csv',rawFileName:'RAW.csv'});
  assert.equal(out.run_id,'RUN-1');
  assert.equal(out.report_rows[0].content,'담당자 편집 문구');
  assert.equal(out.chronological_events[0].evidence_ids[0],'E-1');
  assert.equal(out.chronological_events[0].wall_time_utc,'2026-09-15T14:52:04.213+00:00');
  assert.equal(out.chronological_events[0].equipment,'GT');
  assert.ok(out.sections.some(section=>section.id==='direct_trigger'));
});
