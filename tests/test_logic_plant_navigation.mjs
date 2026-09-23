import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const dialog=readFileSync(new URL('../apps/web/components/LogicLibrary.js',import.meta.url),'utf8');
const frame=readFileSync(new URL('../apps/web/components/LogicViewerFrame.js',import.meta.url),'utf8');
const drawing=readFileSync(new URL('../apps/web/components/PlantDrawingMaster.js',import.meta.url),'utf8');
const workspace=readFileSync(new URL('../apps/web/components/TripLensWorkspace.js',import.meta.url),'utf8');

test('Logic Master links to the actual Plant drawing and identifies its own equipment diagrams as logic',()=>{
  assert.match(dialog,/href="\/drawing\?view=plant"/);
  assert.match(dialog,/Plant Process View 열기/);
  assert.doesNotMatch(dialog,/>별도 화면</);
  assert.match(frame,/setText\(document\.querySelector\('#equipment-view'\), '설비별 로직'\)/);
});

test('Plant overview opens from its direct URL without an equipment selection',()=>{
  assert.match(drawing,/if\(requested==='plant'\)\s*\{setScreen\('plant'\)/);
  assert.match(workspace,/qs\.set\('view','plant'\)/);
});
