import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {RECOVERY_READINESS_GROUPS} from '../apps/web/lib/recoveryReadiness.mjs';

const tagMaster=fs.readFileSync(new URL('../data/current_v8/live_tag_master.csv',import.meta.url),'utf8');
const logicRuntime=fs.readFileSync(new URL('../data/current_v8/live_logic_runtime.csv',import.meta.url),'utf8');

test('every readiness leaf is backed by a Current V8 live tag and registered logic',()=>{
  const conditions=RECOVERY_READINESS_GROUPS.flatMap(group=>group.conditions);
  assert.ok(conditions.length>=10);
  for(const condition of conditions){
    assert.ok(condition.aliases?.length,condition.id);
    assert.ok(tagMaster.includes(condition.aliases[0]),condition.id+' missing primary tag '+condition.aliases[0]);
    assert.ok(condition.logic_id,condition.id);
    assert.ok(logicRuntime.includes(condition.logic_id),condition.id+' missing logic '+condition.logic_id);
  }
});

test('readiness leaf IDs are unique and shared BOP HRSG groups explicitly affect both trains',()=>{
  const conditions=RECOVERY_READINESS_GROUPS.flatMap(group=>group.conditions);
  assert.equal(new Set(conditions.map(item=>item.id)).size,conditions.length);
  const shared=RECOVERY_READINESS_GROUPS.filter(group=>['hrsg','feedwater'].includes(group.id));
  assert.equal(shared.length,2);
  for(const group of shared)assert.deepEqual(group.affects,['GT','ST']);
});

test('readiness model does not define write commands or new OPC UA output nodes',()=>{
  const serialized=JSON.stringify(RECOVERY_READINESS_GROUPS);
  assert.doesNotMatch(serialized,/RESET_CMD|CLOSE_CMD|START_CMD|WRITE/i);
});
