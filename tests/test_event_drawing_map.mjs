import test from 'node:test';
import assert from 'node:assert/strict';
import {EVENT_DRAWING_MAP,resolveEventDrawing} from '../apps/web/lib/eventDrawingMap.mjs';

test('every enabled EVENT registry rule has exactly one Drawing Master location',()=>{
  assert.equal(EVENT_DRAWING_MAP.length,67);
  assert.equal(new Set(EVENT_DRAWING_MAP.map(x=>x.rule_id)).size,67);
  for(const row of EVENT_DRAWING_MAP){
    assert.ok(row.location_id);
    assert.ok(row.view);
    assert.ok(row.lookup_key.includes('::'));
  }
});

test('runtime EVENT can resolve by exact equipment and tag without fuzzy logic matching',()=>{
  const row=resolveEventDrawing({equipment:'LP BFP',tag:'SPEED_PROVEN_LOST'});
  assert.equal(row.rule_id,'LP_FWP_SPEED_LOST');
  assert.equal(row.location_id,'LP_BFP');
  assert.equal(resolveEventDrawing({equipment:'LP BFP',tag:'SPEED_PROVEN'}),null);
});

test('logic is not encoded as a forced one-to-one Drawing Master relation',()=>{
  assert.equal(EVENT_DRAWING_MAP.some(x=>'logic_id' in x),false);
});
