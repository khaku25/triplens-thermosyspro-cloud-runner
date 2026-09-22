import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
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

test('direct trip reports keep the tripped train ahead of downstream equipment', () => {
  for (const train of ['GT','ST']) {
    const breaker=`52${train}`;
    const latchTag=train==='GT'?'vppGTTripLatch':'vppSTTripLatchPublished';
    const html=exporter.buildReportHtml({
      ...report,
      incident_summary:`${train} direct trip`,
      primary_cause:{
        claim:`외부 ${train} Trip Command 입력`,status:'CANDIDATE',evidence_ids:['R-CMD'],
        related_tags:[train==='GT'?'vppExternalTripCommandNative':'vppExternalSTTripCommandNative'],
      },
      direct_trigger:{
        claim:`${train} Trip Latch 동작`,status:'CONFIRMED',evidence_ids:['E-LATCH'],related_tags:[latchTag],
      },
      critical_events:[
        {claim:`${breaker} 차단기 OPEN`,equipment:breaker,status:'OBSERVED',evidence_ids:['E-CB'],related_tags:[`vpp${breaker}Closed`]},
        {claim:'HP DRUM 후속 경보',equipment:'HP DRUM',status:'OBSERVED',evidence_ids:['E-DRUM'],related_tags:['vppHPDrumLLRaw']},
      ],
      chronological_events:[
        {model_time_s:48.4,equipment:train,claim:`${train} TRIP LATCH ACTIVE`,category:'PROTECTION',evidence_ids:['E-LATCH'],related_tags:[latchTag]},
        {model_time_s:48.5,equipment:breaker,claim:`${breaker} BREAKER OPEN`,category:'PROTECTION',evidence_ids:['E-CB'],related_tags:[`vpp${breaker}Closed`]},
        {model_time_s:60,equipment:'HP DRUM',claim:'HP DRUM ALARM',category:'ALARM',evidence_ids:['E-DRUM'],related_tags:['vppHPDrumLLRaw']},
      ],
      report_rows:[],
    });
    assert.match(html,new RegExp(`대상 설비<\\/th><td>${train}(?: ·|<)`));
  }
});

