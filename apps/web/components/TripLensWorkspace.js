'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_LOGIC_SUMMARY,
  DEMO_ANALYSIS,
  EMPTY_ANALYSIS,
  STATUS_LABELS,
  WORKSPACE_TABS,
} from '../lib/contracts';

const API_BASE = (process.env.NEXT_PUBLIC_TRIPLENS_API_BASE || 'https://triplens-agent-api-preview.vercel.app').replace(/\/$/, '');
const DIRECT_UPLOAD_LIMIT = 4_000_000;

function splitCsvLine(line) {
  const cells = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        cell += '"';
        i += 1;
      } else {
        quoted = !quoted;
      }
    } else if (ch === ',' && !quoted) {
      cells.push(cell);
      cell = '';
    } else {
      cell += ch;
    }
  }
  cells.push(cell);
  return cells;
}

async function summarizeEventFile(file) {
  if (!file) return { rows: 0, dcs: 0, ecms: 0, trip: 0 };
  const text = await file.text();
  const lines = text.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return { rows: 0, dcs: 0, ecms: 0, trip: 0 };
  const header = splitCsvLine(lines[0]);
  const sourceIndex = header.indexOf('source');
  const eventClassIndex = header.indexOf('event_class');
  const tagIndex = header.indexOf('tag');
  let dcs = 0;
  let ecms = 0;
  let trip = 0;
  for (const line of lines.slice(1)) {
    const row = splitCsvLine(line);
    const source = String(row[sourceIndex] || '').toUpperCase();
    const eventClass = String(row[eventClassIndex] || '').toUpperCase();
    const tag = String(row[tagIndex] || '').toUpperCase();
    if (source.includes('DCS')) dcs += 1;
    if (source.includes('ECMS') || source.includes('OPENMODELICA')) ecms += 1;
    if (eventClass.includes('PROTECTION') || tag.includes('TRIP')) trip += 1;
  }
  return { rows: lines.length - 1, dcs, ecms, trip };
}

function ClaimCard({ title, item }) {
  const status = item?.status || 'UNKNOWN';
  return (
    <section className="claim-card">
      <div className="claim-head">
        <span>{title}</span>
        <strong>{STATUS_LABELS[status] || status}</strong>
      </div>
      <div className="claim-text">{item?.claim || '분석 결과 대기'}</div>
      <div className="claim-meta">
        <span>근거: {(item?.evidence_ids || []).join(', ') || '—'}</span>
        <span>태그: {(item?.related_tags || []).join(', ') || '—'}</span>
        {item?.recorded_time ? <span>시각: {item.recorded_time}s</span> : null}
      </div>
    </section>
  );
}

function CauseView({ analysis }) {
  return (
    <div className="panel-stack">
      <div className="section-heading">
        <div>
          <div className="eyebrow">HYBRID AGENT RESULT</div>
          <h2>원인 분석</h2>
        </div>
        <div className={analysis.verification_gate === 'PASS' ? 'gate pass' : 'gate hold'}>
          Verification Gate · {analysis.verification_gate || 'HOLD'}
        </div>
      </div>
      <ClaimCard title="Primary Cause · 선행 원인" item={analysis.primary_cause} />
      <ClaimCard title="Direct Trigger · 직접 Trip 원인" item={analysis.direct_trigger} />
      <section className="report-table">
        <h3>Propagation · 파급 과정</h3>
        {(analysis.propagation || []).length ? analysis.propagation.map((item, i) => (
          <div className="table-row" key={`prop-${i}`}>
            <span>{i + 1}</span>
            <span>{STATUS_LABELS[item.status] || item.status}</span>
            <span>{item.claim}</span>
            <span>{(item.evidence_ids || []).join(', ')}</span>
          </div>
        )) : <div className="empty-line">파급 과정 분석 대기</div>}
      </section>
      <section className="report-table">
        <h3>Causal Chain</h3>
        {(analysis.causal_chain || []).length ? analysis.causal_chain.map((item, i) => (
          <div className="timeline-line" key={`chain-${i}`}><b>{String(i + 1).padStart(2, '0')}</b><span>{typeof item === 'string' ? item : item.claim || item.description || JSON.stringify(item)}</span></div>
        )) : <div className="empty-line">인과관계 구성 대기</div>}
      </section>
    </div>
  );
}

