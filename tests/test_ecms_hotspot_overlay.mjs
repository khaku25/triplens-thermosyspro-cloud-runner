import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {ECMS_HOTSPOT_PAGES,resolveEcmsHotspot} from '../apps/web/lib/ecmsHotspots.mjs';

test('MATLAB-exported ECMS SVGs retain source geometry',()=>{
  const overview=fs.readFileSync(new URL('../apps/web/public/drawing/ecms-overview-matlab.svg',import.meta.url),'utf8');
  const detail=fs.readFileSync(new URL('../apps/web/public/drawing/ecms-6p9kv-matlab.svg',import.meta.url),'utf8');
  assert.match(overview,/viewBox="0 0 1400 800"/);
  assert.match(overview,/CB-TIE-AB/);
  assert.match(detail,/viewBox="0 0 1500 900"/);
  assert.match(detail,/VCB-A02/);
});

test('ECMS hotspot map uses uploaded MATLAB geometry',()=>{
  assert.deepEqual(ECMS_HOTSPOT_PAGES.ECMS_6P9KV.hotspots['VCB-A02'].box,[585,295,50,62]);
  assert.deepEqual(ECMS_HOTSPOT_PAGES.ECMS_6P9KV.hotspots['CB-TIE-AB'].box,[700,220,100,82]);
  assert.deepEqual(ECMS_HOTSPOT_PAGES.ECMS_VPP.hotspots['52GT'].box,[165,311,50,48]);
  assert.equal(resolveEcmsHotspot('ECMS_6P9KV','LP BFP').key,'FWP-LP');
});

test('drawing UI renders coordinate hotspot overlays and EVENT labels',()=>{
  const viewer=fs.readFileSync(new URL('../apps/web/components/InlineSvgNavigator.js',import.meta.url),'utf8');
  const drawing=fs.readFileSync(new URL('../apps/web/components/PlantDrawingMaster.js',import.meta.url),'utf8');
  assert.match(viewer,/triplens-hotspot-layer/);
  assert.match(viewer,/triplens-highlight-layer/);
  assert.match(viewer,/eventLabel/);
  assert.match(drawing,/ecms-overview-matlab\.svg/);
  assert.match(drawing,/ecms-6p9kv-matlab\.svg/);
  assert.match(drawing,/EVENT ·/);
});
