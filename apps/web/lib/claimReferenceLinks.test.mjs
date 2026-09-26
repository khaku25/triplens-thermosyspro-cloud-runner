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

test('unmapped evidence does not guess a Plant View location',()=>{
  const targets=buildClaimReferenceTargets(
    {related_tags:['vppUnknownTag'],evidence_ids:['EV-UNKNOWN']},
    [{evidence_id:'EV-UNKNOWN',equipment:'GT-extra',tag:'TRIP_LATCH',source_node:'vppUnknownTag'}],
  );

  assert.equal(targets.logicTag,'vppUnknownTag');
  assert.equal(targets.drawingHref,'');
});
