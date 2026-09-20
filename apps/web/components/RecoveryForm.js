'use client';
import {normalizeRecovery,recoveryStatusLabel,validateRecovery} from '../lib/recoveryModel.mjs';

export default function RecoveryForm({value,onChange,catalog=[]}){
  // Controlled inputs retain unfinished spaces/lines; validation uses a normalized snapshot.
  const recovery={...normalizeRecovery(value),...value};
  const validation=validateRecovery(recovery,catalog);
  const status=recovery.status==='UNKNOWN'&&!recovery.decision_entered?'':recovery.status;
  const evidence=[...new Set(catalog.map(row=>row.evidence_id||row.event_id).filter(Boolean))];
  function edit(field,next){onChange({...recovery,[field]:next,approved_at:''});}
  function selectStatus(next){
    onChange({...recovery,status:next,decision_entered:Boolean(next),approved_at:''});
  }
  function approve(){
    if(!validation.valid||!validation.recovery.approver)return;
    onChange({...validation.recovery,approved_at:new Date().toISOString()});
  }
  return <section className="recovery-form" aria-label="복구 기록 입력">
    <div className="recovery-fields">
      <label>복구 상태<select aria-label="복구 상태" value={status} onChange={event=>selectStatus(event.target.value)}>
        <option value="">선택</option>
        {['RECOVERED','PARTIAL','NOT_RECOVERED','UNKNOWN'].map(state=><option key={state} value={state}>{recoveryStatusLabel(state)}</option>)}
      </select></label>
      <label>복구 시각<input aria-label="복구 시각" type="datetime-local" value={recovery.recovered_at} onChange={event=>edit('recovered_at',event.target.value)}/></label>
      <label>수행자<input aria-label="수행자" value={recovery.operator} onChange={event=>edit('operator',event.target.value)}/></label>
      <label>기록상 승인자<input aria-label="기록상 승인자" value={recovery.approver} onChange={event=>edit('approver',event.target.value)}/></label>
      <label className="recovery-wide">실제 수행 조치<textarea aria-label="실제 수행 조치" rows={3} value={recovery.actions} onChange={event=>edit('actions',event.target.value)}/></label>
      <label className="recovery-wide">재기동 조건<textarea aria-label="재기동 조건" rows={3} value={recovery.restart_conditions} onChange={event=>edit('restart_conditions',event.target.value)}/></label>
      <label className="recovery-wide">복구 근거 ID<select multiple size={5} aria-label="복구 근거 ID" value={recovery.evidence_ids} onChange={event=>edit('evidence_ids',[...event.target.selectedOptions].map(option=>option.value))}>
        {validation.missing_evidence.map(id=><option key={id} value={id}>{id} · 현재 근거 없음</option>)}
        {evidence.map(id=><option key={id} value={id}>{id}</option>)}
      </select><small>현재 분석 근거에서 선택합니다. Ctrl/Cmd 키로 여러 근거를 선택하거나 해제할 수 있습니다.</small></label>
    </div>
    {validation.missing_evidence.length>0&&<p className="warning-box">선택한 근거를 현재 분석에서 찾을 수 없습니다: {validation.missing_evidence.join(', ')}</p>}
    <div className="recovery-approval"><button className="export-button" type="button" disabled={!validation.valid||!validation.recovery.approver||Boolean(recovery.approved_at)} onClick={approve}>승인 기록</button>{recovery.approved_at?<span>승인 기록 시각: {recovery.approved_at}</span>:null}</div>
  </section>;
}
