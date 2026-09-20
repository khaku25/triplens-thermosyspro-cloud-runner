# TripLens Report Integrity, Recovery Workflow, and Logic Diagram V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a trustworthy 10-section TripLens report with complete EVENT evidence, explicit recovery workflow states, a lower-density responsive UI, and schema-2 logic diagrams, then pass GitHub checks before a single main merge triggers Vercel.

**Architecture:** Pure report-integrity and recovery modules become the authoritative adapters between uploaded/server data and UI/export code. The real workspace moves to a new report adapter while the frozen `/testbench` path retains its existing legacy adapter and nine-section fixture behavior. Logic assets move to schema 2 with new managed node IDs and are regenerated from source rather than hand-edited.

**Tech Stack:** Next.js/React, Node `node:test`, Python `unittest`, Playwright, CommonJS report renderer, Python XML/draw.io generator, GitHub Actions, Vercel Git integration.

**Spec:** `docs/superpowers/specs/2026-09-20-report-integrity-recovery-diagram-v2-design.md`

## Global Constraints

- Do not modify `apps/web/components/IntegrationTestbench.js`, `apps/web/lib/integrationTestbench.mjs`, `tests/test_integration_testbench.mjs`, or the static device fixtures.
- Do not change Gemini prompts, causal decision logic, EVENT/RAW source files, or the ThermoSysPro physical model.
- Preserve the human CSV's eight visible columns.
- Reserve `UNKNOWN` for explicit engineering uncertainty; display missing human data as `입력 대기` and completed-but-unapproved records as `승인 대기`.
- Do not deploy Vercel until local tests and all PR checks pass.
- The current Vercel configuration deploys only `main`; one merge may update both web and agent-api projects.
- Never claim that Evidence Policy PASS means engineering cause confirmation or restart approval.

## Review Focus

- A 21-EVENT upload with a 14-entry retrieved catalog must export all 21 EVENT evidence rows and zero dangling references.
- An uploaded generic tag such as `TRIP_LATCH` must be replaced by the enriched `vppGTTripLatch` without mutating either input object.
- An approved recovery record edited afterward must return to approval pending, and recovery approval must remain independent of cause Verification Gate.
- Legacy testbench fixture rendering must still contain `9. 증거자료` even though real app reports contain `10. 증거자료`.
- A schema-1 draw.io layout must migrate once, while a schema-2 layout must preserve schema-2 node geometry on subsequent regeneration.

---

### Task 1: Report evidence integrity and ten-section semantics

**Files:**
- Create: `apps/web/lib/reportIntegrity.mjs`
- Create: `tests/test_report_integrity.mjs`
- Modify: `apps/web/lib/analysisClient.mjs`
- Modify: `tests/test_analysis_client.mjs`
- Modify: `tests/test_report_semantic_placement.mjs`
- Modify: `services/agent-api/triplens/engineering_reviewer.py`
- Modify: `services/agent-api/tests/test_reviewer_report_evidence.py`
- Modify: `services/agent-api/tests/test_review_reference_fix.py`

**Interfaces:**
- Produces: `eventIdentity(event) -> string`, `preferredSourceTag(event) -> string`, `mergeEvents(uploaded, enriched) -> Event[]`, `mergeEvidenceCatalog(events, retrieved) -> Evidence[]`, `validateReportReferences(rows) -> {valid:boolean, missing:string[]}`.
- Produces: `buildDraftRows(envelope, recoveryRows=[]) -> ReportRow[]` with ten real-app sections.
- Consumes: existing normalized EVENT objects, partial `evidence_catalog`, and the stable eight-column `draftCSV()` contract.

- [ ] **Step 1: Add a failing asymmetric-catalog test**

Create `tests/test_report_integrity.mjs` with 21 uploaded EVENT rows, 21 enriched rows, and only the first 14 rows in `retrieved`. Assert:

```js
const events=mergeEvents(uploaded,enriched);
const catalog=mergeEvidenceCatalog(events,retrieved);
assert.equal(events[0].source_node,'vppGTTripLatch');
assert.equal(uploaded[0].source_node,undefined);
assert.equal(catalog.filter(x=>x.source_kind==='EVENT').length,21);
const rows=buildDraftRows({events,evidence_catalog:catalog,analysis:{}});
assert.deepEqual(validateReportReferences(rows),{valid:true,missing:[]});
for(const id of ['E15','E16','E17','E18','E19','E20','E21'])
  assert.ok(rows.some(r=>r.section==='증거자료'&&r.evidence_ids===id));
```