test('tag-driven direct commands keep their causal train despite noisy downstream prose', () => {
  for (const train of ['GT','ST']) {
    const externalTag=train==='GT'?'vppExternalTripCommandNative':'vppExternalSTTripCommandNative';
    const html=exporter.buildReportHtml({
      ...report,
      primary_cause:{
        claim:`외부 명령 이후 HP DRUM 경보와 52${train} 개방이 관측되었습니다.`,
        status:'CANDIDATE',evidence_ids:['R-CMD'],related_tags:[externalTag],
      },
      direct_trigger:{claim:'직접 트립 동작',status:'OBSERVED',evidence_ids:['E-TRIP'],related_tags:[]},
      critical_events:[{claim:'HP DRUM 후속 경보',equipment:'HP DRUM',status:'OBSERVED',evidence_ids:['E-DRUM'],related_tags:['vppHPDrumLLRaw']}],
      chronological_events:[],
      report_rows:[],
    });
    assert.match(html,new RegExp(`대상 설비<\\/th><td>${train}(?: ·|<)`));
  }
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
  assert.match(html,/장애 요약<\/th><td>ST Trip Latch 동작 · 추가 검증 필요/);
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

test('FLOW_LOW stays LOW when the equipment name itself ends in FLOW', () => {
  const html=exporter.buildReportHtml({
    ...report,
    critical_events:[],
    propagation:[],
    chronological_events:[{
      model_time_s:48.72,equipment:'GT EXHAUST',category:'ALARM',
      claim:'GT EXHAUST FLOW LOW ALARM',status:'OBSERVED',
      evidence_ids:['EV-FLOW-LOW'],related_tags:['vppGTExhaustMassFlowTH'],
    }],
    report_rows:[],
  });
  assert.match(html,/GT 배기유량 LOW/);
  assert.doesNotMatch(html,/GT 배기유량 LOW-LOW/);
});

test('Blind Test 2 scenario 07 preserves distinct FLOW_LOW and FLOW_LOW_LOW propagation severities', () => {
  const scenario = JSON.parse(readFileSync(new URL('./fixtures/07-ip-drum-hh-propagation.json', import.meta.url), 'utf8'));
  const html = exporter.buildReportHtml(scenario);
  assert.match(html,/HP 터빈 증기유량 LOW → HP 터빈 증기유량 LOW-LOW/);
  assert.doesNotMatch(html,/HP 터빈 증기유량 LOW-LOW → HP 터빈 증기유량 LOW-LOW/);
});

test('Blind Test 2 scenario 02 repairs appositive particles and keeps paired alarm prose', () => {
  const criticalClaim='47.92초(RAW:21:vppExternalSTTripCommandNative, 0.0)와 49.0초(RAW:22:vppExternalSTTripCommandNative, 1.0) 사이에 외부 ST 트립 명령 신호인 vppExternalSTTripCommandNative가 활성화 전환되었습니다.';
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:criticalClaim,
    critical_events:[{claim:criticalClaim,status:'CANDIDATE',evidence_ids:['RAW:21:vppExternalSTTripCommandNative','RAW:22:vppExternalSTTripCommandNative'],related_tags:['vppExternalSTTripCommandNative']}],
    propagation:[
      {
        claim:'ST 트립 래치 작동에 따라 47.92초와 49.0초 사이에 52ST 차단기 트립 명령인 vpp52STTripCmd가 0.0(RAW:21:vpp52STTripCmd)에서 1.0(RAW:22:vpp52STTripCmd)으로 출력되었고, 차단기 폐로 상태인 vpp52STClosed가 1.0(RAW:21:vpp52STClosed)에서 0.0(RAW:22:vpp52STClosed)으로 개방되었습니다.',
        stage:'propagation',status:'OBSERVED',evidence_ids:['R1','R2'],related_tags:['vpp52STTripCmd','vpp52STClosed'],
      },
      {
        claim:'ST 트립 후 47.92초와 49.0초 사이에 HP 터빈 가감 밸브 개도인 vppHPAdmissionPos와 IP 터빈 가감 밸브 개도인 vppIPAdmissionPos가 0.8에서 약 0.245로 급격히 폐쇄 동작하였습니다(RAW:21:vppHPAdmissionPos, RAW:22:vppHPAdmissionPos, RAW:21:vppIPAdmissionPos, RAW:22:vppIPAdmissionPos).',
        stage:'propagation',status:'OBSERVED',evidence_ids:['R3','R4'],related_tags:['vppHPAdmissionPos','vppIPAdmissionPos'],
      },
      {
        claim:'터빈 증기 밸브 급폐쇄로 인해 모델 시간 49.2초에 HP 터빈 증기 유량 저하 알람(vppHPTurbineSteamFlowTH, 402.27 t/h, SESSION_20260915_145853-00003)이 발생하였고, 49.8초에는 극저 알람(126.25 t/h, SESSION_20260915_145853-00005)이 뒤이어 발생하였습니다.',
        stage:'propagation',status:'OBSERVED',evidence_ids:['E-LOW','E-LOW-LOW'],related_tags:['vppHPTurbineSteamFlowTH'],original_tags:['FLOW_LOW','FLOW_LOW_LOW'],
      },
    ],
    report_rows:[],
  });
  const operatorPage=html.split('</main>')[0];
  assert.match(operatorPage,/외부 ST 트립 명령 신호가 활성 상태로 전환됨/);
  assert.match(operatorPage,/52ST 차단기 트립 명령이 0\.0.*차단기 폐로 상태가 1\.0/);
  assert.match(operatorPage,/HP 터빈 가감 밸브 개도와 IP 터빈 가감 밸브 개도가/);
  assert.match(operatorPage,/HP 터빈 증기 유량 저하 알람\(402\.27 t\/h.*49\.8초에는 극저 알람\(126\.25 t\/h/);
  assert.doesNotMatch(operatorPage,/명령인이|상태인이|개도인[과가]|\(신호, 신호\)|HP 터빈 증기유량 LOW-LOW/);
});

test('Blind Test 2 scenario 03 keeps a one-signal LOW and LOW-LOW narrative intact', () => {
  const pairedClaim='49.32초 및 49.92초에 가스터빈 트립의 후속 영향으로 배기가스 질량유량(vppGTExhaustMassFlowTH)의 Low 및 Low-Low 경보가 순차적으로 발생하였습니다.';
  const html=exporter.buildReportHtml({
    ...report,
    propagation:[{
      claim:pairedClaim,stage:'propagation',status:'OBSERVED',evidence_ids:['E-LOW','E-LOW-LOW'],
      related_tags:['vppGTExhaustMassFlowTH'],
    }],
    report_rows:[],
  });
  const operatorPage=html.split('</main>')[0];
  assert.match(operatorPage,/배기가스 질량유량의 Low 및 Low-Low 경보가 순차적으로 발생하였습니다/);
  assert.doesNotMatch(operatorPage,/GT 배기유량 LOW-LOW/);
});

test('Blind Test 2 scenario 04 uses a grammatical completed activation phrase', () => {
  const activationClaim='차단기 개방에 따른 펌프 감속으로 인해 50.033242초에 회전속도 검증 상실(SESSION_20260915_152523-00005, vppIPFWPSpeedProven)이 발생하였고, 이어 50.28초에 중압 급수 유량이 저하되어 저유량 경보(SESSION_20260915_152523-00006, vppIPFWPMassFlowTH)가 활성화되었습니다.';
  const html=exporter.buildReportHtml({
    ...report,
    propagation:[{claim:activationClaim,stage:'propagation',status:'OBSERVED',evidence_ids:['E-SPEED','E-FLOW'],related_tags:['vppIPFWPSpeedProven','vppIPFWPMassFlowTH']}],
    report_rows:[],
  });
  assert.match(html,/저유량 경보\(SESSION_20260915_152523-00006\)가 활성화됨/);
  assert.doesNotMatch(html,/경보\(SESSION_20260915_152523-00006\)가 활성(?:[.<]|\s*→)/);
});

test('Blind Test 2 scenario 07 restores interval subjects and translates turbine alarm codes', () => {
  const criticalClaim='48.04 s와 49.04 s 사이 구간에서 vppIPDrumInventoryDisturbanceMassFlowTH가 0.0에서 900.0 t/h로, vppIPDrumInventoryFaultFlowCommand.signal이 0.0에서 250.0으로 급증하여 IP 드럼 내 비정상적 유체 유입이 시작되었습니다.';
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:criticalClaim,
    critical_events:[{claim:criticalClaim,status:'OBSERVED',evidence_ids:['R1','R2'],related_tags:['vppIPDrumInventoryDisturbanceMassFlowTH','vppIPDrumInventoryFaultFlowCommand.signal']}],
    propagation:[
      {
        claim:'72.92 s 및 73.24 s에 증기터빈 정지에 따라 고압터빈 증기 유량(vppHPTurbineSteamFlowTH)이 급감하며 HP TURBINE::FLOW_LOW(346.06 t/h) 및 HP TURBINE::FLOW_LOW_LOW(191.36 t/h) 경보가 발생했습니다.',
        stage:'propagation',status:'OBSERVED',evidence_ids:['E-HP-L','E-HP-LL'],related_tags:['HP TURBINE::FLOW_LOW','HP TURBINE::FLOW_LOW_LOW','vppHPTurbineSteamFlowTH'],original_tags:['FLOW_LOW','FLOW_LOW_LOW'],
      },
      {
        claim:'73.44 s, 73.72 s, 74.16 s에 걸쳐 저압터빈 유량(vppLPTurbineSteamFlowTH) 및 중압터빈 유량(vppIPTurbineSteamFlowTH)이 급감하여 LP TURBINE::FLOW_LOW, LP TURBINE::FLOW_LOW_LOW, IP TURBINE::FLOW_LOW, IP TURBINE::FLOW_LOW_LOW 경보가 순차적으로 활성화되었습니다.',
        stage:'propagation',status:'OBSERVED',evidence_ids:['E-LP-L','E-LP-LL','E-IP-L','E-IP-LL'],related_tags:['vppLPTurbineSteamFlowTH','vppIPTurbineSteamFlowTH'],original_tags:['FLOW_LOW','FLOW_LOW_LOW'],
      },
    ],
    report_rows:[],
  });
  const operatorPage=html.split('</main>')[0];
  assert.match(operatorPage,/사이 구간에서 IP 드럼 외란 유량이 0\.0에서 900\.0 t\/h로/);
  for(const phrase of [
    'HP 터빈 증기유량 LOW(346.06 t/h)','HP 터빈 증기유량 LOW-LOW(191.36 t/h)',
    'LP 터빈 증기유량 LOW','LP 터빈 증기유량 LOW-LOW','IP 터빈 증기유량 LOW','IP 터빈 증기유량 LOW-LOW',
  ]) assert.match(operatorPage,new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  assert.match(operatorPage,/경보가 순차적으로 활성화됨/);
  assert.doesNotMatch(operatorPage,/사이 구간에서가|(?:HP|IP|LP) TURBINE::FLOW|순차적으로 활성(?:[.<]|\s*→)/);
});

test('Blind Test 2 scenario 10 retains labels for standalone technical-tag lists', () => {
  const directClaim='48.92초에 등록 로직 CMD-FWP-LP-TRIP에 따라 생성된 vppLPFWPTripCommandNative, vppLPFWPTripLatchNative 및 차단기 트립 지령 vppVCBA02TripCommandNative가 LP BFP 정지 및 VCB-A02 개로의 직접적 트리거로 작용했습니다.';
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:directClaim,
    direct_trigger:{claim:directClaim,status:'CANDIDATE',evidence_ids:['R1','R2','R3'],related_tags:['vppLPFWPTripCommandNative','vppLPFWPTripLatchNative','vppVCBA02TripCommandNative']},
    report_rows:[],
  });
  const operatorPage=html.split('</main>')[0];
  assert.match(operatorPage,/생성된 LP BFP 트립 명령, LP BFP 트립 래치 및 차단기 트립 지령이/);
  assert.doesNotMatch(operatorPage,/생성된\s*(?:,\s*)?및|생성된 vppLPFWP/);
});

