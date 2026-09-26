import test from 'node:test';
import assert from 'node:assert/strict';
import {buildClaimReferenceTargets} from './claimReferenceLinks.mjs';
import {EVENT_DRAWING_MAP} from './eventDrawingMap.mjs';
import {resolveEquipmentDrawing} from './equipmentDrawingMaster.mjs';
import {resolvePlantFocus} from './plantDrawingFocus.mjs';

test('cited GT breaker event links to its exact ECMS symbol',()=>{
  const targets=buildClaimReferenceTargets(
    {related_tags:['vpp52GTClosed'],evidence_ids:['EV-52GT']},
    [{evidence_id:'EV-52GT',equipment:'52GT',tag:'BREAKER_OPEN',source_node:'vpp52GTClosed'}],
  );

  assert.equal(targets.logicTag,'vpp52GTClosed');
  assert.deepEqual(targets.drawingLinks,[{
    equipment:'52GT',
    href:'/drawing?equipment=52GT&view=vpp&event=vpp52GTClosed',
  }]);
});

test('ST power evidence links to the 52ST breaker even when its evidence row names another area',()=>{
  const targets=buildClaimReferenceTargets(
    {related_tags:['vppSTGridPowerMW'],evidence_ids:['EV-ST-POWER']},
    [{evidence_id:'EV-ST-POWER',equipment:'HP DRUM',tag:'GRID_POWER',source_node:'vppSTGridPowerMW'}],
  );

  assert.equal(targets.logicTag,'vppSTGridPowerMW');
  assert.deepEqual(targets.drawingLinks,[{
    equipment:'52ST',
    href:'/drawing?equipment=52ST&view=ecms&tag=vppSTGridPowerMW',
  }]);
});

test('ST breaker event evidence links to 52ST with event semantics',()=>{
  const targets=buildClaimReferenceTargets(
    {related_tags:['vpp52STClosed'],evidence_ids:['EV-ST-BREAKER']},
    [{evidence_id:'EV-ST-BREAKER',equipment:'HP DRUM',tag:'BREAKER_OPEN',source_node:'vpp52STClosed'}],
  );

  assert.equal(targets.logicTag,'vpp52STClosed');
  assert.deepEqual(targets.drawingLinks,[{
    equipment:'52ST',
    href:'/drawing?equipment=52ST&view=ecms&event=vpp52STClosed',
  }]);
});

test('simultaneous GT and ST latches expose both corresponding drawings',()=>{
  const targets=buildClaimReferenceTargets(
    {related_tags:['vppGTTripLatch','vppSTTripLatchPublished'],evidence_ids:['EV-GT-LATCH','EV-ST-LATCH']},
    [
      {evidence_id:'EV-GT-LATCH',rule_id:'GT_TRIP_LATCH',equipment:'GT',tag:'TRIP_LATCH',source_node:'vppGTTripLatch'},
      {evidence_id:'EV-ST-LATCH',rule_id:'ST_TRIP_LATCH',equipment:'ST',tag:'TRIP_LATCH',source_node:'vppSTTripLatchPublished'},
    ],
  );

  assert.deepEqual(targets.drawingLinks,[
    {equipment:'GT',href:'/drawing?equipment=GT&view=plant&event=vppGTTripLatch'},
    {equipment:'52ST',href:'/drawing?equipment=52ST&view=ecms&event=vppSTTripLatchPublished'},
  ]);
});

test('ECMS-only breakers open their exact SLD and generator-breaker symbols',()=>{
  const auxiliary=buildClaimReferenceTargets(
    {related_tags:['vppECMSCBInAClosed'],evidence_ids:['EV-CB-IN-A']},
    [{evidence_id:'EV-CB-IN-A',rule_id:'CB_IN_A_OPEN',equipment:'CB-IN-A',tag:'BREAKER_OPEN',source_node:'vppECMSCBInAClosed'}],
  );
  const gtBreaker=buildClaimReferenceTargets(
    {related_tags:['vpp52GTClosed'],evidence_ids:['EV-52GT']},
    [{evidence_id:'EV-52GT',rule_id:'GT_BREAKER_OPEN',equipment:'52GT',tag:'BREAKER_OPEN',source_node:'vpp52GTClosed'}],
  );

  assert.deepEqual(auxiliary.drawingLinks,[{equipment:'CB-IN-A',href:'/drawing?equipment=CB-IN-A&view=sld&event=vppECMSCBInAClosed'}]);
  assert.deepEqual(gtBreaker.drawingLinks,[{equipment:'52GT',href:'/drawing?equipment=52GT&view=vpp&event=vpp52GTClosed'}]);
});

test('all 67 registered EVENT identities produce a drawing destination',()=>{
  assert.equal(EVENT_DRAWING_MAP.length,67);
  for(const event of EVENT_DRAWING_MAP){
    const targets=buildClaimReferenceTargets(
      {related_tags:[event.source_node],evidence_ids:[event.rule_id]},
      [{evidence_id:event.rule_id,...event}],
    );
    assert.equal(targets.drawingLinks.length,1,event.rule_id+' has no drawing link');
    const url=new URL(targets.drawingLinks[0].href,'https://triplens.test');
    const equipment=resolveEquipmentDrawing(event.equipment);
    const plant=resolvePlantFocus(equipment);
    if(event.source_node?.startsWith('vppST')||event.source_node?.includes('52ST')){
      assert.equal(url.searchParams.get('equipment'),'52ST',event.rule_id);
      assert.equal(url.searchParams.get('view'),'ecms',event.rule_id);
    }else if(equipment?.equipment_type==='BREAKER'||equipment?.equipment_type==='BUS'){
      assert.equal(url.searchParams.get('equipment'),equipment.event_equipment,event.rule_id);
      assert.equal(url.searchParams.get('view'),equipment.ecms_page==='ECMS_6P9KV'?'sld':'vpp',event.rule_id);
    }else if(plant){
      assert.equal(url.searchParams.get('equipment'),equipment.event_equipment,event.rule_id);
      assert.equal(url.searchParams.get('view'),'plant',event.rule_id);
    }
  }
});

test('unmapped evidence does not guess a Plant View location',()=>{
  const targets=buildClaimReferenceTargets(
    {related_tags:['vppUnknownTag'],evidence_ids:['EV-UNKNOWN']},
    [{evidence_id:'EV-UNKNOWN',equipment:'GT-extra',tag:'TRIP_LATCH',source_node:'vppUnknownTag'}],
  );

  assert.equal(targets.logicTag,'vppUnknownTag');
  assert.deepEqual(targets.drawingLinks,[]);
});
