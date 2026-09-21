'use client';
import {deriveRecoveryReadiness,READINESS_STATUS} from '../lib/recoveryReadiness.mjs';

const STATUS_TEXT={
  [READINESS_STATUS.SATISFIED]:'READY',
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
      <div><span className="readiness-kicker">MODEL-DERIVED</span><h3>GT / ST 재기동 준비상태</h3></div>
      <p>RAW.csv가 준비되면 Current V8 등록 신호를 기준으로 GT·ST 기동 준비조건을 계산합니다.</p>
    </section>;
  }
  return <section className="recovery-readiness" aria-label="모델 기반 GT ST 재기동 준비상태">
    <header className="readiness-head">
      <div>
        <span className="readiness-kicker">MODEL-DERIVED · CURRENT V8</span>
        <h3>GT / ST 재기동 준비상태</h3>
        <p>GT·ST 각각의 기동조건에 BOP/HRSG 공통 준비조건을 연계해 평가합니다.</p>
      </div>
      <div className="readiness-final" data-status={readiness.status}>
        <small>GT + ST START READINESS</small>
        <strong>{readiness.ready?'READY':'NOT READY'}</strong>
        <span>{readiness.satisfied} / {readiness.total} LEAF CONDITIONS SATISFIED</span>
      </div>
    </header>

    <div className="readiness-trains">
      {readiness.trains.map(train=><section className="readiness-train" data-status={train.status} key={train.id}>
        <small>{train.id==='gt-ready'?'GAS TURBINE':'STEAM TURBINE'}</small>
        <strong>{train.label}</strong>
        <StateBadge status={train.status}/>
      </section>)}
    </div>

    <section className="readiness-shared" data-status={readiness.bop_hrsg.status}>
      <div><small>SHARED PREREQUISITE</small><strong>{readiness.bop_hrsg.label}</strong></div>
      <StateBadge status={readiness.bop_hrsg.status}/>
      <div className="readiness-shared-deps">
        {readiness.bop_hrsg.dependencies.map(group=><span key={group.id}>{group.label}<StateBadge status={group.status}/></span>)}
      </div>
    </section>

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
              <div><dt>영향</dt><dd>{condition.affects?.join(' · ')||'—'} READY TO START</dd></div>
            </dl>
          </details>)}
        </div>
      </section>)}
    </div>

    <footer className="readiness-foot">
      {readiness.blocked_count?<div className="readiness-blockers"><b>Blocking condition</b><span>{readiness.blockers.map(item=>`${item.label} → ${item.affects.join('/')}`).join(' · ')}</span></div>:null}
      {readiness.missing_count?<div className="readiness-missing"><b>Data completeness</b><span>{readiness.missing_count}개 필수 입력 미확인</span></div>:null}
      <p>실제 발전소 APS 로직을 복제한 것이 아니라, Current V8에 존재하는 보호·설비 태그를 이용해 GT·ST 재기동 준비관계를 모델화한 읽기 전용 파생 표시입니다.</p>
    </footer>
  </section>;
}
