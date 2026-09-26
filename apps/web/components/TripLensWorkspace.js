'use client';

import {useEffect,useMemo,useRef,useState} from 'react';
import {LogicLibraryDialog,openLogicLibrary} from './LogicLibrary';
import RecoveryForm from './RecoveryForm';
import RecoveryReadiness from './RecoveryReadiness';
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
  loadSession,
  saveSession,
} from '../lib/analysisClient.mjs';
import {buildWorkspaceSession,canRestoreWorkspaceSession} from '../lib/workspaceSession.mjs';
import {buildEvidenceLogicTargets} from '../lib/integrationTestbench.mjs';
import {mergeEvents,mergeEvidenceCatalog} from '../lib/reportIntegrity.mjs';
import {buildClaimReferenceTargets} from '../lib/claimReferenceLinks.mjs';
import {EMPTY_RECOVERY,normalizeRecovery,recoveryStatusLabel} from '../lib/recoveryModel.mjs';
import {applyRecoveryRows,buildWorkspaceExportReport,restoreWorkspaceReportRows,WORKSPACE_REPORT_VERSION} from '../lib/reportAdapter.mjs';
import {
  analysisDisplayData,
  compactTimeline,
  conciseClaim,
  displayEventTime,
  friendlyTag,
  incidentMetrics,
  inputStatus,
  operatorSummary,
  operatorPhrase,
  operatorReviewItems,
  selectDetailEvidence,
  summarizeEvidence,
} from '../lib/workspacePresentation.mjs';
import reportExporter from '../lib/reportExporter.cjs';
import {analysisApiUrl} from '../lib/analysisApi.mjs';
import '../app/integration.css';

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
  const response=await fetch(analysisApiUrl(path),body?{method:'POST',body}:undefined);
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
  const label=named?'사건 기록 열기':'상세 기록 열기';
  return <span className="evidence-links">{values.map((id,index)=><button key={id} title={'ID: '+id} aria-label={label+' '+(index+1)} onClick={()=>onOpen({kind:'evidence',value:id})}>{label}</button>)}</span>;
}

function ClaimReferenceActions({item,catalog}){
  const references=buildClaimReferenceTargets(item,catalog);
  if(!references.logicTag&&!references.drawingHref)return null;
  return <span className="claim-reference-actions" aria-label="근거 바로가기">
    {references.logicTag?<button type="button" onClick={()=>openLogicLibrary({tag:references.logicTag})}>[로직]</button>:null}
    {references.drawingHref?<a href={references.drawingHref} target="_blank" rel="noreferrer">[드로잉]</a>:null}
  </span>;
}

function ClaimEvidence({item,onOpen,catalog}){
  const tags=summarizeEvidence(item?.related_tags||[],5);
  const allTags=[...tags.visible,...tags.hidden];
  const ids=[...new Set((item?.evidence_ids||[]).filter(Boolean))];
  if(!tags.visible.length&&!ids.length)return null;
  const time=displayEventTime(item);
  const timeText=[time.primary,time.secondary].filter(value=>value&&value!=='시각 미확인').join(' · ');
  const openClaim=()=>onOpen({kind:'claim',evidenceIds:ids,tags:allTags});
  return <div className="claim-evidence">
    <div className="claim-evidence-summary"><span>근거</span><strong>{timeText||'연결 기록'}{ids.length?` · ${ids.length}건`:''}</strong>
      <ClaimReferenceActions item={item} catalog={catalog}/>
    </div>
    <details>
      <summary>상세 근거 보기{ids.length?` · ${ids.length}건`:''}</summary>
      <div className="detail-evidence-list">
        {allTags.length?<div className="raw-tag-list" aria-label="원시 근거 태그"><b>원시 태그</b>{allTags.map(tag=><button key={tag} className="raw-tag-link" title={tag} onClick={()=>onOpen({kind:'tag',value:tag})}>{tag}</button>)}</div>:null}
        {ids.length?<button className="tag-link" onClick={openClaim}>연결 근거 모아보기 · {ids.length}건</button>:null}
      </div>
    </details>
  </div>;
}

