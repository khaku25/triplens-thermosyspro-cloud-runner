# TripLens AI Output Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace free-form AI result presentation with a deterministic, evidence-linked incident-analysis contract that cleanly separates Direct Trigger, Primary Cause, Propagation, Critical Events, uncertainty, verification state, and draft-report output.

**Architecture:** Add a small standalone browser/CommonJS-compatible contract module that normalizes Gemini-like analysis results into a stable TripLens incident-analysis object. Keep the source EVENT/RAW evidence immutable, keep AI confidence separate from engineering verification, and let the existing report exporter consume the normalized object to produce the v2 industrial report structure and draft CSV. Do not change Modelica, OPC UA, physical-model code, or legacy apps.

**Tech Stack:** Vanilla JavaScript (CommonJS/browser UMD), Node.js built-in `node:test`, existing `webapp/triplens_report_export.js` helpers.

**Spec:** `docs/superpowers/specs/2026-09-17-triplens-incident-report-v2-design.md`

## Global Constraints

- Current baseline: Windows Local V8 TripLens.
- Standard input: `EVENT.csv + RAW.csv`.
- TripLens remains a READ-ONLY accident-analysis layer.
- Preserve existing EVENT/RAW and analysis source objects; normalization must return new objects.
- No cause claim may be promoted to supported output without an Evidence ID.
- Primary Cause defaults to `CANDIDATE`; it may become `CONFIRMED` only when evidence exists, time ordering is valid, Logic Master is verified, counter-evidence is absent, and Verification Gate is PASS.
- Direct Trigger represents the protection/command/latch that directly caused the trip.
- Propagation represents post-trip effects such as breaker, speed, flow, or output changes.
- AI confidence and engineering verification status are separate fields.
- `Verification Gate = HOLD` forbids final-confirmed wording but does not block draft export.
- Chronological EVENT/RAW arrays have no arbitrary five-item limit.
- Do not modify v5/v6/v7 apps, V8 Virtual Plant, Modelica, OPC UA, or physical-model logic.

---

### Task 1: Add the normalized AI output contract

**Files:**
- Create: `webapp/triplens_ai_output_contract.js`
- Create: `tests/test_ai_output_contract.mjs`

**Interfaces:**
- Consumes: raw analysis object with optional `critical_events`, `primary_cause`, `direct_trigger`, `propagation`, `causal_chain`, `counter_evidence`, `additional_evidence_required`, `recommendations`, `verification_gate`.
- Produces: `normalizeAnalysis(raw, options)` returning `{ critical_events, primary_cause, direct_trigger, propagation, causal_chain, counter_evidence, additional_evidence_required, review_recommendations, verification_gate, finality }`.
- Produces: `normalizeClaim(value, stage, context)` and `statusLabel(status)`.

- [ ] **Step 1: Write the failing tests**

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const contract = require('../webapp/triplens_ai_output_contract.js');

test('primary cause remains candidate unless engineering confirmation gates all pass', () => {
  const normalized = contract.normalizeAnalysis({
    verification_gate: 'HOLD',
    primary_cause: {
      status: 'CONFIRMED', claim: 'LP BFP speed degradation',
      evidence_ids: ['RAW-017'], recorded_time: '30.120',
      logic_master_status: 'VERIFIED', counter_evidence: [], ai_confidence: 0.99,
    },
  });
  assert.equal(normalized.primary_cause.status, 'CANDIDATE');
  assert.equal(normalized.primary_cause.ai_confidence, 0.99);
});

test('unsupported cause claim fails closed to unknown', () => {
  const normalized = contract.normalizeAnalysis({ primary_cause: { claim: 'Pump cavitation' } });
  assert.equal(normalized.primary_cause.status, 'UNKNOWN');
  assert.deepEqual(normalized.primary_cause.evidence_ids, []);
});