test('standalone tag labels stay outside parentheses while parenthetical tag lists disappear', () => {
  const directClaim='등록 로직에 따라 생성된 vppLPFWPTripCommandNative, vppLPFWPTripLatchNative 및 확인 목록(vppLPFWPTripCommandNative, vppLPFWPTripLatchNative)과 계측값(vppLPDrumInventoryFaultFlowCommand.signal: 0.0 -> 160.0)이 기록되었습니다.';
  const html=exporter.buildReportHtml({
    ...report,
    direct_trigger:{claim:directClaim,status:'CANDIDATE',evidence_ids:['R1'],related_tags:['vppLPFWPTripCommandNative','vppLPFWPTripLatchNative','vppLPDrumInventoryFaultFlowCommand.signal']},
    report_rows:[],
  });
  const operatorPage=html.split('</main>')[0];
  assert.match(operatorPage,/생성된 LP BFP 트립 명령, LP BFP 트립 래치 및 확인 목록/);
  assert.match(operatorPage,/계측값\(LP 드럼 외란 유입 지령: 0\.0 -&gt; 160\.0\)/);
  assert.doesNotMatch(operatorPage,/확인 목록\((?:신호|LP BFP)/);
});

test('report prose removes tag citations without leaving punctuation or detached Korean particles', () => {
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:'47.12초(RAW:20:vppHPDrumInventoryDisturbanceMassFlowTH)에서 외란이 시작되었습니다.',
    critical_events:[{
      claim:'48.04초에 외란 유량 지시 vppIPDrumInventoryFaultFlowCommand.signal이 상승했습니다.',
      status:'OBSERVED',evidence_ids:['RAW:20:vppIPDrumInventoryFaultFlowCommand.signal'],
      related_tags:['vppIPDrumInventoryFaultFlowCommand.signal'],
    }],
    propagation:[{
      claim:'model_time_s=48.44s에 트립 명령 vppVCBA02TripCommandNative에 의해 차단기 접점 vppECMSVCBA02Closed가 개로되고 운전 상태 vppLPFWPRunning이 정지했습니다.',
      status:'OBSERVED',evidence_ids:['EV-PROP'],related_tags:['vppVCBA02TripCommandNative'],
    }],
    report_rows:[],
  });
  assert.doesNotMatch(html,/47\.12초\(RAW:20:\)/);
  assert.match(html,/외란 유량 지시가 상승/);
  assert.match(html,/트립 명령에 의해 차단기 접점이 개로되고 운전 상태가 정지/);
  assert.doesNotMatch(html,/model_time_s|지시 이|명령 에|접점 가|상태 이/);
});

