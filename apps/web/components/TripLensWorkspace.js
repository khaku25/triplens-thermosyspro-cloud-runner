'use client';

import {useEffect,useMemo,useRef,useState} from 'react';
import {LogicLibraryDialog,openLogicLibrary} from './LogicLibrary';
import RecoveryForm from './RecoveryForm';
import {WORKSPACE_TABS} from '../lib/contracts';
import {
  normalizeDisplayAnalysis,
  claimText,
  modelTime,
  parseCSV,
  summarizeEvents,
  buildDraftRows,
  draftCSV,
  REPORT_COLUMNS,
  displayError,
  clearSession,
} from '../lib/analysisClient.mjs';
import {buildEvidenceLogicTargets} from '../lib/integrationTestbench.mjs';
import {mergeEvents,mergeEvidenceCatalog} from '../lib/reportIntegrity.mjs';
import {EMPTY_RECOVERY,normalizeRecovery,recoveryStatusLabel} from '../lib/recoveryModel.mjs';
import {applyRecoveryRows,buildWorkspaceExportReport} from '../lib/reportAdapter.mjs';
import {
  analysisDisplayData,
  conciseClaim,
  friendlyTag,
  inputStatus,
  summarizeEvidence,
} from '../lib/workspacePresentation.mjs';
import reportExporter from '../lib/reportExporter.cjs';
import '../app/integration.css';

const API_BASE=(process.env.NEXT_PUBLIC_TRIPLENS_API_BASE||'https://triplens-agent-api-preview.vercel.app').replace(/\/$/,'');
const CLAIM_STATUS_CHOICES=['UNKNOWN','OBSERVED','CANDIDATE'];
const REPORT_KEYS=['section','item','content','status','evidence_ids','tags','time','note'];
const RAW_META_FIELDS=new Set(['record_sequence','session_id','incident_id','model_time_s','wall_time_utc','collector_quality','quality','time']);
const REPORT_STATUS_TEXT={
  CONFIRMED:'확인',
  CANDIDATE:'분석 항목',
  OBSERVED:'관측',
  UNKNOWN:'확인 필요',
  INPUT_PENDING:'기록 없음',
  APPROVAL_PENDING:'기록됨',
  APPROVED:'승인 완료',
};

async function request(path,body){
  const response=await fetch(`${API_BASE}${path}`,body?{method:'POST',body}:undefined);
  let data;
  try{data=await response.json();}
  catch{throw new Error(`서버 응답을 읽지 못했습니다. HTTP ${response.status}`);}
  if(!response.ok)throw new Error(displayError(data.detail||data));
  return data;
}

function rawTagCount(data){
  return data?.fields?.filter(field=>!RAW_META_FIELDS.has(field)).length||0;
}

function reportStatusLabel(status){
  return REPORT_STATUS_TEXT[status]||recoveryStatusLabel(status);
}

function EvidenceLinks({ids,onOpen,named=false}){
  const values=[...new Set((ids||[]).filter(Boolean))];
  if(!values.length)return <span className="muted">연결된 근거 없음</span>;
  return <span className="evidence-links">{values.map((id,index)=><button key={id} onClick={()=>onOpen({kind:'evidence',value:id})}>{named?`근거 ${index+1}`:id}</button>)}</span>;
}

function ClaimEvidence({item,onOpen}){
  const tags=summarizeEvidence(item?.related_tags||[],5);
  const ids=[...new Set((item?.evidence_ids||[]).filter(Boolean))];
  if(!tags.visible.length&&!ids.length)return null;
  return <div className="claim-evidence">
    {tags.visible.length?<div className="evidence-pills" aria-label="핵심 근거 태그">{tags.visible.map(tag=><button key={tag} onClick={()=>onOpen({kind:'tag',value:tag})}>{friendlyTag(tag)}</button>)}</div>:null}
    <details>
      <summary>상세 근거 보기{ids.length?` · ${ids.length}건`:''}</summary>
      <div className="detail-evidence-list">
        <EvidenceLinks ids={ids} onOpen={onOpen}/>
        {[...tags.visible,...tags.hidden].map(tag=><button className="tag-link" key={tag} onClick={()=>onOpen({kind:'tag',value:tag})}>{friendlyTag(tag)}</button>)}
      </div>
    </details>
  </div>;
}

