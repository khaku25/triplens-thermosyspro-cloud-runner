import test from 'node:test';
import assert from 'node:assert/strict';
import core from '../webapp/triplens_core.js';

test('parseCsv handles quoted commas and escaped quotes', () => {
  const rows = core.parseCsv('time,equipment,message\n1.2,GT,"Trip, latch"\n1.3,ST,"A ""quoted"" alarm"');
  assert.equal(rows.length, 2);
  assert.equal(rows[0].message, 'Trip, latch');
  assert.equal(rows[1].message, 'A "quoted" alarm');
});

test('buildEventMap deterministically maps latch and HP flow LL rules', () => {
  const map = core.buildEventMap([
    {rule_id:'GT_TRIP_LATCH', equipment:'GT', tag:'TRIP_LATCH', source_node:'vppGTTripLatch', enabled:'1'},
    {rule_id:'ST_TRIP_LATCH', equipment:'ST', tag:'TRIP_LATCH', source_node:'vppSTTripLatchPublished', enabled:'1'},
    {rule_id:'HP_STEAM_FLOW_LOW_LOW', equipment:'HP TURBINE', tag:'FLOW_LOW_LOW', source_node:'vppHPTurbineSteamFlowTH', enabled:'1'}
  ]);
  assert.equal(core.resolveEventTag({equipment:'GT', tag:'TRIP_LATCH'}, map).canonical_tag, 'GT.TRIP.LATCH');
  assert.equal(core.resolveEventTag({equipment:'ST', tag:'TRIP_LATCH'}, map).canonical_tag, 'ST.TRIP.LATCH');
  assert.equal(core.resolveEventTag({equipment:'HP TURBINE', tag:'FLOW_LOW_LOW'}, map).canonical_tag, 'HRSG.HP.STEAM.FLOW.LL');
});

test('resolveEventTag returns explicit unmapped status without fuzzy matching', () => {
  const map = core.buildEventMap([]);
  const resolved = core.resolveEventTag({equipment:'HP TURBINE', tag:'FLOW_LOW_LOWISH'}, map);
  assert.equal(resolved.mapping_status, 'UNMAPPED_EVENT_TAG');
  assert.equal(resolved.canonical_tag, '');
});

test('analyzeDualLog builds deterministic sections and warns when RAW ends before EVENT', () => {
  const registry = [
    {rule_id:'GT_TRIP_LATCH', equipment:'GT', tag:'TRIP_LATCH', source_node:'vppGTTripLatch', priority:'CRITICAL', enabled:'1'},
    {rule_id:'GT_BREAKER_OPEN', equipment:'52GT', tag:'BREAKER_OPEN', source_node:'vpp52GTClosed', priority:'HIGH', enabled:'1'}
  ];
  const map = core.buildEventMap(registry);
  const events = [
    {time:'30.0', rule_id:'GT_TRIP_LATCH', equipment:'GT', tag:'TRIP_LATCH', state:'ACTIVE', value:'1'},
    {time:'30.2', rule_id:'GT_BREAKER_OPEN', equipment:'52GT', tag:'BREAKER_OPEN', state:'ACTIVE', value:'0'}
  ];
  const raw = [{time:'0'},{time:'30.1'}];
  const report = core.analyzeDualLog(events, raw, map, {run_id:'R-1', event_filename:'EVENT.csv', raw_filename:'RAW.csv'});
  assert.equal(report.run_id, 'R-1');
  assert.equal(report.primary_cause.canonical_tag, 'GT.TRIP.LATCH');
  assert.equal(report.direct_trigger.canonical_tag, 'GT.TRIP.LATCH');
  assert.equal(report.critical_events.length, 2);
  assert.equal(report.causal_chain.length, 1);
  assert.equal(report.raw_coverage.status, 'INSUFFICIENT_POST_EVENT_WINDOW');
});

test('buildGeminiPayload drops forbidden metadata keys', () => {
  const report = {
    run_id:'R-2',
    event_evidence:[{event_id:'E1', scenario:'secret', expected_root_cause:'answer', equipment:'GT', canonical_tag:'GT.TRIP.LATCH'}],
    raw_evidence:[{time:30, tag:'GT.SPEED', value:0, fault_injection:'trip'}],
    logic_context:[],
    incident_summary:{status:'DETERMINISTIC'}
  };
  const payload = core.buildGeminiPayload(report);
  const text = JSON.stringify(payload).toLowerCase();
  assert.equal(text.includes('scenario'), false);
  assert.equal(text.includes('expected_root_cause'), false);
  assert.equal(text.includes('fault_injection'), false);
  assert.equal(payload.event_evidence[0].canonical_tag, 'GT.TRIP.LATCH');
});