function TimelineView({ analysis, summary }) {
  return (
    <div className="panel-stack">
      <div className="section-heading">
        <div>
          <div className="eyebrow">EVENT + RAW</div>
          <h2>사고 진행 과정</h2>
        </div>
        <span className="muted">{summary.rows} EVENT rows</span>
      </div>
      <div className="metric-strip">
        <div><b>{summary.dcs}</b><span>DCS EVENT</span></div>
        <div><b>{summary.ecms}</b><span>ECMS EVENT</span></div>
        <div><b>{summary.trip}</b><span>TRIP / PROTECTION</span></div>
        <div><b>{(analysis.critical_events || []).length}</b><span>Critical Events</span></div>
      </div>
      <section className="report-table">
        <h3>Critical Events</h3>
        {(analysis.critical_events || []).length ? analysis.critical_events.map((item, i) => (
          <div className="table-row critical" key={`ce-${i}`}>
            <span>{item.recorded_time || '—'}</span>
            <span>{STATUS_LABELS[item.status] || item.status}</span>
            <span>{item.claim}</span>
            <span>{(item.evidence_ids || []).join(', ') || '—'}</span>
          </div>
        )) : <div className="empty-line">Dual Log 입력 후 Gemini가 사고적으로 중요한 Event를 선택합니다.</div>}
      </section>
      <div className="note">전체 SOE는 유지하며 Critical Events는 강조용 부분집합입니다.</div>
    </div>
  );
}

function ChecksView() {
  return (
    <div className="panel-stack">
      <div className="section-heading"><div><div className="eyebrow">READ-ONLY CHECKLIST</div><h2>즉시 확인·대응</h2></div></div>
      <div className="warning-box">조작 지시가 아니라 EVENT/RAW 근거를 기준으로 한 우선 확인 항목입니다.</div>
      {['Trip / Latch 선후관계', 'Breaker 상태', '속도·유량 공정 응답', 'Logic Master 등록 여부', '반대근거 존재 여부'].map((x, i) => (
        <div className="check-row" key={x}><span>{String(i + 1).padStart(2, '0')}</span><strong>{x}</strong><em>분석 후 상태 표시</em></div>
      ))}
    </div>
  );
}

function RecoveryView({ analysis }) {
  const hold = analysis.verification_gate !== 'PASS';
  return (
    <div className="panel-stack">
      <div className="section-heading"><div><div className="eyebrow">HUMAN APPROVAL REQUIRED</div><h2>복구 판단</h2></div></div>
      <div className={hold ? 'recovery-card hold' : 'recovery-card pass'}>
        <span>검증 상태</span><b>{hold ? 'HOLD · 검증 미완료' : 'PASS · 검증 통과'}</b>
        <p>TripLens는 재기동 명령을 생성하지 않습니다. 담당자가 증거와 미확인 항목을 검토해 최종 승인합니다.</p>
      </div>
      <div className="check-row"><span>01</span><strong>Evidence 연결</strong><em>{hold ? '검토 필요' : '확인'}</em></div>
      <div className="check-row"><span>02</span><strong>Logic Master</strong><em>{hold ? '검토 필요' : '확인'}</em></div>
      <div className="check-row"><span>03</span><strong>Counter Evidence</strong><em>{(analysis.counter_evidence || []).length ? '존재' : '미검출/검토 필요'}</em></div>
      <div className="check-row"><span>04</span><strong>Human Final Approval</strong><em>REQUIRED</em></div>
    </div>
  );
}

function EvidenceView({ analysis }) {
  const evidence = useMemo(() => {
    const rows = [];
    for (const item of [...(analysis.critical_events || []), analysis.primary_cause, analysis.direct_trigger, ...(analysis.propagation || [])]) {
      if (!item) continue;
      for (const id of item.evidence_ids || []) {
        rows.push({ id, claim: item.claim || '', status: item.status || 'UNKNOWN', tags: (item.related_tags || []).join(', ') });
      }
    }
    return rows;
  }, [analysis]);
  return (
    <div className="panel-stack">
      <div className="section-heading"><div><div className="eyebrow">EVIDENCE EXPLORER</div><h2>Event 근거</h2></div></div>
      <section className="report-table">
        <div className="table-head"><span>근거 ID</span><span>상태</span><span>연결 Claim</span><span>관련 태그</span></div>
        {evidence.length ? evidence.map((row, i) => (
          <div className="table-row" key={`${row.id}-${i}`}><span>{row.id}</span><span>{row.status}</span><span>{row.claim}</span><span>{row.tags || '—'}</span></div>
        )) : <div className="empty-line">Evidence ID가 아직 없습니다.</div>}
      </section>
    </div>
  );
}