function ClaimCard({title,item,onOpen}){
  const text=conciseClaim(claimText(item));
  return <section className="claim-card cause-card">
    <div className="claim-head"><h3>{title}</h3>{item?.model_time_s!=null?<time>{modelTime(item.model_time_s)}</time>:null}</div>
    <div className="claim-text">{text.summary||'분석 결과가 없습니다.'}</div>
    {text.detail?<details className="claim-detail"><summary>전체 설명 보기</summary><p>{text.detail}</p></details>:null}
    <ClaimEvidence item={item} onOpen={onOpen}/>
  </section>;
}

function AnalysisList({items,onOpen}){
  if(!items?.length)return <p className="empty-line">표시할 분석 결과가 없습니다.</p>;
  return <div className="analysis-list">{items.map((item,index)=>{
    const text=conciseClaim(claimText(item),150);
    return <article key={`${item?.claim||'item'}-${index}`}>
      <div><b>{index+1}</b><p>{text.summary}</p>{item?.model_time_s!=null?<time>{modelTime(item.model_time_s)}</time>:null}</div>
      <ClaimEvidence item={item} onOpen={onOpen}/>
      {text.detail?<details><summary>전체 설명 보기</summary><p>{text.detail}</p></details>:null}
    </article>;
  })}</div>;
}

function EventTable({events,onOpen}){
  return <div className="scroll-table"><table><thead><tr><th>모델 시각</th><th>설비</th><th>사건</th><th>원천</th><th>근거</th></tr></thead><tbody>{events.map((event,index)=><tr key={event.event_id||index}><td>{modelTime(event.model_time_s)}</td><td>{event.equipment||'—'}</td><td>{event.message||friendlyTag(event.tag)}</td><td>{event.source||'—'}</td><td><EvidenceLinks ids={[event.evidence_id||event.event_id]} onOpen={onOpen} named/></td></tr>)}</tbody></table></div>;
}

function WaitingPanel({status}){
  return <div className="waiting-panel"><div className="waiting-mark">TL</div><h2>{status.title}</h2>{status.detail?<p>{status.detail}</p>:null}</div>;
}

