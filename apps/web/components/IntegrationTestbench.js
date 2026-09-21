'use client';
import {useEffect,useMemo,useState} from 'react';
import {LogicLibraryDialog,openLogicLibrary} from './LogicLibrary';
import {DEVICE_TEST_CASES,buildExportReport,evaluateDeviceCases} from '../lib/integrationTestbench.mjs';
import reportExporter from '../lib/reportExporter.cjs';
import '../app/integration.css';

const SAMPLE_REPORT_ROWS=[
  {section:'개요',item:'장애 요약',content:'단위기기 연동 테스트용 보고서 문구',status:'OBSERVED',evidence_ids:'TEST-EV-1',tags:'vppGTTripLatch',time:'48.440 s',note:'합성 테스트 데이터',edited:true},
  {section:'발생 원인',item:'직접 Trip 원인',content:'등록 로직 연결 검증용 후보',status:'CANDIDATE',evidence_ids:'TEST-EV-1',tags:'vppGTTripLatch',time:'48.440 s',note:'원인 확정 아님'},
];

function sampleReport(){
  return buildExportReport({
    result:{run_id:'TESTBENCH-LOCAL',data_digest:'STATIC-FIXTURE'},
    analysis:{verification_gate:'HOLD',critical_events:[],primary_cause:{},direct_trigger:{},propagation:[],causal_chain:[],counter_evidence:[]},
    events:[],catalog:[],reportRows:SAMPLE_REPORT_ROWS,eventFileName:'TEST_EVENT.csv',rawFileName:'TEST_RAW.csv',
  });
}

export default function IntegrationTestbench(){
  const [index,setIndex]=useState(null);
  const [error,setError]=useState('');
  useEffect(()=>{let active=true;fetch('/logic-assets/logic_diagram_index.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();}).then(data=>{if(active)setIndex(data);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[]);
  const rows=useMemo(()=>index?evaluateDeviceCases(index):[],[index]);
  const report=useMemo(sampleReport,[]);
  const reportChecks=useMemo(()=>{
    const html=reportExporter.buildReportHtml(report);
    const pinpoint=reportExporter.buildPinpointCsv(report);
    return [
      {label:'편집 행 → 보고서 V2',pass:html.includes(SAMPLE_REPORT_ROWS[0].content)&&!html.includes('EVENT + RAW 사고분석 초안')},
      {label:'A4 PDF 출력 템플릿',pass:html.includes('@page{size:A4')&&html.includes('4. 복구조치 및 확인사항')},
      {label:'PINPOINT.csv 스키마',pass:pinpoint.startsWith('run_id,pinpoint_rank,causal_stage,claim,disposition,')},
    ];
  },[report]);
  const allPass=rows.length===DEVICE_TEST_CASES.length&&rows.every(row=>row.status==='PASS')&&reportChecks.every(check=>check.pass);
  return <main className="testbench-shell">
    <header className="testbench-head"><div><div className="eyebrow">STATIC INTEGRATION TESTBENCH</div><h1>TripLens 연동 단위기기 테스트</h1><p>Gemini/API를 호출하지 않고 배포물의 Tag Master → Logic Master → draw.io 도면 → 보고서 V2 연결만 검사합니다.</p></div><a className="back-button" href="/">분석 화면으로</a></header>
    <section className={`testbench-summary ${allPass?'pass':'hold'}`} aria-live="polite"><b>{error?'FAIL':index?(allPass?'ALL PASS':'FAIL'):'검사 중'}</b><span>{error?`도면 인덱스를 읽지 못했습니다: ${error}`:index?`기기 ${rows.filter(r=>r.status==='PASS').length}/${DEVICE_TEST_CASES.length} · 보고서 ${reportChecks.filter(c=>c.pass).length}/${reportChecks.length}`:'정적 자산을 불러오는 중입니다.'}</span></section>
    <section className="testbench-panel"><div className="section-heading"><h2>단위기기 연결</h2><span>실데이터/원인판정 미사용</span></div><div className="scroll-table"><table><thead><tr><th>설비</th><th>Source Tag</th><th>등록 Rule</th><th>Tag</th><th>Link</th><th>Logic</th><th>Page</th><th>도면 확인</th></tr></thead><tbody>{rows.map(row=><tr key={row.id} data-status={row.status}><td><b>{row.equipment}</b><small>{row.status}</small></td><td>{row.tag}</td><td>{row.rule}</td>{Object.values(row.checks).map((pass,i)=><td key={i} className={pass?'check-pass':'check-fail'}>{pass?'PASS':'FAIL'}</td>)}<td><div className="testbench-actions"><button onClick={()=>openLogicLibrary({tag:row.tag})}>태그 도면</button><button onClick={()=>openLogicLibrary({rule:row.rule})}>Rule 도면</button></div></td></tr>)}</tbody></table></div></section>
    <section className="testbench-panel"><div className="section-heading"><h2>보고서 V2 내보내기</h2><span>합성 fixture · 외부 호출 없음</span></div><div className="report-checks">{reportChecks.map(check=><div key={check.label}><b className={check.pass?'check-pass':'check-fail'}>{check.pass?'PASS':'FAIL'}</b><span>{check.label}</span></div>)}</div><div className="testbench-actions"><button onClick={()=>reportExporter.printReport(report)}>샘플 보고서 V2 PDF</button><button onClick={()=>reportExporter.downloadPinpointCsv(report,'TripLens_TESTBENCH_PINPOINT.csv')}>샘플 PINPOINT.csv</button></div></section>
    <section className="warning-box">이 화면의 PASS는 정적 연결 무결성을 뜻합니다. 사고 원인 확정, 실설비 상태 확인, 운전·복구 승인을 뜻하지 않습니다.</section>
    <LogicLibraryDialog />
  </main>;
}