test('report prose preserves evidence times and repairs grammar around removed technical tags', () => {
  const firstEvent='이벤트 로그에 model_time_s 31.4초 시점에 LP BFP 트립 푸시버튼 눌림(LP_BFP_TRIP_PB PRESSED) 이벤트가 기록되었으나, 동 시점의 RAW 데이터(LP_BFP_TRIP_PB 및 vppLPFWPTripPushbuttonNative)는 0.0으로 비활성 상태였습니다.';
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:firstEvent,
    critical_events:[{
      claim:firstEvent,status:'OBSERVED',model_time_s:31.4,
      evidence_ids:['EV-PB','RAW:7:vppLPFWPTripPushbuttonNative'],
      related_tags:['LP_BFP_TRIP_PB','vppLPFWPTripPushbuttonNative'],
    }],
    primary_cause:{
      claim:'47.88초와 48.88초 사이에 vppLPDrumInventoryFaultFlowCommand.signal이 0.0에서 160.0으로 인가되고, vppLPDrumInventoryDisturbanceMassFlowTH가 0.0 t/h에서 576.0 t/h로 급증했습니다.',
      status:'CANDIDATE',evidence_ids:['RAW:21:vppLPDrumInventoryFaultFlowCommand.signal'],
      related_tags:['vppLPDrumInventoryFaultFlowCommand.signal','vppLPDrumInventoryDisturbanceMassFlowTH'],
    },
    direct_trigger:{
      claim:'model_time_s 48.92초에 LP BFP 트립 래치(vppLPFWPTripLatchState)가 활성화되어 VCB-A02 트립 명령(vppVCBA02TripCommandNative)이 발령된 것입니다.',
      status:'CANDIDATE',model_time_s:48.92,evidence_ids:['RAW:22:vppVCBA02TripCommandNative'],
      related_tags:['vppLPFWPTripLatchState','vppVCBA02TripCommandNative'],
    },
    propagation:[{
      claim:'외부 ST 트립 명령(vppExternalSTTripCommandNative)이 인가되었습니다. 표본 간격에 따른 시간적 불확실성이 존재합니다.',
      status:'OBSERVED',evidence_ids:['RAW:22:vppExternalSTTripCommandNative'],
      related_tags:['vppExternalSTTripCommandNative'],
    }],
    chronological_events:[{
      model_time_s:31.84,category:'EVENT',status:'OBSERVED',evidence_ids:['EV-IP'],
      claim:'미등록 관측 상태였으며 이 시점의 실제 RAW 신호 전이로 즉시 이어지지 않았습니다.',
    }],
    report_rows:[],
  });
  assert.match(html,/이벤트 로그에 31\.4초 시점에/);
  assert.match(html,/RAW 데이터\(LP_BFP_TRIP_PB\)는/);
  assert.match(html,/48\.92초에 LP BFP 트립 래치가 활성화되어 VCB-A02 트립 명령이 발령됨/);
  assert.match(html,/47\.88초와 48\.88초 사이에 LP 드럼 외란 유입 지령이 0\.0에서 160\.0으로 인가되고, LP 드럼 외란 유량이 0\.0 t\/h/);
  assert.match(html,/인가 · 표본 간격에 따른 시간적 불확실성이 존재/);
  assert.match(html,/상태였으며 이 시점/);
  assert.doesNotMatch(html,/model_time_s|이벤트 로그에 시점에|LP_BFP_TRIP_PB 및\)|사이에가|인가되고, 가|발령된 것|상태였으며가|인가 표본/);
});

