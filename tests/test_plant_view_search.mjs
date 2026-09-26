import test from 'node:test';
import assert from 'node:assert/strict';
import {EQUIPMENT_DRAWING_MASTER} from '../apps/web/lib/equipmentDrawingMaster.mjs';
import {plantDrawingHref,searchPlantViewEquipment} from '../apps/web/lib/plantViewSearch.mjs';

test('Plant View equipment search uses Equipment Master names and aliases',()=>{
  const matches=searchPlantViewEquipment(EQUIPMENT_DRAWING_MASTER,'  st breaker ');
  assert.deepEqual(matches.map(row=>row.equipment_id),['52ST']);
  assert.ok(searchPlantViewEquipment(EQUIPMENT_DRAWING_MASTER,'HP BFP').some(row=>row.event_equipment==='HP BFP'));
  assert.deepEqual(searchPlantViewEquipment(EQUIPMENT_DRAWING_MASTER,'no such equipment'),[]);
});

test('Plant View search opens the exact mapped equipment destination',()=>{
  const gt=EQUIPMENT_DRAWING_MASTER.find(row=>row.equipment_id==='GT');
  const stBreaker=EQUIPMENT_DRAWING_MASTER.find(row=>row.equipment_id==='52ST');
  const hpBfp=EQUIPMENT_DRAWING_MASTER.find(row=>row.event_equipment==='HP BFP');
  assert.equal(plantDrawingHref(gt),'/drawing?equipment=GT&view=plant');
  assert.equal(plantDrawingHref(stBreaker),'/drawing?equipment=52ST&view=ecms');
  assert.equal(plantDrawingHref(hpBfp),'/drawing?equipment=HP+BFP&view=plant');
});
