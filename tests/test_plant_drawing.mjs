import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {PLANT_PROCESS,PLANT_REGISTERED_SIGNALS,modelBoxStyle} from '../apps/web/lib/plantHotspots.mjs';
import {EQUIPMENT_DRAWING_MASTER,resolveEquipmentDrawing} from '../apps/web/lib/equipmentDrawingMaster.mjs';
import {ECMS_HOTSPOT_PAGES} from '../apps/web/lib/ecmsHotspots.mjs';

const required=['GT','GTG','HP_DRUM','IP_DRUM','LP_DRUM','HP_TURBINE','IP_TURBINE','LP_TURBINE',
  'HP_TURB_ADM_VLV','IP_TURB_ADM_VLV',
  'HP_BYPASS_VLV','LP_BYPASS_VLV','HP_SPRAY','LP_SPRAY','HP_BFP','IP_BFP','LP_BFP',
  'HP_BFP_NRV','IP_BFP_NRV','LP_BFP_NRV','CONDENSER'];

test('v36 source symbols have exact boxes, no drawn ST generator, and valid overlay bounds',()=>{
  assert.deepEqual(PLANT_PROCESS.viewBox,[-240,-165,240,140]);
  for(const id of required){
    const hit=PLANT_PROCESS.hotspots[id];
    assert.ok(hit,`missing ${id}`);
    const style=modelBoxStyle(hit.box);
    for(const key of ['left','top','width','height']) assert.match(style[key],/^\d+(\.\d+)?%$/);
  }
  assert.deepEqual(PLANT_PROCESS.hotspots.LP_BFP.box,[140,-88,164,-64]);
  assert.deepEqual(PLANT_PROCESS.hotspots.HP_BYPASS_VLV.box,[-112,22,-86,42]);
  assert.deepEqual(PLANT_PROCESS.hotspots.HP_TURB_ADM_VLV.box,[-114,62,-84,86]);
  assert.deepEqual(PLANT_PROCESS.hotspots.IP_TURB_ADM_VLV.box,[78,62,108,86]);
  assert.deepEqual(PLANT_PROCESS.hotspots.CONDENSER.box,[180,-48,228,-10]);
  assert.equal(PLANT_PROCESS.hotspots.ST,undefined);
  assert.equal(PLANT_PROCESS.hotspots.HP_FWCV,undefined,'v36 has no separate FWCV symbol');
});

test('existing equipment master exactly maps required EVENT and operator names into v36',()=>{
  for(const [name,location,feeder] of [
    ['LP BFP','LP_BFP','VCB-A02'],['FWP-LP','LP_BFP','VCB-A02'],
    ['HP BFP','HP_BFP','VCB-A01'],['IP BFP','IP_BFP','VCB-B01'],
    ['HP Bypass','HP_BYPASS_VLV',''],['LP Bypass','LP_BYPASS_VLV',''],
    ['Condenser','CONDENSER',''],['GTG','GTG','GT'],
  ]){
    const row=resolveEquipmentDrawing(name);
    assert.ok(row,`missing ${name}`);
    assert.equal(row.plant_location_id,location);
    assert.equal(row.ecms_location_id,feeder);
    assert.ok(PLANT_PROCESS.hotspots[row.plant_location_id]);
  }
  for(const id of required){
    assert.ok(EQUIPMENT_DRAWING_MASTER.some(row=>row.plant_location_id===id),`unbound ${id}`);
  }
  assert.equal(resolveEquipmentDrawing('LP BFP extra'),null);
  assert.equal(resolveEquipmentDrawing('ST').ecms_location_id,'ST');
});

test('current ECMS MATLAB overlays remain registered separately',()=>{
  assert.ok(ECMS_HOTSPOT_PAGES.ECMS_VPP.hotspots['BUS-A']);
  assert.ok(ECMS_HOTSPOT_PAGES.ECMS_6P9KV.hotspots['VCB-A01']);
  assert.ok(ECMS_HOTSPOT_PAGES.ECMS_6P9KV.hotspots['VCB-A02']);
  assert.ok(ECMS_HOTSPOT_PAGES.ECMS_6P9KV.hotspots['VCB-B01']);
});

test('Plant view publishes ST grid-power navigation without a fabricated snapshot value',()=>{
  assert.deepEqual(PLANT_REGISTERED_SIGNALS,[{
    label:'ST GRID POWER',
    tag:'vppSTGridPowerMW',
    unit:'MW',
    access:'READ-ONLY',
    href:'/logic?tag=vppSTGridPowerMW',
  }]);
  assert.equal('value' in PLANT_REGISTERED_SIGNALS[0],false);
});

test('web image is the 2044 x 1285 source capture; Modelica remains unmodified',()=>{
  const png=readFileSync(new URL('../apps/web/public/drawing/plant-process-v36.png',import.meta.url));
  assert.deepEqual([...png.subarray(16,24)],[0,0,7,252,0,0,5,5]);
  const source=readFileSync(new URL('../modelica/TripLens_CombinedCycle_TripTAC_ProcessView_v36.mo',import.meta.url),'utf8');
  assert.match(source,/Diagram\(coordinateSystem\(preserveAspectRatio = false, extent = \{\{-240, -165\}, \{240, 140\}\}/);
});