test('production LP BFP analysis removes the appositive suffix with its technical tag', () => {
  const criticalClaim='31.4s에 LP BFP 트립 푸시버튼 동작 이벤트(LP_BFP_TRIP_PB)가 기록되었으나(SESSION_20260915_152746-00001), 해당 시점의 연계 물리 신호인 vppLPFWPTripPushbuttonNative는 0.0 상태(RAW:7:vppLPFWPTripPushbuttonNative)를 유지하여 즉각적인 트립 로직 동작으로 이어지지 않았음.';
  const primaryClaim='LP BFP(저압 급수 펌프) 트립 푸시버튼 신호인 vppLPFWPTripPushbuttonNative가 47.96s(0.0)와 48.92s(1.0) 사이 구간에서 활성화되어 등록된 연계 로직(CMD-FWP-LP-TRIP)에 트립 신호를 입력함.';
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:criticalClaim,
    critical_events:[{
      claim:criticalClaim,status:'OBSERVED',evidence_ids:['SESSION_20260915_152746-00001','RAW:7:vppLPFWPTripPushbuttonNative'],
      related_tags:['vppLPFWPTripPushbuttonNative'],
    }],
    primary_cause:{
      claim:primaryClaim,status:'CANDIDATE',evidence_ids:['RAW:21:vppLPFWPTripPushbuttonNative','RAW:22:vppLPFWPTripPushbuttonNative'],
      related_tags:['vppLPFWPTripPushbuttonNative'],time_interval_s:[47.96,48.92],
    },
    report_rows:[],
  });
  assert.match(html,/연계 물리 신호는 0\.0 상태/);
  assert.match(html,/트립 푸시버튼 신호가 47\.96s\(0\.0\)와 48\.92s\(1\.0\)/);
  assert.doesNotMatch(html,/신호인(?:은|는|이|가|을|를|와|과)/);
});

