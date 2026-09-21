import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const workspace=fs.readFileSync(new URL('../apps/web/components/TripLensWorkspace.js',import.meta.url),'utf8');
const component=fs.readFileSync(new URL('../apps/web/components/RecoveryReadiness.js',import.meta.url),'utf8');
const contracts=fs.readFileSync(new URL('../apps/web/lib/contracts.js',import.meta.url),'utf8');

test('screen 04 renders live RAW readiness before the human recovery record',()=>{
  assert.match(workspace,/RecoveryReadiness rawData=\{rawData\}/);
  assert.match(workspace,/실제 복구 기록/);
  assert.ok(workspace.indexOf('RecoveryReadiness rawData={rawData}')<workspace.indexOf('RecoveryForm value={recovery}'));
});

test('screen 04 uses a fixed GT BOP HRSG ST permissive frame',()=>{
  assert.match(component,/GT \/ ST 재기동 준비상태/);
  assert.match(component,/GT READY TO START/);
  assert.match(component,/BOP \/ HRSG READY TO START/);
  assert.match(component,/ST READY TO START/);
  assert.match(component,/프레임과 AND 관계는 고정/);
});

test('leaf states are ON OFF DATA while top readiness stays READY NOT READY',()=>{
  assert.match(component,/SATISFIED\]:'ON'/);
  assert.match(component,/BLOCKED\]:'OFF'/);
  assert.match(component,/DATA_MISSING\]:'DATA'/);
  assert.match(component,/SATISFIED\]:'READY'/);
  assert.match(component,/BLOCKED\]:'NOT READY'/);
});

test('screen 04 includes inline equipment SVGs without remote image dependencies',()=>{
  for(const name of ['GTIcon','HRSGIcon','STIcon'])assert.match(component,new RegExp(`function ${name}`));
  assert.match(component,/viewBox="0 0 48 48"/);
  assert.doesNotMatch(component,/https?:\/\/|<img/);
});

test('production component contains no fixture or scenario selector',()=>{
  assert.doesNotMatch(component,/NORMAL|LP_BFP_TRIP|DATA_MISSING\)\s*=>|fixture\(|demo-switch/i);
});

test('readiness UI remains read-only and exposes no plant control actions',()=>{
  assert.match(component,/CURRENT V8 · READ ONLY/);
  assert.doesNotMatch(component,/TRIP RESET|SENSOR RESET|BREAKER CLOSE|START COMMAND/);
});

test('navigation identifies recovery readiness and human record as one workspace',()=>{
  assert.match(contracts,/label: '복구 · 준비상태'/);
  assert.match(contracts,/sub: 'GT·HRSG·ST 준비상태 · 복구 기록'/);
});
