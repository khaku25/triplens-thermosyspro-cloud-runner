import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const exporter = require('../webapp/triplens_report_export.js');

const report = {
  title: 'TripLens Incident Analysis Report',
  run_id: 'RUN-TEST-001',
  verification_gate: 'HOLD',
  metadata: { run_id: 'RUN-TEST-001', event_file: 'EVENT.csv', raw_file: 'RAW.csv' },
  incident_summary: 'Dual Log evidence preserved',
  critical_events: [{ claim: 'ST Trip latch active', disposition: 'CONFIRMED', evidence: [{ source_system:'DCS1', event_id:'EV-1', original_time:'48.440', aligned_time:'48.440', equipment:'ST', event_tag:'TRIP_LATCH', canonical_tag:'ST.TRIP.LATCH', value:1, unit:'BOOL', state:'ACTIVE', evidence_role:'TRIGGER', mapping_status:'EVENT_RULE' }] }],
  primary_cause: { claim:'Cause candidate', disposition:'CANDIDATE', evidence_ids:['RAW-017'], related_tags:['ST.SPEED'], recorded_time:'48.200', ai_confidence:0.84, logic_master_status:'NOT_VERIFIED', review_required:true },
  direct_trigger: { claim:'ST Trip latch', status:'CONFIRMED', evidence_ids:['EV-1'], related_tags:['ST.TRIP.LATCH'], recorded_time:'48.440', logic_master_status:'VERIFIED' },
  propagation: [{ claim:'52ST open -> secondary alarms', status:'OBSERVED', evidence_ids:['EV-2'], related_tags:['52ST'], recorded_time:'48.610' }],
  causal_chain: ['ST Trip latch', '52ST breaker open'],
  key_evidence: [{ source:'EVENT.csv', tag:'TRIP_LATCH' }],
  recovery_check: 'Not fully recovered',
  gemini_analysis: 'Additional engineering review text',
  counter_evidence: ['No independent mechanical-failure evidence'],
  additional_evidence_required: ['Protection relay record'],
  recommendations: [{ claim:'보호 설정 검토', evidence_ids:['EV-1'] }],
  chronological_events: Array.from({length:12},(_,i)=>({ recorded_time:String(48+i/10), category:'SOE', claim:`Chronology ${i+1}`, status:'OBSERVED', evidence_ids:[`SEQ-${i+1}`], related_tags:[`TAG_${i+1}`] })),
};

