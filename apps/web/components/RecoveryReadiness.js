'use client';
import {deriveRecoveryReadiness,READINESS_STATUS} from '../lib/recoveryReadiness.mjs';

const LEAF_STATUS_TEXT={
  [READINESS_STATUS.SATISFIED]:'ON',
  [READINESS_STATUS.BLOCKED]:'OFF',
  [READINESS_STATUS.DATA_MISSING]:'DATA',
};

const READY_STATUS_TEXT={
  [READINESS_STATUS.SATISFIED]:'READY',
  [READINESS_STATUS.BLOCKED]:'NOT READY',
  [READINESS_STATUS.DATA_MISSING]:'DATA MISSING',
};

function GTIcon({small=false}){
  return <svg className={small?'readiness-svg small':'readiness-svg'} viewBox="0 0 48 48" aria-hidden="true">
    <rect className="icon-plate" x="2" y="2" width="44" height="44" rx="12"/>
    <path className="icon-line" d="M9 24h8l6-7h7l6 7h3"/>
    <path className="icon-line" d="M14 28h18"/>
    <circle className="icon-fill" cx="12" cy="24" r="2.2"/>
    <circle className="icon-fill" cx="38" cy="24" r="2.2"/>
    <path className="icon-line" d="M26 15l3-4"/>
  </svg>;
}

function HRSGIcon({small=false}){
  return <svg className={small?'readiness-svg small':'readiness-svg'} viewBox="0 0 48 48" aria-hidden="true">
    <rect className="icon-plate" x="2" y="2" width="44" height="44" rx="12"/>
    <rect className="icon-line" x="13" y="11" width="17" height="22" rx="2"/>
    <path className="icon-line" d="M30 16h6v18h-6"/>
    <path className="icon-line" d="M13 18H9m4 8H9m4 8H9"/>
    <path className="icon-line" d="M18 33v4m7-4v4"/>
  </svg>;
}

function STIcon({small=false}){
  return <svg className={small?'readiness-svg small':'readiness-svg'} viewBox="0 0 48 48" aria-hidden="true">
    <rect className="icon-plate" x="2" y="2" width="44" height="44" rx="12"/>
    <path className="icon-line" d="M10 27h9l5-6h7l5 6h2"/>
    <path className="icon-line" d="M15 31h17"/>
    <path className="icon-line" d="M31 16c4 1 6 4 7 8"/>
    <circle className="icon-fill" cx="12" cy="27" r="2.2"/>
    <circle className="icon-fill" cx="37" cy="27" r="2.2"/>
  </svg>;
}

function LeafBadge({status}){
  return <span className="readiness-state" data-status={status}>{LEAF_STATUS_TEXT[status]||status}</span>;
}

function ReadyBadge({status}){
  return <span className="readiness-state ready-badge" data-status={status}>{READY_STATUS_TEXT[status]||status}</span>;
}

function TrainCard({train}){
  const isGt=train.id==='gt-ready';
  return <section className="readiness-train" data-status={train.status}>
    <div className="readiness-train-title">
      {isGt?<GTIcon/>:<STIcon/>}
      <div>
        <small>{isGt?'GAS TURBINE':'STEAM TURBINE'}</small>
        <strong>{train.label}</strong>
      </div>
    </div>
    <ReadyBadge status={train.status}/>
  </section>;
}

export default function RecoveryReadiness({rawData}){
  const records=rawData?.records||[];
  const readiness=deriveRecoveryReadiness(records);

  if(!records.length){
    return <section className="recovery-readiness empty-readiness">
      <div className="readiness-empty-title"><GTIcon/><HRSGIcon/><STIcon/></div>
      <div><span className="readiness-kicker">CURRENT V8 · READ ONLY</span><h3>GT / ST 재기동 준비상태</h3></div>
      <p>RAW.csv 입력 후 등록 태그의 실제 값으로 고정 Permissive 화면이 자동 갱신됩니다.</p>
    </section>;
  }

  const gt=readiness.trains.find(item=>item.id==='gt-ready');
  const st=readiness.trains.find(item=>item.id==='st-ready');

  return <section className="recovery-readiness" aria-label="GT ST 재기동 준비상태">
    <header className="readiness-head">
      <div>
        <span className="readiness-kicker">CURRENT V8 · READ ONLY</span>
        <h3>GT / ST 재기동 준비상태</h3>
        <p>프레임과 AND 관계는 고정되며, 업로드된 RAW 태그 상태만 ON/OFF로 변경됩니다.</p>
      </div>
      <div className="readiness-legend" aria-label="상태 범례">
        <span><i data-status="SATISFIED"/>ON · 조건 만족</span>
        <span><i data-status="BLOCKED"/>OFF · 미충족</span>
        <span><i data-status="DATA_MISSING"/>DATA · 태그 없음</span>
      </div>
    </header>

    <div className="readiness-train-row">
      <TrainCard train={gt}/>
      <div className="readiness-link" aria-hidden="true">←</div>
      <section className="readiness-train shared" data-status={readiness.bop_hrsg.status}>
        <div className="readiness-train-title">
          <HRSGIcon/>
          <div><small>SHARED PREREQUISITE</small><strong>{readiness.bop_hrsg.label}</strong></div>
        </div>
        <ReadyBadge status={readiness.bop_hrsg.status}/>
      </section>
      <div className="readiness-link" aria-hidden="true">→</div>
      <TrainCard train={st}/>
    </div>

    <div className="readiness-grid">
      {readiness.groups.map(group=><section className="readiness-group" key={group.id}>
        <header>
          <div>
            <h4>{group.label}</h4>
            <small>{group.affects.join(' / ')} READY TO START</small>
          </div>
          <LeafBadge status={group.status}/>
        </header>
        <div className="readiness-conditions">
          {group.conditions.map(condition=><details className="readiness-condition" key={condition.id}>
            <summary>
              <span className="condition-label"><i data-status={condition.status}/>{condition.label}</span>
              <LeafBadge status={condition.status}/>
            </summary>
            <dl>
              <div><dt>Source Tag</dt><dd>{condition.source_key||condition.aliases?.[0]||'—'}</dd></div>
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
      {readiness.blocked_count?<div className="readiness-blockers"><b>현재 Blocking</b><span>{readiness.blockers.map(item=>`${item.label} → ${item.affects.join('/')}`).join(' · ')}</span></div>:null}
      {readiness.missing_count?<div className="readiness-missing"><b>데이터 누락</b><span>{readiness.missing_count}개 필수 입력 태그를 RAW에서 찾지 못했습니다.</span></div>:null}
      {!readiness.blocked_count&&!readiness.missing_count?<div className="readiness-clear"><b>Blocking 없음</b><span>현재 모델 조건이 모두 ON입니다.</span></div>:null}
      <p>Current V8 등록 태그로 계산한 모델 기반 준비상태이며 실제 사업소 APS 기동 승인 로직 또는 조작 명령은 아닙니다.</p>
    </footer>
  </section>;
}
