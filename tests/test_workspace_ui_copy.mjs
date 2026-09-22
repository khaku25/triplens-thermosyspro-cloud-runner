import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const source=fs.readFileSync(new URL('../apps/web/components/TripLensWorkspace.js',import.meta.url),'utf8');
const logicViewerSource=fs.readFileSync(new URL('../apps/web/components/LogicViewerFrame.js',import.meta.url),'utf8');
const integrationCss=fs.readFileSync(new URL('../apps/web/app/integration.css',import.meta.url),'utf8');

test('cause screen uses operator-facing Korean hierarchy',()=>{
  for(const text of ['발생 원인','직접 보호동작','파급 과정','시간순 사고 경위'])assert.match(source,new RegExp(text));
  assert.doesNotMatch(source,/title="Primary Cause"|title="Direct Trigger"|<h3>Propagation<\/h3>|<h3>Causal Chain<\/h3>/);
  assert.match(source,/operatorSummary/);
  assert.match(source,/conciseClaim/);
  assert.match(source,/displayEventTime/);
});

test('direct-trigger detail selects cited evidence instead of full tag history',()=>{
  assert.match(source,/selectDetailEvidence\(catalog,detail\)/);
  assert.match(source,/kind:'claim'/);
});

test('each evidence card has one grouped logic-master entry',()=>{
  assert.match(source,/로직 보기/);
  assert.match(source,/관련 로직/);
  assert.doesNotMatch(source,/로직 연결 ·/);
});

test('report preview defaults to concise operator summary and keeps editing collapsed',()=>{
  assert.match(source,/operator-report-preview/);
  assert.match(source,/4페이지 운전 고장상보 형식/);
  assert.match(source,/report-editor/);
});

test('Drawing Master is named and remains reachable from the mobile workspace',()=>{
  assert.match(source,/Logic \/ TAG \/ Drawing Master/);
  assert.doesNotMatch(integrationCss,/\.app-shell \.side-links\s*,\s*\.app-shell \.boundary\s*\{display:none\}/);
});

test('overflow analysis items and raw evidence tags stay available in disclosures',()=>{
  assert.match(source,/hidden-analysis-items/);
  assert.match(source,/원시 근거 태그/);
});

test('logic viewer replaces internal diagram copy with operator labels',()=>{
  for(const text of ['태그·로직 연결도','태그 검색 · 설비별 분류 · 로직 연결 · 상세 정보','입력 태그','파생 출력','입·출력 연결']){
    assert.match(logicViewerSource,new RegExp(text));
  }
  assert.match(logicViewerSource,/operatorDiagramText/);
  assert.match(logicViewerSource,/querySelectorAll\('#diagram \[aria-label\]'\)/);
});


test('screen 03 is a structured operator checklist instead of AI prose cards',()=>{
  assert.match(source,/추가 확인·검토/);
  assert.match(source,/operatorReviewItems/);
  assert.match(source,/review-check-card/);
  assert.match(source,/확인 필요/);
  assert.match(source,/담당자 검토/);
  assert.doesNotMatch(source,/즉시 확인·대응/);
});
