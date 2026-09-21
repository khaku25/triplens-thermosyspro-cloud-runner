import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const workspace=fs.readFileSync(new URL('../apps/web/components/TripLensWorkspace.js',import.meta.url),'utf8');
const component=fs.readFileSync(new URL('../apps/web/components/RecoveryReadiness.js',import.meta.url),'utf8');
const contracts=fs.readFileSync(new URL('../apps/web/lib/contracts.js',import.meta.url),'utf8');

test('recovery workspace renders model-derived readiness before human recovery record',()=>{
  assert.match(workspace,/RecoveryReadiness rawData=\{rawData\}/);
  assert.match(workspace,/실제 복구 기록/);
  assert.ok(workspace.indexOf('RecoveryReadiness rawData={rawData}')<workspace.indexOf('RecoveryForm value={recovery}'));
});

test('readiness UI is display-only and does not expose plant control actions',()=>{
  assert.match(component,/FINAL READINESS/);
  assert.match(component,/실제 발전소 APS 기동 Permissive 또는 운전 승인 로직이 아니라/);
  assert.doesNotMatch(component,/TRIP RESET|SENSOR RESET|BREAKER CLOSE|START COMMAND/);
});

test('navigation identifies recovery readiness and human record as one workspace',()=>{
  assert.match(contracts,/label: '복구 · 준비상태'/);
  assert.match(contracts,/sub: '파생 준비상태 · 실제 조치 기록'/);
});
