import test from 'node:test';
import assert from 'node:assert/strict';
import {buildClaimReferenceTargets} from './claimReferenceLinks.mjs';

test('cited event links to its logic tag and exact Plant View location',()=>{
  const targets=buildClaimReferenceTargets(
    {related_tags:['vpp52GTClosed'],evidence_ids:['EV-52GT']},
    [{evidence_id:'EV-52GT',equipment:'52GT',tag:'BREAKER_OPEN',source_node:'vpp52GTClosed'}],
  );

  assert.equal(targets.logicTag,'vpp52GTClosed');
  assert.equal(targets.drawingHref,'/drawing?equipment=GT&view=plant&event=vpp52GTClosed');
});

test('ST power evidence links to the 52ST breaker even when its evidence row names another area',()=>{
  const targets=buildClaimReferenceTargets(
    {related_tags:['vppSTGridPowerMW'],evidence_ids:['EV-ST-POWER']},
    [{evidence_id:'EV-ST-POWER',equipment:'HP DRUM',tag:'GRID_POWER',source_node:'vppSTGridPowerMW'}],
  );

  assert.equal(targets.logicTag,'vppSTGridPowerMW');
  assert.equal(targets.drawingHref,'/drawing?equipment=52ST&view=ecms&tag=vppSTGridPowerMW');
});

test('ST breaker event evidence links to 52ST with event semantics',()=>{
  const targets=buildClaimReferenceTargets(
    {related_tags:['vpp52STClosed'],evidence_ids:['EV-ST-BREAKER']},
    [{evidence_id:'EV-ST-BREAKER',equipment:'HP DRUM',tag:'BREAKER_OPEN',source_node:'vpp52STClosed'}],
  );

  assert.equal(targets.logicTag,'vpp52STClosed');
  assert.equal(targets.drawingHref,'/drawing?equipment=52ST&view=ecms&event=vpp52STClosed');
});

test('unmapped evidence does not guess a Plant View location',()=>{
  const targets=buildClaimReferenceTargets(
    {related_tags:['vppUnknownTag'],evidence_ids:['EV-UNKNOWN']},
    [{evidence_id:'EV-UNKNOWN',equipment:'GT-extra',tag:'TRIP_LATCH',source_node:'vppUnknownTag'}],
  );

  assert.equal(targets.logicTag,'vppUnknownTag');
  assert.equal(targets.drawingHref,'');
});
