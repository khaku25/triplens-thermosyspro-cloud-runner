import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const overview=fs.readFileSync(new URL('../apps/web/public/drawing/ecms-overview.svg',import.meta.url),'utf8');
const detail=fs.readFileSync(new URL('../apps/web/public/drawing/ecms-6p9kv.svg',import.meta.url),'utf8');
const ui=fs.readFileSync(new URL('../apps/web/components/PlantDrawingMaster.js',import.meta.url),'utf8');
const inline=fs.readFileSync(new URL('../apps/web/components/InlineSvgNavigator.js',import.meta.url),'utf8');

test('ECMS overview preserves manual BUS-A and BUS-B drill-down targets',()=>{
  assert.match(overview,/data-view="BUS-A"/);
  assert.match(overview,/data-view="BUS-B"/);
  assert.match(overview,/data-equipment="CB-TIE-AB"/);
});

test('6.9 kV detail exposes direct-jump equipment identities',()=>{
  for(const id of ['BUS-A','BUS-B','CB-TIE-AB','CB-IN-A','CB-IN-B','VCB-A01','VCB-A02','VCB-B01','FWP-HP','FWP-LP','FWP-IP']){
    assert.ok(detail.includes('data-equipment="'+id+'"'),'missing '+id);
  }
});

test('Drawing Master supports overview navigation and URL equipment direct jump',()=>{
  assert.match(ui,/new URLSearchParams\(window\.location\.search\)/);
  assert.match(ui,/params\.get\('equipment'\)/);
  assert.match(ui,/overviewNavigate/);
  assert.match(ui,/ecms-detail/);
  assert.match(ui,/ECMS Overview/);
  assert.match(ui,/Direct Jump/);
  assert.match(inline,/data-view/);
  assert.match(inline,/data-equipment/);
  assert.match(inline,/triplens-highlight-layer/);
});

// Workflow trigger: verifies the committed clickable ECMS assets and direct-jump contract.
