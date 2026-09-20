import {buildDraftRows} from './analysisClient.mjs';
import {buildExportReport} from './integrationTestbench.mjs';
import {validateReportReferences} from './reportIntegrity.mjs';
import {
  deriveRecoveryWorkflow,
  normalizeRecovery,
  recoveryStatusLabel,
  recoverySummary,
  validateRecovery,
  workflowLabel,
} from './recoveryModel.mjs';

const ACTION_SECTION='운전원·정비 조치사항';
const RESULT_SECTION='조치 결과 및 복구 판정';
const RECOVERY_SECTIONS=new Set([ACTION_SECTION,RESULT_SECTION]);

function row(section,item,content,status,evidence_ids='',time='',note='',row_id=''){
  return {section,item,content,status,evidence_ids,tags:'',time,note,row_id};
}

export function recoveryReportRows(value){
  const recovery=normalizeRecovery(value);
  const workflow=deriveRecoveryWorkflow(recovery);
  const pending=workflow==='INPUT_PENDING';
  const evidenceIds=recovery.evidence_ids.join('; ');
  const actor=[recovery.operator&&`수행자: ${recovery.operator}`,recovery.approver&&`기록상 승인자: ${recovery.approver}`].filter(Boolean).join(' · ');
  return [
    row(ACTION_SECTION,'실제 수행 조치',recovery.actions||'복구·조치 기록 입력 대기',workflow,evidenceIds,recovery.recovered_at,recovery.operator&&`수행자: ${recovery.operator}`,'RECOVERY-actions'),
    row(RESULT_SECTION,'복구 상태',pending?'복구 판정 입력 대기':recoveryStatusLabel(recovery),pending?'INPUT_PENDING':recovery.status,evidenceIds,recovery.recovered_at,'','RECOVERY-status'),
    row(RESULT_SECTION,'재기동 조건',recovery.restart_conditions||'재기동 조건 입력 대기',workflow,evidenceIds,recovery.recovered_at,'','RECOVERY-restart'),
    row(RESULT_SECTION,'담당자·승인자',actor||'담당자·승인자 입력 대기',workflow,'',recovery.approved_at,recovery.approved_at?`승인 기록: ${recovery.approved_at}`:'','RECOVERY-approval'),
  ];
}

export function applyRecoveryRows(rows,value){
  const source=Array.isArray(rows)?rows:[];
  const replacements=recoveryReportRows(value);
  const inserted=new Set();
  const output=[];
  for(const existing of source){
    const section=String(existing?.section||existing?.['구분']||'');
    if(!RECOVERY_SECTIONS.has(section)){
      output.push({...existing});
      continue;
    }
    if(!inserted.has(section)){
      output.push(...replacements.filter(candidate=>candidate.section===section));
      inserted.add(section);
    }
  }
  for(const section of [ACTION_SECTION,RESULT_SECTION]){
    if(!inserted.has(section))output.push(...replacements.filter(candidate=>candidate.section===section));
  }
  return output;
}

export function buildWorkspaceExportReport(args={}){
  const result=args.result||{};
  const analysis=args.analysis||result.analysis||{};
  const events=Array.isArray(args.events)?args.events:(result.events||[]);
  const catalog=Array.isArray(args.catalog)?args.catalog:(result.evidence_catalog||[]);
  const recovery=normalizeRecovery(args.recovery);
  const baseRows=Array.isArray(args.reportRows)&&args.reportRows.length
    ?args.reportRows
    :buildDraftRows({...result,analysis,events,evidence_catalog:catalog});
  const reportRows=applyRecoveryRows(baseRows,recovery);
  const reference_integrity=validateReportReferences(reportRows);
  const recovery_validation=validateRecovery(recovery,[...events,...catalog]);
  const recovery_workflow=deriveRecoveryWorkflow(recovery);
  const document_state=analysis.verification_gate==='PASS'&&recovery_workflow==='APPROVED'?'REVIEWED':'DRAFT';
  const legacy=buildExportReport({...args,result,analysis,events,catalog,reportRows});
  return {
    ...legacy,
    report_rows:reportRows,
    recovery,
    recovery_check:recoverySummary(recovery),
    recovery_status:recovery.status,
    recovery_actions:recovery.actions,
    recovered_at:recovery.recovered_at,
    recovery_operator:recovery.operator,
    restart_conditions:recovery.restart_conditions,
    recovery_approver:recovery.approver,
    recovery_approved_at:recovery.approved_at,
    recovery_workflow,
    recovery_workflow_label:workflowLabel(recovery_workflow),
    document_state,
    reference_integrity,
    report_integrity:reference_integrity,
    integrity:reference_integrity,
    recovery_validation,
  };
}
