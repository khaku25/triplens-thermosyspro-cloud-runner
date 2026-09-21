import test from 'node:test';
import assert from 'node:assert/strict';
import {deriveRecoveryReadiness,RECOVERY_READINESS_GROUPS,READINESS_STATUS} from '../apps/web/lib/recoveryReadiness.mjs';

function clearRow(){
  const row={model_time_s:'100.000'};
  for(const condition of RECOVERY_READINESS_GROUPS.flatMap(group=>group.conditions)){
    row[condition.aliases[0]]='0';
  }
  return row;
}

test('all registered recovery inputs clear produces READY',()=>{
  const result=deriveRecoveryReadiness([clearRow()]);
  assert.equal(result.status,READINESS_STATUS.SATISFIED);
  assert.equal(result.ready,true);
  assert.equal(result.satisfied,result.total);
  assert.equal(result.blocked_count,0);
  assert.equal(result.missing_count,0);
});

test('one active LP BFP trip latch blocks final readiness',()=>{
  const row=clearRow();
  row.vppLPFWPTripLatchNative='1';
  const result=deriveRecoveryReadiness([row]);
  assert.equal(result.status,READINESS_STATUS.BLOCKED);
  assert.equal(result.ready,false);
  assert.equal(result.blocked_count,1);
  assert.equal(result.blockers[0].id,'lp-fwp-trip-latch');
});

test('missing required input is fail-closed as DATA_MISSING',()=>{
  const row=clearRow();
  delete row.vppIPDrumLLRaw;
  const result=deriveRecoveryReadiness([row]);
  assert.equal(result.status,READINESS_STATUS.DATA_MISSING);
  assert.equal(result.ready,false);
  assert.equal(result.missing_count,1);
  assert.equal(result.missing[0].id,'ip-drum-ll');
});

test('raw__ prefixed columns resolve without adding new OPC UA tags',()=>{
  const base=clearRow();
  const row={model_time_s:base.model_time_s};
  for(const [key,value] of Object.entries(base)){
    if(key==='model_time_s')continue;
    row['raw__'+key]=value;
  }
  const result=deriveRecoveryReadiness([row]);
  assert.equal(result.ready,true);
  assert.equal(result.missing_count,0);
});

test('latest non-empty sample controls the readiness state',()=>{
  const first=clearRow();
  first.model_time_s='90.000';
  first.vppGTTripLatch='1';
  const last=clearRow();
  last.model_time_s='100.000';
  last.vppGTTripLatch='0';
  const result=deriveRecoveryReadiness([first,last]);
  assert.equal(result.ready,true);
  const gt=result.groups.flatMap(group=>group.conditions).find(item=>item.id==='gt-trip-latch');
  assert.equal(gt.model_time_s,'100.000');
});
