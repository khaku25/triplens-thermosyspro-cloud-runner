# TripLens Hybrid Agent Evidence Tools v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Python an evidence/search/verifier layer while reserving Critical Events, Primary Cause, Direct Trigger, Propagation, and Causal Chain decisions for the Gemini agent, with bounded tool responses to control token use.

**Architecture:** Add a standalone Python EvidenceStore that reads immutable EVENT.csv + RAW.csv and exposes six bounded tools. Keep the existing dual-log analyzer as an evidence-readiness verifier, but explicitly mark its output as candidate evidence rather than causal decisions. A small policy document/config defines the Gemini decision boundary and token budget. Existing Verification Gate / AI output contract remains the post-analysis guard.

**Tech Stack:** Python 3 standard library, unittest, existing EVENT/RAW CSV contracts, existing TripLens JavaScript AI output contract.

**Spec:** `docs/superpowers/specs/2026-09-17-triplens-incident-report-v2-design.md`

## Global Constraints

- Standard input remains EVENT.csv + RAW.csv.
- TripLens remains READ-ONLY.
- Do not modify Modelica, OPC UA, v5/v6/v7, or V8 Virtual Plant physics.
- Python must not generate Primary Cause, Direct Trigger, Propagation, Critical Events, or Causal Chain as final decisions.
- Gemini may only reason from Evidence Policy-approved tool results.
- Unregistered Logic Master tags remain explicit and are never inferred.
- Default maximum Gemini tool calls per analysis: 8.
- search_events response cap: 20.
- get_event_window response cap: 30.
- get_raw_window response cap: 50 rows and 8 tags.
- get_tag_series response cap: 50 points plus numeric summary.
- Same EVENT/RAW digest + Logic Master version + Tool/Prompt version may reuse a prior result.

---

### Task 1: Bounded evidence tool layer

**Files:**
- Create: `scripts/triplens_agent_tools.py`
- Create: `tests/test_agent_tools.py`

**Interfaces:**
- Produces `EvidenceStore(event_csv, raw_csv, logic_rows=None)`.
- Produces `search_events()`, `get_event_window()`, `get_raw_window()`, `get_tag_series()`, `get_logic_context()`, `get_equipment_state()`.
- Produces `AgentToolSession` with an eight-call budget.
- Produces `build_agent_bootstrap()` which contains metadata/manifest but not bulk EVENT/RAW rows.

- [ ] Write tests that prove response caps, exact Logic Master matching, explicit raw-tag requests, and eight-call budget.
- [ ] Verify RED because the module does not exist.
- [ ] Implement the evidence store and tool session.
- [ ] Verify GREEN with `python3 tests/test_agent_tools.py`.

### Task 2: Separate deterministic evidence readiness from causal decisions

**Files:**
- Modify: `scripts/triplens_dual_log_analyzer.py`
- Create: `tests/test_dual_log_agent_role.py`

**Interfaces:**
- Existing `analyze_dual_logs()` remains callable.
- Adds `analysis_role=EVIDENCE_PROVIDER_ONLY`, `decision_authority=GEMINI_AGENT`, `status_scope=EVIDENCE_READINESS_ONLY`.
- Adds `candidate_evidence` for onset/protection-chain/process-response candidates.
- Does not emit final causal decision keys.

- [ ] Write a failing role-boundary regression test.
- [ ] Add role metadata and candidate evidence envelope while retaining legacy readiness status.
- [ ] Run both new Python test files.

### Task 3: Agent policy and prompt contract

**Files:**
- Create: `config/triplens_hybrid_agent_v1.json`
- Create: `docs/triplens_hybrid_agent_prompt.md`

**Interfaces:**
- Gemini receives small bootstrap metadata first.
- Gemini must use tools for evidence and must return the existing structured AI output contract.
- Primary Cause defaults to CANDIDATE unless Verification Gate later promotes it.

- [ ] Encode token/response limits and decision ownership.
- [ ] Encode search-first, counter-evidence-first prompt rules.
- [ ] Explicitly forbid bulk RAW context and precomputed answer metadata.

### Task 4: CI regression coverage

**Files:**
- Modify: `.github/workflows/build-logic-db.yml`

**Interfaces:**
- PRs touching the hybrid agent tools run both Python regression tests.

- [ ] Add new paths to push/pull_request triggers.
- [ ] Add a Hybrid Agent evidence-tool regression step.
- [ ] Verify the workflow passes on the PR.