export default function TripLensWorkspace({ mode = 'blind' }) {
  const [activeTab, setActiveTab] = useState('timeline');
  const [eventFile, setEventFile] = useState(null);
  const [rawFile, setRawFile] = useState(null);
  const [summary, setSummary] = useState({ rows: 0, dcs: 0, ecms: 0, trip: 0 });
  const [analysis, setAnalysis] = useState(mode === 'demo' ? DEMO_ANALYSIS : EMPTY_ANALYSIS);
  const [logic, setLogic] = useState(DEFAULT_LOGIC_SUMMARY);
  const [drawer, setDrawer] = useState(false);
  const [busy, setBusy] = useState(false);
  const [apiMessage, setApiMessage] = useState(API_BASE ? 'API 연결 대기' : 'API URL 미설정 · UI Preview');
  const [reportOpen, setReportOpen] = useState(false);

  useEffect(() => {
    if (!API_BASE) return;
    fetch(`${API_BASE}/contract`)
      .then((r) => r.ok ? r.json() : Promise.reject(new Error('contract unavailable')))
      .then((data) => {
        if (data.logic_summary) setLogic(data.logic_summary);
        setApiMessage('Agent API 연결됨');
      })
      .catch(() => setApiMessage('Agent API 연결 확인 필요'));
  }, []);

  async function onEventFile(file) {
    setEventFile(file || null);
    if (file) setSummary(await summarizeEventFile(file));
    else setSummary({ rows: 0, dcs: 0, ecms: 0, trip: 0 });
  }

  async function runAnalysis() {
    if (!eventFile || !rawFile) return;
    if (!API_BASE) {
      setApiMessage('NEXT_PUBLIC_TRIPLENS_API_BASE 설정 후 분석 가능');
      return;
    }
    if (eventFile.size + rawFile.size > DIRECT_UPLOAD_LIMIT) {
      setApiMessage('직접 업로드 한도 초과 · Vercel Blob 경로 필요');
      return;
    }
    setBusy(true);
    setApiMessage('Gemini Hybrid Agent 분석 중');
    try {
      const body = new FormData();
      body.append('event', eventFile);
      body.append('raw', rawFile);
      const response = await fetch(`${API_BASE}/analyze`, { method: 'POST', body });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.message || 'analysis failed');
      setAnalysis(data.analysis || EMPTY_ANALYSIS);
      setApiMessage(`Run ${data.run_id || 'completed'} · ${data.analysis?.verification_gate || 'HOLD'}`);
      setActiveTab('cause');
    } catch (error) {
      setApiMessage(error instanceof Error ? error.message : '분석 실패');
    } finally {
      setBusy(false);
    }
  }

  const combinedSize = (eventFile?.size || 0) + (rawFile?.size || 0);
  const inputReady = Boolean(eventFile && rawFile);

  let view = <TimelineView analysis={analysis} summary={summary} />;
  if (activeTab === 'cause') view = <CauseView analysis={analysis} />;
  if (activeTab === 'checks') view = <ChecksView />;
  if (activeTab === 'recovery') view = <RecoveryView analysis={analysis} />;
  if (activeTab === 'evidence') view = <EvidenceView analysis={analysis} />;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">TL</div>
          <div><h1>TripLens</h1><span>DUAL-INPUT ACCIDENT ANALYSIS</span></div>
        </div>
        <div className="status-rail">
          <div><span>입력 상태</span><b>{inputReady || mode === 'demo' ? 'Dual Log 준비' : 'Dual Log 대기'}</b></div>
          <div><span>DCS EVENT</span><b>{summary.dcs}</b></div>
          <div><span>ECMS EVENT</span><b>{summary.ecms}</b></div>
          <div><span>TRIP</span><b>{summary.trip}</b></div>
          <div className="dual-badge">DUAL LOG = EVENT + RAW</div>
        </div>
      </header>

      {mode === 'demo' ? <div className="demo-banner">DEMO ONLY · SYNTHETIC · 운영 데이터가 아닙니다.</div> : null}

      <div className="workspace">
        <aside className="sidebar">
          <div className="side-title">ANALYSIS WORKSPACE</div>
          <nav>
            {WORKSPACE_TABS.map((tab) => (
              <button key={tab.id} className={activeTab === tab.id ? 'nav-item active' : 'nav-item'} onClick={() => setActiveTab(tab.id)}>
                <span className="nav-no">{tab.no}</span><span><b>{tab.label}</b><em>{tab.sub}</em></span>
              </button>
            ))}
          </nav>
          <div className="side-links">
            <button onClick={() => setDrawer(true)}><b>LM</b><span>Event Logic Master<em>Live {logic.live_rules} · ALARM {logic.alarm} · PROT {logic.protection}</em></span></button>
            <a href="https://www.notion.so/" target="_blank" rel="noreferrer"><b>N</b><span>Notion 현황판<em>개발 · 검증 기록</em></span></a>
            <a href="https://triplens-m-alarm-console.junsic25.chatgpt.site/" target="_blank" rel="noreferrer"><b>AC</b><span>알림발생기<em>Dual Log 생성 보조</em></span></a>
          </div>
          <div className="boundary">
            <b>입력 경계</b>
            <span>EVENT = 화면 사건</span>
            <span>RAW = 전체 Historian</span>
            <span>정답·주입 metadata 금지</span>
          </div>
          <a className="demo-link" href={mode === 'demo' ? '/' : '/demo'}>{mode === 'demo' ? '운영 블라인드 화면으로' : '분리된 시연 화면'}</a>
        </aside>

        <section className="main-area">
          <section className="intake">
            <div>
              <div className="eyebrow">DUAL LOG INTAKE</div>
              <h2>EVENT.csv + RAW.csv</h2>
              <p>EVENT에서 사고 시작점을 찾고 RAW Historian에서 필요한 태그만 조회합니다. 전체 Historian을 Gemini prompt에 넣지 않습니다.</p>
            </div>
            <div className="file-grid">
              <label className={eventFile ? 'file-card ready' : 'file-card'}>
                <span>EVENT.csv</span><b>{eventFile?.name || '사건 로그 · 선택 대기'}</b><em>{eventFile ? `${(eventFile.size / 1024).toFixed(1)} KB` : 'Alarm · Operator · Protection'}</em>
                <input type="file" accept=".csv,text/csv" onChange={(e) => onEventFile(e.target.files?.[0])} />
              </label>
              <label className={rawFile ? 'file-card ready' : 'file-card'}>
                <span>RAW.csv</span><b>{rawFile?.name || '전체 Historian · 선택 대기'}</b><em>{rawFile ? `${(rawFile.size / 1024).toFixed(1)} KB` : 'Analog · Digital · Command'}</em>
                <input type="file" accept=".csv,text/csv" onChange={(e) => setRawFile(e.target.files?.[0] || null)} />
              </label>
            </div>
            <div className="intake-actions">
              <span>{apiMessage}</span>
              <span>{combinedSize ? `합계 ${(combinedSize / 1024).toFixed(1)} KB` : ''}</span>
              <button disabled={!inputReady || busy || mode === 'demo'} onClick={runAnalysis}>{busy ? '분석 중…' : '이 Dual Log 분석하기'}</button>
              <button className="secondary" onClick={() => setReportOpen((v) => !v)}>고장보고서 초안 보기</button>
            </div>
          </section>

          <section className="analysis-surface">{view}</section>

          {reportOpen ? (
            <section className="report-preview">
              <div className="section-heading"><div><div className="eyebrow">FAILURE REPORT DRAFT</div><h2>설비 고장 분석보고서 (초안)</h2></div><div className="gate hold">검증 {analysis.verification_gate || 'HOLD'}</div></div>
              <div className="report-meta"><span>Analysis Engine: Gemini</span><span>Data: EVENT + RAW</span><span>Human Finalization Required</span></div>
              <ClaimCard title="선행 원인 · Primary Cause" item={analysis.primary_cause} />
              <ClaimCard title="직접 Trip 원인 · Direct Trigger" item={analysis.direct_trigger} />
              <div className="note">웹 분석 화면과 보고서의 표현은 다를 수 있으나 Evidence ID와 Engineering Status는 동일 객체를 사용합니다.</div>
            </section>
          ) : null}
        </section>
      </div>

      {drawer ? (
        <div className="drawer-backdrop" onClick={() => setDrawer(false)}>
          <aside className="logic-drawer" onClick={(e) => e.stopPropagation()}>
            <button className="drawer-close" onClick={() => setDrawer(false)}>닫기 ×</button>
            <div className="eyebrow">CURRENT V8</div>
            <h2>Event Logic Master</h2>
            <div className="logic-total"><b>{logic.live_rules}</b><span>Live Alarm / Protection rules</span></div>
            <div className="logic-row"><span>ALARM</span><b>{logic.alarm}</b></div>
            <div className="logic-row"><span>PROTECTION</span><b>{logic.protection}</b></div>
            <div className="logic-row"><span>Active Logic Core</span><b>{logic.active_logic_core}</b></div>
            <p className="muted">GPT.site의 고정 94 표시는 사용하지 않습니다. 현재 GitHub runtime registry와 Logic Core를 동적으로 표시합니다.</p>
            <div className="warning-box">미등록 관측 태그 → 로직 조건식 추론 금지</div>
          </aside>
        </div>
      ) : null}
    </main>
  );
}
