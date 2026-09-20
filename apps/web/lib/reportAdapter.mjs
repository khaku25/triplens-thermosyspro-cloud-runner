import {buildDraftRows,REPORT_SECTIONS} from './analysisClient.mjs';
import {buildExportReport} from './integrationTestbench.mjs';
import {mergeEvents,mergeEvidenceCatalog,validateReportReferences} from './reportIntegrity.mjs';
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
export const WORKSPACE_REPORT_VERSION=2;
const SOE_SECTION='시간대별 사건·자동동작(SOE)';

// Session schema is independent of the unchanged analysis contract. Migrate
// unversioned legacy rows, but never "repair" edits to an already-current report.
export function restoreWorkspaceReportRows({result={},uploadedEvents=[],reportRows=[],recovery,reportVersion}={}){
  const events=mergeEvents(uploadedEvents,result.events||[]);
  const catalog=mergeEvidenceCatalog(events,result.evidence_catalog||[]);
  const source=Array.isArray(reportRows)?reportRows:[];
  const sections=new Set(source.map(row=>row.section));
  const available=new Set(source.filter(row=>row.section==='증거자료').flatMap(row=>String(row.evidence_ids||'').split(';').map(id=>id.trim())));
  const current=reportVersion===WORKSPACE_REPORT_VERSION||(
    REPORT_SECTIONS.every(section=>sections.has(section))&&
    !sections.has('시간대별 조치사항')&&!sections.has('조치 결과')&&
    catalog.every(entry=>available.has(entry.evidence_id))
  );
  if(current&&source.length)return applyRecoveryRows(source.map((row,index)=>({...row,row_id:row.row_id||`RESTORED-${index}`})),recovery);

  const sectionName=section=>section==='시간대별 조치사항'?SOE_SECTION:section==='조치 결과'?RESULT_SECTION:section;
  const tokens=value=>String(value||'').split(';').map(id=>id.trim()).filter(Boolean).sort().join(';');
  const family=row=>String(row.item||'').replace(/\s+\d+$/,'');
  const remaining=new Set(source);
  const base=buildDraftRows({...result,events,evidence_catalog:catalog});
  const rows=base.map(fresh=>{
    if(RECOVERY_SECTIONS.has(fresh.section))return fresh;
    const candidates=[...remaining].filter(old=>sectionName(old.section)===fresh.section);
    let match=candidates.find(old=>old.row_id&&old.row_id===fresh.row_id);
    if(!match){
      const semantic=candidates.filter(old=>family(old)===family(fresh)&&tokens(old.evidence_ids)===tokens(fresh.evidence_ids));
      match=semantic.length===1?semantic[0]:semantic.find(old=>old.item===fresh.item&&old.time===fresh.time);
    }
    if(!match)return fresh;
    remaining.delete(match);
    // Generic original tags were a legacy merge artifact. Enrich only that
    // known value; custom user tags and all other matched editable cells survive.
    const linked=catalog.filter(entry=>tokens(fresh.evidence_ids).split(';').includes(entry.evidence_id));
    const originalTags=new Set(linked.flatMap(entry=>[entry.original_tag,entry.tag]).filter(Boolean));
    const tags=originalTags.has(match.tags)?fresh.tags:match.tags;
    return {...fresh,...match,section:fresh.section,tags,row_id:match.row_id||fresh.row_id};
  });
  // Retain unmatched user rows rather than guessing that an edit is disposable.
  // Recovery sections alone are derived exclusively from the structured record.
  for(const old of remaining){
    const section=sectionName(old.section);
    if(RECOVERY_SECTIONS.has(section))continue;
    const at=rows.findLastIndex(row=>row.section===section);
    rows.splice(at<0?rows.length:at+1,0,{...old,section,row_id:old.row_id||`RESTORED-${source.indexOf(old)}`});
  }
  return applyRecoveryRows(rows,recovery);
}

function row(section,item,content,status,evidence_ids='',time='',note='',row_id=''){
  return {section,item,content,status,evidence_ids,tags:'',time,note,row_id};
}

export function recoveryReportRows(value){
  const recovery=normalizeRecovery(value);
  const workflow=deriveRecoveryWorkflow(recovery);
  const pending=workflow==='INPUT_PENDING';
  const evidenceIds=recovery.evidence_ids.join('; ');
  const actor=[recovery.operator&&`수행자: ${recovery.operator}`,recovery.approver&&`기록상 승인자: ${recovery.approver}`].filter(Boolean).join(' · ');
  const restartConditions=recovery.restart_conditions||(recovery.status==='RECOVERED'?'재기동 조건 입력 대기':'해당 없음 (필수 입력 아님)');
  return [
    row(ACTION_SECTION,'실제 수행 조치',recovery.actions||'복구·조치 기록 입력 대기',workflow,evidenceIds,recovery.recovered_at,recovery.operator&&`수행자: ${recovery.operator}`,'RECOVERY-actions'),
    row(RESULT_SECTION,'복구 상태',pending?'복구 판정 입력 대기':recoveryStatusLabel(recovery),pending?'INPUT_PENDING':recovery.status,evidenceIds,recovery.recovered_at,'','RECOVERY-status'),
    row(RESULT_SECTION,'재기동 조건',restartConditions,workflow,evidenceIds,recovery.recovered_at,'','RECOVERY-restart'),
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
  const catalog=mergeEvidenceCatalog(events,Array.isArray(args.catalog)?args.catalog:(result.evidence_catalog||[]));
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
    // PINPOINT serializes sections, not report_rows. Keep the frozen adapter
    // unchanged and append the same authoritative recovery rows used by PDF/CSV.
    sections:[...legacy.sections,{
      id:'recovery',title:'Recovery',value:recoveryReportRows(recovery).map(item=>({
        claim:[item.item,item.content,item.time,item.note].filter(Boolean).join(' · '),
        status:item.status,
        recovery_status:recovery.status,
        review_required:document_state!=='REVIEWED',
        evidence:catalog.filter(entry=>item.evidence_ids.split(';').map(id=>id.trim()).includes(String(entry.evidence_id||entry.event_id))).map(entry=>({
          ...entry,
          event_id:entry.evidence_id||entry.event_id,
          source_system:entry.source||entry.source_kind||'',
          original_time:entry.model_time_s==null?'':String(entry.model_time_s),
          aligned_time:entry.model_time_s==null?'':String(entry.model_time_s),
          event_tag:entry.original_tag||entry.tag||'',
          canonical_tag:entry.canonical_tag||entry.source_node||'',
          logic_id:(entry.logic_ids||[]).join('; '),
        })),
      })),
    }],
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
