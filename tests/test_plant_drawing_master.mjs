import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const source=fs.readFileSync(new URL('../apps/web/components/PlantDrawingMaster.js',import.meta.url),'utf8');
const page=fs.readFileSync(new URL('../apps/web/app/drawing/page.js',import.meta.url),'utf8');

test('plant drawing master exposes ThermoSys valve, bypass, VPP and SLD views',()=>{
  for(const token of ['fmu_valves_overview.svg','turbine_bypass_vpp.svg','triplens_ecms_vpp.svg','triplens_ecms_6p9kv.svg']) assert.match(source,new RegExp(token.replaceAll('.','\\.')));
  assert.match(source,/HP-FWCV/);
  assert.match(source,/HP-TURB-ADM-VLV/);
  assert.match(source,/IP-TURB-ADM-VLV/);
});

test('drawing master is a distinct plant route and keeps logic as auxiliary view',()=>{
  assert.match(page,/PlantDrawingMaster/);
  assert.match(source,/href="\/logic"/);
  assert.match(source,/READ-ONLY 도면 탐색/);
});
