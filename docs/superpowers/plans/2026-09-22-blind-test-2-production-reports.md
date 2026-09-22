# Blind Test 2 Production Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the approved TripLens fixes and collect twelve production-site PDF failure reports by directly uploading the twelve Blind Test 2 EVENT/RAW pairs.

**Architecture:** Treat the production website as the system under test. Verify and hash the twelve local copies first, promote the reviewed commit through the repository's main-only Vercel deployment path, then execute one isolated browser session per pair through upload, bootstrap, analysis, and the site's report-print path. Validate every resulting PDF structurally and visually before uploading it to the matching Google Drive scenario folder.

**Tech Stack:** Next.js 16, FastAPI, Vercel Git deployments, agent-browser/Chromium, Node test runner, Python PDF tooling, Google Drive connector.

**Spec:** `docs/superpowers/specs/2026-09-22-blind-test-2-production-reports-design.md`

## Global Constraints

- Analyze only each scenario's actual EVENT/RAW pair; prior reports and expected answers are not analyzer inputs.
- Never pass scenario ID, scenario name, expected cause, root cause, answer label, fault injection, fault preset, or TEST_AUDIT metadata to the analyzer.
- Reset browser workspace state between scenarios.
- Preserve HOLD, partial, and failed validation states honestly.
- Do not overwrite older Drive reports; use a distinct final filename.
- Deploy through the repository's paired main-branch Vercel flow; do not bypass it with an unlinked direct CLI production deploy.
- A completed scenario requires a site-produced, non-empty, visually verified PDF.

## Review Focus

- EVENT and RAW files from different scenarios must never be paired.
- Browser state from one scenario must not survive into the next upload.
- Analysis completion must be distinguished from timeout, API error, or stale prior content.
- The PDF must contain run-specific evidence rather than only static sample rows.
- Popup/print capture must preserve all four pages without table or approval-grid overflow.

---

### Task 1: Freeze the twelve-input manifest

**Files:**
- Create: `output/blind-test-2-final/input-manifest.json`
- Read: `/workspace/scratch/e9883b80971f/working/clean_csv/**`

**Interfaces:**
- Consumes: the twelve numbered scenario names and their local EVENT/RAW copies.
- Produces: a manifest containing absolute source path, byte size, SHA-256, CSV header, and row count for each file.

- [ ] **Step 1: Enumerate all twelve expected scenario names and require one EVENT and one RAW file for each.**
- [ ] **Step 2: Compute byte size, SHA-256, header, and row count for all twenty-four files.**
- [ ] **Step 3: Fail the preflight if any pair is missing, duplicated, empty, or uses an incompatible header.**
- [ ] **Step 4: Write and independently review `input-manifest.json`.**

### Task 2: Verify and promote the deployment commit

**Files:**
- Verify: `apps/web/vercel.json`
- Verify: `services/agent-api/vercel.json`
- Test: `tests/test_report_export.mjs`
- Test: `tests/test_integration_testbench.mjs`

**Interfaces:**
- Consumes: the current feature branch containing the report-grid and Drawing Master commits.
- Produces: one reviewed main-branch merge commit deployed by both configured Vercel projects.

- [ ] **Step 1: Fetch origin, confirm the branch is clean, and confirm `origin/main` is an ancestor or integrate it without discarding user work.**
- [ ] **Step 2: Run the focused report, integration, Drawing Master, API, and Next production-build checks.**
- [ ] **Step 3: Push the feature branch, create/reuse a pull request, and wait for required GitHub checks.**
- [ ] **Step 4: Merge once into `main` and record the exact merge SHA.**
- [ ] **Step 5: Confirm both Vercel project checks are successful for that SHA and verify web `/`, `/logic`, `/testbench` plus API `/health` and `/contract`.**

### Task 3: Execute twelve production browser analyses

**Files:**
- Create: `output/blind-test-2-final/run-results.json`
- Create: `output/blind-test-2-final/browser-evidence/`
- Read: `output/blind-test-2-final/input-manifest.json`

**Interfaces:**
- Consumes: the production web URL, deployed SHA, and input manifest.
- Produces: a per-scenario record of upload, bootstrap, analysis, report-control, and reset outcomes plus screenshots and response evidence.

- [ ] **Step 1: Open production and record a clean baseline screenshot, URL, deployed SHA, and absence of framework errors.**
- [ ] **Step 2: For each manifest row, start from a reset workspace and upload only that EVENT/RAW pair.**
- [ ] **Step 3: Wait for bootstrap readiness, start analysis, and require a terminal analysis state with current run-specific content.**
- [ ] **Step 4: Save screenshots and the visible run/evidence identifiers before opening the report.**
- [ ] **Step 5: If a boundary fails, preserve evidence, stop that run, add a failing regression test, fix, redeploy, and retry from fresh upload.**

### Task 4: Capture and verify twelve site-produced PDFs

**Files:**
- Create: `output/pdf/blind-test-2-final/*.pdf`
- Create: `output/blind-test-2-final/pdf-verification.json`
- Create: `tmp/pdfs/blind-test-2-final/`

**Interfaces:**
- Consumes: each completed production analysis and its report-print view.
- Produces: twelve final PDFs and machine/visual verification records.

- [ ] **Step 1: Open the site's PDF report control for the completed scenario and capture the printed document without reconstructing its content externally.**
- [ ] **Step 2: Require a readable PDF, non-zero size, expected four-page structure, scenario-run evidence identifiers, and no unresolved placeholder-only report.**
- [ ] **Step 3: Render every page to PNG and inspect approval grid, tables, line wrapping, margins, and page breaks.**
- [ ] **Step 4: Record PDF hash, page count, text checks, and visual verdict in `pdf-verification.json`.**
- [ ] **Step 5: Repeat until all twelve scenario entries have a verified site-produced PDF.**

### Task 5: Publish reports and update technical evidence

**Files:**
- Modify: `docs/INTEGRATION_TESTBENCH_REPORT_V2.md`
- Create: `docs/BLIND_TEST_2_PRODUCTION_REPORTS_2026-09-22.md`
- Create: `output/blind-test-2-final/collection-manifest.json`

**Interfaces:**
- Consumes: deployed SHA, run results, PDF verification, and twelve final PDFs.
- Produces: Drive-hosted reports in the twelve existing scenario folders and a durable technical evidence index.

- [ ] **Step 1: Upload each final PDF to its matching `5. BLIND TEST/<scenario>` folder without overwriting the older second-pass PDF.**
- [ ] **Step 2: Read back each Drive file's metadata and record its observed ID, URL, size, and modified time.**
- [ ] **Step 3: Add the deployed SHA, input hashes, analysis outcome, PDF checks, and Drive links to the technical evidence document.**
- [ ] **Step 4: Re-run focused tests/build and perform a final production smoke check.**
- [ ] **Step 5: Review the complete branch and report any honest residual limits or failed scenarios without converting them to PASS.**
