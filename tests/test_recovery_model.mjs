import test from 'node:test';
import assert from 'node:assert/strict';
import {
  EMPTY_RECOVERY,
  deriveRecoveryWorkflow,
  editRecovery,
  hasRecoveryRecord,
  normalizeRecovery,
  parseEvidenceIds,
  recoveryStatusLabel,
  recoverySummary,
  validateRecovery,
  workflowLabel,
} from '../apps/web/lib/recoveryModel.mjs';

const catalog = [{evidence_id:'E1'},{event_id:'E2'}];
const completeRecovered = {
  status:'RECOVERED',
  recovered_at:'2026-09-20T09:30:00Z',
  operator:'Lee',
  actions:'현장 점검 및 보호계전기 복귀 확인',
  restart_conditions:'진동·윤활유압 정상 확인 후 재기동',
  evidence_ids:['E1'],
  approver:'',
  approved_at:'',
};
const notRecovered = {
  status:'NOT_RECOVERED',
  operator:'Park',
  actions:'재기동 보류 및 정비 인계',
  evidence_ids:['E2'],
};

test('empty recovery is human input pending and is not presented as engineering UNKNOWN', () => {
  assert.equal(normalizeRecovery(EMPTY_RECOVERY).status,'UNKNOWN');
  assert.equal(deriveRecoveryWorkflow(EMPTY_RECOVERY),'INPUT_PENDING');
  assert.equal(workflowLabel('INPUT_PENDING'),'복구 기록 입력 대기');
  assert.doesNotMatch(recoverySummary(EMPTY_RECOVERY),/UNKNOWN/);
  assert.equal(hasRecoveryRecord(EMPTY_RECOVERY),false);
  assert.equal(hasRecoveryRecord(completeRecovered),true);
  assert.equal(hasRecoveryRecord({status:'UNKNOWN',decision_entered:true,operator:'Lee',actions:'판단 보류'}),true);
  assert.equal(hasRecoveryRecord({status:'UNKNOWN',approver:'Kim'}),false);
  assert.equal(hasRecoveryRecord({status:'UNKNOWN',evidence_ids:['E1']}),false);
});

test('complete recovery waits for explicit approval timestamp and then becomes approved', () => {
  assert.equal(deriveRecoveryWorkflow(completeRecovered),'APPROVAL_PENDING');
  assert.equal(deriveRecoveryWorkflow({...completeRecovered,approver:'Kim'}),'APPROVAL_PENDING');
  assert.equal(deriveRecoveryWorkflow({...completeRecovered,approver:'Kim',approved_at:'2026-09-20T10:00:00Z'}),'APPROVED');
  assert.equal(workflowLabel('APPROVAL_PENDING'),'복구 기록 완료 · 승인 대기');
  assert.equal(workflowLabel('APPROVED'),'복구 기록 승인 완료');
});

test('editing an approved record clears its approval action marker', () => {
  const approved={...completeRecovered,approver:'Kim',approved_at:'2026-09-20T10:00:00Z'};
  const edited=editRecovery(approved,'actions','수정');
  assert.equal(edited.actions,'수정');
  assert.equal(edited.approved_at,'');
  assert.equal(deriveRecoveryWorkflow(edited),'APPROVAL_PENDING');
});

test('validation applies status-specific required fields without requiring recovered time for NOT_RECOVERED', () => {
  assert.equal(validateRecovery({...notRecovered,recovered_at:''},catalog).valid,true);
  assert.deepEqual(validateRecovery({...completeRecovered,recovered_at:''},catalog).missing_fields,['recovered_at']);
  assert.deepEqual(validateRecovery({...completeRecovered,restart_conditions:''},catalog).missing_fields,['restart_conditions']);
  assert.equal(validateRecovery({status:'PARTIAL',recovered_at:'2026-09-20T09:30:00Z',operator:'Lee',actions:'제한 운전'},catalog).valid,true);
});

test('explicit engineering UNKNOWN requires a recorded decision, operator, and uncertainty reason', () => {
  const incomplete=validateRecovery({status:'UNKNOWN',decision_entered:true,operator:'Lee',actions:''},catalog);
  assert.deepEqual(incomplete.missing_fields,['actions']);
  const complete=validateRecovery({status:'UNKNOWN',decision_entered:true,operator:'Lee',actions:'계전기 기록 부재로 판단 불가'},catalog);
  assert.equal(complete.valid,true);
  assert.equal(deriveRecoveryWorkflow({status:'UNKNOWN',decision_entered:true,operator:'Lee',actions:'계전기 기록 부재로 판단 불가',approver:'Kim',approved_at:'2026-09-20T10:00:00Z'}),'APPROVED');
  assert.equal(recoveryStatusLabel('UNKNOWN'),'복구 여부 공학적 미확인');
});

test('evidence IDs normalize to a deduplicated string array and unresolved IDs fail validation', () => {
  assert.deepEqual(parseEvidenceIds([' E1 ','E1','E2; E1']),['E1','E2']);
  assert.deepEqual(normalizeRecovery({...completeRecovered,evidence_ids:'E1; E1, E2'}).evidence_ids,['E1','E2']);
  assert.deepEqual(validateRecovery({...completeRecovered,evidence_ids:['E1','NOPE']},catalog).missing_evidence,['NOPE']);
});

test('an unrecognized status remains invalid and can never become approved UNKNOWN', () => {
  const invalid={
    ...completeRecovered,
    status:'TYPO',
    decision_entered:true,
    approver:'Kim',
    approved_at:'2026-09-20T10:00:00Z',
  };
  assert.notEqual(normalizeRecovery(invalid).status,'UNKNOWN');
  assert.deepEqual(validateRecovery(invalid,catalog).missing_fields,['status']);
  assert.equal(validateRecovery(invalid,catalog).valid,false);
  assert.equal(deriveRecoveryWorkflow(invalid),'INPUT_PENDING');
});

test('blank, null, and omitted statuses stay invalid and input-pending despite approval fields', () => {
  const cases=[
    {label:'empty',status:''},
    {label:'whitespace',status:'   '},
    {label:'null',status:null},
    {label:'omitted'},
  ];
  for(const item of cases){
    const value={
      decision_entered:true,
      operator:'Lee',
      actions:'판단 기록',
      approver:'Kim',
      approved_at:'2026-09-20T10:00:00Z',
      ...(Object.hasOwn(item,'status')?{status:item.status}:{}),
    };
    assert.equal(normalizeRecovery(value).status,'',item.label);
    assert.deepEqual(validateRecovery(value,catalog).missing_fields,['status'],item.label);
    assert.equal(validateRecovery(value,catalog).valid,false,item.label);
    assert.equal(deriveRecoveryWorkflow(value),'INPUT_PENDING',item.label);
  }
});
