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

const API_BASE=(process.env.NEXT_PUBLIC_TRIPLENS_API_BASE||'/api/triplens').replace(/\/$/,'');
const CLAIM_STATUS_CHOICES=['UNKNOWN','OBSERVED','CANDIDATE'];
const REPORT_KEYS=['section','item','content','status','evidence_ids','tags','time','note'];
const RAW_META_FIELDS=new Set(['record_sequence','session_id','incident_id','model_time_s','wall_time_utc','collector_quality','quality','time']);
const REPORT_STATUS_TEXT={
  CONFIRMED:'íì¸',
  CANDIDATE:'ë¶ì í­ëª©',
  OBSERVED:'ê´ì¸¡',
  UNKNOWN:'íì¸ íì',
  INPUT_PENDING:'ê¸°ë¡ ìì',
  APPROVAL_PENDING:'ê¸°ë¡ë¨',
  APPROVED:'ì¹ì¸ ìë£',
};

async function request(path,body){
  const response=await fetch(`${API_BASE}${path}`,body?{method:'POST',body}:undefined);
  let data;
  try{data=await response.json();}
  catch{throw new Error(`ìë² ìëµì ì½ì§ ëª»íìµëë¤. HTTP ${response.status}`);}
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
    {tags.visible.length?<div className="evidence-pills" aria-label="íµì¬ ê·¼ê±° íê·¸">{tags.visible.map(tag=><span key={tag}>{friendlyTag(tag)}</span>)}</div>:null}
    <span className="detail-cue">ìì¸ ë³´ê¸°{ids.length?` Â· ${ids.length}ê±´`:''}</span>
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
  return <section className={`claim-card cause-card ${canOpen?'interactive-surface':''}`} role={canOpen?'button':undefined} tabIndex={canOpen?0:undefined} aria-label={canOpen?`${title} ìì¸ ë³´ê¸°`:undefined} onClick={open} onKeyDown={event=>{if(canOpen&&(event.key==='Enter'||event.key===' ')){event.preventDefault();open();}}}>
    <div className="claim-head"><h3>{title}</h3>{time.primary!=='ìê° ë¯¸íì¸'?<time>{time.primary}{time.secondary?<small>{time.secondary}</small>:null}</time>:null}</div>
    <div className="claim-text">{summary||'ë¶ì ê²°ê³¼ê° ììµëë¤.'}</div>
    <ClaimEvidence item={item}/>
  </section>;
}

function AnalysisList({items,stage,onOpen,limit=5}){
  if(!items?.length)return <p className="empty-line">íìí  ë¶ì ê²°ê³¼ê° ììµëë¤.</p>;
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
    return <article key={`${item?.claim||'item'}-${index}`} className={canOpen?'interactive-surface':''} role={canOpen?'button':undefined} tabIndex={canOpen?0:undefined} aria-label={canOpen?`${summary} ìì¸ ë³´ê¸°`:undefined} onClick={open} onKeyDown={event=>{if(canOpen&&(event.key==='Enter'||event.key===' ')){event.preventDefault();open();}}}>
      <div><b>{String(index+1).padStart(2,'0')}</b><p>{summary}</p>{time.primary!=='ìê° ë¯¸íì¸'?<time>{time.primary}{time.secondary?<small>{time.secondary}</small>:null}</time>:null}</div>
      <ClaimEvidence item={item}/>
    </article>;
  };
  return <div className="analysis-list">{visible.map(renderItem)}{hidden.length?<details className="hidden-analysis-items"><summary>íì ë¶ì {hidden.length}ê±´ ë³´ê¸°</summary><div>{hidden.map((item,index)=>renderItem(item,index+limit))}</div></details>:null}</div>;
}