function ClaimCard({title,item,stage,onOpen,catalog}){
  const original=claimText(item);
  const compact=conciseClaim(operatorSummary(item,stage),140);
  const summary=compact.summary;
  const detail=original&&original!==summary?operatorPhrase(original,10000):compact.detail;
  const time=displayEventTime(item);
  return <section className="claim-card cause-card">
    <div className="claim-head"><h3>{title}</h3>{time.primary!=='시각 미확인'?<time>{time.primary}{time.secondary?<small>{time.secondary}</small>:null}</time>:null}</div>
    <div className="claim-text">{summary||'분석 결과 없음'}</div>
    {detail?<details className="claim-detail"><summary>상세 분석 설명</summary><p>{detail}</p></details>:null}
    <ClaimEvidence item={item} onOpen={onOpen} catalog={catalog}/>
  </section>;
}

function AnalysisList({items,stage,onOpen,catalog,limit=5}){
  if(!items?.length)return <p className="empty-line">표시할 분석 결과 없음</p>;
  const visible=items.slice(0,limit);
  const hidden=items.slice(limit);
  const renderItem=(item,index)=>{
    const original=claimText(item);
    const compact=conciseClaim(typeof item==='string'?item:operatorSummary(item,stage),150);
    const summary=compact.summary;
    const detail=original&&original!==summary?operatorPhrase(original,10000):compact.detail;
    const time=displayEventTime(item);
    return <article key={`${item?.claim||'item'}-${index}`}>
      <div><b>{String(index+1).padStart(2,'0')}</b><p>{summary}</p>{time.primary!=='시각 미확인'?<time>{time.primary}{time.secondary?<small>{time.secondary}</small>:null}</time>:null}</div>
      <ClaimEvidence item={item} onOpen={onOpen} catalog={catalog}/>
      {detail?<details><summary>상세 분석 설명</summary><p>{detail}</p></details>:null}
    </article>;
  };
  return <div className="analysis-list">{visible.map(renderItem)}{hidden.length?<details className="hidden-analysis-items"><summary>후속 분석 {hidden.length}건 보기</summary><div>{hidden.map((item,index)=>renderItem(item,index+limit))}</div></details>:null}</div>;
}

function eventReferenceItem(event){
  return {
    related_tags:[event.source_node,event.canonical_tag,event.original_tag,event.tag].filter(Boolean),
    evidence_ids:[event.evidence_id||event.event_id].filter(Boolean),
  };
}

function EventTable({events,onOpen,catalog}){
  return <div className="scroll-table"><table><thead><tr><th>시간</th><th>설비</th><th>사건</th><th>원천</th><th>근거</th></tr></thead><tbody>{events.map((event,index)=>{const time=displayEventTime(event);const referenceItem=eventReferenceItem(event);return <tr key={event.event_id||index}><td><b>{time.primary}</b>{time.secondary?<small>{time.secondary}</small>:null}</td><td>{event.equipment||'—'}</td><td>{operatorSummary(event)||event.message||friendlyTag(event.tag)}</td><td>{event.source||'—'}</td><td><div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}><EvidenceLinks ids={referenceItem.evidence_ids} onOpen={onOpen} named/><ClaimReferenceActions item={referenceItem} catalog={catalog}/></div></td></tr>;})}</tbody></table></div>;
}

function OperatorTimeline({events,onOpen,catalog}){
  const timeline=compactTimeline(events,7);
  return <div className="operator-timeline">{timeline.visible.map((event,index)=>{const time=displayEventTime(event);const summary=conciseClaim(operatorSummary(event)||event.message||friendlyTag(event.tag),140).summary;const referenceItem=eventReferenceItem(event);return <article key={event.event_id||index}><time><b>{time.primary}</b>{time.secondary?<small>{time.secondary}</small>:null}</time><div><span>{event.equipment||event.event_class||'PLANT'}</span><strong>{summary}</strong></div><div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}><EvidenceLinks ids={referenceItem.evidence_ids} onOpen={onOpen} named/><ClaimReferenceActions item={referenceItem} catalog={catalog}/></div></article>;})}{timeline.hiddenCount?<p>후속 기록 {timeline.hiddenCount}건은 전체 사건 기록에서 확인</p>:null}</div>;
}

