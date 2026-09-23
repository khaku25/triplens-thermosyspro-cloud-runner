import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PLANT_PROCESS} from '../apps/web/lib/plantHotspots.mjs';
import {EQUIPMENT_DRAWING_MASTER,resolveEquipmentDrawing} from '../apps/web/lib/equipmentDrawingMaster.mjs';

const page=fs.readFileSync(new URL('../apps/web/app/drawing/page.js',import.meta.url),'utf8');

test('plant Drawing Master keeps known valve detail bindings alongside the v36 overview',()=>{
  for(const id of ['HP-FWCV','HP-TURB-ADM-VLV','IP-TURB-ADM-VLV']) {
    const row=resolveEquipmentDrawing(id);
    assert.ok(row?.detail_asset?.endsWith('.svg'));
  }
  assert.ok(PLANT_PROCESS.hotspots.HP_BYPASS_VLV);
  assert.ok(PLANT_PROCESS.hotspots.LP_BYPASS_VLV);
  assert.match(page,/PlantDrawingMaster/);
});

test('all registered valve and NRV detail assets are served unchanged by the web app',()=>{
  for(const row of EQUIPMENT_DRAWING_MASTER.filter(row=>row.detail_asset)){
    const original=fs.readFileSync(new URL('../'+row.detail_asset,import.meta.url));
    const served=fs.readFileSync(new URL('../apps/web/public/'+row.detail_asset,import.meta.url));
    assert.deepEqual(served,original,row.equipment_id+' web SVG differs from registered asset');
  }
});