function EventTable({events,onOpen}){
  return <div className="scroll-table"><table><thead><tr><th>Model Time</th><th>ì¤ë¹</th><th>ì¬ê±´</th><th>ìì²</th><th>ìì¸</th></tr></thead><tbody>{events.map((event,index)=>{const time=displayAccidentTime(event);const ids=event.evidence_ids?.length?event.evidence_ids:[event.evidence_id||event.event_id].filter(Boolean);const title=operatorSummary(event)||event.message||friendlyTag(event.tag);const open=()=>onOpen({kind:'claim',title,evidenceIds:ids,tags:[event.source_node||event.tag].filter(Boolean)});return <tr className="interactive-row" role="button" tabIndex={0} aria-label={`${title} ìì¸ ë³´ê¸°`} key={event.event_id||index} onClick={open} onKeyDown={keyEvent=>{if(keyEvent.key==='Enter'||keyEvent.key===' '){keyEvent.preventDefault();open();}}}><td><b>{time.primary}</b>{time.secondary?<small>{time.secondary}</small>:null}</td><td>{event.equipment||'â'}</td><td>{title}</td><td>{event.source||'â'}</td><td>ìì¸ ë³´ê¸°</td></tr>;})}</tbody></table></div>;
}

function OperatorTimeline({events,onOpen}){
  const timeline=compactTimeline(events,7);
  return <div className="operator-timeline">{timeline.visible.map((event,index)=>{const time=displayAccidentTime(event);const summary=conciseClaim(operatorSummary(event)||event.message||friendlyTag(event.tag),140).summary;const ids=event.evidence_ids?.length?event.evidence_ids:[event.evidence_id||event.event_id].filter(Boolean);const open=()=>onOpen({kind:'claim',title:summary,evidenceIds:ids,tags:[...(event.related_tags||[]),event.source_node||event.tag].filter(Boolean)});return <article className="interactive-surface" role="button" tabIndex={0} aria-label={`${summary} ìì¸ ë³´ê¸°`} key={event.event_id||index} onClick={open} onKeyDown={keyEvent=>{if(keyEvent.key==='Enter'||keyEvent.key===' '){keyEvent.preventDefault();open();}}}><time><b>{time.primary}</b>{time.secondary?<small>{time.secondary}</small>:null}</time><div><span>{event.equipment||event.event_class||'PLANT'}</span><strong>{summary}</strong></div><span className="detail-cue">ìì¸ ë³´ê¸°</span></article>;})}{timeline.hiddenCount?<p>íì ê¸°ë¡ {timeline.hiddenCount}ê±´ì ì ì²´ ì¬ê±´ ê¸°ë¡ìì íì¸</p>:null}</div>;
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
  const title=detail.title||first?.display_name||first?.message||(detail.kind==='tag'?'íê·¸ ìì¸':'ìì¸ ê·¼ê±°');
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
        {time.secondary?<div><dt>ê¸°ë¡ ìê°</dt><dd>{time.secondary}</dd></div>:null}
        <div><dt>ìí</dt><dd>{entry.state||String(entry.value??'â')}</dd></div>
      </dl>
      <details className="technical-details"><summary>ê¸°ì  ì ë³´ ë³´ê¸°</summary><dl><div><dt>íê·¸</dt><dd>{entry.canonical_tag||entry.source_node||entry.tag||'â'}</dd></div><div><dt>ìì ê°</dt><dd>{String(entry.value??'â')}</dd></div><div><dt>êµ¬ë¶</dt><dd>{entry.source_kind||entry.source||'â'}</dd></div></dl></details>
    </section>;
  };
  if(logicSelection){
    const query=new URLSearchParams();
    if(logicSelection.rule)query.set('rule',logicSelection.rule);
    else if(logicSelection.tag)query.set('tag',logicSelection.tag);
    const src=`/logic-assets/viewer.html${query.toString()?'#'+query:''}`;
    return <aside className="evidence-drawer" role="dialog" aria-modal="false" aria-labelledby="evidence-drawer-title" tabIndex={-1} ref={drawerRef}>
      <header className="evidence-drawer-head">
        <button ref={logicBackRef} className="drawer-back" type="button" onClick={()=>setLogicSelection(null)}>ì¬ê±´ ìì¸ë¡ ëìê°ê¸°</button>
        <div><span>ì°ê²° ë¡ì§</span><h2 id="evidence-drawer-title">{title}</h2></div>
        <button type="button" onClick={onClose} aria-label="ìì¸ í¨ë ë«ê¸°">ë«ê¸°</button>
      </header>
      <div className="evidence-drawer-body drawer-logic-view">
        {targets.roles.length?<div className="drawer-logic-tabs" aria-label="ì°ê²° ë¡ì§ ëª©ë¡">{targets.roles.map(role=><button type="button" className={logicSelection.rule===role.id?'active':''} key={role.id} onClick={()=>setLogicSelection({tag:'',rule:role.id})}><span>{role.label}</span><b>{role.id}</b></button>)}</div>:null}
        <LogicViewerFrame key={`${logicSelection.tag}-${logicSelection.rule}`} title={`${title} ì°ê²° ë¡ì§`} src={src} tag={logicSelection.tag} rule={logicSelection.rule} style={{width:'100%',flex:1,minHeight:0,border:0,display:'block'}}/>
      </div>
    </aside>;
  }
  return <aside className="evidence-drawer" role="dialog" aria-modal="false" aria-labelledby="evidence-drawer-title" tabIndex={-1} ref={drawerRef}>
    <header className="evidence-drawer-head">
      <div><span>ìì¸ ì ë³´</span><h2 id="evidence-drawer-title">{title}</h2></div>
      <button type="button" onClick={onClose} aria-label="ìì¸ í¨ë ë«ê¸°">ë«ê¸°</button>
    </header>
    <div className="evidence-drawer-body">
      {detail.summary?<p className="drawer-summary">{detail.summary}</p>:null}
      {detail.description?<details className="drawer-description"><summary>ë¶ì ì¤ëª</summary><p>{detail.description}</p></details>:null}
      {detail.tags?.length?<div className="drawer-tags"><b>ì¶ê° ê·¼ê±° íê·¸</b>{detail.tags.map(tag=><span key={tag}>{friendlyTag(tag)}</span>)}</div>:null}
      <div className="drawer-actions"><button type="button" onClick={onShowSources}>ìë³¸ EVENTÂ·RAW ë³´ê¸°</button>{targets.entry?<button ref={logicTriggerRef} className="drawer-logic-button" type="button" onClick={()=>setLogicSelection({tag:targets.entry.tag,rule:''})}><b>ì°ê²° ë¡ì§ ë³´ê¸° Â· {targets.entry.ruleCount}ê°</b></button>:null}</div>
      {coreRows.length?coreRows.map((entry,index)=>renderEvidenceCard(entry,index)):<div className="empty-state">ì°ê²°ë ìì¸ ê·¼ê±°ê° ììµëë¤.</div>}
      {rows.length>5?<details className="drawer-raw-list"><summary>ìì ë°ì´í° ë³´ê¸° Â· {rows.length-5}ê±´</summary><div>{rawRows.map((entry,index)=>renderEvidenceCard(entry,index,'raw'))}{rows.length>25?<p>ëë¨¸ì§ {rows.length-25}ê±´ì ìë³¸ EVENTÂ·RAW íë©´ìì íì¸íì¸ì.</p>:null}</div></details>:null}
    </div>
  </aside>;
}

