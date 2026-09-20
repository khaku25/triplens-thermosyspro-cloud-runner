import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const resolver = require('../webapp/event_tag_resolver.js');

const rows = [
  { rule_id:'GT_TRIP_LATCH', equipment:'GT', event_tag:'TRIP_LATCH', source_node:'vppGTTripLatch', tag_id:'GT.TRIP.LATCH', event_lookup_key:'GT::TRIP_LATCH', mapping_method:'SPECIAL_CANONICAL' },
  { rule_id:'ST_TRIP_LATCH', equipment:'ST', event_tag:'TRIP_LATCH', source_node:'vppSTTripLatchPublished', tag_id:'ST.TRIP.LATCH', event_lookup_key:'ST::TRIP_LATCH', mapping_method:'SPECIAL_CANONICAL' },
  { rule_id:'HP_STEAM_FLOW_LOW_LOW', equipment:'HP TURBINE', event_tag:'FLOW_LOW_LOW', source_node:'vppHPTurbineSteamFlowTH', tag_id:'HRSG.HP.STEAM.FLOW.LL', event_lookup_key:'HP TURBINE::FLOW_LOW_LOW', mapping_method:'SOURCE_ALIAS_PLUS_EVENT_SEMANTIC' },
];
const index = resolver.buildEventTagIndex(rows);

test('generic TRIP_LATCH is disambiguated by equipment', () => {
  const gt = resolver.describeResolvedEvent({equipment:'GT', tag:'TRIP_LATCH'}, index);
  const st = resolver.describeResolvedEvent({equipment:'ST', tag:'TRIP_LATCH'}, index);
  assert.equal(gt.canonical_tag, 'GT.TRIP.LATCH');
  assert.equal(st.canonical_tag, 'ST.TRIP.LATCH');
  assert.equal(gt.mapping_status, 'EQUIPMENT_TAG_EXACT');
});

test('explicit GT latch aliases resolve to the GT latch and never to trip command', () => {
  for (const alias of ['GT.TRIP.LATCH','GT_TRIP_LATCH','vppGTTripLatch']) {
    const result = resolver.describeResolvedEvent({tag:alias}, index);
    assert.equal(result.canonical_tag, 'GT.TRIP.LATCH', alias);
    assert.equal(result.source_node, 'vppGTTripLatch', alias);
  }
});

test('ST published latch alias resolves to the ST latch', () => {
  const result = resolver.describeResolvedEvent({tag:'vppSTTripLatchPublished'}, index);
  assert.equal(result.canonical_tag, 'ST.TRIP.LATCH');
  assert.equal(result.source_node, 'vppSTTripLatchPublished');
});

test('trip command is not treated as a trip latch alias', () => {
  const result = resolver.describeResolvedEvent({equipment:'GT', tag:'GT_TRIP_COMMAND'}, index);
  assert.equal(result.mapping_status, 'UNMAPPED_EVENT_TAG');
  assert.equal(result.canonical_tag, undefined);
});

test('HP turbine FLOW_LOW_LOW resolves without guessing from tag name', () => {
  const result = resolver.describeResolvedEvent({equipment:'HP TURBINE', tag:'FLOW_LOW_LOW'}, index);
  assert.equal(result.canonical_tag, 'HRSG.HP.STEAM.FLOW.LL');
  assert.equal(result.mapping_method, 'SOURCE_ALIAS_PLUS_EVENT_SEMANTIC');
});

test('rule id takes precedence over generic event tag', () => {
  const result = resolver.describeResolvedEvent({rule_id:'ST_TRIP_LATCH', equipment:'GT', tag:'TRIP_LATCH'}, index);
  assert.equal(result.canonical_tag, 'ST.TRIP.LATCH');
  assert.equal(result.mapping_status, 'EVENT_RULE_ID');
});

test('unknown event is explicit rather than fabricated', () => {
  const result = resolver.describeResolvedEvent({equipment:'X', tag:'SOMETHING_NEW'}, index);
  assert.equal(result.mapping_status, 'UNMAPPED_EVENT_TAG');
  assert.equal(result.canonical_tag, undefined);
});