function OperatorReportPreview({analysis,events,recovery}){
  const timeline=compactTimeline(events,7);
  const primary=operatorPhrase(operatorSummary(analysis.primary_cause,'primary'),140);
  const direct=operatorPhrase(operatorSummary(analysis.direct_trigger,'direct'),140);
  return <div className="operator-report-preview">
    <div className="operator-report-causes"><div><span>발생 원인</span><strong>{primary||'기록 없음'}</strong></div><div><span>직접 보호동작</span><strong>{direct||'기록 없음'}</strong></div></div>
    <div className="operator-report-timeline"><h3>시간순 사고 경위</h3>{timeline.visible.map((event,index)=>{const time=displayEventTime(event);const summary=operatorPhrase(operatorSummary(event)||event.message||friendlyTag(event.tag),140);return <div key={event.event_id||index}><time>{time.primary}</time><b>{event.equipment||event.event_class||'PLANT'}</b><span>{summary}</span></div>;})}{timeline.hiddenCount?<p>후속 기록 {timeline.hiddenCount}건 · 상세 분석 데이터 참조</p>:null}</div>
    <div className="operator-report-recovery"><span>복구조치 및 확인사항</span><strong>{recovery.actions||'기록 없음'}</strong></div>
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
  const [pdfPreviewHtml,setPdfPreviewHtml]=useState('');
  const [evidenceQuery,setEvidenceQuery]=useState('');
  const [recovery,setRecovery]=useState(()=>normalizeRecovery(EMPTY_RECOVERY));
  const [restored,setRestored]=useState(false);
  const version=useRef(0);
  const clearRequested=useRef(false);

  const analysis=useMemo(()=>normalizeDisplayAnalysis(result?.analysis||{}),[result]);
  const currentData=useMemo(()=>analysisDisplayData({result}),[result]);
  const events=useMemo(()=>result?mergeEvents(eventData?.records||[],currentData.events):[],[result,eventData,currentData]);
  const catalog=useMemo(()=>result?mergeEvidenceCatalog(events,currentData.catalog):[],[result,events,currentData]);
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
    let active=true;
    request('/contract').then(value=>{if(active)setContract(value);}).catch(()=>{});
    return()=>{active=false;};
  },[]);

  useEffect(()=>{
    let active=true;
    (async()=>{
      try{
        const saved=await loadSession();
        if(!active||!canRestoreWorkspaceSession(saved,mode))return;
        const savedEvents=saved.eventData||(saved.eventFile?parseCSV(await saved.eventFile.text()):null);
        const savedRaw=saved.rawData||(saved.rawFile?parseCSV(await saved.rawFile.text()):null);
        if(!active)return;
        setEventFile(saved.eventFile||null);
        setRawFile(saved.rawFile||null);
        setEventData(savedEvents);
        setRawData(savedRaw);
        setResult(saved.result||null);
        setReportRows(restoreWorkspaceReportRows({
          result:saved.result||{},
          uploadedEvents:savedEvents?.records||[],
          reportRows:saved.reportRows||[],
          recovery:saved.recovery||EMPTY_RECOVERY,
          reportVersion:saved.reportVersion,
        }));
        setRecovery(normalizeRecovery(saved.recovery||EMPTY_RECOVERY));
        setActiveTab(saved.activeTab||'timeline');
        if(saved.result||saved.eventFile||saved.rawFile)setStatusText('브라우저에 보관된 분석을 복원했습니다.');
      }catch{
        if(active)setStatusText('이 브라우저에서 이전 분석을 복원하지 못했습니다. 파일을 다시 선택해 주세요.');
      }finally{
        if(active)setRestored(true);
      }
    })();
    return()=>{active=false;};
  },[mode]);

  useEffect(()=>{
    if(!restored)return;
    if(clearRequested.current){
      clearRequested.current=false;
      return;
    }
    if(!eventFile&&!rawFile&&!result&&!reportRows.length)return;
    const timer=setTimeout(()=>saveSession(buildWorkspaceSession({
      mode,eventFile,rawFile,eventData,rawData,result,reportRows,
      reportVersion:WORKSPACE_REPORT_VERSION,recovery,activeTab,
    })).catch(()=>setStatusText('브라우저 저장 공간에 분석을 보관하지 못했습니다.')),
    250);
    return()=>clearTimeout(timer);
  },[restored,mode,eventFile,rawFile,eventData,rawData,result,reportRows,recovery,activeTab]);

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
    clearRequested.current=true;
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

  function exportPDF(){
    if(exportBlocked)return;
    try{
      setPdfPreviewHtml(reportExporter.buildReportHtml(exportReport));
      setStatusText('');
    }catch(error){
      setStatusText(`PDF 보고서를 준비하지 못했습니다: ${error?.message||'보고서 내용을 확인해 주세요.'}`);
    }
  }
  function exportDetailedCSV(){if(!exportBlocked)reportExporter.downloadPinpointCsv(exportReport,`TripLens_상세분석데이터_${result?.run_id||'analysis'}.csv`);}

  function editReportRow(row,key,value){
    setReportRows(rows=>rows.map(existing=>existing.row_id===row.row_id?{...existing,[key]:value,edited:true}:existing));
  }

  const detailRows=selectDetailEvidence(catalog,detail);

  let view;
  if(!result){
    view=<WaitingPanel status={status}/>;
  }else if(detail){
    view=<div className="panel-stack evidence-page">
      <button className="back-button" onClick={()=>setDetail(null)}>이전 화면</button>
      <div className="section-heading"><h2>{detail.kind==='tag'?'태그 추이':'근거 상세'}</h2></div>
      {detailRows.length?detailRows.map((entry,index)=>{
        const targets=buildEvidenceLogicTargets(entry);
        const time=displayEventTime(entry);
        return <section className="claim-card evidence-detail" key={entry.evidence_id||index}>
          <h3>{entry.display_name||entry.message||friendlyTag(entry.source_node||entry.tag)}</h3>
          <dl>
            <div><dt>시간</dt><dd>{time.primary}{time.secondary?` · ${time.secondary}`:''}</dd></div>
            <div><dt>태그</dt><dd>{entry.canonical_tag||entry.source_node||entry.tag||'—'}</dd></div>
            <div><dt>값 / 상태</dt><dd>{String(entry.value??'—')} {entry.state?`/ ${entry.state}`:''}</dd></div>
          </dl>
          {entry.message?<p>{entry.message}</p>:null}
          {targets.entry?<div className="logic-targets" aria-label="로직 연결"><button type="button" onClick={()=>openLogicLibrary({tag:targets.entry.tag})}><b>{friendlyTag(targets.entry.tag)} 로직 보기</b><small>관련 로직 {targets.entry.ruleCount}개</small></button></div>:null}
        </section>;
      }):<div className="empty-state">연결된 상세 근거가 없습니다.</div>}
    </div>;
  }else if(activeTab==='cause'){
    view=<div className="panel-stack cause-layout">
      <div className="section-heading"><div><h2>원인 분석</h2></div></div>
      <div className="cause-grid">
        <ClaimCard title="발생 원인" stage="primary" item={analysis.primary_cause} onOpen={setDetail} catalog={catalog}/>
        <ClaimCard title="직접 보호동작" stage="direct" item={analysis.direct_trigger} onOpen={setDetail} catalog={catalog}/>
      </div>
      <section className="analysis-section">
        <div className="analysis-section-head"><div><h3>파급 과정</h3></div><p>보호동작 이후의 설비 변화</p></div>
        <AnalysisList items={analysis.propagation} stage="propagation" onOpen={setDetail} catalog={catalog}/>
      </section>
      <section className="analysis-section causal-section">
        <div className="analysis-section-head"><div><h3>시간순 사고 경위</h3></div><p>상세 인과관계</p></div>
        <details><summary>상세 시간순서 보기</summary><AnalysisList items={analysis.causal_chain} stage="causal" onOpen={setDetail} catalog={catalog}/></details>
      </section>
    </div>;
  }else if(activeTab==='timeline'){
    view=<div className="panel-stack">
      <div className="section-heading"><h2>사고 진행 과정</h2><span>EVENT {events.length}건</span></div>
      <section className="analysis-section"><h3>주요 사건</h3><OperatorTimeline events={events} onOpen={setDetail} catalog={catalog}/></section>
      <details className="analysis-details"><summary>전체 사건 기록 보기 · {events.length}건</summary><EventTable events={events} onOpen={setDetail} catalog={catalog}/></details>
    </div>;
  }else if(activeTab==='checks'){
    const checks=operatorReviewItems(analysis);
    const requiredCount=checks.filter(item=>item.kind==='required').length;
    const reviewCount=checks.filter(item=>item.kind==='review').length;
    view=<div className="panel-stack">
      <div className="section-heading"><div><h2>추가 확인·검토</h2><p>원인 확정을 위해 남은 확인 대상과 담당자 검토사항</p></div></div>
      {checks.length?<><div className="review-summary"><div><span>확인 필요</span><b>{requiredCount}</b></div><div><span>담당자 검토</span><b>{reviewCount}</b></div></div>
      <div className="review-checklist">{checks.map((item,index)=><article className="review-check-card" key={`${item.kind}-${item.title}-${index}`}>
        <div className="review-check-no">{String(index+1).padStart(2,'0')}</div>
        <div className="review-check-main">
          <header><strong>{item.title}</strong><span data-kind={item.kind}>{item.status}</span></header>
          {item.detail?<p>{item.detail}</p>:null}
          {item.tags.length?<div className="review-tags">{item.tags.map(tag=><em key={tag}>{friendlyTag(tag)}</em>)}</div>:null}
        </div>
      </article>)}</div></>:<div className="empty-state">추가 확인·검토 항목 없음</div>}
    </div>;
  }else if(activeTab==='recovery'){
    view=<div className="panel-stack">
      <div className="section-heading"><h2>복구 · 설비 준비상태</h2></div>
      <RecoveryReadiness rawData={rawData}/>
      <div className="section-heading recovery-record-heading"><h2>실제 복구 기록</h2><span>운전·정비 담당자 입력</span></div>
      <RecoveryForm value={recovery} onChange={setRecovery} catalog={catalog}/>
    </div>;
  }else{
    const filtered=catalog.filter(entry=>JSON.stringify([entry.evidence_id,entry.tag,entry.source_node,entry.canonical_tag]).toLowerCase().includes(evidenceQuery.toLowerCase()));
    view=<div className="panel-stack"><div className="section-heading"><h2>Event / RAW 근거</h2><span>{filtered.length}건</span></div><input className="filter-input" aria-label="근거 검색" placeholder="근거 또는 태그 검색" value={evidenceQuery} onChange={event=>setEvidenceQuery(event.target.value)}/><div className="scroll-table"><table><thead><tr><th>근거</th><th>종류</th><th>모델 시각</th><th>신호</th><th>값</th></tr></thead><tbody>{filtered.map((entry,index)=><tr key={entry.evidence_id||index}><td><EvidenceLinks ids={[entry.evidence_id]} onOpen={setDetail} named/></td><td>{entry.source_kind||entry.source||'—'}</td><td>{modelTime(entry.model_time_s)}</td><td><button className="tag-link" onClick={()=>setDetail({kind:'tag',value:entry.source_node||entry.tag})}>{friendlyTag(entry.source_node||entry.canonical_tag||entry.tag)}</button></td><td>{String(entry.value??'—')}</td></tr>)}</tbody></table></div></div>;
  }

  return <main className="app-shell">
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

        {reportOpen&&result?<section className="report-preview">
          <div className="section-heading report-actions">
            <h2>설비 고장 분석보고서</h2>
            <button className="export-button" disabled={exportBlocked} onClick={exportPDF}>보고서 PDF 저장</button>
            <details className="export-menu"><summary>내보내기</summary><div><button className="export-button" disabled={exportBlocked} onClick={exportCSV}>보고서 CSV</button><button className="export-button" disabled={exportBlocked} onClick={exportDetailedCSV}>상세 분석 데이터 CSV</button></div></details>
          </div>
          <p className="report-help">핵심 사고 경위를 1~2페이지 운전 고장상보 형식으로 저장합니다.</p>
          <OperatorReportPreview analysis={analysis} events={events} recovery={recovery}/>
          <details className="report-editor"><summary>보고서 세부 항목 편집</summary><div className="scroll-table"><table className="editable-report"><thead><tr>{REPORT_COLUMNS.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{displayReportRows.map((row,index)=>{
            const recoveryRow=row.row_id?.startsWith('RECOVERY-');
            return <tr key={row.row_id||index} data-row-id={row.row_id}>{REPORT_KEYS.map((key,column)=><td key={key} data-label={REPORT_COLUMNS[column]}>{key==='status'?(recoveryRow||!CLAIM_STATUS_CHOICES.includes(row.status)?<span className="report-status" data-status={row.status}>{reportStatusLabel(row.status)}</span>:<select aria-label={`보고서 ${index+1} 상태`} value={row.status} onChange={event=>editReportRow(row,key,event.target.value)}>{CLAIM_STATUS_CHOICES.map(statusValue=><option key={statusValue} value={statusValue}>{REPORT_STATUS_TEXT[statusValue]}</option>)}</select>):recoveryRow?<div className="report-readonly">{row[key]||'—'}{key==='content'?<button className="tag-link" onClick={()=>{setActiveTab('recovery');setDetail(null);requestAnimationFrame(()=>document.querySelector('.recovery-form')?.scrollIntoView({block:'start'}));}}>복구 기록에서 편집</button>:null}</div>:<textarea aria-label={`보고서 ${index+1} ${key}`} value={row[key]||''} onChange={event=>editReportRow(row,key,event.target.value)}/>}</td>)}</tr>;
          })}</tbody></table></div></details>
        </section>:null}
      </section>
    </div>
    {pdfPreviewHtml?<ReportPdfDialog html={pdfPreviewHtml} onClose={()=>setPdfPreviewHtml('')} onError={message=>setStatusText(message)}/>:null}
    <LogicLibraryDialog analysisMode/>
  </main>;
}

