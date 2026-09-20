const RECOVERY_STATUSES=new Set(['UNKNOWN','PARTIAL','RECOVERED','NOT_RECOVERED']);

const text=value=>value==null?'':String(value).trim();

export const EMPTY_RECOVERY=Object.freeze({
  status:'UNKNOWN',
  decision_entered:false,
  recovered_at:'',
  operator:'',
  actions:'',
  restart_conditions:'',
  evidence_ids:Object.freeze([]),
  approver:'',
  approved_at:'',
});

export function parseEvidenceIds(value){
  const values=Array.isArray(value)?value:[value];
  const ids=values.flatMap(item=>String(item??'').split(/[;,\n\r]+/)).map(text).filter(Boolean);
  return [...new Set(ids)];
}

export function normalizeRecovery(value={}){
  const source=value&&typeof value==='object'?value:{};
  const status=text(source.status).toUpperCase()||'UNKNOWN';
  return {
    status,
    decision_entered:source.decision_entered===true||source.decision_entered===1||source.decision_entered==='true',
    recovered_at:text(source.recovered_at),
    operator:text(source.operator),
    actions:text(source.actions),
    restart_conditions:text(source.restart_conditions),
    evidence_ids:parseEvidenceIds(source.evidence_ids),
    approver:text(source.approver),
    approved_at:text(source.approved_at),
  };
}

function requiredFields(value){
  if(!RECOVERY_STATUSES.has(value.status))return ['status'];
  if(value.status==='UNKNOWN')return ['decision_entered','operator','actions'];
  if(value.status==='RECOVERED')return ['recovered_at','operator','actions','restart_conditions'];
  if(value.status==='PARTIAL')return ['recovered_at','operator','actions'];
  return ['operator','actions'];
}

function fieldMissing(value,field){
  if(field==='status')return !RECOVERY_STATUSES.has(value.status);
  if(field==='decision_entered')return !value.decision_entered;
  return !value[field];
}

export function validateRecovery(value,catalog=[]){
  const recovery=normalizeRecovery(value);
  const missing_fields=requiredFields(recovery).filter(field=>fieldMissing(recovery,field));
  const available=new Set((Array.isArray(catalog)?catalog:[]).map(item=>text(item?.evidence_id||item?.event_id)).filter(Boolean));
  const missing_evidence=recovery.evidence_ids.filter(id=>!available.has(id));
  return {valid:missing_fields.length===0&&missing_evidence.length===0,missing_fields,missing_evidence,recovery};
}

export function deriveRecoveryWorkflow(value){
  const recovery=normalizeRecovery(value);
  if(requiredFields(recovery).some(field=>fieldMissing(recovery,field)))return 'INPUT_PENDING';
  if(recovery.approver&&recovery.approved_at)return 'APPROVED';
  return 'APPROVAL_PENDING';
}

export function recoveryStatusLabel(value){
  const status=typeof value==='object'?normalizeRecovery(value).status:text(value).toUpperCase();
  return ({
    UNKNOWN:'복구 여부 공학적 미확인',
    PARTIAL:'부분 복구',
    RECOVERED:'복구 완료',
    NOT_RECOVERED:'미복구',
  })[status]||'복구 상태 미입력';
}

export function workflowLabel(value){
  const workflow=typeof value==='object'?deriveRecoveryWorkflow(value):text(value).toUpperCase();
  return ({
    INPUT_PENDING:'복구 기록 입력 대기',
    APPROVAL_PENDING:'복구 기록 완료 · 승인 대기',
    APPROVED:'복구 기록 승인 완료',
  })[workflow]||'복구 기록 입력 대기';
}

export function recoverySummary(value){
  const recovery=normalizeRecovery(value);
  const workflow=deriveRecoveryWorkflow(recovery);
  return workflow==='INPUT_PENDING'?workflowLabel(workflow):`${recoveryStatusLabel(recovery)} · ${workflowLabel(workflow)}`;
}

export function editRecovery(value,field,nextValue){
  const current=normalizeRecovery(value);
  const edited={...current,[field]:field==='evidence_ids'?parseEvidenceIds(nextValue):nextValue};
  if(current.approved_at&&field!=='approved_at')edited.approved_at='';
  return normalizeRecovery(edited);
}
