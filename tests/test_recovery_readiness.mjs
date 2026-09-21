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

test('all current V8 readiness inputs clear makes both GT and ST ready to start',()=>{
  const result=deriveRecoveryReadiness([clearRow()]);
  assert.equal(result.status,READINESS_STATUS.SATISFIED);
  assert.equal(result.ready,true);
  assert.equal(result.trains.find(item=>item.id==='gt-ready').status,READINESS_STATUS.SATISFIED);
  assert.equal(result.trains.find(item=>item.id==='st-ready').status,READINESS_STATUS.SATISFIED);
  assert.equal(result.bop_hrsg.status,READINESS_STATUS.SATISFIED);
});

test('LP BFP trip latch blocks BOP HRSG and propagates to both GT and ST ready-to-start',()=>{
  const row=clearRow();
  row.vppLPFWPTripLatchNative='1';
  const result=deriveRecoveryReadiness([row]);
  assert.equal(result.bop_hrsg.status,READINESS_STATUS.BLOCKED);
  assert.equal(result.trains.find(item=>item.id==='gt-ready').status,READINESS_STATUS.BLOCKED);
  assert.equal(result.trains.find(item=>item.id==='st-ready').status,READINESS_STATUS.BLOCKED);
  assert.equal(result.blockers.find(item=>item.id==='lp-fwp-trip-latch').affects.join('/'),'GT/ST');
});

test('GT-only latch blocks GT start without falsely blocking ST when shared prerequisites are ready',()=>{
  const row=clearRow();
  row.vppGTTripLatch='1';
  const result=deriveRecoveryReadiness([row]);
  assert.equal(result.trains.find(item=>item.id==='gt-ready').status,READINESS_STATUS.BLOCKED);
  assert.equal(result.trains.find(item=>item.id==='st-ready').status,READINESS_STATUS.SATISFIED);
  assert.equal(result.bop_hrsg.status,READINESS_STATUS.SATISFIED);
});

test('missing shared HRSG input fail-closes both GT and ST as data missing',()=>{
  const row=clearRow();
  delete row.vppIPDrumLLRaw;
  const result=deriveRecoveryReadiness([row]);
  assert.equal(result.bop_hrsg.status,READINESS_STATUS.DATA_MISSING);
  assert.equal(result.trains.find(item=>item.id==='gt-ready').status,READINESS_STATUS.DATA_MISSING);
  assert.equal(result.trains.find(item=>item.id==='st-ready').status,READINESS_STATUS.DATA_MISSING);
  assert.equal(result.missing_count,1);
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

test('latest non-empty sample controls the train readiness state',()=>{
  const first=clearRow();
  first.model_time_s='90.000';
  first.vppGTTripLatch='1';
  const last=clearRow();
  last.model_time_s='100.000';
  last.vppGTTripLatch='0';
  const result=deriveRecoveryReadiness([first,last]);
  assert.equal(result.trains.find(item=>item.id==='gt-ready').status,READINESS_STATUS.SATISFIED);
  const gt=result.groups.flatMap(group=>group.conditions).find(item=>item.id==='gt-trip-latch');
  assert.equal(gt.model_time_s,'100.000');
});