Also assert that equal-time events preserve their original order and an edited row containing `MISSING-EVIDENCE` returns `missing:['MISSING-EVIDENCE']`.

- [ ] **Step 2: Run the new test and verify RED**

Run: `node --test tests/test_report_integrity.mjs`

Expected: FAIL because `reportIntegrity.mjs` and its exports do not exist.

- [ ] **Step 3: Implement the pure integrity module**

Implement immutable Map-based merges. `mergeEvidenceCatalog()` must insert every merged EVENT as `source_kind:'EVENT'`, then overlay retrieved entries by evidence ID so retrieved RAW rows remain present and richer duplicate EVENT fields win. `validateReportReferences()` must split semicolon-delimited IDs from every non-`증거자료` row and compare them with the evidence-section IDs.

- [ ] **Step 4: Change report section semantics under failing tests**

Update `REPORT_SECTIONS` to:

```js
[
 '개요','사고 발생 전 운전 현황','장애 현상',
 '시간대별 사건·자동동작(SOE)','발생 원인','운전원·정비 조치사항',
 '조치 결과 및 복구 판정','추정 원인 및 미확인 사항',
 '재발방지 대책 — 검토 권고사항','증거자료'
]
```

Change EVENT rows from `시간대별 조치사항` to `시간대별 사건·자동동작(SOE)`. Add one default `운전원·정비 조치사항` row with content `복구·조치 기록 입력 대기`, status `INPUT_PENDING`, and no fabricated evidence. Add recovery rows only through the optional `recoveryRows` argument.

Update semantic tests to assert automatic EVENT rows never enter the human-action section. Update the reviewer section allowlist and prompt text from nine to ten sections. Add a reviewer test that accepts the ten-section snapshot and still rejects unknown section names before any reviewer call.

- [ ] **Step 5: Run report and reviewer tests and verify GREEN**

Run:

```bash
node --test tests/test_report_integrity.mjs tests/test_analysis_client.mjs tests/test_report_semantic_placement.mjs
python -m unittest services.agent-api.tests.test_reviewer_report_evidence services.agent-api.tests.test_review_reference_fix
```

Expected: all tests PASS; the asymmetric fixture reports zero dangling IDs.

- [ ] **Step 6: Commit Task 1**

```bash
git add apps/web/lib/reportIntegrity.mjs apps/web/lib/analysisClient.mjs tests/test_report_integrity.mjs tests/test_analysis_client.mjs tests/test_report_semantic_placement.mjs services/agent-api/triplens/engineering_reviewer.py services/agent-api/tests/test_reviewer_report_evidence.py services/agent-api/tests/test_review_reference_fix.py
git commit -m "fix: preserve complete report evidence and separate SOE"
```

### Task 2: Recovery domain model and real-app report adapter

**Files:**
- Create: `apps/web/lib/recoveryModel.mjs`
- Create: `apps/web/lib/reportAdapter.mjs`
- Create: `tests/test_recovery_model.mjs`
- Create: `tests/test_report_adapter.mjs`
- Modify: `apps/web/lib/reportExporter.cjs`
- Modify: `tests/test_report_export.mjs`

**Interfaces:**
- Consumes: Task 1 `validateReportReferences()`, `buildDraftRows()`, and the frozen legacy `buildExportReport()` imported from `integrationTestbench.mjs`.
- Produces: `EMPTY_RECOVERY`, `normalizeRecovery(value)`, `validateRecovery(value,catalog)`, `deriveRecoveryWorkflow(value)`, `recoverySummary(value)`, `editRecovery(value,field,nextValue)`, `recoveryStatusLabel(value)`, `workflowLabel(value)`, `parseEvidenceIds(value)`, `recoveryReportRows(value)`, `applyRecoveryRows(rows,value)`, `buildWorkspaceExportReport(args)`.
- `deriveRecoveryWorkflow()` returns `INPUT_PENDING | APPROVAL_PENDING | APPROVED`; domain `status` remains `UNKNOWN | PARTIAL | RECOVERED | NOT_RECOVERED`.

- [ ] **Step 1: Write failing recovery-model tests**

Create `tests/test_recovery_model.mjs` covering:

```js
assert.equal(deriveRecoveryWorkflow(EMPTY_RECOVERY),'INPUT_PENDING');
assert.doesNotMatch(recoverySummary(EMPTY_RECOVERY),/UNKNOWN/);
assert.equal(deriveRecoveryWorkflow(completeRecovered),'APPROVAL_PENDING');
assert.equal(deriveRecoveryWorkflow({...completeRecovered,approver:'Kim',approved_at:'2026-09-20T10:00:00Z'}),'APPROVED');
assert.equal(deriveRecoveryWorkflow(editRecovery(approved,'actions','수정')),'APPROVAL_PENDING');
assert.equal(validateRecovery({...notRecovered,recovered_at:''},catalog).valid,true);
assert.deepEqual(validateRecovery({...completeRecovered,evidence_ids:['E1','NOPE']},catalog).missing_evidence,['NOPE']);
```

Explicit `UNKNOWN` must require `decision_entered:true`, operator, and an uncertainty reason in `actions`. `RECOVERED/PARTIAL` require recovered time, operator, and actions; `RECOVERED` also requires restart conditions. `NOT_RECOVERED` does not require recovered time.

- [ ] **Step 2: Run recovery tests and verify RED**

Run: `node --test tests/test_recovery_model.mjs`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement recovery pure functions**

Store evidence IDs as a deduplicated string array. Any edit to a previously approved object must clear `approved_at`. Labels must be Korean-first:

```text
INPUT_PENDING -> 복구 기록 입력 대기
APPROVAL_PENDING -> 복구 기록 완료 · 승인 대기
APPROVED -> 복구 기록 승인 완료
```

Do not represent an approver name alone as electronic approval; `approved_at` is the explicit approval action marker.

- [ ] **Step 4: Write and run failing real-app adapter tests**

Create `tests/test_report_adapter.mjs`. Assert that `buildWorkspaceExportReport()` injects recovery rows into the ten-section report, projects the same action/time/operator/restart/approver values into the export object, and returns an integrity result. Assert cause `PASS` plus recovery `APPROVAL_PENDING` still produces document state `DRAFT`, while cause `PASS` plus recovery `APPROVED` produces `REVIEWED`.

Run: `node --test tests/test_report_adapter.mjs`

Expected: FAIL because `reportAdapter.mjs` does not exist.

- [ ] **Step 5: Implement the adapter without touching testbench code**

`reportAdapter.mjs` may call the frozen legacy adapter for shared claim enrichment, but must replace `report_rows`, recovery fields, document state, and reference-integrity result for the real workspace. The frozen testbench continues calling `integrationTestbench.mjs` directly.

Update `reportExporter.cjs` so real ten-section `report_rows` render numbered sections through `10. 증거자료`. Preserve the current legacy nine-section fallback when the input has no ten-section workspace rows; this keeps the untouched testbench check for `9. 증거자료` green. Add CSV formula-injection protection to the legacy failure-report CSV path.

- [ ] **Step 6: Run adapter/export tests and verify GREEN**

Run:

```bash
node --test tests/test_recovery_model.mjs tests/test_report_adapter.mjs tests/test_report_export.mjs tests/test_integration_testbench.mjs
```

Expected: all PASS; untouched testbench tests still pass and legacy HTML still contains `9. 증거자료`.

- [ ] **Step 7: Commit Task 2**

```bash
git add apps/web/lib/recoveryModel.mjs apps/web/lib/reportAdapter.mjs apps/web/lib/reportExporter.cjs tests/test_recovery_model.mjs tests/test_report_adapter.mjs tests/test_report_export.mjs
git commit -m "feat: add recovery workflow and ten-section report adapter"
```

### Task 3: Workspace recovery UI, state summary, and responsive information hierarchy

**Files:**
- Create: `apps/web/components/RecoveryForm.js`
- Create: `tests/browser_report_recovery_v2.py`
- Modify: `apps/web/components/TripLensWorkspace.js`
- Modify: `apps/web/components/LogicLibrary.js`
- Modify: `apps/web/app/integration.css`
- Modify: `tests/test_analysis_client.mjs`

**Interfaces:**
- Consumes: Task 1 merge/integrity helpers and Task 2 recovery/report adapter.
- Produces: `RecoveryForm({value,onChange,catalog})` and persisted `recovery` session state.
- Keeps `/testbench`, `IntegrationTestbench.js`, and its labels unchanged.

- [ ] **Step 1: Add a failing browser workflow test**

Create `tests/browser_report_recovery_v2.py` using the existing mocked API fixture pattern. It must assert:

1. analysis completion shows four independent cards: input evidence, cause verification, recovery record, document;
2. initial recovery card says `입력 대기`, not repeated `UNKNOWN`;
3. selecting `복구 완료`, filling time/operator/actions/restart conditions and an existing Evidence ID changes it to `승인 대기`;
4. explicit approval changes it to `승인 완료` only when required fields are complete;
5. changing actions after approval returns it to `승인 대기`;
6. reload preserves recovery data;
7. replacing EVENT or RAW clears recovery to input pending;
8. report CSV contains all 21 EVENT evidence IDs, exact Source tags, and recovery data;
9. an unresolved recovery Evidence ID disables PDF, PINPOINT, and report CSV export;
10. 390x844 viewport has no page-wide horizontal overflow.

- [ ] **Step 2: Run the browser test and verify RED**

Run: `python tests/browser_report_recovery_v2.py`

Expected: FAIL because the recovery form and status cards do not exist.

- [ ] **Step 3: Implement `RecoveryForm`**

Render a status select whose first option is `선택 대기`, fields for recovered time, operator, actual actions, restart conditions, evidence IDs selected from the current catalog, record approver, and an explicit `승인 기록` action. Label the approver field `기록상 승인자`; state that this is a report record, not plant control or authenticated electronic approval.

- [ ] **Step 4: Wire authoritative merged data and recovery state into the workspace**

In `TripLensWorkspace.js`:

- compute display events through `mergeEvents(eventData.records, result?.events || inspected?.events)`;
- compute report catalog through `mergeEvidenceCatalog(events, result?.evidence_catalog)`;
- inside `analyze()`, immediately merge `eventData.records` with `data.events` before calling `buildDraftRows()`; never use the stale closure preference `events.length ? events : data.events`;
- persist normalized recovery with the session;
- clear it on file change and `clear()`;
- build export rows through `applyRecoveryRows()` and `buildWorkspaceExportReport()`;
- disable all three exports when reference/recovery Evidence integrity fails;
- keep recovery-derived rows read-only in the generic report editor and link users to the recovery tab.
- extend human report status labels to render `INPUT_PENDING`, `APPROVAL_PENDING`, and `APPROVED` in Korean while keeping AI claim status choices limited to `UNKNOWN`, `OBSERVED`, and `CANDIDATE`.

- [ ] **Step 5: Reduce default information density**

Add four status cards after analysis. Move Run ID/digests/versions into a closed `감사·버전 정보` details block. Keep Critical Events and Primary/Direct cards open. Put full EVENT, Propagation, Causal Chain, counter evidence, and tool trace in individually labeled details blocks. Show missing engineering information as `추가 확인 N건` rather than repeated UNKNOWN badges.

Change analysis evidence buttons only to:

```text
태그 기준 도면 · {tag}
운전조건·룰 기준 도면 · {rule}
```

Change the logic dialog title/ARIA copy consistently, but do not modify testbench button text.

- [ ] **Step 6: Add responsive report cards and stronger contrast**

Add `data-label` to report cells. Below 700px render each report row as a card with labels; remove the editable table's mobile minimum width. Keep desktop eight-column layout. Increase body/detail text and status contrast without changing the testbench-specific CSS classes.

- [ ] **Step 7: Run focused unit and browser tests and verify GREEN**

Run:

```bash
node --test tests/test_analysis_client.mjs tests/test_report_integrity.mjs tests/test_recovery_model.mjs tests/test_report_adapter.mjs
python tests/browser_report_recovery_v2.py
python tests/browser_v8_review.py
```

Expected: all PASS; the existing browser testbench assertions remain unchanged and green.

- [ ] **Step 8: Commit Task 3**

```bash
git add apps/web/components/RecoveryForm.js apps/web/components/TripLensWorkspace.js apps/web/components/LogicLibrary.js apps/web/app/integration.css tests/browser_report_recovery_v2.py tests/test_analysis_client.mjs
git commit -m "feat: add recovery workflow and focused report UI"
```

### Task 4: draw.io schema 2 generator, viewer, and assets

**Files:**
- Modify: `scripts/logic_assets/drawio.py`
- Modify: `scripts/logic_assets/build.py`
- Modify: `scripts/logic_assets/viewer.html`
- Modify: `scripts/update_triplens_logic.py`
- Modify: `tests/test_logic_assets.py`
- Modify: `tests/test_logic_pipeline.py`
- Modify: `tests/test_logic_update_command.py`
- Modify: `tests/test_logic_viewer.py`
- Modify: `docs/LOGIC_ASSETS.md`
- Regenerate: `logic_diagrams/**`
- Regenerate: `generated/logic/**`
- Regenerate: `apps/web/public/logic-assets/**`