test('chronological critical events are not truncated at five items', () => {
  const events = Array.from({ length: 12 }, (_, i) => ({
    claim: `Event ${i + 1}`, status: 'OBSERVED', evidence_ids: [`EV-${i + 1}`], recorded_time: String(i),
  }));
  const normalized = contract.normalizeAnalysis({ critical_events: events });
  assert.equal(normalized.critical_events.length, 12);
});

test('hold verification blocks final-confirmed wording', () => {
  const normalized = contract.normalizeAnalysis({ verification_gate: 'HOLD' });
  assert.equal(normalized.finality.can_mark_final_confirmed, false);
  assert.equal(normalized.finality.output_label, '고장보고서 초안');
});
```

- [ ] **Step 2: Run the contract tests and verify RED**

Run: `node --test tests/test_ai_output_contract.mjs`
Expected: FAIL because `webapp/triplens_ai_output_contract.js` does not exist.

- [ ] **Step 3: Implement the minimal normalizer**

Implement UMD/CommonJS exports with these rules:

```js
const VALID_STATUSES = new Set(['CONFIRMED', 'CANDIDATE', 'OBSERVED', 'UNKNOWN']);

function normalizeClaim(value, stage, context = {}) {
  const src = value && typeof value === 'object' ? value : { claim: value || '' };
  const evidenceIds = [...new Set([...(src.evidence_ids || []), ...(src.evidence || []).map(e => e.event_id || e.evidence_id).filter(Boolean)])];
  let status = VALID_STATUSES.has(String(src.status || src.disposition || '').toUpperCase())
    ? String(src.status || src.disposition).toUpperCase()
    : 'UNKNOWN';
  if (!evidenceIds.length && stage !== 'PROPAGATION') status = 'UNKNOWN';
  if (stage === 'PRIMARY_CAUSE') {
    const canConfirm = context.verificationGate === 'PASS' && evidenceIds.length > 0 &&
      src.time_order_valid === true && String(src.logic_master_status || '').toUpperCase() === 'VERIFIED' &&
      (!src.counter_evidence || src.counter_evidence.length === 0);
    if (status === 'CONFIRMED' && !canConfirm) status = 'CANDIDATE';
  }
  return { ...normalizedFields, status, evidence_ids: evidenceIds };
}
```

`normalizeAnalysis()` must preserve full `critical_events` length, map recommendations to `review_recommendations`, and expose finality metadata for PASS/HOLD.

- [ ] **Step 4: Run the contract tests and verify GREEN**

Run: `node --test tests/test_ai_output_contract.mjs`
Expected: PASS, 4 tests, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add webapp/triplens_ai_output_contract.js tests/test_ai_output_contract.mjs
git commit -m "feat: add evidence-linked AI output contract"
```

---

### Task 2: Add v2 failure-report draft rows and CSV export

**Files:**
- Modify: `webapp/triplens_report_export.js`
- Modify: `tests/test_report_export.mjs`

**Interfaces:**
- Consumes: normalized analysis contract or compatible legacy report object.
- Produces: `FAILURE_REPORT_COLUMNS` exactly `['구분','항목','내용','상태','근거 ID','관련 태그','기록 시각','비고']`.
- Produces: `failureReportRows(report)`.
- Produces: `buildFailureReportCsv(report)`.
- Produces: `downloadFailureReportCsv(report, filename)` with default filename `고장보고서_초안.csv`.

- [ ] **Step 1: Write failing exporter tests**

Add tests that assert:

```js
test('failure report CSV uses the fixed v2 columns and evidence-linked sections', () => {
  const csv = exporter.buildFailureReportCsv(report);
  assert.match(csv, /^구분,항목,내용,상태,근거 ID,관련 태그,기록 시각,비고/);
  for (const text of ['Primary Cause','Direct Trigger','Propagation','Critical Events']) assert.match(csv, new RegExp(text));
  assert.match(csv, /EV-1/);
});

test('verification HOLD keeps report output as draft and never final confirmed', () => {
  const html = exporter.buildReportHtml({ ...report, verification_gate: 'HOLD' });
  assert.match(html, /고장보고서 초안|검증 미완료/);
  assert.doesNotMatch(html, /Root Cause Confirmed|최종 확정[^ 아님]/);
});
```