test('production LP drum analysis keeps readable labels before colon-prefixed values', () => {
  const criticalClaim='모델 시간 47.88초와 48.88초 사이에서 저압 드럼(LP Drum) 인벤토리 이상 유입 교란 신호(vppLPDrumInventoryFaultFlowCommand.signal: 0.0 -> 160.0, vppLPDrumInventoryDisturbanceMassFlowTH: 0.0 -> 576.0 t/h)가 인가되어 비정상 유입이 시작되었습니다.';
  const primaryClaim='저압 드럼(LP Drum) 계통으로 모델 시간 47.88초와 48.88초 사이에 576 t/h 상당의 비정상 유량 교란(vppLPDrumInventoryFaultFlowCommand.signal: 0 -> 160 kg/s, vppLPDrumInventoryDisturbanceMassFlowTH: 0 -> 576 t/h)이 유입되어 드럼 수위의 제어 불능 급상승을 초래했습니다.';
  const html=exporter.buildReportHtml({
    ...report,
    incident_summary:criticalClaim,
    critical_events:[{
      claim:criticalClaim,status:'CANDIDATE',time_interval_s:[47.88,48.88],
      evidence_ids:['RAW:21:vppLPDrumInventoryFaultFlowCommand.signal','RAW:22:vppLPDrumInventoryDisturbanceMassFlowTH'],
      related_tags:['vppLPDrumInventoryFaultFlowCommand.signal','vppLPDrumInventoryDisturbanceMassFlowTH'],
    }],
    primary_cause:{
      claim:primaryClaim,status:'CANDIDATE',time_interval_s:[47.88,48.88],
      evidence_ids:['RAW:21:vppLPDrumInventoryFaultFlowCommand.signal','RAW:22:vppLPDrumInventoryDisturbanceMassFlowTH'],
      related_tags:['vppLPDrumInventoryFaultFlowCommand.signal','vppLPDrumInventoryDisturbanceMassFlowTH'],
    },
    report_rows:[],
  });
  assert.match(html,/교란 신호\(LP 드럼 외란 유입 지령: 0\.0 -&gt; 160\.0, LP 드럼 외란 유량: 0\.0 -&gt; 576\.0 t\/h\)/);
  assert.match(html,/비정상 유량 교란\(LP 드럼 외란 유입 지령: 0 -&gt; 160 kg\/s, LP 드럼 외란 유량: 0 -&gt; 576 t\/h\)/);
  assert.doesNotMatch(html,/\(\s*:|,\s*:/);
});

test('technical evidence citations are removed as a whole instead of leaving RAW prefixes', () => {
  const html=exporter.buildReportHtml({
    ...report,
    primary_cause:{
      claim:'48.12초에 입력(RAW:21:vppIPFWPTripPushbuttonNative, 0.0)과 운전 상태(EV-4, vppIPFWPRunning RUNNING_LOST)를 확인했습니다.',
      status:'CANDIDATE',evidence_ids:['RAW:21:vppIPFWPTripPushbuttonNative','EV-4'],
      related_tags:['vppIPFWPTripPushbuttonNative','vppIPFWPRunning'],
    },
    report_rows:[],
  });
  const primary=html.match(/<b>선행 원인 \(Primary Cause\)<\/b><div><strong>(.*?)<\/strong>/)?.[1]||'';
  assert.match(primary,/입력\(0\.0\)과 운전 상태\(EV-4, RUNNING_LOST\)/);
  assert.doesNotMatch(primary,/RAW:21:|vppIPFWP/);
});

test('long report narratives use the same technical-tag sanitiser as compact narratives', () => {
  const longDirect='등록된 IP BFP 트립 로직(CMD-FWP-IP-TRIP)에 따라 트립 명령(vppIPFWPTripCommandNative), 트립 래치(vppIPFWPTripLatchNative), 및 차단기 트립 명령(vppVCBB01TripCommandNative)이 48.12초와 49.24초 사이에 활성화되어 48.96초에 VCB-B01 개로(SESSION-00002, vppECMSVCBB01Closed) 및 모터 전원 차단(SESSION-00003, vppIPFWPMotorEnergized)을 직접 트리거했습니다.';
  const html=exporter.buildReportHtml({
    ...report,
    direct_trigger:{
      claim:longDirect,status:'CANDIDATE',time_interval_s:[48.12,49.24],
      evidence_ids:['RAW:21:vppIPFWPTripCommandNative','SESSION-00002','SESSION-00003'],
      related_tags:['vppIPFWPTripCommandNative','vppIPFWPTripLatchNative','vppVCBB01TripCommandNative'],
    },
    report_rows:[],
  });
  const direct=html.match(/<b>직접 Trip 원인 \(Direct Trigger\)<\/b><div><strong>(.*?)<\/strong>/)?.[1]||'';
  assert.match(direct,/트립 명령, 트립 래치 및 차단기 트립 명령/);
  assert.match(direct,/VCB-B01 개로\(SESSION-00002\).*모터 전원 차단\(SESSION-00003\)/);
  assert.doesNotMatch(direct,/vpp[A-Za-z0-9_.-]+|,\s*\)/);
});

