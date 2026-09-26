import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PLANT_PROCESS} from '../apps/web/lib/plantHotspots.mjs';
import {EQUIPMENT_DRAWING_MASTER,resolveEquipmentDrawing} from '../apps/web/lib/equipmentDrawingMaster.mjs';
import {resolvePlantFocus} from '../apps/web/lib/plantDrawingFocus.mjs';
import {ST_POWER_DISPLAY} from '../apps/web/lib/stPowerDisplay.mjs';

const page=fs.readFileSync(new URL('../apps/web/app/drawing/page.js',import.meta.url),'utf8');
const component=fs.readFileSync(new URL('../apps/web/components/PlantDrawingMaster.js',import.meta.url),'utf8');

test('plant Drawing Master keeps known valve detail bindings alongside the v36 overview',()=>{
  for(const id of ['HP-FWCV','HP-TURB-ADM-VLV','IP-TURB-ADM-VLV']) {
    const row=resolveEquipmentDrawing(id);
    assert.ok(row?.detail_asset?.endsWith('.svg'));
  }
  assert.ok(PLANT_PROCESS.hotspots.HP_BYPASS_VLV);
  assert.ok(PLANT_PROCESS.hotspots.LP_BYPASS_VLV);
  assert.match(page,/PlantDrawingMaster/);
});

test('every Plant equipment has an exact source symbol or an explicitly related v36 area',()=>{
  for(const row of EQUIPMENT_DRAWING_MASTER){
    const focus=resolvePlantFocus(row);
    if(!row.plant_location_id){
      assert.equal(focus,null,row.equipment_id+' is ECMS-only');
      assert.ok(row.ecms_location_id,row.equipment_id+' has no diagram');
      continue;
    }
    assert.ok(focus,row.equipment_id+' has no Plant drawing focus');
    assert.ok(PLANT_PROCESS.hotspots[focus.locationId]);
    assert.equal(focus.kind,PLANT_PROCESS.hotspots[row.plant_location_id]?'exact':'related');
  }
  assert.deepEqual(resolvePlantFocus(resolveEquipmentDrawing('HP FWCV')),{locationId:'HP_DRUM',kind:'related'});
  assert.deepEqual(resolvePlantFocus(resolveEquipmentDrawing('GT EXHAUST')),{locationId:'GT',kind:'related'});
  assert.deepEqual(resolvePlantFocus(resolveEquipmentDrawing('HP TURB ADM VALVE')),{locationId:'HP_TURB_ADM_VLV',kind:'exact'});
  assert.equal(PLANT_PROCESS.hotspots.HP_FWCV,undefined,'related fallback cannot create a false valve symbol');
});

test('ST power points to the 52ST breaker in the ECMS drawing',()=>{
  assert.equal(ST_POWER_DISPLAY.drawingHref,'/drawing?equipment=52ST&view=ecms&tag=vppSTGridPowerMW');
  assert.match(component,/href=\{ST_POWER_DISPLAY\.drawingHref\}/);
  assert.match(component,/52ST 차단기 위치/);
  assert.match(component,/setEventLabel\(event\?\('EVENT · '\+event\):tag\?\('TAG · '\+tag\):''\)/);
});

test('all registered valve and NRV detail assets are served unchanged by the web app',()=>{
  for(const row of EQUIPMENT_DRAWING_MASTER.filter(row=>row.detail_asset)){
    const original=fs.readFileSync(new URL('../'+row.detail_asset,import.meta.url));
    const served=fs.readFileSync(new URL('../apps/web/public/'+row.detail_asset,import.meta.url));
    assert.deepEqual(served,original,row.equipment_id+' web SVG differs from registered asset');
  }
});
