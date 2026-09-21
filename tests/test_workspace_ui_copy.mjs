import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../apps/web/components/TripLensWorkspace.js',import.meta.url),'utf8');
const logicViewerSource=fs.readFileSync(new URL('../apps/web/components/LogicViewerFrame.js',import.meta.url),'utf8');
const contractsSource=fs.readFileSync(new URL('../apps/web/lib/contracts.js',import.meta.url),'utf8');
const presentationSource=fs.readFileSync(new URL('../apps/web/lib/workspacePresentation.mjs',import.meta.url),'utf8');
const testbenchSource=fs.readFileSync(new URL('../apps/web/app/testbench/page.js',import.meta.url),'utf8');
const css=fs.readFileSync(new URL('../apps/web/app/integration.css',import.meta.url),'utf8');

test('cause screen uses operator-facing Korean hierarchy',()=>{
  for(const text of ['직접 보호동작','파급 과정','시간순 사고 경위'])assert.match(source,new RegExp(text));
  assert.doesNotMatch(source,/title="Primary Cause"|title="Direct Trigger"|<h3>Propagation<\/h3>|<h3>Causal Chain<\/h3>/);
  assert.match(source,/operatorSummary/);
  assert.match(source,/conciseClaim/);
  assert.match(source,/displayEventTime/);
  assert.match(source,/deriveOperatorAnalysis/);
  assert.match(source,/primaryTitle/);
  assert.match(presentationSource,/primaryTitle:.*발생 원인/);
  assert.match(presentationSource,/사고 개시 신호/);
});

test('development testbench is not reachable in production',()=>{
  assert.match(testbenchSource,/process\.env\.NODE_ENV\s*!==\s*'development'/);
  assert.match(testbenchSource,/notFound\(\)/);
});

test('direct-trigger detail selects cited evidence instead of full tag history',()=>{
  assert.match(source,/selectDetailEvidence\(catalog,detail\)/);
  assert.match(source,/kind:'claim'/);
});

test('evidence detail has one grouped logic-master entry',()=>{
  assert.match(source,/연결 로직 보기 ·/);
  assert.equal(source.match(/className="drawer-logic-button"/g)?.length,1);
  assert.doesNotMatch(source,/로직 연결 ·/);
});

test('report preview defaults to concise operator summary and keeps editing collapsed',()=>{
  assert.match(source,/operator-report-preview/);
  assert.match(source,/operator-report-document-head/);
  assert.match(source,/operator-report-approval/);
  assert.match(source,/보고서 번호/);
  assert.match(source,/사고 개시 신호/);
  assert.match(source,/report=\{exportReport\}/);
  assert.match(source,/운전 고장상보 형식/);
  assert.match(source,/report-editor/);
  assert.match(source,/hasRecoveryRecord\(recovery\)/);
  assert.match(source,/hasRecovery\?<div className="operator-report-recovery"/);
});

test('overflow analysis items and extra evidence tags stay available in disclosures',()=>{
  assert.match(source,/hidden-analysis-items/);
  assert.match(source,/추가 근거 태그/);
});

test('logic viewer replaces internal diagram copy with operator labels',()=>{
  for(const text of ['태그·로직 연결도','태그 검색 · 설비별 분류 · 로직 연결 · 상세 정보','입력 태그','파생 출력','입·출력 연결']){
    assert.match(logicViewerSource,new RegExp(text));
  }
  assert.match(logicViewerSource,/operatorDiagramText/);
  assert.match(logicViewerSource,/querySelectorAll\('#diagram \[aria-label\]'\)/);
});

test('workspace navigation gives timeline and source evidence distinct operator roles',()=>{
  for(const [id,label,sub] of [
    ['timeline','사고 진행 과정','핵심 시간순서'],
    ['cause','원인 분석','원인 · 보호동작 · 파급'],
    ['checks','즉시 확인·대응','주요 확인사항'],
    ['recovery','복구 기록','조치 내용 및 복구 상태'],
    ['evidence','상세 근거','EVENT · RAW 원본 확인'],
  ])assert.match(contractsSource,new RegExp(`id: '${id}', no: '[0-9]+', label: '${label}', sub: '${sub}'`));
});

test('analysis detail remains on the page in one accessible right-side drawer',()=>{
  assert.match(source,/className="evidence-drawer"/);
  assert.match(source,/role="dialog"/);
  assert.match(source,/aria-modal="false"/);
  assert.match(source,/event\.key==='Escape'/);
  assert.doesNotMatch(source,/else if\(detail\)/);
  assert.doesNotMatch(source,/이전 화면/);
});

test('cause cards and event rows expose one whole-surface detail action',()=>{
  assert.match(source,/openDetail/);
  assert.match(source,/role=\{canOpen\?'button'/);
  assert.match(source,/aria-label=.*상세 보기/);
  assert.doesNotMatch(source,/`근거 \$\{index\+1\}`/);
});

test('operator workspace uses the local Korean font stack and responsive drawer',()=>{
  assert.match(css,/Pretendard,"Noto Sans KR","Malgun Gothic",Arial,sans-serif/);
  assert.match(css,/\.app-shell \.evidence-drawer\{[^}]*position:fixed/);
  assert.match(css,/@media\(max-width:700px\)[\s\S]*\.app-shell \.evidence-drawer/);
});

test('detail drawer presents one grouped logic entry and the evidence explorer uses whole rows',()=>{
  assert.equal(source.match(/className="drawer-logic-button"/g)?.length,1);
  assert.match(source,/연결 로직 보기 · \{targets\.entry\.ruleCount\}개/);
  assert.match(source,/setLogicSelection\(\{tag:targets\.entry\.tag,rule:''\}\)/);
  assert.match(source,/사건 상세로 돌아가기/);
  assert.match(source,/원본 EVENT·RAW 보기/);
  assert.match(source,/onShowSources/);
  assert.match(source,/setEvidenceQuery\(''\)/);
  assert.match(source,/prioritizeEvidenceRows/);
  assert.match(source,/logicBackRef/);
  assert.match(source,/logicTriggerRef/);
  assert.match(source,/groupEvidenceRows/);
  assert.match(source,/visibleEvidence/);
  assert.match(source,/Model Time/);
  assert.match(source,/className=\{`interactive-row/);
});

test('evidence explorer provides source and state filters with bounded drawer evidence',()=>{
  assert.match(source,/evidenceKind/);
  assert.match(source,/evidenceState/);
  assert.match(source,/활성 필터/);
  assert.match(source,/rows\.slice\(0,5\)/);
  assert.match(source,/rows\.slice\(5,25\)/);
  assert.match(source,/원시 데이터 보기/);
});