test('PDF report uses the approved four-page Figma V2 shell', () => {
  const html=exporter.buildReportHtml({
    ...report,
    operating_status:{'GT 상태':'운전 중','ST 상태':'운전 중'},
    report_rows:[
      {section:'개요',item:'장애 요약',content:'GT·ST Trip Latch 동작 후 차단기 개방과 공정 저하가 이어짐'},
      {section:'사고 발생 전 운전 현황',item:'GT 상태',content:'운전 중'},
      {section:'장애 현상',item:'최초 Event',content:'GT Trip Latch 동작',status:'CONFIRMED',evidence_ids:'EV-1',tags:'vppGTTripLatch',time:'48.440 s'},
      {section:'발생 원인',item:'선행 원인',content:'GT 운전 중 차단기 개로 원인 활성화됨',status:'CANDIDATE',evidence_ids:'RAW-017',tags:'vppCauseGTBreakerOpenWhileRunning',time:'48.200 s'},
      {section:'증거자료',item:'RAW-017',content:'52GT 투입 명령',status:'OBSERVED',evidence_ids:'RAW-017',tags:'vppECMS52GTClosedCommandNative',time:'48.200 s'},
    ],
  });
  assert.equal((html.match(/class="report-page"/g)||[]).length,4);
  for(const text of [
    '설비 장애·고장 보고서','1. 개요','2. 운전 현황','3. 장애 현상','5. 발생 원인',
    '4. 시간대별 조치사항','5-1. 인과관계 요약','8. 재발방지 대책','9. 증거자료',
    'vppECMS52GTClosedCommandNative','4 / 4',
  ])assert.match(html,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  assert.doesNotMatch(html,/class="doc-meta"|Run ID|Data Digest/);
  assert.doesNotMatch(html,/text-overflow\s*:\s*ellipsis|…|\.\.\./);
  assert.doesNotMatch(html,/입력 필요|입력 대기|미기록|기록 없음/);
});

test('PDF approval grid row stays inside the fixed report header box', () => {
  const html=exporter.buildReportHtml(report);
  assert.match(html,/\.report-head\{[^}]*grid-template-rows:minmax\(0,1fr\)/);
});

test('PDF fitter contains width-sensitive reflow instead of clipping the final section', () => {
  const html=exporter.buildReportHtml(report);
  const script=html.match(/<script>([\s\S]*?)<\/script>/)?.[1] || '';
  const style={transform:'none',width:'100%'};
  const layoutHeight=()=>parseFloat(style.width) >= 102 ? 937 : 951;
  const transformScale=()=>Number(style.transform.match(/scale\(([^)]+)\)/)?.[1] || 1);
  const content={
    style,
    dataset:{},
    get scrollHeight(){return layoutHeight();},
    getBoundingClientRect(){
      const height=layoutHeight()*transformScale();
      return {top:0,bottom:height,height};
    },
  };
  const body={
    clientHeight:926,
    querySelector:selector=>selector==='.page-content'?content:null,
    getBoundingClientRect:()=>({top:0,bottom:926,height:926}),
  };
  const sandbox={
    document:{querySelectorAll:selector=>selector==='.page-body'?[body]:[]},
    window:{},
    requestAnimationFrame:callback=>callback(),
  };
  vm.runInNewContext(script,sandbox);
  sandbox.window.TripLensFitReport();
  const overflow=content.getBoundingClientRect().bottom-body.getBoundingClientRect().bottom;
  assert.ok(overflow <= 1,`report content exceeds its page body by ${overflow.toFixed(3)}px`);
});