**Interfaces:**
- Produces: draw.io root/index/manifest `schema_version: 2` with node IDs `condition:{rule_id}`, `operation:{rule_id}`, `additional:{rule_id}`.
- Preserves: existing page IDs, input IDs `source:{group}:{digest}`, output IDs `output:{rule}:{digest}`, semantic hashes, and export/save behavior.
- Consumes: registered logic source fields `condition`, `delay`, `reset_hysteresis`, `validation_status`, `output_class`.

- [ ] **Step 1: Write schema-2 generator tests**

Extend `tests/test_logic_assets.py` to assert every rule page has exactly one condition, operation, and additional object; edges are only input→condition, condition→operation, and operation→output; additional nodes have no edges; hysteresis is absent from operation labels and present in additional labels. Assert XML root and index both equal schema 2.

Add migration tests:

```python
self.assertNotEqual(v1_logic_geometry, v2_operation_geometry)
self.assertEqual(v2_saved_operation_geometry, v2_regenerated_operation_geometry)
```

Extend update-command tests so schema 1 `logic:` layouts can be migrated once and schema 2 `operation:` layouts can be updated again; numeric-ID legacy previews remain rejected.

- [ ] **Step 2: Run generator/update tests and verify RED**

Run:

```bash
python -m unittest tests.test_logic_assets tests.test_logic_pipeline tests.test_logic_update_command
```

Expected: FAIL because generated schema is 1 and condition/operation/additional nodes do not exist.

- [ ] **Step 3: Implement schema-2 geometry and metadata**

Use columns:

| Column | x | width |
|---|---:|---:|
| INPUT | 40 | 320 |
| CONDITION | 410 | 320 |
| OPERATION | 780 | 320 |
| OUTPUT | 1150 | 360 |

Create column headers per group. Use a minimum rule-branch height of 250px and expand for multiple outputs. Put delay, reset/hysteresis, validation status, and output class only in `additional:{rule}` below the operation block. Do not connect the additional node to signal edges. Use new condition/operation IDs so schema-1 central geometry is not inherited.

- [ ] **Step 4: Update build products and update-command compatibility**

Set manifest/index schema to 2. Synchronize generated block/edge tables with condition, operation, and additional types. In `update_triplens_logic.py`, accept `logic:` as the stable central ID for schema 1 and `operation:` for schema 2, rejecting mixed or unsupported layouts fail-closed.

- [ ] **Step 5: Update viewer behavior under failing Playwright tests**

Change viewer startup to require XML and index schema 2. Add legend entries for condition, operation, and additional information. Selecting a rule highlights all three rule-owned blocks. Only tags, rules, and page links receive button semantics; column/title/additional labels are not announced as controls.

Update `tests/test_logic_viewer.py` to drag/save `operation:AL-HP-LEVEL-HH`, verify the four x-columns do not overlap, verify additional is below operation, and verify mismatched schema fails closed.

Run: `python -m unittest tests.test_logic_viewer`

Expected: PASS after implementation.

- [ ] **Step 6: Regenerate all logic assets and verify them**

Run:

```bash
python scripts/update_triplens_logic.py
python scripts/update_triplens_logic.py --check
```

Expected: first command updates all generated destinations; second prints `{"status":"PASS","mismatches":[]}`.

- [ ] **Step 7: Run complete logic tests and verify GREEN**

Run:

```bash
python -m unittest tests.test_logic_assets tests.test_logic_pipeline tests.test_logic_update_command tests.test_logic_viewer tests.test_logic_web_install tests.test_logic_latest_main_install
node --test tests/test_integration_testbench.mjs
```

Expected: all PASS without modifications to frozen testbench sources.

- [ ] **Step 8: Commit Task 4**

```bash
git add scripts/logic_assets/drawio.py scripts/logic_assets/build.py scripts/logic_assets/viewer.html scripts/update_triplens_logic.py tests/test_logic_assets.py tests/test_logic_pipeline.py tests/test_logic_update_command.py tests/test_logic_viewer.py docs/LOGIC_ASSETS.md logic_diagrams generated/logic apps/web/public/logic-assets
git commit -m "feat: generate readable schema two logic diagrams"
```

### Task 5: Full regression, frozen-scope proof, documentation, and GitHub branch

**Files:**
- Modify: `docs/INTEGRATION_TESTBENCH_REPORT_V2.md`
- Modify: `docs/VERCEL_MIGRATION_P0_README.md`
- Create: `outputs/report-recovery-v2/verification-summary.json` (test artifact; do not commit unless existing policy requires it)