test('report date falls back to a dated EVENT when the first critical item is a RAW interval', () => {
  const html=exporter.buildReportHtml({
    ...report,
    critical_events:[{
      claim:'47.92초에서 48.92초 사이 외부 지령이 활성화되었습니다.',
      status:'CANDIDATE',time_interval_s:[47.92,48.92],evidence_ids:['RAW:21:signal'],
    }],
    chronological_events:[{
      model_time_s:48.44,wall_time_utc:'2026-09-15T14:52:04.212+00:00',
      equipment:'GT',category:'PROTECTION',claim:'GT TRIP LATCH ACTIVE',
      status:'OBSERVED',evidence_ids:['EV-DATED'],related_tags:['vppGTTripLatch'],
    }],
    report_rows:[],
  });
  assert.match(html,/발생일시 2026-09-15/);
  assert.doesNotMatch(html,/발생일시 (?:사고 분석일|날짜 미확인)/);
});

test('unknown direct trigger uses observed protection and follow-on EVENT evidence without placeholders', () => {
  const html=exporter.buildReportHtml({
    ...report,
    verification_gate:'HOLD',
    critical_events:[{
      claim:'LP DRUM LEVEL LOW ALARM',equipment:'LP DRUM',status:'OBSERVED',
      evidence_ids:['EV-LP-LOW'],related_tags:['vppLPDrumLevelM'],
    }],
    primary_cause:{claim:'선행 원인은 미확인입니다.',status:'UNKNOWN',evidence_ids:[],related_tags:['vppLPDrumLevelM']},
    direct_trigger:{claim:'...',description:'...',status:'UNKNOWN',evidence_ids:[],related_tags:[]},
    propagation:[],
    chronological_events:[
      {model_time_s:67.8,wall_time_utc:'2026-09-15T15:21:42.538+00:00',equipment:'LP DRUM',category:'ALARM',claim:'LP DRUM LEVEL LOW ALARM',status:'OBSERVED',evidence_ids:['EV-LP-LOW'],related_tags:['vppLPDrumLevelM']},
      {model_time_s:85.63,wall_time_utc:'2026-09-15T15:22:02.550+00:00',equipment:'GT',category:'PROTECTION',claim:'GT TRIP LATCH ACTIVE',status:'OBSERVED',evidence_ids:['EV-GT'],related_tags:['vppGTTripLatch']},
      {model_time_s:85.63,wall_time_utc:'2026-09-15T15:22:02.552+00:00',equipment:'ST',category:'PROTECTION',claim:'ST TRIP LATCH ACTIVE',status:'OBSERVED',evidence_ids:['EV-ST'],related_tags:['vppSTTripLatchPublished']},
      {model_time_s:85.71,wall_time_utc:'2026-09-15T15:22:19.813+00:00',equipment:'52GT',category:'PROTECTION',claim:'52GT BREAKER OPEN',status:'OBSERVED',evidence_ids:['EV-52GT'],related_tags:['vpp52GTClosed']},
      {model_time_s:85.73,wall_time_utc:'2026-09-15T15:22:24.064+00:00',equipment:'52ST',category:'PROTECTION',claim:'52ST BREAKER OPEN',status:'OBSERVED',evidence_ids:['EV-52ST'],related_tags:['vpp52STClosed']},
    ],
    report_rows:[],
  });
  assert.doesNotMatch(html,/>[.…]{1,3}</);
  assert.match(html,/GT Trip Latch 동작/);
  assert.match(html,/ST Trip Latch 동작 → 52GT 차단기 OPEN → 52ST 차단기 OPEN/);
  assert.match(html,/대상 설비<\/th><td>LP DRUM · 52GT · 52ST/);
  assert.match(html,/추가 검증 필요/);
  assert.doesNotMatch(html,/최종 판정<\/span><b>분석 완료/);
});