export default function TripLensWorkspace({mode='blind'}){
  const [activeTab,setActiveTab]=useState('timeline');
  const [eventFile,setEventFile]=useState(null);
  const [rawFile,setRawFile]=useState(null);
  const [eventData,setEventData]=useState(null);
  const [rawData,setRawData]=useState(null);
  const [result,setResult]=useState(null);
  const [contract,setContract]=useState(null);
  const [statusText,setStatusText]=useState('');
  const [busy,setBusy]=useState(false);
  const [detail,setDetail]=useState(null);
  const [reportOpen,setReportOpen]=useState(false);
  const [reportRows,setReportRows]=useState([]);
  const [evidenceQuery,setEvidenceQuery]=useState('');
  const [recovery,setRecovery]=useState(()=>normalizeRecovery(EMPTY_RECOVERY));
  const version=useRef(0);

  const analysis=useMemo(()=>normalizeDisplayAnalysis(result?.analysis||{}),[result]);
  const currentData=useMemo(()=>analysisDisplayData({result}),[result]);
  const events=useMemo(()=>result?mergeEvents(eventData?.records||[],currentData.events):[],[result,eventData,currentData]);
  const catalog=useMemo(()=>result?mergeEvidenceCatalog(events,currentData.catalog):[],[result,events,currentData]);
  const summary=useMemo(()=>summarizeEvents(events),[events]);
  const displayReportRows=useMemo(()=>applyRecoveryRows(reportRows,recovery),[reportRows,recovery]);
  const exportReport=useMemo(()=>buildWorkspaceExportReport({
    result,analysis,events,catalog,reportRows:displayReportRows,recovery,
    eventFileName:eventFile?.name,rawFileName:rawFile?.name,
  }),[result,analysis,events,catalog,displayReportRows,recovery,eventFile,rawFile]);
  const missingEvidence=[...new Set([...exportReport.reference_integrity.missing,...exportReport.recovery_validation.missing_evidence])];
  const exportBlocked=missingEvidence.length>0;
  const ready=Boolean(eventFile&&rawFile&&eventData&&rawData);
  const status=inputStatus({ready,busy,complete:Boolean(result),eventRows:eventData?.records.length||0,rawTagCount:rawTagCount(rawData)});
  const logic=contract?.logic_summary;

  useEffect(()=>{
    clearSession().catch(()=>{});
    let active=true;
    request('/contract').then(value=>{if(active)setContract(value);}).catch(()=>{});
    return()=>{active=false;};
  },[]);

  function resetAnalysisState(){
    setResult(null);
    setDetail(null);
    setReportRows([]);
    setRecovery(normalizeRecovery(EMPTY_RECOVERY));
    setReportOpen(false);
    setEvidenceQuery('');
    setActiveTab('timeline');
    setStatusText('');
    clearSession().catch(()=>{});
  }

  async function selectFile(kind,file){
    version.current+=1;
    resetAnalysisState();
    if(kind==='event'){
      setEventFile(file||null);
      setEventData(null);
    }else{
      setRawFile(file||null);
      setRawData(null);
    }
    if(!file)return;
    try{
      const parsed=parseCSV(await file.text());
      if(kind==='event')setEventData(parsed);
      else setRawData(parsed);
    }catch(error){setStatusText(error.message);}
  }

  async function analyze(){
    if(!ready||busy||result)return;
    if(eventFile.size+rawFile.size>4_000_000){
      setStatusText('두 파일의 합계는 4 MB 이하여야 합니다.');
      return;
    }
    const revision=version.current;
    const form=()=>{
      const body=new FormData();
      body.append('event',eventFile,eventFile.name||'EVENT.csv');
      body.append('raw',rawFile,rawFile.name||'RAW.csv');
      return body;
    };
    setBusy(true);
    setStatusText('');
    try{
      const prepared=await request('/bootstrap',form());
      if(revision!==version.current)return;
      setContract(prepared.contract);
      if(prepared.evidence_readiness?.status!=='PASS')throw new Error('EVENT.csv와 RAW.csv의 시간 범위와 형식을 확인해 주세요.');
      const data=await request('/analyze',form());
      if(revision!==version.current)return;
      data.analysis=normalizeDisplayAnalysis(data.analysis);
      const mergedEvents=mergeEvents(eventData.records,data.events||[]);
      const mergedCatalog=mergeEvidenceCatalog(mergedEvents,data.evidence_catalog||[]);
      setResult(data);
      setReportRows(buildDraftRows({...data,events:mergedEvents,evidence_catalog:mergedCatalog}));
      setActiveTab('cause');
    }catch(error){
      setStatusText(displayError(error));
    }finally{
      if(revision===version.current)setBusy(false);
    }
  }

  function clear(){
    version.current+=1;
    setEventFile(null);
    setRawFile(null);
    setEventData(null);
    setRawData(null);
    resetAnalysisState();
  }

  function exportCSV(){
    if(exportBlocked)return;
    const blob=new Blob([draftCSV(exportReport.report_rows)],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const anchor=document.createElement('a');
    anchor.href=url;
    anchor.download=`TripLens_고장분석보고서_${result?.run_id||'analysis'}.csv`;
    anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  function exportPDF(){if(!exportBlocked)reportExporter.printReport(exportReport);}
  function exportDetailedCSV(){if(!exportBlocked)reportExporter.downloadPinpointCsv(exportReport,`TripLens_상세분석데이터_${result?.run_id||'analysis'}.csv`);}

  function editReportRow(row,key,value){
    setReportRows(rows=>rows.map(existing=>existing.row_id===row.row_id?{...existing,[key]:value}:existing));
  }

  const detailRows=detail?catalog.filter(entry=>detail.kind==='evidence'
    ?entry.evidence_id===detail.value
    :[entry.tag,entry.source_node,entry.canonical_tag].includes(detail.value)):[];

  let view;
  if(!result){
    view=<WaitingPanel status={status}/>;
  }else if(detail){
    view=<div className="panel-stack evidence-page">
      <button className="back-button" onClick={()=>setDetail(null)}>이전 화면</button>
      <div className="section-heading"><h2>{detail.kind==='evidence'?'근거 상세':'태그 상세 정보'}</h2></div>
      {detailRows.length?detailRows.map((entry,index)=>{
        const targets=buildEvidenceLogicTargets(entry);
        return <section className="claim-card evidence-detail" key={entry.evidence_id||index}>
          <h3>{entry.display_name||entry.message||friendlyTag(entry.source_node||entry.tag)}</h3>
          <dl>
            <div><dt>모델 시각</dt><dd>{modelTime(entry.model_time_s)}</dd></div>
            {entry.wall_time_utc?<div><dt>기록 시각</dt><dd>{entry.wall_time_utc}</dd></div>:null}
            <div><dt>태그</dt><dd>{entry.canonical_tag||entry.source_node||entry.tag||'—'}</dd></div>
            <div><dt>값 / 상태</dt><dd>{String(entry.value??'—')} {entry.state?`/ ${entry.state}`:''}</dd></div>
          </dl>
          {entry.message?<p>{entry.message}</p>:null}
          {targets.tags.length||targets.rules.length?<div className="logic-targets" aria-label="로직 연결">{targets.tags.map(tag=><button type="button" key={`tag-${tag}`} onClick={()=>openLogicLibrary({tag})}>태그 상세 · {friendlyTag(tag)}</button>)}{targets.rules.map(rule=><button type="button" key={`rule-${rule}`} onClick={()=>openLogicLibrary({rule})}>로직 연결 · {rule}</button>)}</div>:null}
        </section>;
      }):<div className="empty-state">연결된 상세 근거가 없습니다.</div>}
    </div>;
  }else if(activeTab==='cause'){
    view=<div className="panel-stack cause-layout">
      <div className="section-heading"><div><span className="section-kicker">INCIDENT ANALYSIS</span><h2>원인 분석</h2></div></div>
      <div className="cause-grid">
        <ClaimCard title="Primary Cause" item={analysis.primary_cause} onOpen={setDetail}/>
        <ClaimCard title="Direct Trigger" item={analysis.direct_trigger} onOpen={setDetail}/>
      </div>
      <section className="analysis-section">
        <div className="analysis-section-head"><div><span>03</span><h3>Propagation</h3></div><p>사고의 파급 과정</p></div>
        <AnalysisList items={analysis.propagation} onOpen={setDetail}/>
      </section>
      <section className="analysis-section causal-section">
        <div className="analysis-section-head"><div><span>04</span><h3>Causal Chain</h3></div><p>시간순 인과관계</p></div>
        <details><summary>상세 시간순서 보기</summary><AnalysisList items={analysis.causal_chain} onOpen={setDetail}/></details>
      </section>
    </div>;
  }else if(activeTab==='timeline'){
    view=<div className="panel-stack">
      <div className="section-heading"><h2>사고 진행 과정</h2><span>EVENT {events.length}건</span></div>
      <section className="analysis-section"><h3>주요 사건</h3><AnalysisList items={analysis.critical_events} onOpen={setDetail}/></section>
      <details className="analysis-details"><summary>전체 사건 기록 보기 · {events.length}건</summary><EventTable events={events} onOpen={setDetail}/></details>
    </div>;
  }else if(activeTab==='checks'){
    const checks=[...analysis.additional_evidence_required,...analysis.review_recommendations];
    view=<div className="panel-stack"><div className="section-heading"><h2>즉시 확인·대응</h2></div>{checks.length?checks.map((text,index)=><div className="check-row" key={index}><span>{String(index+1).padStart(2,'0')}</span><p>{text}</p></div>):<div className="empty-state">추가 확인 항목이 없습니다.</div>}</div>;
  }else if(activeTab==='recovery'){
    view=<div className="panel-stack"><div className="section-heading"><h2>복구 기록</h2></div><RecoveryForm value={recovery} onChange={setRecovery} catalog={catalog}/></div>;
  }else{
    const filtered=catalog.filter(entry=>JSON.stringify([entry.evidence_id,entry.tag,entry.source_node,entry.canonical_tag]).toLowerCase().includes(evidenceQuery.toLowerCase()));
    view=<div className="panel-stack"><div className="section-heading"><h2>Event / RAW 근거</h2><span>{filtered.length}건</span></div><input className="filter-input" aria-label="근거 검색" placeholder="근거 또는 태그 검색" value={evidenceQuery} onChange={event=>setEvidenceQuery(event.target.value)}/><div className="scroll-table"><table><thead><tr><th>근거</th><th>종류</th><th>모델 시각</th><th>신호</th><th>값</th></tr></thead><tbody>{filtered.map((entry,index)=><tr key={entry.evidence_id||index}><td><EvidenceLinks ids={[entry.evidence_id]} onOpen={setDetail} named/></td><td>{entry.source_kind||entry.source||'—'}</td><td>{modelTime(entry.model_time_s)}</td><td><button className="tag-link" onClick={()=>setDetail({kind:'tag',value:entry.source_node||entry.tag})}>{friendlyTag(entry.source_node||entry.canonical_tag||entry.tag)}</button></td><td>{String(entry.value??'—')}</td></tr>)}</tbody></table></div></div>;
  }

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark">TL</div><div><h1>TripLens</h1><span>DUAL-INPUT ACCIDENT ANALYSIS</span></div></div>
      <div className="status-rail">
        <div><span>입력 상태</span><b>{result?'분석 완료':ready?'분석 준비':'Dual Log 대기'}</b></div>
        <div><span>DCS EVENT</span><b>{summary.dcs}</b></div>
        <div><span>ECMS EVENT</span><b>{summary.ecms}</b></div>
        <div><span>TRIP</span><b>{summary.protection}</b></div>
      </div>
    </header>
    {mode==='demo'?<div className="demo-banner">시연용 분석 화면</div>:null}
    <div className="workspace">
      <aside className="sidebar">
        <div className="side-title">ANALYSIS WORKSPACE</div>
        <nav>{WORKSPACE_TABS.map(tab=><button disabled={!result} className={`nav-item ${activeTab===tab.id?'active':''}`} key={tab.id} onClick={()=>{setActiveTab(tab.id);setDetail(null);}}><span className="nav-no">{tab.no}</span><span><b>{tab.label}</b><em>{tab.sub}</em></span></button>)}</nav>
        <div className="side-links"><button onClick={()=>openLogicLibrary()}><b>LM</b><span>Logic / TAG Master<em>{logic?`${logic.live_rules} Logic · ${logic.protection} Protection`:'태그 검색 · 로직 연결'}</em></span></button></div>
        <div className="boundary"><b>READ-ONLY</b><span>분석 및 보고서 전용</span></div>
      </aside>
      <section className="main-area">
        <section className="intake">
          <div className="intake-copy"><div className="eyebrow">DUAL LOG INTAKE</div><h2>EVENT.csv + RAW.csv</h2><p>사건 기록과 공정 데이터를 함께 분석합니다.</p></div>
          <div className="file-grid">{[
            ['event',eventFile,eventData],
            ['raw',rawFile,rawData],
          ].map(([kind,file,data])=><label className={`file-card ${file?'ready':''}`} key={kind}><span>{kind.toUpperCase()}.csv</span><b>{file?.name||'파일 선택'}</b><em>{file?`${(file.size/1024).toFixed(1)} KB · ${data?.records.length??'확인 중'}${kind==='event'?'건':'행'}${kind==='raw'&&data?` · ${rawTagCount(data)}개 태그`:''}`:''}</em><input disabled={busy} type="file" accept=".csv,text/csv" aria-label={`${kind.toUpperCase()} 파일`} onChange={event=>selectFile(kind,event.target.files?.[0])}/></label>)}</div>
          <div className="analysis-status" aria-live="polite"><b>{status.title}</b>{status.detail?<span>{status.detail}</span>:null}{statusText?<em role="alert">{statusText}</em>:null}</div>
          <div className="intake-actions">
            <button disabled={!ready||busy||Boolean(result)} onClick={analyze}>{busy?'분석 중…':result?'분석 완료':'이 Dual Log 분석하기'}</button>
            <button disabled={!result} className="secondary" onClick={()=>{setReportOpen(!reportOpen);setDetail(null);}}>고장분석 보고서 보기</button>
            <button disabled={busy} className="secondary" onClick={clear}>입력·분석 지우기</button>
          </div>
        </section>

        {result&&exportBlocked?<p className="warning-box" role="alert">일부 근거 연결을 확인한 후 내보낼 수 있습니다: {missingEvidence.length}건</p>:null}
        <section className="analysis-surface">{view}</section>

        {reportOpen&&result?<section className="report-preview">
          <div className="section-heading report-actions">
            <h2>설비 고장 분석보고서</h2>
            <button className="export-button" disabled={exportBlocked} onClick={exportPDF}>보고서 PDF 저장</button>
            <details className="export-menu"><summary>내보내기</summary><div><button className="export-button" disabled={exportBlocked} onClick={exportCSV}>보고서 CSV</button><button className="export-button" disabled={exportBlocked} onClick={exportDetailedCSV}>상세 분석 데이터 CSV</button></div></details>
          </div>
          <p className="report-help">보고서 내용을 확인하고 필요한 항목을 편집할 수 있습니다.</p>
          <div className="scroll-table"><table className="editable-report"><thead><tr>{REPORT_COLUMNS.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{displayReportRows.map((row,index)=>{
            const recoveryRow=row.row_id?.startsWith('RECOVERY-');
            return <tr key={row.row_id||index} data-row-id={row.row_id}>{REPORT_KEYS.map((key,column)=><td key={key} data-label={REPORT_COLUMNS[column]}>{key==='status'?(recoveryRow||!CLAIM_STATUS_CHOICES.includes(row.status)?<span className="report-status" data-status={row.status}>{reportStatusLabel(row.status)}</span>:<select aria-label={`보고서 ${index+1} 상태`} value={row.status} onChange={event=>editReportRow(row,key,event.target.value)}>{CLAIM_STATUS_CHOICES.map(statusValue=><option key={statusValue} value={statusValue}>{REPORT_STATUS_TEXT[statusValue]}</option>)}</select>):recoveryRow?<div className="report-readonly">{row[key]||'—'}{key==='content'?<button className="tag-link" onClick={()=>{setActiveTab('recovery');setDetail(null);requestAnimationFrame(()=>document.querySelector('.recovery-form')?.scrollIntoView({block:'start'}));}}>복구 기록에서 편집</button>:null}</div>:<textarea aria-label={`보고서 ${index+1} ${key}`} value={row[key]||''} onChange={event=>editReportRow(row,key,event.target.value)}/>}</td>)}</tr>;
          })}</tbody></table></div>
        </section>:null}
      </section>
    </div>
    <LogicLibraryDialog analysisMode/>
  </main>;
}