**Interfaces:**
- Consumes all prior task outputs.
- Produces a clean branch whose frozen testbench files match `origin/main` byte-for-byte and whose PR checks can gate the single main merge.

- [ ] **Step 1: Update operational documentation**

Document the ten real-app report sections, complete EVENT plus retrieved RAW evidence policy, recovery workflow labels, legacy testbench compatibility path, and the actual deployment sequence `PR CI → one main merge → two Vercel project statuses`. Remove any instruction claiming the current configuration creates a PR Vercel Preview.

- [ ] **Step 2: Install deterministic web dependencies and build**

Run:

```bash
npm ci --prefix apps/web --no-audit --no-fund
npm run build --prefix apps/web
```

Expected: Next.js production build succeeds.

- [ ] **Step 3: Run full relevant suites**

Run:

```bash
node --test tests/test_analysis_client.mjs tests/test_ai_output_contract.mjs tests/test_event_tag_resolver.mjs tests/test_report_integrity.mjs tests/test_recovery_model.mjs tests/test_report_adapter.mjs tests/test_report_export.mjs tests/test_report_row_identity.mjs tests/test_report_semantic_placement.mjs tests/test_integration_testbench.mjs
python -m unittest discover -s services/agent-api/tests -p 'test_*.py' -v
python -m unittest tests.test_logic_assets tests.test_logic_pipeline tests.test_logic_update_command tests.test_logic_viewer tests.test_logic_web_install tests.test_logic_latest_main_install
python scripts/update_triplens_logic.py --check
python tests/browser_report_recovery_v2.py
python tests/browser_v8_review.py
```

Expected: all PASS.

- [ ] **Step 4: Prove frozen files are unchanged**

Run:

```bash
git diff --exit-code origin/main -- apps/web/components/IntegrationTestbench.js apps/web/lib/integrationTestbench.mjs tests/test_integration_testbench.mjs
```

Expected: no output and exit status 0.

- [ ] **Step 5: Verify final diff and commit documentation**

Run `git diff --check` and inspect `git status --short`. Commit only documentation/source/test/generated assets intended by this plan:

```bash
git add docs/INTEGRATION_TESTBENCH_REPORT_V2.md docs/VERCEL_MIGRATION_P0_README.md
git commit -m "docs: record report recovery and deployment gates"
```

- [ ] **Step 6: Push the feature branch once and open a PR**

After rebasing/merging the latest `origin/main` locally and re-running Step 3, push `fix/report-integrity-recovery-diagram-v2` once. Open a PR targeting `main` with the frozen-scope proof and test totals. Do not merge while any required check is pending or failing.

- [ ] **Step 7: Confirm all GitHub PR checks**

Require green results for applicable workflows including V8 evidence UI integration, citation/reviewer references, semantic report placement, logic database/assets, and Vercel migration build. Confirm the PR head still contains latest `origin/main` with:

```bash
git fetch origin
git merge-base --is-ancestor origin/main HEAD
```

Expected: exit status 0 before merge.

### Task 6: Single main merge, Vercel verification, and rollback boundary

**Files:** none unless a separately reviewed rollback fix is required.

**Interfaces:**
- Consumes: fully green PR from Task 5.
- Produces: one main merge and verified web/API deployments.

- [ ] **Step 1: Merge the green PR once**

Use the repository's merge-commit convention. Do not add a second main commit for cosmetic changes. Record the resulting merge SHA.

- [ ] **Step 2: Verify both Vercel deployments for the merge SHA**

Wait for both GitHub deployment statuses:

```text
Vercel – triplens-web-preview
Vercel – triplens-agent-api-preview
```

Both must be `success`. Verify API `/health` reports `deployment_sha` equal to the merge SHA and `/contract` returns the expected Current V8 contract.

- [ ] **Step 3: Run production smoke checks**

Verify web `/`, `/logic`, and `/testbench`; `/testbench` must still show `ALL PASS`. Run one representative EVENT+RAW flow and confirm:

- zero dangling Evidence IDs;
- exact Source tags in report CSV;
- automatic SOE separated from operator actions;
- recovery progresses `입력 대기 → 승인 대기 → 승인 완료`;
- PDF and CSV show the same recovery record;
- mobile page has no global horizontal overflow.

- [ ] **Step 4: Apply the rollback boundary if production verification fails**

Do not push another main fix. Roll back both affected Vercel projects to the prior known-good deployment, open a new fix branch, reproduce the failure with a test, and repeat the PR gate.
