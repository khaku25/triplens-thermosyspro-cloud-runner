'use client';
import {deriveRecoveryReadiness,READINESS_STATUS} from '../lib/recoveryReadiness.mjs';

const STATUS_TEXT={
  [READINESS_STATUS.SATISFIED]:'SATISFIED',
  [READINESS_STATUS.BLOCKED]:'BLOCKED',
  [READINESS_STATUS.DATA_MISSING]:'DATA MISSING',
};

function StateBadge({status}){
  return <span className="readiness-state" data-status={status}>{STATUS_TEXT[status]||status}</span>;
}

export default function RecoveryReadiness({rawData}){
  const records=rawData?.records||[];
  const readiness=deriveRecoveryReadiness(records);
  if(!records.length){
    return <section className="recovery-readiness empty-readiness">
      <div><span className="readiness-kicker">MODEL-DERIVED</span><h3>복구 준비상태</h3></div>
      <p>RAW.csv가 준비되면 Current V8 등록 신호를 기준으로 복구 준비조건을 계산합니다.</p>
    </section>;
  }
  return <section className="recovery-readiness" aria-label="모델 기반 복구 준비상태">
    <header className="readiness-head">
      <div>
        <span className="readiness-kicker">MODEL-DERIVED · CURRENT V8</span>
        <h3>복구 준비상태</h3>
        <p>등록된 보호·설비 상태를 AND 조건으로 평가합니다.</p>
      </div>
      <div className="readiness-final" data-status={readiness.status}>
        <small>FINAL READINESS</small>
        <strong>{readiness.ready?'READY':'NOT READY'}</strong>
        <span>{readiness.satisfied} / {readiness.total} SATISFIED</span>
      </div>
    </header>

    <div className="readiness-grid">
      {readiness.groups.map(group=><section className="readiness-group" key={group.id}>
        <header><h4>{group.label}</h4><StateBadge status={group.status}/></header>
        <div className="readiness-conditions">
          {group.conditions.map(condition=><details className="readiness-condition" key={condition.id}>
            <summary>
              <span>{condition.label}</span>
              <StateBadge status={condition.status}/>
            </summary>
            <dl>
              <div><dt>Source</dt><dd>{condition.source_key||condition.aliases?.[0]||'—'}</dd></div>
              <div><dt>현재 값</dt><dd>{condition.raw_value==null?'—':String(condition.raw_value)}</dd></div>
              <div><dt>Model Time</dt><dd>{condition.model_time_s||'—'}</dd></div>
              <div><dt>Logic</dt><dd>{condition.logic_id||'—'}</dd></div>
            </dl>
          </details>)}
        </div>
      </section>)}
    </div>

    <footer className="readiness-foot">
      {readiness.blocked_count?<div className="readiness-blockers"><b>Blocking condition</b><span>{readiness.blockers.map(item=>item.label).join(' · ')}</span></div>:null}
      {readiness.missing_count?<div className="readiness-missing"><b>Data completeness</b><span>{readiness.missing_count}개 입력 미확인</span></div>:null}
      <p>실제 발전소 APS 기동 Permissive 또는 운전 승인 로직이 아니라, Current V8 패키지의 등록 신호로 계산한 모델 기반 복구 준비 표시입니다.</p>
    </footer>
  </section>;
}