- [ ] **Step 2: Run exporter tests and verify RED**

Run: `node --test tests/test_report_export.mjs`
Expected: FAIL because `buildFailureReportCsv` is not exported and HOLD-specific report semantics are not implemented.

- [ ] **Step 3: Implement failure-report row mapping and CSV generation**

Map normalized contract values into rows with sections:

```js
[
  ['개요', ...],
  ['운전 현황', ...],
  ['장애 현상', ...],
  ['시간대별 조치사항', ...full chronological rows],
  ['Critical Events', ...],
  ['Primary Cause', ...],
  ['Direct Trigger', ...],
  ['Propagation', ...],
  ['Causal Chain', ...],
  ['조치 결과', ...],
  ['반대 근거', ...],
  ['추가 확인 필요', ...],
  ['재발방지 대책', ...review recommendations],
]
```

Do not mutate EVENT/RAW source arrays. Preserve all chronological rows.

- [ ] **Step 4: Replace AI-centric PDF section labels with industrial-report labels**

`buildReportHtml()` should prefer:

- title: `설비 고장 분석보고서 (초안)`
- `발생 원인` table containing 선행 원인 / 직접 Trip 원인 / 파급 과정
- `시간대별 조치사항` as the primary chronology representation
- `반대 근거 / 추가 확인 필요`
- `검토 권고사항` instead of AI-authored final recurrence-prevention wording

Remove `Gemini Analysis` as a first-class report section; model identity may remain in metadata only.

- [ ] **Step 5: Run exporter tests and verify GREEN**

Run: `node --test tests/test_report_export.mjs tests/test_ai_output_contract.mjs`
Expected: PASS, all tests 0 failures.

- [ ] **Step 6: Commit**

```bash
git add webapp/triplens_report_export.js tests/test_report_export.mjs
git commit -m "feat: add industrial failure-report draft export"
```

---

### Task 3: Regression and integration boundary

**Files:**
- Test: `tests/test_event_tag_resolver.mjs`
- Test: `tests/test_ai_output_contract.mjs`
- Test: `tests/test_report_export.mjs`

**Interfaces:**
- Consumes: existing event-tag resolver, new contract module, updated exporter.
- Produces: verified regression result only; no physical-model changes.

- [ ] **Step 1: Run focused tests**

Run:

```bash
node --test tests/test_ai_output_contract.mjs tests/test_report_export.mjs
```

Expected: PASS, 0 failures.

- [ ] **Step 2: Run the existing web helper regression once**

Run:

```bash
node --test tests/test_event_tag_resolver.mjs tests/test_report_export.mjs tests/test_ai_output_contract.mjs
```

Expected: PASS, 0 failures.

- [ ] **Step 3: Verify no forbidden scope changed**

Run:

```bash
git diff --name-only e52301612f37e6705e2e3a323226cf8f03cf3268...HEAD
```

Expected changed implementation paths are limited to `webapp/`, `tests/`, and `docs/`; no Modelica, OPC UA, v5/v6/v7, or physical-model files.

- [ ] **Step 4: Commit any final documentation-only adjustment**

```bash
git add docs/superpowers/plans/2026-09-18-triplens-ai-output-contract.md
git commit -m "docs: record AI output contract implementation plan"
```

## Self-review

- Spec coverage: AI-result structure, evidence linkage, Primary Cause fail-closed behavior, HOLD behavior, unlimited chronology, industrial report labeling, CSV output, and immutable sources are all mapped to tasks.
- Placeholder scan: no TBD/TODO placeholders are present.
- Type consistency: `normalizeAnalysis`, `normalizeClaim`, `failureReportRows`, and `buildFailureReportCsv` are defined once and used consistently.
- Known boundary: the production `chatgpt.site` dashboard source is not present in this repository, so this plan applies the contract and export layer here; wiring the visual dashboard requires the actual operating UI source/deployment project.
