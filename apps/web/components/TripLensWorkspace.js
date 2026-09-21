'use client';

import {useEffect,useMemo,useRef,useState} from 'react';
import {LogicLibraryDialog,openLogicLibrary} from './LogicLibrary';
import LogicViewerFrame from './LogicViewerFrame';
import RecoveryForm from './RecoveryForm';
import {WORKSPACE_TABS} from '../lib/contracts';
import {
  normalizeDisplayAnalysis,
  claimText,
  modelTime,
  parseCSV,
  buildDraftRows,
  draftCSV,
  REPORT_COLUMNS,
  displayError,
  clearSession,
} from '../lib/analysisClient.mjs';
import {buildEvidenceLogicTargets} from '../lib/integrationTestbench.mjs';
import {mergeEvents,mergeEvidenceCatalog} from '../lib/reportIntegrity.mjs';
import {EMPTY_RECOVERY,hasRecoveryRecord,normalizeRecovery,recoveryStatusLabel} from '../lib/recoveryModel.mjs';
import {applyRecoveryRows,buildWorkspaceExportReport} from '../lib/reportAdapter.mjs';
import {
  analysisDisplayData,
  compactTimeline,
  conciseClaim,
  deriveOperatorAnalysis,
  displayAccidentTime,
  displayEventTime,
  friendlyTag,
  groupEvidenceRows,
  incidentMetrics,
  inputStatus,
  operatorSummary,
  prioritizeEvidenceRows,
  selectDetailEvidence,
  sortByModelTime,
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

function ClaimEvidence({item}){
  const tags=summarizeEvidence(item?.related_tags||[],5);
  const ids=[...new Set((item?.evidence_ids||[]).filter(Boolean))];
  if(!tags.visible.length&&!ids.length)return null;
  return <div className="claim-evidence">
    {tags.visible.length?<div className="evidence-pills" aria-label="핵심 근거 태그">{tags.visible.map(tag=><span key={tag}>{friendlyTag(tag)}</span>)}</div>:null}
    <span className="detail-cue">상세 보기{ids.length?` · ${ids.length}건`:''}</span>
  </div>;
}

function ClaimCard({title,item,stage,onOpen}){
  const original=claimText(item);
  const compact=conciseClaim(operatorSummary(item,stage),140);
  const summary=compact.summary;
  const detail=original&&original!==summary?original:compact.detail;
  const time=displayAccidentTime(item);
  const evidenceIds=[...new Set((item?.evidence_ids||[]).filter(Boolean))];
  const tags=[...new Set((item?.related_tags||[]).filter(Boolean))];
  const canOpen=Boolean(evidenceIds.length||tags.length||detail);
  const open=()=>canOpen&&onOpen({kind:'claim',title,summary,description:detail,evidenceIds,tags});
  return <section className={`claim-card cause-card ${canOpen?'interactive-surface':''}`} role={canOpen?'button':undefined} tabIndex={canOpen?0:undefined} aria-label={canOpen?`${title} 상세 보기`:undefined} onClick={open} onKeyDown={event=>{if(canOpen&&(event.key==='Enter'||event.key===' ')){event.preventDefault();open();}}}>
    <div className="claim-head"><h3>{title}</h3>{time.primary!=='시각 미확인'?<time>{time.primary}{time.secondary?<small>{time.secondary}</small>:null}</time>:null}</div>
    <div className="claim-text">{summary||'분석 결과가 없습니다.'}</div>
    <ClaimEvidence item={item}/>
  </section>;
}

function AnalysisList({items,stage,onOpen,limit=5}){
  if(!items?.length)return <p className="empty-line">표시할 분석 결과가 없습니다.</p>;
  const ordered=sortByModelTime(items);
  const visible=ordered.slice(0,limit);
  const hidden=ordered.slice(limit);
  const renderItem=(item,index)=>{
    const original=claimText(item);
    const compact=conciseClaim(typeof item==='string'?item:operatorSummary(item,stage),150);
    const summary=compact.summary;
    const detail=original&&original!==summary?original:compact.detail;
    const time=displayAccidentTime(item);
    const evidenceIds=[...new Set((item?.evidence_ids||[]).filter(Boolean))];
    const tags=[...new Set((item?.related_tags||[]).filter(Boolean))];
    const canOpen=Boolean(evidenceIds.length||tags.length||detail);
    const open=()=>canOpen&&onOpen({kind:'claim',title:summary,summary,description:detail,evidenceIds,tags});
    return <article key={`${item?.claim||'item'}-${index}`} className={canOpen?'interactive-surface':''} role={canOpen?'button':undefined} tabIndex={canOpen?0:undefined} aria-label={canOpen?`${summary} 상세 보기`:undefined} onClick={open} onKeyDown={event=>{if(canOpen&&(event.key==='Enter'||event.key===' ')){event.preventDefault();open();}}}>
      <div><b>{String(index+1).padStart(2,'0')}</b><p>{summary}</p>{time.primary!=='시각 미확인'?<time>{time.primary}{time.secondary?<small>{time.secondary}</small>:null}</time>:null}</div>
      <ClaimEvidence item={item}/>
    </article>;
  };
  return <div className="analysis-list">{visible.map(renderItem)}{hidden.length?<details className="hidden-analysis-items"><summary>후속 분석 {hidden.length}건 보기</summary><div>{hidden.map((item,index)=>renderItem(item,index+limit))}</div></details>:null}</div>;
}

function EventTable({events,onOpen}){
  return <div className="scroll-table"><table><thead><tr><th>Model Time</th><th>설비</th><th>사건</th><th>원천</th><th>상세</th></tr></thead><tbody>{events.map((event,index)=>{const time=displayAccidentTime(event);const ids=event.evidence_ids?.length?event.evidence_ids:[event.evidence_id||event.event_id].filter(Boolean);const title=operatorSummary(event)||event.message||friendlyTag(event.tag);const open=()=>onOpen({kind:'claim',title,evidenceIds:ids,tags:[event.source_node||event.tag].filter(Boolean)});return <tr className="interactive-row" role="button" tabIndex={0} aria-label={`${title} 상세 보기`} key={event.event_id||index} onClick={open} onKeyDown={keyEvent=>{if(keyEvent.key==='Enter'||keyEvent.key===' '){keyEvent.preventDefault();open();}}}><td><b>{time.primary}</b>{time.secondary?<small>{time.secondary}</small>:null}</td><td>{event.equipment||'—'}</td><td>{title}</td><td>{event.source||'—'}</td><td>상세 보기</td></tr>;})}</tbody></table></div>;
}

function OperatorTimeline({events,onOpen}){
  const timeline=compactTimeline(events,7);
  return <div className="operator-timeline">{timeline.visible.map((event,index)=>{const time=displayAccidentTime(event);const summary=conciseClaim(operatorSummary(event)||event.message||friendlyTag(event.tag),140).summary;const ids=event.evidence_ids?.length?event.evidence_ids:[event.evidence_id||event.event_id].filter(Boolean);const open=()=>onOpen({kind:'claim',title:summary,evidenceIds:ids,tags:[...(event.related_tags||[]),event.source_node||event.tag].filter(Boolean)});return <article className="interactive-surface" role="button" tabIndex={0} aria-label={`${summary} 상세 보기`} key={event.event_id||index} onClick={open} onKeyDown={keyEvent=>{if(keyEvent.key==='Enter'||keyEvent.key===' '){keyEvent.preventDefault();open();}}}><time><b>{time.primary}</b>{time.secondary?<small>{time.secondary}</small>:null}</time><div><span>{event.equipment||event.event_class||'PLANT'}</span><strong>{summary}</strong></div><span className="detail-cue">상세 보기</span></article>;})}{timeline.hiddenCount?<p>후속 기록 {timeline.hiddenCount}건은 전체 사건 기록에서 확인</p>:null}</div>;
}

function EvidenceDrawer({detail,rows,onClose,onShowSources,drawerRef}){
  const [logicSelection,setLogicSelection]=useState(null);
  const logicBackRef=useRef(null);
  const logicTriggerRef=useRef(null);
  const returningFromLogic=useRef(false);
  useEffect(()=>{
    if(logicSelection){returningFromLogic.current=true;requestAnimationFrame(()=>logicBackRef.current?.focus());}
    else if(returningFromLogic.current){returningFromLogic.current=false;requestAnimationFrame(()=>logicTriggerRef.current?.focus());}
  },[logicSelection]);
  if(!detail)return null;
  const first=rows[0];
  const title=detail.title||first?.display_name||first?.message||(detail.kind==='tag'?'태그 상세':'상세 근거');
  const targets=buildEvidenceLogicTargets(rows);
  const coreRows=rows.slice(0,5);
  const rawRows=rows.slice(5,25);
  const renderEvidenceCard=(entry,index,prefix='core')=>{
    const time=displayAccidentTime(entry);
    const displayName=entry.display_name||entry.message||friendlyTag(entry.source_node||entry.tag);
    return <section className="drawer-evidence-card" key={`${prefix}-${entry.evidence_id||index}`}>
      <h3>{displayName}</h3>
      <dl>
        <div><dt>Model Time</dt><dd>{time.primary}</dd></div>
        {time.secondary?<div><dt>기록 시각</dt><dd>{time.secondary}</dd></div>:null}
        <div><dt>상태</dt><dd>{entry.state||String(entry.value??'—')}</dd></div>
      </dl>
      <details className="technical-details"><summary>기술 정보 보기</summary><dl><div><dt>태그</dt><dd>{entry.canonical_tag||entry.source_node||entry.tag||'—'}</dd></div><div><dt>원시 값</dt><dd>{String(entry.value??'—')}</dd></div><div><dt>구분</dt><dd>{entry.source_kind||entry.source||'—'}</dd></div></dl></details>
    </section>;
  };
  if(logicSelection){
    const query=new URLSearchParams();
    if(logicSelection.rule)query.set('rule',logicSelection.rule);
    else if(logicSelection.tag)query.set('tag',logicSelection.tag);
    const src=`/logic-assets/viewer.html${query.toString()?'#'+query:''}`;
    return <aside className="evidence-drawer" role="dialog" aria-modal="false" aria-labelledby="evidence-drawer-title" tabIndex={-1} ref={drawerRef}>
      <header className="evidence-drawer-head">
        <button ref={logicBackRef} className="drawer-back" type="button" onClick={()=>setLogicSelection(null)}>사건 상세로 돌아가기</button>
        <div><span>연결 로직</span><h2 id="evidence-drawer-title">{title}</h2></div>
        <button type="button" onClick={onClose} aria-label="상세 패널 닫기">닫기</button>
      </header>
      <div className="evidence-drawer-body drawer-logic-view">
        {targets.roles.length?<div className="drawer-logic-tabs" aria-label="연결 로직 목록">{targets.roles.map(role=><button type="button" className={logicSelection.rule===role.id?'active':''} key={role.id} onClick={()=>setLogicSelection({tag:'',rule:role.id})}><span>{role.label}</span><b>{role.id}</b></button>)}</div>:null}
        <LogicViewerFrame key={`${logicSelection.tag}-${logicSelection.rule}`} title={`${title} 연결 로직`} src={src} tag={logicSelection.tag} rule={logicSelection.rule} style={{width:'100%',flex:1,minHeight:0,border:0,display:'block'}}/>
      </div>
    </aside>;
  }
  return <aside className="evidence-drawer" role="dialog" aria-modal="false" aria-labelledby="evidence-drawer-title" tabIndex={-1} ref={drawerRef}>
    <header className="evidence-drawer-head">
      <div><span>상세 정보</span><h2 id="evidence-drawer-title">{title}</h2></div>
      <button type="button" onClick={onClose} aria-label="상세 패널 닫기">닫기</button>
    </header>
    <div className="evidence-drawer-body">
      {detail.summary?<p className="drawer-summary">{detail.summary}</p>:null}
      {detail.description?<details className="drawer-description"><summary>분석 설명</summary><p>{detail.description}</p></details>:null}
      {detail.tags?.length?<div className="drawer-tags"><b>추가 근거 태그</b>{detail.tags.map(tag=><span key={tag}>{friendlyTag(tag)}</span>)}</div>:null}
      <div className="drawer-actions"><button type="button" onClick={onShowSources}>원본 EVENT·RAW 보기</button>{targets.entry?<button ref={logicTriggerRef} className="drawer-logic-button" type="button" onClick={()=>setLogicSelection({tag:targets.entry.tag,rule:''})}><b>연결 로직 보기 · {targets.entry.ruleCount}개</b></button>:null}</div>
      {coreRows.length?coreRows.map((entry,index)=>renderEvidenceCard(entry,index)):<div className="empty-state">연결된 상세 근거가 없습니다.</div>}
      {rows.length>5?<details className="drawer-raw-list"><summary>원시 데이터 보기 · {rows.length-5}건</summary><div>{rawRows.map((entry,index)=>renderEvidenceCard(entry,index,'raw'))}{rows.length>25?<p>나머지 {rows.length-25}건은 원본 EVENT·RAW 화면에서 확인하세요.</p>:null}</div></details>:null}
    </div>
  </aside>;
}

function OperatorReportPreview({analysis,events,recovery,report}){
  const timeline=compactTimeline(events,7);
  const primary=conciseClaim(operatorSummary(analysis.primary_cause,'primary'),140).summary;
  const direct=conciseClaim(operatorSummary(analysis.direct_trigger,'direct'),140).summary;
  const documentMeta=reportExporter.reportDocumentMeta(report);
  const hasRecovery=hasRecoveryRecord(recovery);
  return <div className="operator-report-preview">
    <header className="operator-report-document-head">
      <div className="operator-report-title"><span>TRIPLENS INCIDENT REPORT</span><h3>설비 고장 분석보고서</h3><p>EVENT·RAW 기반 사고 경위 및 보호동작 분석</p></div>
      <table className="operator-report-approval"><caption>결재</caption><thead><tr><th>작성</th><th>검토</th><th>승인</th></tr></thead><tbody><tr><td>{documentMeta.author||'\u00a0'}</td><td>{documentMeta.reviewer||'\u00a0'}</td><td>{documentMeta.approver||'\u00a0'}</td></tr><tr><td>{documentMeta.authoredAt||'\u00a0'}</td><td>{documentMeta.reviewedAt||'\u00a0'}</td><td>{documentMeta.approvedAt||'\u00a0'}</td></tr></tbody></table>
      <dl className="operator-report-document-meta"><div><dt>보고서 번호</dt><dd>{documentMeta.reportNo}</dd></div><div><dt>사고 시각</dt><dd>{documentMeta.incidentTime.primary}{documentMeta.incidentTime.secondary?<small>{documentMeta.incidentTime.secondary}</small>:null}</dd></div><div><dt>대상 설비</dt><dd>{documentMeta.equipment}</dd></div><div><dt>입력 자료</dt><dd>{documentMeta.inputFiles}</dd></div></dl>
    </header>
    <div className="operator-report-causes"><div><span>사고 개시 신호</span><strong>{primary||'—'}</strong></div><div><span>직접 보호동작</span><strong>{direct||'—'}</strong></div></div>
    <div className="operator-report-timeline"><h3>시간순 사고 경위</h3>{timeline.visible.map((event,index)=>{const display=displayEventTime(event);const primaryTime=event.model_time_s===null||event.model_time_s===undefined?display.primary:modelTime(event.model_time_s);const secondaryTime=primaryTime===display.primary?display.secondary:display.primary;const summary=conciseClaim(operatorSummary(event)||event.message||friendlyTag(event.tag),140).summary;return <div key={event.event_id||index}><time>{primaryTime}{secondaryTime?<small>{secondaryTime}</small>:null}</time><b>{event.equipment||event.event_class||'PLANT'}</b><span>{summary}</span></div>;})}{timeline.hiddenCount?<p>후속 기록 {timeline.hiddenCount}건은 상세 분석 데이터에 포함됩니다.</p>:null}</div>
    {hasRecovery?<div className="operator-report-recovery"><span>복구조치 및 확인사항</span><strong>{recovery.actions}</strong></div>:null}
  </div>;
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
  const [evidenceKind,setEvidenceKind]=useState('');
  const [evidenceState,setEvidenceState]=useState('');
  const [recovery,setRecovery]=useState(()=>normalizeRecovery(EMPTY_RECOVERY));
  const version=useRef(0);
  const drawerRef=useRef(null);
  const detailReturnFocus=useRef(null);

  const analysis=useMemo(()=>normalizeDisplayAnalysis(result?.analysis||{}),[result]);
  const currentData=useMemo(()=>analysisDisplayData({result}),[result]);
  const events=useMemo(()=>result?mergeEvents(eventData?.records||[],currentData.events):[],[result,eventData,currentData]);
  const catalog=useMemo(()=>result?mergeEvidenceCatalog(events,currentData.catalog):[],[result,events,currentData]);
  const operatorPresentation=useMemo(()=>deriveOperatorAnalysis(analysis,catalog),[analysis,catalog]);
  const operatorAnalysis=operatorPresentation.analysis;
  const evidenceRows=useMemo(()=>groupEvidenceRows(catalog),[catalog]);
  const metrics=useMemo(()=>incidentMetrics(events),[events]);
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

  useEffect(()=>{
    if(!detail)return undefined;
    requestAnimationFrame(()=>drawerRef.current?.focus());
    const onKeyDown=event=>{
      if(event.key==='Escape'){
        setDetail(null);
        requestAnimationFrame(()=>detailReturnFocus.current?.focus?.());
      }
    };
    window.addEventListener('keydown',onKeyDown);
    return()=>window.removeEventListener('keydown',onKeyDown);
  },[detail]);

  useEffect(()=>{
    if(activeTab!=='evidence'||!detail)return;
    requestAnimationFrame(()=>document.querySelector('.evidence-table .interactive-row.selected')?.scrollIntoView({block:'center'}));
  },[activeTab,detail,evidenceRows]);

  function openDetail(next){
    if(!next)return;
    detailReturnFocus.current=document.activeElement;
    setDetail(next);
  }

  function closeDetail(){
    setDetail(null);
    requestAnimationFrame(()=>detailReturnFocus.current?.focus?.());
  }

  function resetAnalysisState(){
    setResult(null);
    setDetail(null);
    setReportRows([]);
    setRecovery(normalizeRecovery(EMPTY_RECOVERY));
    setReportOpen(false);
    setEvidenceQuery('');
    setEvidenceKind('');
    setEvidenceState('');
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
    setReportRows(rows=>rows.map(existing=>existing.row_id===row.row_id?{...existing,[key]:value,edited:true}:existing));
  }

  const detailRows=selectDetailEvidence(catalog,detail);

  let view;
  if(!result){
    view=<WaitingPanel status={status}/>;
  }else if(activeTab==='cause'){
    view=<div className="panel-stack cause-layout">
      <div className="section-heading"><div><h2>원인 분석</h2></div></div>
      <div className="cause-grid">
        <ClaimCard title={operatorPresentation.primaryTitle} stage="primary" item={operatorAnalysis.primary_cause} onOpen={openDetail}/>
        <ClaimCard title="직접 보호동작" stage="direct" item={operatorAnalysis.direct_trigger} onOpen={openDetail}/>
      </div>
      <section className="analysis-section">
        <div className="analysis-section-head"><div><h3>파급 과정</h3></div><p>보호동작 이후의 설비 변화</p></div>
        <AnalysisList items={operatorAnalysis.propagation} stage="propagation" onOpen={openDetail}/>
      </section>
      <section className="analysis-section causal-section">
        <div className="analysis-section-head"><div><h3>시간순 사고 경위</h3></div><p>상세 인과관계</p></div>
        <details><summary>상세 시간순서 보기</summary><AnalysisList items={operatorAnalysis.causal_chain} stage="causal" onOpen={openDetail}/></details>
      </section>
    </div>;
  }else if(activeTab==='timeline'){
    view=<div className="panel-stack">
      <div className="section-heading"><h2>사고 진행 과정</h2><span>EVENT {events.length}건</span></div>
      <section className="analysis-section"><h3>주요 사건</h3><OperatorTimeline events={events} onOpen={openDetail}/></section>
      <details className="analysis-details"><summary>전체 사건 기록 보기 · {events.length}건</summary><EventTable events={events} onOpen={openDetail}/></details>
    </div>;
  }else if(activeTab==='checks'){
    const checks=[...analysis.additional_evidence_required,...analysis.review_recommendations];
    view=<div className="panel-stack"><div className="section-heading"><h2>즉시 확인·대응</h2></div>{checks.length?checks.map((text,index)=><div className="check-row" key={index}><span>{String(index+1).padStart(2,'0')}</span><p>{text}</p></div>):<div className="empty-state">추가 확인 항목이 없습니다.</div>}</div>;
  }else if(activeTab==='recovery'){
    view=<div className="panel-stack"><div className="section-heading"><h2>복구 기록</h2></div><RecoveryForm value={recovery} onChange={setRecovery} catalog={catalog}/></div>;
  }else{
    const evidenceKinds=[...new Set(evidenceRows.map(entry=>String(entry.source_kind||entry.source||'')).filter(Boolean))].sort();
    const evidenceStates=[...new Set(evidenceRows.map(entry=>String(entry.state||'')).filter(Boolean))].sort();
    const filtered=evidenceRows.filter(entry=>{
      const matchesQuery=JSON.stringify([entry.display_name,entry.message,entry.tag,entry.source_node,entry.canonical_tag,entry.state]).toLowerCase().includes(evidenceQuery.toLowerCase());
      const matchesKind=!evidenceKind||String(entry.source_kind||entry.source||'')===evidenceKind;
      const matchesState=!evidenceState||String(entry.state||'')===evidenceState;
      return matchesQuery&&matchesKind&&matchesState;
    });
    const activeEvidenceFilters=[evidenceQuery,evidenceKind,evidenceState].filter(Boolean).length;
    const visibleEvidence=prioritizeEvidenceRows(filtered,detail,200);
    view=<div className="panel-stack"><div className="section-heading"><h2>상세 근거</h2><span>{filtered.length}건{activeEvidenceFilters?` · 활성 필터 ${activeEvidenceFilters}개`:''}</span></div><div className="evidence-filter-bar"><input className="filter-input" aria-label="근거 검색" placeholder="신호 또는 태그 검색" value={evidenceQuery} onChange={event=>setEvidenceQuery(event.target.value)}/><select aria-label="근거 구분 필터" value={evidenceKind} onChange={event=>setEvidenceKind(event.target.value)}><option value="">전체 구분</option>{evidenceKinds.map(kind=><option key={kind} value={kind}>{kind}</option>)}</select><select aria-label="근거 상태 필터" value={evidenceState} onChange={event=>setEvidenceState(event.target.value)}><option value="">전체 상태</option>{evidenceStates.map(state=><option key={state} value={state}>{state}</option>)}</select>{activeEvidenceFilters?<button type="button" onClick={()=>{setEvidenceQuery('');setEvidenceKind('');setEvidenceState('');}}>필터 초기화</button>:null}</div><div className="scroll-table evidence-table"><table><thead><tr><th>Model Time</th><th>구분</th><th>신호</th><th>상태</th><th>값</th></tr></thead><tbody>{visibleEvidence.map((entry,index)=>{const time=displayAccidentTime(entry);const ids=entry.evidence_ids?.length?entry.evidence_ids:[entry.evidence_id].filter(Boolean);const signal=entry.display_name||entry.message||friendlyTag(entry.source_node||entry.canonical_tag||entry.tag);const selected=ids.some(id=>detail?.evidenceIds?.includes(id)||detail?.value===id);const open=()=>openDetail({kind:'claim',title:signal,evidenceIds:ids,tags:[entry.source_node||entry.canonical_tag||entry.tag].filter(Boolean)});return <tr className={`interactive-row ${selected?'selected':''}`} role="button" tabIndex={0} aria-label={`${signal} 상세 보기`} key={entry.evidence_id||index} onClick={open} onKeyDown={keyEvent=>{if(keyEvent.key==='Enter'||keyEvent.key===' '){keyEvent.preventDefault();open();}}}><td><b>{time.primary}</b>{time.secondary?<small>{time.secondary}</small>:null}</td><td>{entry.source_kind||entry.source||'—'}</td><td>{signal}{entry.repeat_count>1?<small>동일 상태 {entry.repeat_count}건</small>:null}</td><td>{entry.state||'—'}</td><td>{String(entry.value??'—')}</td></tr>;})}</tbody></table>{filtered.length>visibleEvidence.length?<p className="evidence-overflow">후속 근거 {filtered.length-visibleEvidence.length}건 · 검색 또는 필터로 범위를 좁혀 주세요.</p>:null}</div></div>;
  }

  return <main className={`app-shell ${detail?'detail-open':''}`}>
    <header className="topbar">
      <div className="brand"><div className="brand-mark">TL</div><div><h1>TripLens</h1><span>DUAL-INPUT ACCIDENT ANALYSIS</span></div></div>
      <div className="status-rail">
        <div><span>입력 상태</span><b>{result?'분석 완료':ready?'분석 준비':'Dual Log 대기'}</b></div>
        <div><span>최초 동작</span><b>{metrics.firstTime}</b></div>
        <div><span>보호 동작</span><b>{metrics.protection}건</b></div>
        <div><span>후속 알람</span><b>{metrics.alarms}건</b></div>
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
          ].map(([kind,file,data])=><label className={`file-card ${file?'ready':''}`} key={kind}><span>{kind.toUpperCase()}.csv</span><b>{file?.name||'파일 선택'}</b><em>{file?`${(file.size/1024).toFixed(1)} KB · ${data?.records.length??'확인 중'}${kind==='event'?'건':'행'}${kind==='raw'&&data?` · ${rawTagCount(data)}개 태그`:''}`:''}</em><input disabled={busy} type="file" accept=".csv,text/csv" aria-label={`${kind.toUpperCase()} 파일`} onClick={event=>{event.currentTarget.value='';}} onChange={event=>selectFile(kind,event.target.files?.[0])}/></label>)}</div>
          <div className="analysis-status" aria-live="polite"><b>{status.title}</b>{status.detail?<span>{status.detail}</span>:null}{statusText?<em role="alert">{statusText}</em>:null}</div>
          <div className="intake-actions">
            <button disabled={!ready||busy||Boolean(result)} onClick={analyze}>{busy?'분석 중…':result?'분석 완료':'이 Dual Log 분석하기'}</button>
            <button disabled={!result} className="secondary" onClick={()=>{setReportOpen(!reportOpen);setDetail(null);}}>고장분석 보고서 보기</button>
            <button disabled={busy} className="secondary" onClick={clear}>입력·분석 지우기</button>
          </div>
        </section>

        {result&&exportBlocked?<p className="warning-box" role="alert">일부 근거 연결을 확인한 후 내보낼 수 있습니다: {missingEvidence.length}건</p>:null}
        <section className="analysis-surface">{view}</section>
        <EvidenceDrawer key={detail?.evidenceIds?.join('|')||detail?.title||'closed'} detail={detail} rows={detailRows} onClose={closeDetail} onShowSources={()=>{setEvidenceQuery('');setEvidenceKind('');setEvidenceState('');setActiveTab('evidence');}} drawerRef={drawerRef}/>

        {reportOpen&&result?<section className="report-preview">
          <div className="section-heading report-actions">
            <h2>보고서 미리보기</h2>
            <button className="export-button" disabled={exportBlocked} onClick={exportPDF}>보고서 PDF 저장</button>
            <details className="export-menu"><summary>내보내기</summary><div><button className="export-button" disabled={exportBlocked} onClick={exportCSV}>보고서 CSV</button><button className="export-button" disabled={exportBlocked} onClick={exportDetailedCSV}>상세 분석 데이터 CSV</button></div></details>
          </div>
          <p className="report-help">핵심 사고 경위를 1~2페이지 운전 고장상보 형식으로 저장합니다.</p>
          <OperatorReportPreview analysis={operatorAnalysis} events={events} recovery={recovery} report={exportReport}/>
          <details className="report-editor"><summary>보고서 세부 항목 편집</summary><div className="scroll-table"><table className="editable-report"><thead><tr>{REPORT_COLUMNS.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{displayReportRows.map((row,index)=>{
            const recoveryRow=row.row_id?.startsWith('RECOVERY-');
            return <tr key={row.row_id||index} data-row-id={row.row_id}>{REPORT_KEYS.map((key,column)=><td key={key} data-label={REPORT_COLUMNS[column]}>{key==='status'?(recoveryRow||!CLAIM_STATUS_CHOICES.includes(row.status)?<span className="report-status" data-status={row.status}>{reportStatusLabel(row.status)}</span>:<select aria-label={`보고서 ${index+1} 상태`} value={row.status} onChange={event=>editReportRow(row,key,event.target.value)}>{CLAIM_STATUS_CHOICES.map(statusValue=><option key={statusValue} value={statusValue}>{REPORT_STATUS_TEXT[statusValue]}</option>)}</select>):recoveryRow?<div className="report-readonly">{row[key]||'—'}{key==='content'?<button className="tag-link" onClick={()=>{setActiveTab('recovery');setDetail(null);requestAnimationFrame(()=>document.querySelector('.recovery-form')?.scrollIntoView({block:'start'}));}}>복구 기록에서 편집</button>:null}</div>:<textarea aria-label={`보고서 ${index+1} ${key}`} value={row[key]||''} onChange={event=>editReportRow(row,key,event.target.value)}/>}</td>)}</tr>;
          })}</tbody></table></div></details>
        </section>:null}
      </section>
    </div>
    <LogicLibraryDialog analysisMode/>
  </main>;
}