function ReportPdfDialog({html,onClose,onError}){
  const dialogRef=useRef(null);
  const frameRef=useRef(null);
  const [ready,setReady]=useState(false);

  useEffect(()=>{
    const dialog=dialogRef.current;
    if(!dialog)return;
    if(!dialog.open)dialog.showModal();
    return()=>{if(dialog.open)dialog.close();};
  },[]);

  function frameLoaded(){
    const view=frameRef.current?.contentWindow;
    if(!view)return;
    Promise.resolve(view.document.fonts?.ready).then(()=>{
      if(typeof view.TripLensFitReport==='function')view.TripLensFitReport();
      setReady(true);
    }).catch(()=>setReady(true));
  }

  function printReport(){
    const view=frameRef.current?.contentWindow;
    if(!view||typeof view.print!=='function'){
      onError('이 브라우저에서 보고서 인쇄 창을 열 수 없습니다.');
      return;
    }
    try{
      if(typeof view.TripLensFitReport==='function')view.TripLensFitReport();
      view.focus();
      view.print();
    }catch(error){
      onError(`보고서 인쇄 창을 열지 못했습니다: ${error?.message||'브라우저 설정을 확인해 주세요.'}`);
    }
  }

  return <dialog ref={dialogRef} className="report-pdf-dialog" aria-label="PDF 보고서 미리보기" onCancel={event=>{event.preventDefault();onClose();}}>
    <header><div><h2>고장분석보고서 PDF 미리보기</h2><p>PDF 저장 / 인쇄를 누른 뒤 인쇄 창에서 ‘PDF로 저장’을 선택하세요.</p></div><button type="button" onClick={onClose}>닫기</button></header>
    <iframe ref={frameRef} srcDoc={html} title="고장분석보고서 PDF 미리보기" onLoad={frameLoaded}/>
    <footer><span>보고서 4쪽 · 인쇄 설정은 브라우저 대화상자에서 선택합니다.</span><button type="button" disabled={!ready} onClick={printReport}>PDF 저장 / 인쇄</button></footer>
  </dialog>;
}
