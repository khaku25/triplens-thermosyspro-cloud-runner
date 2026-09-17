# TripLens Independent Vercel Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a dependency-light TripLens web application on Vercel that independently processes V8 `EVENT.csv` + `RAW.csv`, preserves deterministic evidence, exports full PDF/PINPOINT reports, and optionally calls Gemini through a server-side route.

**Architecture:** Static browser code performs CSV parsing, validation, deterministic EVENT resolution, evidence construction, baseline causal reconstruction, rendering, PDF report preparation, and CSV export. A Vercel `/api/analyze` function accepts only a compact filtered evidence payload and returns a structured Gemini engineering review; missing-key or upstream failures fail closed without erasing deterministic analysis.

**Tech Stack:** Vanilla HTML/CSS/JavaScript, Node.js built-in test runner, Vercel static hosting + Node serverless function, existing `event_tag_resolver.js` and `triplens_report_export.js`.

**Spec:** `docs/superpowers/specs/2026-09-17-triplens-vercel-independent-webapp-design.md`

## Global Constraints

- GitHub is the Source of Truth; Vercel is the deployment target.
- Input contract is `EVENT.csv` + `RAW.csv`.
- EVENT resolution is deterministic only: canonical tag id → rule id → source-node alias → exact `(equipment,event_tag)` → `UNMAPPED_EVENT_TAG`; no fuzzy matching.
- Gemini key must exist only as `GEMINI_API_KEY` in the server environment.
- Scenario/root-cause/answer/fault-injection metadata must not be forwarded to Gemini.
- Baseline EVENT/RAW analysis must remain visible when Gemini fails.
- PDF export is built from full analysis state, not the visible scroll viewport.
- PINPOINT.csv is derived output only.
- TripLens remains READ-ONLY; no OT write endpoint or equipment command.

---

### Task 1: Deterministic Dual Log core

**Files:**
- Create: `webapp/triplens_core.js`
- Test: `tests/test_triplens_core.mjs`

**Interfaces:**
- Consumes: CSV text strings and EVENT mapping rows.
- Produces: `parseCsv(text)`, `buildEventMap(registryRows)`, `analyzeDualLog(eventRows, rawRows, eventMap, metadata)` and compact evidence payload builders.

- [ ] **Step 1: Write failing tests** for quoted CSV parsing, GT/ST latch disambiguation, HP TURBINE `FLOW_LOW_LOW -> HRSG.HP.STEAM.FLOW.LL`, unmapped explicit status, deterministic incident sections, RAW coverage warning, and metadata filtering.
- [ ] **Step 2: Run `node --test tests/test_triplens_core.mjs`** and verify RED because `triplens_core.js` does not exist.
- [ ] **Step 3: Implement minimal UMD core module** with deterministic rules and no fuzzy matching.
- [ ] **Step 4: Re-run the focused test** and verify all Task 1 tests pass.
- [ ] **Step 5: Commit** core + tests.

### Task 2: Independent browser application

**Files:**
- Create: `webapp/index.html`
- Create: `webapp/styles.css`
- Create: `webapp/app.js`
- Test: `tests/test_webapp_smoke.mjs`

**Interfaces:**
- Consumes: browser File API, `/config/alarm_registry_v1.csv`, `TripLensCore`, `TripLensEventTags`, `TripLensReportExport`.
- Produces: interactive Dual Log intake, deterministic report state, evidence tables, Tag Master mapping status, PDF and PINPOINT controls.

- [ ] **Step 1: Write failing static smoke test** asserting entry document contains EVENT/RAW inputs, analysis/export controls, and all required script imports.
- [ ] **Step 2: Run `node --test tests/test_webapp_smoke.mjs`** and verify RED.
- [ ] **Step 3: Implement accessible responsive HTML/CSS/JS**; load registry, parse files locally, render all deterministic sections, preserve a mobile back path, and wire existing full-report/PINPOINT helpers.
- [ ] **Step 4: Re-run smoke and existing resolver/report tests** and verify green.
- [ ] **Step 5: Commit** browser app.

### Task 3: Fail-closed Gemini server route

**Files:**
- Create: `api/analyze.js`
- Test: `tests/test_analyze_api.mjs`

**Interfaces:**
- Consumes: POST JSON `{run_id,event_evidence,raw_evidence,logic_context,deterministic_summary}`.
- Produces: controlled JSON error without key; structured JSON analysis when upstream Gemini succeeds.

- [ ] **Step 1: Write failing tests** for non-POST rejection, missing-key response, metadata-key rejection/filtering, empty upstream response failure, and structured success normalization.
- [ ] **Step 2: Run `node --test tests/test_analyze_api.mjs`** and verify RED.
- [ ] **Step 3: Implement serverless handler** with input bounds, allowlisted schema, `GEMINI_API_KEY`, fetch timeout, JSON extraction, and fail-closed errors.
- [ ] **Step 4: Re-run API tests** and verify green.
- [ ] **Step 5: Commit** API route.

### Task 4: Vercel build/release contract

**Files:**
- Create: `package.json`
- Create: `vercel.json`
- Create: `.github/workflows/test-independent-webapp.yml`
- Modify: `README.md` with independent webapp run/deploy notes.

**Interfaces:**
- Consumes: repository source.
- Produces: `npm test` regression command and Vercel routing for `/` + `/api/analyze`.

- [ ] **Step 1: Add failing release-contract assertions** to smoke tests for `vercel.json` and `package.json`.
- [ ] **Step 2: Run full `npm test`/Node test suite and verify the new assertions fail before config exists.**
- [ ] **Step 3: Add minimal package/config/workflow/docs.**
- [ ] **Step 4: Run `npm test` plus existing Python EVENT coverage test where available; verify all pass.**
- [ ] **Step 5: Commit** release contract.

### Task 5: PR, merge, Vercel production deployment, live verification

**Files:** none unless deployment verification exposes a bug.

**Interfaces:**
- Consumes: green feature branch.
- Produces: merged `main`, Vercel production deployment URL, production smoke evidence.

- [ ] **Step 1: Open PR** from `feat/vercel-independent-webapp` to `main` and wait for CI.
- [ ] **Step 2: Verify CI is green** and review changed files against the design requirements.
- [ ] **Step 3: Merge PR** only after the fresh green verification.
- [ ] **Step 4: Deploy `main` to Vercel**, then inspect build logs/deployment status.
- [ ] **Step 5: Fetch the live URL** and verify the TripLens entry page, EVENT/RAW controls, full report/PINPOINT controls, and controlled `/api/analyze` missing-key behavior.
- [ ] **Step 6: Report the actual live URL and any remaining Gemini-key setup requirement without claiming AI success unless a key-backed request has been verified.**
