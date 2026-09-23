import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { PLANT_PROCESS, ECMS_VIEWS, modelBoxStyle } from '../apps/web/lib/plantHotspots.mjs';
import { resolveEquipment, resolveDrawingRequest, drawingHref } from '../apps/web/lib/equipmentMaster.mjs';

const required = ['GT','GTG','HP_DRUM','IP_DRUM','LP_DRUM','HP_TURBINE','IP_TURBINE','LP_TURBINE',
  'HP_BYPASS_VLV','LP_BYPASS_VLV','HP_SPRAY','LP_SPRAY','HP_BFP','IP_BFP','LP_BFP',
  'HP_BFP_NRV','IP_BFP_NRV','LP_BFP_NRV','CONDENSER'];

test('v36 diagram coordinates cover the real visible plant symbols', () => {
  assert.deepEqual(PLANT_PROCESS.viewBox, [-240,-165,240,140]);
  for (const id of required) {
    const hotspot = PLANT_PROCESS.hotspots[id];
    assert.ok(hotspot, `missing ${id}`);
    assert.ok(hotspot.box[0] < hotspot.box[2] && hotspot.box[1] < hotspot.box[3]);
    const css = modelBoxStyle(hotspot.box, PLANT_PROCESS.viewBox);
    for (const key of ['left','top','width','height']) assert.match(css[key], /^\d+(\.\d+)?%$/);
  }
  assert.deepEqual(PLANT_PROCESS.hotspots.LP_BFP.box, [140,-88,164,-64]);
  assert.deepEqual(PLANT_PROCESS.hotspots.HP_BYPASS_VLV.box, [-112,22,-86,42]);
  assert.deepEqual(PLANT_PROCESS.hotspots.CONDENSER.box, [180,-48,228,-10]);
  assert.equal(PLANT_PROCESS.hotspots.ST, undefined, 'v36 has no ST generator symbol');
});

test('known EVENT equipment resolves exactly to process location and ECMS feeder', () => {
  for (const [name, location, feeder] of [
    ['LP BFP','LP_BFP','VCB-A02'],['FWP-LP','LP_BFP','VCB-A02'],
    ['HP BFP','HP_BFP','VCB-A01'],['IP BFP','IP_BFP','VCB-B01'],
    ['HP-BYPASS-VLV','HP_BYPASS_VLV',null],['LP Bypass','LP_BYPASS_VLV',null],
    ['Condenser','CONDENSER',null],
  ]) {
    const record = resolveEquipment(name);
    assert.equal(record.plant_location_id, location);
    assert.equal(record.ecms_location_id, feeder);
    assert.equal(resolveDrawingRequest({equipment:name}).view, 'plant');
    assert.equal(resolveDrawingRequest({equipment:name}).locationId, location);
    assert.match(drawingHref(name), /^\/drawing\?equipment=/);
  }
  assert.deepEqual(resolveDrawingRequest({equipment:'LP BFP',view:'ecms'}),
    {view:'ecms',page:'detail',locationId:'VCB-A02',record:resolveEquipment('LP BFP')});
  assert.equal(resolveEquipment('LP BFP extra'), null, 'no substring guess');
  assert.equal(resolveEquipment(''), null);
});

test('ECMS overview, bus drill down and breaker direct jump stay distinct', () => {
  assert.deepEqual(Object.keys(ECMS_VIEWS), ['overview','detail']);
  for (const equipment of ['52GT','52ST','BUS-A','BUS-B','CB-TIE-AB','VCB-A01','VCB-A02','VCB-B01']) {
    const target = resolveDrawingRequest({equipment});
    assert.equal(target.view,'ecms');
    assert.ok(ECMS_VIEWS[target.page].hotspots[target.locationId]);
  }
  assert.equal(resolveDrawingRequest({equipment:'BUS-A'}).page,'overview');
  assert.equal(resolveDrawingRequest({equipment:'BUS-A',page:'detail'}).page,'detail');
  assert.equal(resolveDrawingRequest({equipment:'VCB-A01'}).page,'detail');
  assert.deepEqual(resolveDrawingRequest({equipment:'unregistered'}),
    {view:'ecms',page:'overview',locationId:null,record:null});
});

test('source diagram is left untouched and the published image has the source frame size', () => {
  const image = readFileSync(new URL('../apps/web/public/drawing/plant-process-v36.png', import.meta.url));
  assert.deepEqual([...image.subarray(16,24)], [0,0,7,252,0,0,5,5]);
  const source = readFileSync(new URL('../modelica/TripLens_CombinedCycle_TripTAC_ProcessView_v36.mo', import.meta.url),'utf8');
  assert.match(source,/Diagram\(coordinateSystem\(preserveAspectRatio = false, extent = \{\{-240, -165\}, \{240, 140\}\}/);
});
