import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {resolveEquipmentDrawing} from '../apps/web/lib/equipmentDrawingMaster.mjs';
import {resolveLogicEquipmentPage,logicDrawingHref} from '../apps/web/lib/logicEquipmentPages.mjs';

const index=JSON.parse(fs.readFileSync(new URL('../apps/web/public/logic-assets/logic_diagram_index.json',import.meta.url),'utf8'));
const pageEquipment={
  'GT Exhaust':'GT EXHAUST',
  'ST Protection':'ST',
  'FWP HP':'HP BFP',
  'GT Protection':'GT',
  'IP Drum':'IP DRUM',
  'FWP IP':'IP BFP',
  'LP Drum':'LP DRUM',
  'HP Drum':'HP DRUM',
  'FWP LP':'LP BFP',
};

test('every real equipment logic page resolves to its registered physical drawing identity',()=>{
  const pages=Object.values(index.pages).filter(page=>page.scope==='equipment');
  assert.deepEqual(pages.map(page=>page.name).sort(),Object.keys(pageEquipment).sort());
  for(const page of pages){
    const row=resolveLogicEquipmentPage(page.name);
    assert.equal(row,resolveEquipmentDrawing(pageEquipment[page.name]),page.name);
    const url=new URL(logicDrawingHref(page.name),'https://example.test');
    assert.equal(url.pathname,'/drawing');
    assert.equal(url.searchParams.get('equipment'),row.event_equipment);
    assert.equal(url.searchParams.get('view'),row.plant_location_id?'plant':'ecms');
  }
});

test('LP Drum and GT Exhaust jump to Plant; unknown logic pages get a generic drawing link',()=>{
  assert.equal(new URL(logicDrawingHref('LP Drum'),'https://example.test').searchParams.get('equipment'),'LP DRUM');
  assert.equal(new URL(logicDrawingHref('GT Exhaust'),'https://example.test').searchParams.get('equipment'),'GT EXHAUST');
  assert.equal(resolveLogicEquipmentPage('Unregistered equipment'),null);
  assert.equal(logicDrawingHref('Unregistered equipment'),'/drawing?view=plant');
});
