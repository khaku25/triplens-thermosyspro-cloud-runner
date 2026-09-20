'use client';
import {editRecovery,normalizeRecovery,recoveryStatusLabel,validateRecovery,workflowLabel} from '../lib/recoveryModel.mjs';

const FIELD_LABELS={status:'복구 상태',decision_entered:'복구 여부 판단',recovered_at:'복구 시각',operator:'수행자',actions:'실제 수행 조치',restart_conditions:'재기동 조건'};

export default function RecoveryForm({value,onChange,catalog=[]}){
  const recovery=normalizeRecovery(value);
  const validation=validateRecovery(recovery,catalog);
  const status=recovery.status==='UNKNOWN'&&!recovery.decision_entered?'':recovery.status;
  const evidence=[...new Set(catalog.map(row=>row.evidence_id||row.event_id).filter(Boolean))];
  function edit(field,next){onChange(editRecovery(recovery,field,next));}
  function selectStatus(next){
    onChange(editRecovery(editRecovery(recovery,'status',next),'decision_entered',Boolean(next)));
  }
  function approve(){
    if(!validateRecovery(recovery,catalog).valid||!recovery.approver)return;
    onChange({...recovery,approved_at:new Date().toISOString()});
  }
  return <section className="recovery-form" aria-label="복구 기록 입력">
    <p className="warning-box">보고서용 기록입니다. 설비 제어 또는 인증된 전자승인이 아니며, 설비 운전·재기동 판단을 대신하지 않습니다. 원인 검증과 복구 기록 승인은 독립입니다.</p>
    <p className="workflow-state" aria-live="polite">{workflowLabel(recovery)}</p>
    <div className="recovery-fields">
      <label>복구 상태<select aria-label="복구 상태" value={status} onChange={event=>selectStatus(event.target.value)}>
        <option value="">선택 대기</option>
        {['RECOVERED','PARTIAL','NOT_RECOVERED','UNKNOWN'].map(state=><option key={state} value={state}>{recoveryStatusLabel(state)}</option>)}
      </select></label>
      <label>복구 시각<input aria-label="복구 시각" type="datetime-local" value={recovery.recovered_at} onChange={event=>edit('recovered_at',event.target.value)}/></label>
      <label>수행자<input aria-label="수행자" value={recovery.operator} onChange={event=>edit('operator',event.target.value)}/></label>
      <label>기록상 승인자<input aria-label="기록상 승인자" value={recovery.approver} onChange={event=>edit('approver',event.target.value)}/></label>
      <label className="recovery-wide">실제 수행 조치<textarea aria-label="실제 수행 조치" rows={3} value={recovery.actions} onChange={event=>edit('actions',event.target.value)}/><small>공학적 미확인 선택 시 판단 근거와 미확인 사유를 기록하세요.</small></label>
      <label className="recovery-wide">재기동 조건<textarea aria-label="재기동 조건" rows={3} value={recovery.restart_conditions} onChange={event=>edit('restart_conditions',event.target.value)}/></label>
      <label className="recovery-wide">복구 근거 ID<select multiple size={5} aria-label="복구 근거 ID" value={recovery.evidence_ids} onChange={event=>edit('evidence_ids',[...event.target.selectedOptions].map(option=>option.value))}>
        {validation.missing_evidence.map(id=><option key={id} value={id}>{id} · 현재 근거 없음</option>)}
        {evidence.map(id=><option key={id} value={id}>{id}</option>)}
      </select><small>현재 Catalog에서 선택합니다. Ctrl/Cmd 키로 여러 근거를 선택하거나 해제할 수 있습니다.</small></label>
    </div>
    {validation.missing_fields.length>0&&<p className="note">입력 대기: {validation.missing_fields.map(field=>FIELD_LABELS[field]).join(', ')}</p>}
    {validation.missing_evidence.length>0&&<p className="warning-box">연결할 수 없는 복구 근거: {validation.missing_evidence.join(', ')}. 현재 근거로 변경하거나 선택을 해제하세요.</p>}
    <div className="recovery-approval"><button className="export-button" type="button" disabled={!validation.valid||!recovery.approver||Boolean(recovery.approved_at)} onClick={approve}>승인 기록</button><span>{recovery.approved_at?`승인 기록 시각: ${recovery.approved_at}`:'필수 정보와 기록상 승인자를 입력한 뒤 명시적으로 승인 기록을 남기세요.'}</span></div>
  </section>;
}
