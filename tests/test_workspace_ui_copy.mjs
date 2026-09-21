import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../apps/web/components/TripLensWorkspace.js',import.meta.url),'utf8');
const logicViewerSource=fs.readFileSync(new URL('../apps/web/components/LogicViewerFrame.js',import.meta.url),'utf8');
const contractsSource=fs.readFileSync(new URL('../apps/web/lib/contracts.js',import.meta.url),'utf8');
const presentationSource=fs.readFileSync(new URL('../apps/web/lib/workspacePresentation.mjs',import.meta.url),'utf8');
const testbenchSource=fs.readFileSync(new URL('../apps/web/app/testbench/page.js',import.meta.url),'utf8');
const css=fs.readFileSync(new URL('../apps/web/app/integration.css',import.meta.url),'utf8');
const proxySource=fs.readFileSync(new URL('../apps/web/app/api/triplens/[...path]/route.js',import.meta.url),'utf8');

test('cause screen uses operator-facing Korean hierarchy',()=>{
  for(const text of ['ì§ì  ë³´í¸ëì','íê¸ ê³¼ì ','ìê°ì ì¬ê³  ê²½ì'])assert.match(source,new RegExp(text));
  assert.doesNotMatch(source,/title="Primary Cause"|title="Direct Trigger"|<h3>Propagation<\/h3>|<h3>Causal Chain<\/h3>/);
  assert.match(source,/operatorSummary/);
  assert.match(source,/conciseClaim/);
  assert.match(source,/displayEventTime/);
  assert.match(source,/deriveOperatorAnalysis/);
  assert.match(source,/primaryTitle/);
  assert.match(presentationSource,/primaryTitle:.*ë°ì ìì¸/);
  assert.match(presentationSource,/ì¬ê³  ê°ì ì í¸/);
});

test('analysis requests use a same-origin proxy by default',()=>{
  assert.match(source,/process\.env\.NEXT_PUBLIC_TRIPLENS_API_BASE\|\|\s*'\/api\/triplens'/);
  assert.match(proxySource,/TRIPLENS_API_UPSTREAM\|\|'https:\/\/triplens-agent-api-preview\.vercel\.app'/);
  assert.match(proxySource,/request\.formData\(\)/);
  assert.match(proxySource,/cache:'no-store'/);
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
  assert.match(source,/ì°ê²° ë¡ì§ ë³´ê¸° Â·/);
  assert.equal(source.match(/className="drawer-logic-button"/g)?.length,1);
  assert.doesNotMatch(source,/ë¡ì§ ì°ê²° Â·/);
});

test('report preview defaults to concise operator summary and keeps editing collapsed',()=>{
  assert.match(source,/operator-report-preview/);
  assert.match(source,/operator-report-document-head/);
  assert.match(source,/operator-report-approval/);
  assert.match(source,/ë³´ê³ ì ë²í¸/);
  assert.match(source,/ë°ì ìì¸/);
  assert.match(source,/report=\{exportReport\}/);
  assert.match(source,/íµì¬ ì¬ê³  ê²½ìì ê²°ì¬ ì ë³´/);
  assert.match(source,/report-editor/);
  assert.match(source,/hasRecoveryRecord\(recovery\)/);
  assert.match(source,/hasRecovery\?<div className="operator-report-recovery"/);
});

test('overflow analysis items and extra evidence tags stay available in disclosures',()=>{
  assert.match(source,/hidden-analysis-items/);
  assert.match(source,/ì¶ê° ê·¼ê±° íê·¸/);
});

test('logic viewer replaces internal diagram copy with operator labels',()=>{
  for(const text of ['íê·¸Â·ë¡ì§ ì°ê²°ë','íê·¸ ê²ì Â· ì¤ë¹ë³ ë¶ë¥ Â· ë¡ì§ ì°ê²° Â· ìì¸ ì ë³´','ìë ¥ íê·¸','íì ì¶ë ¥','ìÂ·ì¶ë ¥ ì°ê²°']){
    assert.match(logicViewerSource,new RegExp(text));
  }
  assert.match(logicViewerSource,/operatorDiagramText/);
  assert.match(logicViewerSource,/querySelectorAll\('#diagram \[aria-label\]'\)/);
});

test('workspace navigation gives timeline and source evidence distinct operator roles',()=>{
  for(const [id,label,sub] of [
    ['timeline','ì¬ê³  ì§í ê³¼ì ','íµì¬ ìê°ìì'],
    ['cause','ìì¸ ë¶ì','ìì¸ Â· ë³´í¸ëì Â· íê¸'],
    ['checks','ì¦ì íì¸Â·ëì','ì£¼ì íì¸ì¬í­'],
    ['recovery','ë³µêµ¬ ê¸°ë¡','ì¡°ì¹ ë´ì© ë° ë³µêµ¬ ìí'],
    ['evidence','ìì¸ ê·¼ê±°','EVENT Â· RAW ìë³¸ íì¸'],
  ])assert.match(contractsSource,new RegExp(`id: '${id}', no: '[0-9]+', label: '${label}', sub: '${sub}'`));
});

test('analysis detail remains on the page in one accessible right-side drawer',()=>{
  assert.match(source,/className="evidence-drawer"/);
  assert.match(source,/role="dialog"/);
  assert.match(source,/aria-modal="false"/);
  assert.match(source,/event\.key==='Escape'/);
  assert.doesNotMatch(source,/else if\(detail\)/);
  assert.doesNotMatch(source,/ì´ì  íë©´/);
});

test('cause cards and event rows expose one whole-surface detail action',()=>{
  assert.match(source,/openDetail/);
  assert.match(source,/role=\{canOpen\?'button'/);
  assert.match(source,/aria-label=.*ìì¸ ë³´ê¸°/);
  assert.doesNotMatch(source,/`ê·¼ê±° \$\{index\+1\}`/);
});

test('operator workspace uses the local Korean font stack and responsive drawer',()=>{
  assert.match(css,/Pretendard,"Noto Sans KR","Malgun Gothic",Arial,sans-serif/);
  assert.match(css,/\.app-shell \.evidence-drawer\{[^}]*position:fixed/);
  assert.match(css,/@media\(max-width:700px\)[\s\S]*\.app-shell \.evidence-drawer/);
});

test('detail drawer presents one grouped logic entry and the evidence explorer uses whole rows',()=>{
  assert.equal(source.match(/className="drawer-logic-button"/g)?.length,1);
  assert.match(source,/ì°ê²° ë¡ì§ ë³´ê¸° Â· \{targets\.entry\.ruleCount\}ê°/);
  assert.match(source,/setLogicSelection\(\{tag:targets\.entry\.tag,rule:''\}\)/);
  assert.match(source,/ì¬ê±´ ìì¸ë¡ ëìê°ê¸°/);
  assert.match(source,/ìë³¸ EVENTÂ·RAW ë³´ê¸°/);
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
  assert.match(source,/íì± íí°/);
  assert.match(source,/rows\.slice\(0,5\)/);
  assert.match(source,/rows\.slice\(5,25\)/);
  assert.match(source,/ìì ë°ì´í° ë³´ê¸°/);
});