test('combined propagation card cites the stable evidence union for every visible propagation claim', () => {
  const profiles = [
    ['05', [2, 3]],
    ['06', [1, 1, 2, 3]],
    ['07', [1, 2, 4]],
    ['08', [3, 3, 1]],
    ['10', [3, 3, 1]],
    ['11', [3, 6, 1]],
    ['12', [2, 2, 1]],
  ];
  for (const [scenario, evidenceCounts] of profiles) {
    const propagation = evidenceCounts.map((count, itemIndex) => ({
      claim:`Scenario ${scenario} propagation ${itemIndex + 1}`,
      status:'OBSERVED',
      recorded_time:String(60 + itemIndex),
      evidence_ids:Array.from({length:count}, (_, evidenceIndex) =>
        scenario === '10' && itemIndex === 1 && evidenceIndex === 0
          ? `S${scenario}-I1-E1`
          : `S${scenario}-I${itemIndex + 1}-E${evidenceIndex + 1}`),
    }));
    if (scenario === '06') propagation.push({
      claim:'Scenario 06 hidden fifth propagation',
      status:'OBSERVED',
      evidence_ids:['S06-HIDDEN-EVIDENCE'],
    });
    const visible = propagation.slice(0, 4);
    const expectedIds = [...new Set(visible.flatMap(item => item.evidence_ids))];
    const html = exporter.buildReportHtml({
      ...report,
      primary_cause:{...report.primary_cause,evidence_ids:[`S${scenario}-PRIMARY-ONLY`]},
      direct_trigger:{...report.direct_trigger,evidence_ids:[`S${scenario}-DIRECT-ONLY`]},
      propagation,
      report_rows:[],
    });
    const card = html.match(/<div class="chain-row"><div class="chain-time">[^<]*<\/div><div class="chain-card"><b>파급 결과 \(Propagation\)<\/b>[\s\S]*?<\/div><\/div>/)?.[0] || '';
    assert.ok(card, `scenario ${scenario} propagation card is present`);
    const evidenceLine = card.match(/<small>(.*?)<\/small>/)?.[1] || '';
    assert.equal(evidenceLine, `근거 ID ${expectedIds.join(' · ')}`, `scenario ${scenario} uses the ordered visible evidence union`);
    assert.doesNotMatch(evidenceLine, new RegExp(`S${scenario}-(?:PRIMARY|DIRECT)-ONLY`));
    if (scenario === '06') assert.doesNotMatch(evidenceLine, /S06-HIDDEN-EVIDENCE/);
  }
});