test('four-page PDF bounds large timelines and discloses CSV continuation', () => {
  const html=exporter.buildReportHtml({
    ...report,
    chronological_events:Array.from({length:40},(_,index)=>({
      recorded_time:48+index/10,
      category:'SOE',
      claim:`Bulk event ${String(index+1).padStart(2,'0')}`,
      status:'OBSERVED',
      evidence_ids:[`BULK-${index+1}`],
    })),
  });
  assert.equal((html.match(/class="report-page"/g)||[]).length,4);
  assert.match(html,/Bulk event 12/);
  assert.doesNotMatch(html,/Bulk event 13/);
  assert.match(html,/총 이벤트<\/span><b>40건/);
  assert.match(html,/PDF 표시<\/span><b>12건/);
  assert.match(html,/나머지 28건은 보고서 CSV/);
  assert.match(html,/function fitReportPages\(\)/);
  assert.match(html,/@media print\{[\s\S]*?\.report-page\{[^}]*overflow:hidden!important/);
  assert.doesNotMatch(html,/\.report-page,section,table,tr\{overflow:visible/);
});

test('PDF report HTML follows the Figma V2 operating report structure', () => {
  const html = exporter.buildReportHtml(report);
  for (const text of ['설비 장애·고장 보고서','1. 개요','2. 운전 현황','3. 장애 현상','5. 발생 원인','4. 시간대별 조치사항','5-1. 인과관계 요약','9. 증거자료','EVENT.csv','RAW.csv']) assert.match(html,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  for (const text of ['Verification Gate','AI Confidence','CANDIDATE','(초안)']) assert.doesNotMatch(html,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  assert.match(html,/\.report-page\{margin:0;height:297mm!important;min-height:297mm!important;max-height:297mm!important;overflow:hidden!important\}/);
  assert.match(html,/window\.TripLensFitReport=fitReportPages/);
  assert.doesNotMatch(html,/T\+0\.000 s/);
  assert.doesNotMatch(html,/>Gemini Analysis</);
});

test('PINPOINT CSV keeps canonical evidence and review state', () => {
  const csv = exporter.buildPinpointCsv(report);
  assert.match(csv,/^run_id,pinpoint_rank,causal_stage,claim,disposition,/);
  assert.match(csv,/RUN-TEST-001/);
  assert.match(csv,/ST\.TRIP\.LATCH/);
  assert.match(csv,/TRIP_LATCH/);
  assert.match(csv,/CONFIRMED/);
  assert.match(csv,/CANDIDATE/);
});

test('failure report CSV uses the fixed v2 columns and evidence-linked sections', () => {
  const csv = exporter.buildFailureReportCsv(report);
  assert.match(csv,/^구분,항목,내용,상태,근거 ID,관련 태그,기록 시각,비고/);
  for (const text of ['Primary Cause','Direct Trigger','Propagation','Critical Events']) assert.match(csv,new RegExp(text));
  assert.match(csv,/EV-1/);
  assert.equal((csv.match(/Chronology /g)||[]).length,12);
});

test('internal verification state is not shown as unfinished report copy', () => {
  const html = exporter.buildReportHtml(report);
  assert.match(html,/설비 장애·고장 보고서/);
  assert.doesNotMatch(html,/초안|Verification Gate|HOLD|검증 미완료/);
  assert.doesNotMatch(html,/Root Cause Confirmed/);
  assert.doesNotMatch(html,/>최종 확정</);
});

test('concise PDF preserves editable summary and direct-trigger wording', () => {
  const edited = {
    ...report,
    report_rows: [
      { section:'개요', item:'장애 요약', content:'운전 담당자가 수정한 최종 초안 문구', status:'OBSERVED', evidence_ids:'EV-1', tags:'ST.TRIP.LATCH', time:'48.440 s', note:'담당자 편집' },
      { section:'발생 원인', item:'직접 Trip 원인', content:'편집된 직접 Trip 원인', status:'CANDIDATE', evidence_ids:'EV-EDITED', tags:'ST.TRIP.LATCH', time:'48.440 s', note:'최종 승인 전' },
    ],
  };
  const html = exporter.buildReportHtml(edited);
  assert.match(html,/운전 담당자가 수정한 최종 초안 문구/);
  assert.match(html,/편집된 직접 Trip 원인/);
  const directCause=html.match(/<div class="cause-row"><b>직접 Trip 원인 \(Direct Trigger\)<\/b>[\s\S]*?<span class="status">[^<]+<\/span><\/div>/)?.[0] || '';
  assert.match(directCause,/△ 후보/);
  assert.doesNotMatch(directCause,/■ 확인/);
  assert.match(html,/EV-EDITED/);
  assert.doesNotMatch(html,/직접 보호동작은 확인/);
  assert.doesNotMatch(html,/Dual Log evidence preserved/);
});

test('editable timeline rows keep their own review status and evidence', () => {
  const html=exporter.buildReportHtml({
    ...report,
    chronological_events:[{
      recorded_time:48.5,
      category:'SOE',
      claim:'original confirmed event',
      status:'CONFIRMED',
      evidence_ids:['EV-ORIGINAL'],
      related_tags:['ORIGINAL.TAG'],
    }],
    report_rows:[{
      section:'시간대별 사건·자동동작(SOE)',
      item:'SOE 1',
      content:'operator downgraded event',
      status:'CANDIDATE',
      evidence_ids:'EV-EDITED',
      tags:'EDITED.TAG',
      time:'49.000 s',
      edited:true,
    }],
  });
  const row=html.match(/<tr><td><b>49\.000 s<\/b><\/td>[\s\S]*?operator downgraded event[\s\S]*?<\/tr>/)?.[0] || '';
  assert.match(row,/△ 후보/);
  assert.match(row,/EV-EDITED/);
  assert.doesNotMatch(row,/■ 확인|EV-ORIGINAL/);
  assert.doesNotMatch(html,/EV-ORIGINAL/);
});

test('workspace PDF projects ten-section source rows into the four-page report', () => {
  const workspaceSections = [
    '개요','사고 발생 전 운전 현황','장애 현상','시간대별 사건·자동동작(SOE)','발생 원인',
    '운전원·정비 조치사항','조치 결과 및 복구 판정','추정 원인 및 미확인 사항',
    '재발방지 대책 — 검토 권고사항','증거자료',
  ];
  const workspaceHtml=exporter.buildReportHtml({...report,report_rows:workspaceSections.map(section=>({section,item:'검토',content:'내용'}))});
  assert.equal((workspaceHtml.match(/class="report-page"/g)||[]).length,4);
  assert.match(workspaceHtml,/4\. 시간대별 조치사항/);
  assert.match(workspaceHtml,/9\. 증거자료/);
  assert.match(workspaceHtml,/내용/);
  assert.doesNotMatch(workspaceHtml,/10\. 증거자료/);

  const legacyHtml=exporter.buildReportHtml({...report,report_rows:[{section:'개요',item:'검토',content:'내용'}]});
  assert.match(legacyHtml,/9\. 증거자료/);
  assert.doesNotMatch(legacyHtml,/10\. 증거자료/);
});

test('legacy failure-report CSV neutralizes spreadsheet formulas without changing eight columns', () => {
  const csv=exporter.buildFailureReportCsv({...report,incident_summary:'=HYPERLINK("https://example.invalid")'});
  assert.match(csv,/'=HYPERLINK/);
  assert.doesNotMatch(csv,/개요,장애 요약,=HYPERLINK/);
  const summaryLine=csv.split('\r\n').find(line=>line.includes('HYPERLINK'));
  assert.equal(summaryLine.match(/,/g).length,7);
});

test('workspace document state keeps the same finished report title', () => {
  const reportRows=[{section:'운전원·정비 조치사항',item:'실제 수행 조치',content:'점검 완료'}];
  const draft=exporter.buildReportHtml({...report,verification_gate:'PASS',document_state:'DRAFT',report_rows:reportRows});
  assert.match(draft,/설비 장애·고장 보고서/);
  assert.doesNotMatch(draft,/설비 장애·고장 보고서 \(초안\)|설비 장애·고장 보고서 \(검토본\)/);
  const reviewed=exporter.buildReportHtml({...report,verification_gate:'PASS',document_state:'REVIEWED',report_rows:reportRows});
  assert.match(reviewed,/설비 장애·고장 보고서/);
  assert.doesNotMatch(reviewed,/설비 장애·고장 보고서 \(초안\)|설비 장애·고장 보고서 \(검토본\)/);
});

test('default PDF hides developer metadata while keeping raw tags on the evidence page', () => {
  const operatorReport={
    ...report,
    metadata:{
      ...report.metadata,
      data_digest:'secret-digest',
      analysis_engine:'Gemini Tool Analysis',
    },
    primary_cause:{
      ...report.primary_cause,
      claim:'외부 트립 명령 태그 vppExternalTripCommandNative가 47.92초와 48.92초 사이에서 인가됨.',
      related_tags:['vppExternalTripCommandNative'],
    },
    direct_trigger:{
      ...report.direct_trigger,
      claim:'model_time_s 48.44초에 GT TRIP LATCH(vppGTTripLatch) 및 ST TRIP LATCH(vppSTTripLatchPublished)가 1.0(ACTIVE)으로 동시에 작동함.',
      related_tags:['vppGTTripLatch','vppSTTripLatchPublished'],
    },
    chronological_events:Array.from({length:12},(_,index)=>({
      recorded_time:48.44+index/10,
      wall_time_utc:`2026-09-15T14:52:${String(4+index).padStart(2,'0')}.213+00:00`,
      equipment:index<2?'GT':'HRSG',
      category:index<2?'PROTECTION':'ALARM',
      claim:index===0?'GT TRIP LATCH ACTIVE':index===1?'52GT BREAKER OPEN':`후속 알람 ${index}`,
      related_tags:index===0?['vppGTTripLatch']:[],
    })),
    report_rows:[],
  };
  const html=exporter.buildReportHtml(operatorReport);
  for(const text of ['1. 개요','5. 발생 원인','직접 보호동작','4. 시간대별 조치사항','기록 시각','내용','9. 증거자료','vppGTTripLatch','후속 알람 11'])assert.match(html,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  for(const text of ['Run ID','Data Digest','Analysis Engine','model_time_s','secret-digest'])assert.doesNotMatch(html,new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  assert.match(html,/@page\{size:A4;margin:0\}/);
});

test('detailed CSV remains available after the PDF is shortened', () => {
  const csv=exporter.buildPinpointCsv(report);
  assert.match(csv,/event_id/);
  assert.match(csv,/ST\.TRIP\.LATCH/);
  assert.match(csv,/EV-1/);
});

test('operator PDF wraps unusually long AI prose without truncating it', () => {
  const longClaim='상세 원인 설명 '.repeat(40).trim();
  const html=exporter.buildReportHtml({
    ...report,
    primary_cause:{claim:longClaim,related_tags:[]},
    report_rows:[],
  });
  assert.match(html,new RegExp(longClaim));
  assert.doesNotMatch(html,/…|text-overflow\s*:\s*ellipsis/);
});

test('operator PDF preserves real edits even when known source tags are present', () => {
  const edited={
    ...report,
    primary_cause:{claim:'원본 선행 원인',related_tags:['vppExternalTripCommandNative']},
    direct_trigger:{claim:'원본 직접 동작',related_tags:['vppGTTripLatch']},
    chronological_events:[{model_time_s:48.52,equipment:'52GT',claim:'원본 사건',evidence_ids:['EV-EDIT'],related_tags:['vpp52GTClosed']}],
    report_rows:[
      {section:'발생 원인',item:'선행 원인',content:'운전원이 수정한 발생 원인'},
      {section:'발생 원인',item:'직접 Trip 원인',content:'운전원이 수정한 직접 보호동작'},
      {section:'시간대별 사건·자동동작(SOE)',item:'SOE 1',content:'운전원이 수정한 차단기 동작',evidence_ids:'EV-EDIT',time:'48.520 s'},
    ],
  };
  const html=exporter.buildReportHtml(edited);
  for(const text of ['운전원이 수정한 발생 원인','운전원이 수정한 직접 보호동작','운전원이 수정한 차단기 동작'])assert.match(html,new RegExp(text));
  for(const text of ['외부 Trip Command 입력','GT Trip Latch 동작','52GT 차단기 OPEN'])assert.doesNotMatch(html,new RegExp(text));
});

test('operator PDF does not infer OPEN from a closed-state tag', () => {
  const html=exporter.buildReportHtml({
    ...report,
    chronological_events:[{model_time_s:48.52,equipment:'52GT',claim:'52GT 차단기 정상 투입 상태',value:1,state:'CLOSED',related_tags:['vpp52GTClosed']}],
    report_rows:[],
  });
  assert.match(html,/52GT 차단기 정상 투입 상태/);
  assert.doesNotMatch(html,/52GT 차단기 OPEN/);
});


test('operator report removes conversational AI endings from generated conclusions', () => {
  const html=exporter.buildReportHtml({
    ...report,
    primary_cause:{
      claim:'외부 GT Trip 명령 입력이 관측되었습니다. 운전 의도는 미확인입니다.',
      related_tags:['vppExternalTripCommandNative'],
      model_time_s:48.4,
    },
    direct_trigger:{
      claim:'48.44초에 가스터빈 트립 래치 및 증기터빈 트립 래치가 활성화되었습니다.',
      related_tags:['vppGTTripLatch','vppSTTripLatchPublished'],
      model_time_s:48.44,
    },
    report_rows:[],
  });
  assert.match(html,/외부 (?:GT )?Trip Command 입력/);
  assert.match(html,/GT·ST Trip Latch 동시 동작/);
  for(const text of ['활성화되었습니다','관측되었습니다','확인할 수 있습니다','확정할 수 없습니다'])assert.doesNotMatch(html,new RegExp(text));
});

test('production report derives specific equipment from claim evidence instead of stage labels', () => {
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:'IP BFP trip sequence',
    critical_events:[{
      claim:'IP BFP 트립 푸시버튼 입력이 관측되었습니다.',
      status:'OBSERVED',evidence_ids:['E-IP'],related_tags:['vppIPFWPTripPushbuttonNative'],
      evidence:[{event_id:'E-IP',equipment:'IP BFP',event_tag:'IP_BFP_TRIP_PB'}],
    }],
    primary_cause:{claim:'IP BFP 수동 트립 입력',status:'CANDIDATE',evidence_ids:['R-IP'],related_tags:['vppIPFWPTripPushbuttonNative']},
    direct_trigger:{
      claim:'VCB-B01 차단기가 개로되었습니다.',status:'CANDIDATE',evidence_ids:['E-VCB'],related_tags:['vppECMSVCBB01Closed'],
      evidence:[{event_id:'E-VCB',equipment:'VCB-B01',event_tag:'BREAKER_OPEN'}],
    },
    propagation:[{
      claim:'IP 급수 유량 저하가 관측되었습니다.',status:'OBSERVED',evidence_ids:['E-FW'],related_tags:['vppIPFWPMassFlowTH'],
      evidence:[{event_id:'E-FW',equipment:'IP FEEDWATER',event_tag:'FLOW_LOW'}],
    }],
    chronological_events:[
      {model_time_s:31.84,equipment:'IP BFP',claim:'IP BFP TRIP PB PRESSED',category:'OPERATOR_ACTION',evidence_ids:['E-IP'],related_tags:['vppIPFWPTripPushbuttonNative']},
      {model_time_s:48.96,equipment:'VCB-B01',claim:'VCB-B01 OPEN',category:'PROTECTION',evidence_ids:['E-VCB'],related_tags:['vppECMSVCBB01Closed']},
      {model_time_s:50.28,equipment:'IP FEEDWATER',claim:'IP FW FLOW LOW ALARM',category:'ALARM',evidence_ids:['E-FW'],related_tags:['vppIPFWPMassFlowTH']},
    ],
    report_rows:[],
  });
  assert.match(html,/대상 설비<\/th><td>IP BFP · VCB-B01 · IP FEEDWATER<\/td>/);
  assert.doesNotMatch(html,/설비 CRITICAL_EVENT|대상 설비<\/th><td>ST|대상 설비<\/th><td>HRSG/);
});

test('production report prioritizes drum equipment over generic turbine and stage labels', () => {
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:'HP drum disturbance',
    critical_events:[{
      claim:'48.04초에서 49.04초 사이에 고압 드럼 외란 유량이 급증했습니다.',
      status:'OBSERVED',evidence_ids:['R-HP'],related_tags:['vppHPDrumInventoryDisturbanceMassFlowTH'],
    }],
    primary_cause:{claim:'HP 드럼 인벤토리 외란',status:'CANDIDATE',evidence_ids:['R-HP'],related_tags:['vppHPDrumInventoryDisturbanceMassFlowTH']},
    direct_trigger:{claim:'ST Trip Latch 동작',status:'CANDIDATE',evidence_ids:['E-ST'],related_tags:['vppSTTripLatchPublished']},
    chronological_events:[
      {model_time_s:50.56,equipment:'HP FEEDWATER',claim:'HP FW FLOW LOW ALARM',category:'ALARM',evidence_ids:['E-FW']},
      {model_time_s:60.52,equipment:'HP DRUM',claim:'HP DRUM LEVEL HIGH ALARM',category:'ALARM',evidence_ids:['E-DRUM']},
      {model_time_s:72.64,equipment:'ST',claim:'ST TRIP LATCH ACTIVE',category:'PROTECTION',evidence_ids:['E-ST'],related_tags:['vppSTTripLatchPublished']},
    ],
    report_rows:[],
  });
  assert.match(html,/대상 설비<\/th><td>HP DRUM/);
  assert.doesNotMatch(html,/대상 설비<\/th><td>(?:ST|GT|HRSG|CRITICAL_EVENT)(?: ·|<)/);
});

test('empty model narratives fall back to the first observed protection event', () => {
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:'설명 미제공',
    critical_events:[{claim:'설명 미제공',status:'UNKNOWN',evidence_ids:[],related_tags:[]}],
    primary_cause:{},direct_trigger:{},propagation:[],
    chronological_events:[
      {model_time_s:48.6,equipment:'ST',category:'PROTECTION',claim:'ST TRIP LATCH ACTIVE',state:'ACTIVE',value:1,evidence_ids:['E-ST'],related_tags:['vppSTTripLatchPublished']},
      {model_time_s:48.7,equipment:'52ST',category:'PROTECTION',claim:'52ST BREAKER OPEN',state:'OPEN',value:0,evidence_ids:['E-52'],related_tags:['vpp52STClosed']},
    ],
    report_rows:[],
  });
  assert.match(html,/대상 설비<\/th><td>ST/);
  assert.match(html,/장애 요약<\/th><td>ST Trip Latch 동작<\/td>/);
  assert.match(html,/직접 Trip 원인 \(Direct Trigger\)[\s\S]*?ST Trip Latch 동작/);
  assert.doesNotMatch(html,/설명 미제공/);
});

test('operator narrative keeps interval beginnings and removes tag-stripping punctuation holes', () => {
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:'47.12초에서 48.12초 사이 HP 드럼 외란',
    critical_events:[{
      claim:'47.12초에서 48.12초 사이에 HP 드럼 손실 외란(vppHPDrumInventoryDisturbanceMassFlowTH 급감)이 시작되었습니다.',
      status:'OBSERVED',evidence_ids:['R1','R2'],related_tags:['vppHPDrumInventoryDisturbanceMassFlowTH'],time_interval_s:[47.12,48.12],
    }],
    primary_cause:{
      claim:'47.12초에서 48.12초 사이에 외란 유출(vppHPDrumInventoryFaultFlowCommand.signal = -160.0, vppHPDrumInventoryDisturbanceMassFlowTH = -576.0 t/h)이 발생했습니다.',
      status:'CANDIDATE',evidence_ids:['R1','R2'],related_tags:['vppHPDrumInventoryFaultFlowCommand.signal','vppHPDrumInventoryDisturbanceMassFlowTH'],time_interval_s:[47.12,48.12],
    },
    direct_trigger:report.direct_trigger,
    propagation:[{
      claim:'저-저 경보(vppHPTurbineSteamFlowTH, 191.36 t/h)가 발생했습니다.',
      status:'OBSERVED',evidence_ids:['E-LL'],related_tags:['vppHPTurbineSteamFlowTH'],
    }],
    report_rows:[],
  });
  assert.match(html,/47\.12초에서 48\.12초 사이/);
  assert.doesNotMatch(html,/(?:^|>)서 48\.12초|\(\s*(?:,|=)|,\s*=/);
  assert.match(html,/외란 유출\(-160\.0, -576\.0 t\/h\)/);
  assert.match(html,/저-저 경보\(191\.36 t\/h\)/);
});

test('LOW-LOW evidence is not collapsed to LOW in report wording', () => {
  const html=exporter.buildReportHtml({
    ...report,
    propagation:[{
      claim:'HP TURBINE STEAM FLOW LOW-LOW ALARM',status:'OBSERVED',state:'ACTIVE',
      evidence_ids:['E-LL'],related_tags:['vppHPTurbineSteamFlowTH'],
    }],
    report_rows:[],
  });
  assert.match(html,/HP 터빈 증기유량 LOW-LOW/);
});
