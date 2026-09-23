import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {EQUIPMENT_DRAWING_MASTER,resolveEquipmentDrawing} from '../apps/web/lib/equipmentDrawingMaster.mjs';

function parseCsv(text){
  const lines=text.trim().split(/\r?\n/);
  const head=lines[0].split(',');
  return lines.slice(1).map(line=>{
    const out=[]; let cur=''; let quoted=false;
    for(let i=0;i<line.length;i++){
      const ch=line[i];
      if(ch==='"'){
        if(quoted&&line[i+1]==='"'){cur+='"';i++}
        else quoted=!quoted;
      }else if(ch===','&&!quoted){out.push(cur);cur='';}
      else cur+=ch;
    }
    out.push(cur);
    return Object.fromEntries(head.map((h,i)=>[h,out[i]||'']));
  });
}

test('equipment drawing master covers every enabled EVENT equipment exactly',()=>{
  const registry=parseCsv(fs.readFileSync(new URL('../config/alarm_registry_v1.csv',import.meta.url),'utf8')).filter(x=>x.enabled==='1');
  const equipment=[...new Set(registry.map(x=>x.equipment))];
  assert.equal(equipment.length,40);
  assert.equal(EQUIPMENT_DRAWING_MASTER.length,40);
  for(const name of equipment){
    const row=resolveEquipmentDrawing(name);
    assert.ok(row,'missing equipment: '+name);
    assert.equal(row.mapping_status,'BOUND');
    assert.ok(row.plant_location_id||row.ecms_location_id,'no drawing location: '+name);
  }
});

test('BFP aliases keep plant and feeder locations without EVENT-specific mapping',()=>{
  const hp=resolveEquipmentDrawing('HP BFP');
  const ip=resolveEquipmentDrawing('IP BFP');
  const lp=resolveEquipmentDrawing('LP BFP');
  assert.deepEqual([hp.plant_location_id,hp.ecms_location_id],['HP_BFP','VCB-A01']);
  assert.deepEqual([ip.plant_location_id,ip.ecms_location_id],['IP_BFP','VCB-B01']);
  assert.deepEqual([lp.plant_location_id,lp.ecms_location_id],['LP_BFP','VCB-A02']);
  assert.equal(resolveEquipmentDrawing('FWP-LP'),lp);
});

test('resolver is exact and never fuzzy substitutes equipment names',()=>{
  assert.equal(resolveEquipmentDrawing('LP BF'),null);
  assert.equal(resolveEquipmentDrawing('VCB A02'),null);
});
