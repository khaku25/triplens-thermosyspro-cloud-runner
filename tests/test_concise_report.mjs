import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {normalizeDisplayAnalysis,buildDraftRows,draftCSV} from '../apps/web/lib/analysisClient.mjs';
import {operatorSummary} from '../apps/web/lib/workspacePresentation.mjs';
import {buildWorkspaceExportReport} from '../apps/web/lib/reportAdapter.mjs';
const require=createRequire(import.meta.url);
const contract=require('../apps/web/lib/triplens_ai_output_contract.js');
const exporter=require('../apps/web/lib/reportExporter.cjs');
const long='47.6초와 48.72초 사이에 LP 드럼 인벤토리 외란 지령 신호가 0.0에서 -160.0으로 감소하고, 인벤토리 외란 유량이 0.0 t/h에서 -576.0 t/h로 급감하여 LP 드럼 수위 저하를 유발한 기동 원인으로 분석됩니다. 정확한 발생 시각은 미확인이며 표본 구간만 확인됩니다.';
const short='LP 드럼 재고량 감소 외란이 수위 저하의 원인 후보입니다.';
const primary={claim:long,report_summary:short,status:'CANDIDATE',evidence_ids:['RAW:21:flow','RAW:22:flow'],related_tags:['vppLPDrumInventoryDisturbanceMassFlowTH'],model_time_s:null,time_interval_s:[47.6,48.72],ai_confidence:.84};
const direct={claim:'GT·ST Trip Latch 동시 동작',report_summary:'GT·ST Trip Latch 동시 동작',status:'CANDIDATE',evidence_ids:['EV-2','EV-3'],related_tags:['vppGTTripLatch','vppSTTripLatchPublished'],model_time_s:85.633};
const propagation={claim:'86.08초에 GT 배기가스 온도가 678.049166 K로 감소하여 온도 LOW 경보가 발생했습니다.',report_summary:'GT 배기온도 LOW 경보가 발생했습니다.',status:'OBSERVED',evidence_ids:['EV-4'],related_tags:['vppGTExhaustTemperatureK'],model_time_s:86.08};
function analysis(){return {primary_cause:structuredClone(primary),direct_trigger:structuredClone(direct),critical_events:[structuredClone(primary)],propagation:[structuredClone(propagation)],causal_chain:[],counter_evidence:[],additional_evidence_required:[],review_recommendations:[],verification_gate:'HOLD'};}
function report(a=analysis(),reportRows=[]){return buildWorkspaceExportReport({result:{run_id:'CONCISE-REGRESSION',analysis:a},analysis:a,reportRows});}

test('JSON adapters and UI prefer the separate summary without overwriting full claims',()=>{
  const a=analysis();const before=structuredClone(a);
  assert.equal(contract.normalizeAnalysis(a).primary_cause.report_summary,short);
  assert.equal(normalizeDisplayAnalysis(a).primary_cause.report_summary,short);
  assert.equal(operatorSummary(a.primary_cause,'primary'),short);
  assert.equal(a.primary_cause.claim,long);
  assert.deepEqual(a,before);
});

test('first report page is concise; detail page retains complete narrative and timestamps',()=>{
  const r=report();const before=structuredClone(r);const html=exporter.buildReportHtml(r);
  const pages=html.split('</main>');
  assert.ok(pages[0].includes(short));
  assert.ok(!pages[0].includes('인벤토리 외란 지령 신호가'));
  assert.ok(pages[1].includes(long));
  assert.ok(pages[1].includes('678.049166'));
  assert.ok(pages[0].includes('47.600')&&pages[0].includes('48.720'));
  assert.ok(pages[0].includes('정확한 발생 시각 미확인'));
  assert.ok(pages[0].includes('85.633'));
  assert.equal((html.match(/class="report-page"/g)||[]).length,4);
  assert.deepEqual(r,before);
});

test('conflicting HP BFP evidence remains explicit even in a short headline',()=>{
  const a=analysis();a.primary_cause={...primary,claim:'HP BFP 푸시버튼은 원인 후보이나 RAW 불일치와 17.44초 동작 지연은 추가 검증이 필요합니다.',report_summary:'HP BFP 푸시버튼은 원인 후보이며 RAW 불일치·동작 지연은 추가 검증이 필요합니다.',time_interval_s:null,model_time_s:31};
  const html=exporter.buildReportHtml(report(a));
  assert.ok(html.split('</main>')[0].includes('RAW 불일치'));
  assert.ok(html.includes('17.44초'));
});

test('CSV exports remain full-detail and evidence-complete, not display summaries',()=>{
  const a=analysis();const rows=buildDraftRows({analysis:a});const csv=draftCSV(rows);
  assert.ok(csv.includes('인벤토리 외란 지령 신호가'));
  assert.ok(csv.includes('RAW:21:flow; RAW:22:flow'));
  assert.ok(csv.includes('47.600 ~ 48.720'));
  assert.ok(!csv.includes(short));
});

test('invalid summaries never conceal the original narrative or get truncated',()=>{
  for(const invalid of ['확정된 원인입니다.','vppInvented 신호가 원인입니다.',long]){
    const a=analysis();a.primary_cause.report_summary=invalid;
    const c=contract.normalizeAnalysis(a).primary_cause;
    assert.equal(c.report_summary,null);
    assert.equal(c.claim,long);
    const html=exporter.buildReportHtml(report(a));
    assert.ok(!html.includes('vppInvented'));
    assert.ok(html.includes('정확한 발생 시각'));
  }
});

test('manual report edits override generated summary instead of restoring stale prose',()=>{
  const a=analysis();const edit='담당자 수정: 외란 입력 경위 추가 확인';
  const html=exporter.buildReportHtml(report(a,[{section:'발생 원인',item:'선행 원인',content:edit,edited:true,status:'CANDIDATE',evidence_ids:'RAW:21:flow; RAW:22:flow',time:'47.600 ~ 48.720 s (표본 구간)'}]));
  const page=html.split('</main>')[0];
  assert.ok(page.includes(edit));
  const cause=page.split('선행 원인 (Primary Cause)')[1].split('직접 Trip 원인')[0];
  assert.ok(!cause.includes(short));
});

test('changing AI confidence alone does not change first-page text or evidence',()=>{
  const a=analysis();const b=analysis();a.primary_cause.ai_confidence=.3;b.primary_cause.ai_confidence=.95;
  assert.equal(exporter.buildReportHtml(report(a)),exporter.buildReportHtml(report(b)));
});

test('summary numbers must equal source tokens, not substrings of larger readings',()=>{
  const item={...primary,claim:'외란 유량 900 t/h 증가가 원인 후보입니다.',report_summary:'외란 유량 9 t/h가 원인 후보입니다.'};
  assert.equal(contract.reportSummary(item),'');
});