function OperatorReportPreview({analysis,events,recovery,report}){
  const timeline=compactTimeline(events,7);
  const primary=conciseClaim(operatorSummary(analysis.primary_cause,'primary'),140).summary;
  const direct=conciseClaim(operatorSummary(analysis.direct_trigger,'direct'),140).summary;
  const summary=primary&&direct&&primary!==direct?`${primary} ì´í ${direct}ì´ íì¸ë¨.`:(direct||primary||'â');
  const conclusion=`${direct||'ì§ì  ë³´í¸ëì'} ì´í ì°¨ë¨ê¸° ê°ë°©ê³¼ íì ê³µì  ìëµì´ ìì°¨ì ì¼ë¡ ë°ìí¨.`;
  const documentMeta=reportExporter.reportDocumentMeta(report);
  const hasRecovery=hasRecoveryRecord(recovery);
  return <div className="operator-report-preview">
    <header className="operator-report-document-head">
      <div className="operator-report-title"><span>TRIPLENS INCIDENT REPORT</span><h3>ì¤ë¹ ê³ ì¥ ë¶ìë³´ê³ ì</h3><p>EVENTÂ·RAW ê¸°ë° ì¬ê³  ê²½ì ë° ë³´í¸ëì ë¶ì</p></div>
      <table className="operator-report-approval"><caption>ê²°ì¬</caption><thead><tr><th>ìì±</th><th>ê²í </th><th>ì¹ì¸</th></tr></thead><tbody><tr><td>{documentMeta.author||'\u00a0'}</td><td>{documentMeta.reviewer||'\u00a0'}</td><td>{documentMeta.approver||'\u00a0'}</td></tr><tr><td>{documentMeta.authoredAt||'\u00a0'}</td><td>{documentMeta.reviewedAt||'\u00a0'}</td><td>{documentMeta.approvedAt||'\u00a0'}</td></tr></tbody></table>
      <dl className="operator-report-document-meta"><div><dt>ë³´ê³ ì ë²í¸</dt><dd>{documentMeta.reportNo}</dd></div><div><dt>ì¬ê³  ìê°</dt><dd>{documentMeta.incidentTime.primary}{documentMeta.incidentTime.secondary?<small>{documentMeta.incidentTime.secondary}</small>:null}</dd></div><div><dt>ëì ì¤ë¹</dt><dd>{documentMeta.equipment}</dd></div><div><dt>ìë ¥ ìë£</dt><dd>{documentMeta.inputFiles}</dd></div></dl>
    </header>
    <div className="operator-report-summary"><span>ì¬ê³  ê°ì</span><strong>{summary}</strong></div>
    <div className="operator-report-causes"><div><span>ë°ì ìì¸</span><strong>{primary||'â'}</strong></div><div><span>ì§ì  ë³´í¸ëì</span><strong>{direct||'â'}</strong></div></div>
    <div className="operator-report-timeline"><h3>ìê°ì ì¬ê³  ê²½ì</h3>{timeline.visible.map((event,index)=>{const display=displayEventTime(event);const primaryTime=event.model_time_s===null||event.model_time_s===undefined?display.primary:modelTime(event.model_time_s);const secondaryTime=primaryTime===display.primary?display.secondary:display.primary;const summary=conciseClaim(operatorSummary(event)||event.message||friendlyTag(event.tag),140).summary;return <div key={event.event_id||index}><time>{primaryTime}{secondaryTime?<small>{secondaryTime}</small>:null}</time><b>{event.equipment||event.event_class||'PLANT'}</b><span>{summary}</span></div>;})}{timeline.hiddenCount?<p>íì ê¸°ë¡ {timeline.hiddenCount}ê±´ì ìì¸ ë¶ì ë°ì´í°ì í¬í¨ë©ëë¤.</p>:null}</div>
    <div className="operator-report-conclusion"><span>ë¶ì ê²°ë¡ </span><strong>{conclusion}</strong></div>
    {hasRecovery?<div className="operator-report-recovery"><span>ë³µêµ¬ì¡°ì¹ ë° íì¸ì¬í­</span><strong>{recovery.actions}</strong></div>:null}
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
      setStatusText('ë íì¼ì í©ê³ë 4 MB ì´íì¬ì¼ í©ëë¤.');
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
      if(prepared.evidence_readiness?.status!=='PASS')throw new Error('EVENT.csvì RAW.csvì ìê° ë²ìì íìì íì¸í´ ì£¼ì¸ì.');
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
    anchor.download=`TripLens_ê³ ì¥ë¶ìë³´ê³ ì_${result?.run_id||'analysis'}.csv`;
    anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  function exportPDF(){if(!exportBlocked)reportExporter.printReport(exportReport);}
  function exportDetailedCSV(){if(!exportBlocked)reportExporter.downloadPinpointCsv(exportReport,`TripLens_ìì¸ë¶ìë°ì´í°_${result?.run_id||'analysis'}.csv`);}

  function editReportRow(row,key,value){
    setReportRows(rows=>rows.map(existing=>existing.row_id===row.row_id?{...existing,[key]:value,edited:true}:existing));
  }

  const detailRows=selectDetailEvidence(catalog,detail);

  let view;
  if(!result){
    view=<WaitingPanel status={status}/>;
  }else if(activeTab==='cause'){
    view=<div className="panel-stack cause-layout">
      <div className="section-heading"><div><h2>ìì¸ ë¶ì</h2></div></div>
      <div className="cause-grid">
        <ClaimCard title={operatorPresentation.primaryTitle} stage="primary" item={operatorAnalysis.primary_cause} onOpen={openDetail}/>
        <ClaimCard title="ì§ì  ë³´í¸ëì" stage="direct" item={operatorAnalysis.direct_trigger} onOpen={openDetail}/>
      </div>
      <section className="analysis-section">
        <div className="analysis-section-head"><div><h3>íê¸ ê³¼ì </h3></div><p>ë³´í¸ëì ì´íì ì¤ë¹ ë³í</p></div>
        <AnalysisList items={operatorAnalysis.propagation} stage="propagation" onOpen={openDetail}/>
      </section>
      <section className="analysis-section causal-section">
        <div className="analysis-section-head"><div><h3>ìê°ì ì¬ê³  ê²½ì</h3></div><p>ìì¸ ì¸ê³¼ê´ê³</p></div>
        <details><summary>ìì¸ ìê°ìì ë³´ê¸°</summary><AnalysisList items={operatorAnalysis.causal_chain} stage="causal" onOpen={openDetail}/></details>
      </section>
    </div>;
  }else if(activeTab==='timeline'){
    view=<div className="panel-stack">
      <div className="section-heading"><h2>ì¬ê³  ì§í ê³¼ì </h2><span>EVENT {events.length}ê±´</span></div>
      <section className="analysis-section"><h3>ì£¼ì ì¬ê±´</h3><OperatorTimeline events={events} onOpen={openDetail}/></section>
      <details className="analysis-details"><summary>ì ì²´ ì¬ê±´ ê¸°ë¡ ë³´ê¸° Â· {events.length}ê±´</summary><EventTable events={events} onOpen={openDetail}/></details>
    </div>;
  }else if(activeTab==='checks'){
    const checks=[...analysis.additional_evidence_required,...analysis.review_recommendations];
    view=<div className="panel-stack"><div className="section-heading"><h2>ì¦ì íì¸Â·ëì</h2></div>{checks.length?checks.map((text,index)=><div className="check-row" key={index}><span>{String(index+1).padStart(2,'0')}</span><p>{text}</p></div>):<div className="empty-state">ì¶ê° íì¸ í­ëª©ì´ ììµëë¤.</div>}</div>;
  }else if(activeTab==='recovery'){
    view=<div className="panel-stack"><div className="section-heading"><h2>ë³µêµ¬ ê¸°ë¡</h2></div><RecoveryForm value={recovery} onChange={setRecovery} catalog={catalog}/></div>;
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
    view=<div className="panel-stack"><div className="section-heading"><h2>ìì¸ ê·¼ê±°</h2><span>{filtered.length}ê±´{activeEvidenceFilters?` Â· íì± íí° ${activeEvidenceFilters}ê°`:''}</span></div><div className="evidence-filter-bar"><input className="filter-input" aria-label="ê·¼ê±° ê²ì" placeholder="ì í¸ ëë íê·¸ ê²ì" value={evidenceQuery} onChange={event=>setEvidenceQuery(event.target.value)}/><select aria-label="ê·¼ê±° êµ¬ë¶ íí°" value={evidenceKind} onChange={event=>setEvidenceKind(event.target.value)}><option value="">ì ì²´ êµ¬ë¶</option>{evidenceKinds.map(kind=><option key={kind} value={kind}>{kind}</option>)}</select><select aria-label="ê·¼ê±° ìí íí°" value={evidenceState} onChange={event=>setEvidenceState(event.target.value)}><option value="">ì ì²´ ìí</option>{evidenceStates.map(state=><option key={state} value={state}>{state}</option>)}</select>{activeEvidenceFilters?<button type="button" onClick={()=>{setEvidenceQuery('');setEvidenceKind('');setEvidenceState('');}}>íí° ì´ê¸°í</button>:null}</div><div className="scroll-table evidence-table"><table><thead><tr><th>Model Time</th><th>êµ¬ë¶</th><th>ì í¸</th><th>ìí</th><th>ê°</th></tr></thead><tbody>{visibleEvidence.map((entry,index)=>{const time=displayAccidentTime(entry);const ids=entry.evidence_ids?.length?entry.evidence_ids:[entry.evidence_id].filter(Boolean);const signal=entry.display_name||entry.message||friendlyTag(entry.source_node||entry.canonical_tag||entry.tag);const selected=ids.some(id=>detail?.evidenceIds?.includes(id)||detail?.value===id);const open=()=>openDetail({kind:'claim',title:signal,evidenceIds:ids,tags:[entry.source_node||entry.canonical_tag||entry.tag].filter(Boolean)});return <tr className={`interactive-row ${selected?'selected':''}`} role="button" tabIndex={0} aria-label={`${signal} ìì¸ ë³´ê¸°`} key={entry.evidence_id||index} onClick={open} onKeyDown={keyEvent=>{if(keyEvent.key==='Enter'||keyEvent.key===' '){keyEvent.preventDefault();open();}}}><td><b>{time.primary}</b>{time.secondary?<small>{time.secondary}</small>:null}</td><td>{entry.source_kind||entry.source||'â'}</td><td>{signal}{entry.repeat_count>1?<small>ëì¼ ìí {entry.repeat_count}ê±´</small>:null}</td><td>{entry.state||'â'}</td><td>{String(entry.value??'â')}</td></tr>;})}</tbody></table>{filtered.length>visibleEvidence.length?<p className="evidence-overflow">íì ê·¼ê±° {filtered.length-visibleEvidence.length}ê±´ Â· ê²ì ëë íí°ë¡ ë²ìë¥¼ ì¢í ì£¼ì¸ì.</p>:null}</div></div>;
  }

  return <main className={`app-shell ${detail?'detail-open':''}`}>
    <header className="topbar">
      <div className="brand"><div className="brand-mark">TL</div><div><h1>TripLens</h1><span>DUAL-INPUT ACCIDENT ANALYSIS</span></div></div>
      <div className="status-rail">
        <div><span>ìë ¥ ìí</span><b>{result?'ë¶ì ìë£':ready?'ë¶ì ì¤ë¹':'Dual Log ëê¸°'}</b></div>
        <div><span>ìµì´ ëì</span><b>{metrics.firstTime}</b></div>
        <div><span>ë³´í¸ ëì</span><b>{metrics.protection}ê±´</b></div>
        <div><span>íì ìë</span><b>{metrics.alarms}ê±´</b></div>
      </div>
    </header>
    {mode==='demo'?<div className="demo-banner">ìì°ì© ë¶ì íë©´</div>:null}
    <div className="workspace">
      <aside className="sidebar">
        <div className="side-title">ANALYSIS WORKSPACE</div>
        <nav>{WORKSPACE_TABS.map(tab=><button disabled={!result} className={`nav-item ${activeTab===tab.id?'active':''}`} key={tab.id} onClick={()=>{setActiveTab(tab.id);setDetail(null);}}><span className="nav-no">{tab.no}</span><span><b>{tab.label}</b><em>{tab.sub}</em></span></button>)}</nav>
        <div className="side-links"><button onClick={()=>openLogicLibrary()}><b>LM</b><span>Logic / TAG Master<em>{logic?`${logic.live_rules} Logic Â· ${logic.protection} Protection`:'íê·¸ ê²ì Â· ë¡ì§ ì°ê²°'}</em></span></button></div>
        <div className="boundary"><b>READ-ONLY</b><span>ë¶ì ë° ë³´ê³ ì ì ì©</span></div>
      </aside>
      <section className="main-area">
        <section className="intake">
          <div className="intake-copy"><div className="eyebrow">DUAL LOG INTAKE</div><h2>EVENT.csv + RAW.csv</h2><p>ì¬ê±´ ê¸°ë¡ê³¼ ê³µì  ë°ì´í°ë¥¼ í¨ê» ë¶ìí©ëë¤.</p></div>
          <div className="file-grid">{[
            ['event',eventFile,eventData],
            ['raw',rawFile,rawData],
          ].map(([kind,file,data])=><label className={`file-card ${file?'ready':''}`} key={kind}><span>{kind.toUpperCase()}.csv</span><b>{file?.name||'íì¼ ì í'}</b><em>{file?`${(file.size/1024).toFixed(1)} KB Â· ${data?.records.length??'íì¸ ì¤'}${kind==='event'?'ê±´':'í'}${kind==='raw'&&data?` Â· ${rawTagCount(data)}ê° íê·¸`:''}`:''}</em><input disabled={busy} type="file" accept=".csv,text/csv" aria-label={`${kind.toUpperCase()} íì¼`} onClick={event=>{event.currentTarget.value='';}} onChange={event=>selectFile(kind,event.target.files?.[0])}/></label>)}</div>
          <div className="analysis-status" aria-live="polite"><b>{status.title}</b>{status.detail?<span>{status.detail}</span>:null}{statusText?<em role="alert">{statusText}</em>:null}</div>
          <div className="intake-actions">
            <button disabled={!ready||busy||Boolean(result)} onClick={analyze}>{busy?'ë¶ì ì¤â¦':result?'ë¶ì ìë£':'ì´ Dual Log ë¶ìíê¸°'}</button>
            <button disabled={!result} className="secondary" onClick={()=>{setReportOpen(!reportOpen);setDetail(null);}}>ê³ ì¥ë¶ì ë³´ê³ ì ë³´ê¸°</button>
            <button disabled={busy} className="secondary" onClick={clear}>ìë ¥Â·ë¶ì ì§ì°ê¸°</button>
          </div>
        </section>

        {result&&exportBlocked?<p className="warning-box" role="alert">ì¼ë¶ ê·¼ê±° ì°ê²°ì íì¸í í ë´ë³´ë¼ ì ììµëë¤: {missingEvidence.length}ê±´</p>:null}
        <section className="analysis-surface">{view}</section>
        <EvidenceDrawer key={detail?.evidenceIds?.join('|')||detail?.title||'closed'} detail={detail} rows={detailRows} onClose={closeDetail} onShowSources={()=>{setEvidenceQuery('');setEvidenceKind('');setEvidenceState('');setActiveTab('evidence');}} drawerRef={drawerRef}/>

        {reportOpen&&result?<section className="report-preview">
          <div className="section-heading report-actions">
            <h2>ë³´ê³ ì ë¯¸ë¦¬ë³´ê¸°</h2>
            <button className="export-button" disabled={exportBlocked} onClick={exportPDF}>ë³´ê³ ì PDF ì ì¥</button>
            <details className="export-menu"><summary>ë´ë³´ë´ê¸°</summary><div><button className="export-button" disabled={exportBlocked} onClick={exportCSV}>ë³´ê³ ì CSV</button><button className="export-button" disabled={exportBlocked} onClick={exportDetailedCSV}>ìì¸ ë¶ì ë°ì´í° CSV</button></div></details>
          </div>
          <p className="report-help">íµì¬ ì¬ê³  ê²½ìì ê²°ì¬ ì ë³´ë¥¼ íì¸í©ëë¤.</p>
          <OperatorReportPreview analysis={operatorAnalysis} events={events} recovery={recovery} report={exportReport}/>
          <details className="report-editor"><summary>ë³´ê³ ì ì¸ë¶ í­ëª© í¸ì§</summary><div className="scroll-table"><table className="editable-report"><thead><tr>{REPORT_COLUMNS.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{displayReportRows.map((row,index)=>{
            const recoveryRow=row.row_id?.startsWith('RECOVERY-');
            return <tr key={row.row_id||index} data-row-id={row.row_id}>{REPORT_KEYS.map((key,column)=><td key={key} data-label={REPORT_COLUMNS[column]}>{key==='status'?(recoveryRow||!CLAIM_STATUS_CHOICES.includes(row.status)?<span className="report-status" data-status={row.status}>{reportStatusLabel(row.status)}</span>:<select aria-label={`ë³´ê³ ì ${index+1} ìí`} value={row.status} onChange={event=>editReportRow(row,key,event.target.value)}>{CLAIM_STATUS_CHOICES.map(statusValue=><option key={statusValue} value={statusValue}>{REPORT_STATUS_TEXT[statusValue]}</option>)}</select>):recoveryRow?<div className="report-readonly">{row[key]||'â'}{key==='content'?<button className="tag-link" onClick={()=>{setActiveTab('recovery');setDetail(null);requestAnimationFrame(()=>document.querySelector('.recovery-form')?.scrollIntoView({block:'start'}));}}>ë³µêµ¬ ê¸°ë¡ìì í¸ì§</button>:null}</div>:<textarea aria-label={`ë³´ê³ ì ${index+1} ${key}`} value={row[key]||''} onChange={event=>editReportRow(row,key,event.target.value)}/>}</td>)}</tr>;
          })}</tbody></table></div></details>
        </section>:null}
      </section>
    </div>
    <LogicLibraryDialog analysisMode/>
  </main>;
}
