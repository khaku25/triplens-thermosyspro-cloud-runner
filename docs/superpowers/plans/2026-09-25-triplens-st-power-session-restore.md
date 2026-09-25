# TripLens ST Power and Session Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ST POWER visibly discoverable in Plant View and preserve the completed analysis when the user returns from Drawing Master.

**Architecture:** Keep ST POWER as a presentation link to the existing verified tag/logic asset; do not invent a live numeric value in the static Plant View. Re-enable the existing IndexedDB session mechanism for the analysis workspace, with a versioned payload and explicit clearing only when the user presses the clear button.

**Tech Stack:** Next.js 16, React 19, browser IndexedDB, ECMAScript modules, Node test runner, standard-library unittest source-contract tests.

**Spec:** Current user request and clarification: show `ST POWER · vppSTGridPowerMW · MW` in Plant View without a prominent “실시간 아님” label; preserve analysis state after Drawing Master navigation.

## Global Constraints

- Do not discard or overwrite unrelated dirty worktree changes.
- Do not expose a fabricated current ST POWER number in Plant View.
- Keep the existing source-observation and runtime-verification status in the underlying logic/data assets and technical documentation.
- Do not place EVENT/RAW contents in the URL; persist the workspace locally through the existing IndexedDB helpers.
- The explicit “입력·분석 지우기” action remains the user-controlled deletion path.

## Review Focus

- Returning to `/` after a completed analysis restores both uploaded File objects and parsed records; test in the session payload contract and component contract.
- A saved session from another workspace mode or schema version is ignored; test the version/mode guard.
- Clearing a workspace does not immediately re-save an empty session over the deletion; test the persistence control flow contract.
- ST POWER is visible in Plant View and links to the exact `vppSTGridPowerMW` logic route; test the display descriptor and rendered source contract.
- The ST display contains a tag/unit identity but no invented numeric value or unwanted “실시간 아님” presentation copy; test the descriptor and rendered source.

### Task 1: Restore the analysis workspace across route navigation

**Files:**
- Create: `apps/web/lib/workspaceSession.mjs`
- Test: `apps/web/lib/workspaceSession.test.mjs`
- Test: `tests/test_workspace_persistence_contract.py`
- Modify: `apps/web/components/TripLensWorkspace.js`

**Interfaces:**
- Produces `WORKSPACE_SESSION_VERSION`, `buildWorkspaceSession(state)`, and `canRestoreWorkspaceSession(value, mode)` from `workspaceSession.mjs`.
- Consumes the existing `loadSession`, `saveSession`, `clearSession`, `parseCSV`, and report restoration helpers from the workspace.

- [ ] **Step 1: Write the failing unit test for the versioned payload and guard**

  Add Node tests that require `buildWorkspaceSession` to retain mode, File-like values, parsed data, result, report rows, recovery, and active tab, and require `canRestoreWorkspaceSession` to reject a different mode or schema version.

  ```js
  test('builds a restorable workspace payload without dropping analysis state', () => {
    const payload = buildWorkspaceSession({ mode: 'blind', eventFile, rawFile, eventData, rawData, result, reportRows, recovery, activeTab: 'cause' });
    assert.equal(payload.schema_version, WORKSPACE_SESSION_VERSION);
    assert.equal(payload.eventFile, eventFile);
    assert.deepEqual(payload.result, result);
    assert.equal(payload.activeTab, 'cause');
    assert.equal(canRestoreWorkspaceSession(payload, 'blind'), true);
  });

  test('rejects sessions from another mode or schema version', () => {
    const payload = buildWorkspaceSession({ mode: 'blind' });
    assert.equal(canRestoreWorkspaceSession({...payload, mode: 'demo'}, 'blind'), false);
    assert.equal(canRestoreWorkspaceSession({...payload, schema_version: 999}, 'blind'), false);
  });
  ```

- [ ] **Step 2: Run the focused test and verify it fails because the module is missing**

  Run `node --test apps/web/lib/workspaceSession.test.mjs`.

  Expected: FAIL with an import/module-not-found error for `workspaceSession.mjs`.

- [ ] **Step 3: Add the minimal session payload helper**

  Implement `buildWorkspaceSession` as a plain serializable object that intentionally keeps File/Blob values for IndexedDB, and implement `canRestoreWorkspaceSession` with exact schema-version and mode checks. Do not put persistence side effects in this helper.

- [ ] **Step 4: Run the focused test and verify it passes**

  Run `node --test apps/web/lib/workspaceSession.test.mjs`.

  Expected: all focused session-helper tests pass.

- [ ] **Step 5: Write the failing integration contract test**

  Add standard-library `unittest` assertions that `TripLensWorkspace.js` imports `loadSession` and `saveSession`, calls `loadSession` during restoration, persists `buildWorkspaceSession`, and does not clear the session in the initial mount effect.

- [ ] **Step 6: Run the integration contract test and verify it fails against the current implementation**

  Run `python tests/test_workspace_persistence_contract.py`.

  Expected: FAIL because the current component imports only `clearSession`, clears on mount, and never loads or saves a session.

- [ ] **Step 7: Reconnect IndexedDB restoration and debounced persistence**

  In `TripLensWorkspace.js`:

  - Import `loadSession`, `saveSession`, `buildWorkspaceSession`, `canRestoreWorkspaceSession`, `restoreWorkspaceReportRows`, and the existing report version constant.
  - Add a `restored` state and a clear guard ref.
  - On mount, load the session, check mode/schema, restore the two File objects and parsed CSV data, restore result/report rows/recovery/active tab, then mark restoration complete.
  - Replace the mount-time `clearSession()` call with the restoration effect.
  - Add a debounced save effect keyed to the restored workspace state.
  - Keep `clearSession()` in explicit reset paths, and prevent the clear button from being followed by an automatic empty-session write.
  - Preserve existing behavior that selecting a new file invalidates the previous analysis.

- [ ] **Step 8: Run the integration contract test and focused unit test**

  Run `python tests/test_workspace_persistence_contract.py && node --test apps/web/lib/workspaceSession.test.mjs`.

  Expected: all tests pass.

- [ ] **Step 9: Commit the session restoration task**

  ```bash
  git add apps/web/lib/workspaceSession.mjs apps/web/lib/workspaceSession.test.mjs apps/web/components/TripLensWorkspace.js tests/test_workspace_persistence_contract.py
  git commit -m "fix(web): restore analysis after drawing navigation"
  ```

### Task 2: Make ST POWER visible in Plant View

**Files:**
- Create: `apps/web/lib/stPowerDisplay.mjs`
- Test: `apps/web/lib/stPowerDisplay.test.mjs`
- Test: `tests/test_st_power_plant_display.py`
- Modify: `apps/web/components/PlantDrawingMaster.js`

**Interfaces:**
- Produces `ST_POWER_DISPLAY` with the exact label, tag, unit, and logic href.
- Consumes the already-published `vppSTGridPowerMW` logic asset; the Plant View card does not create or imply a live measurement.

- [ ] **Step 1: Write the failing ST display tests**

  Add Node assertions for `ST_POWER_DISPLAY.label === 'ST POWER'`, `tag === 'vppSTGridPowerMW'`, `unit === 'MW'`, and `href === '/logic?tag=vppSTGridPowerMW'`. Add standard-library `unittest` source assertions that PlantDrawingMaster imports the descriptor, renders the label/tag/unit, links to the exact route, and contains neither a fabricated numeric value nor the phrase `실시간 아님` in the visible card.

- [ ] **Step 2: Run the focused ST tests and verify they fail**

  Run `node --test apps/web/lib/stPowerDisplay.test.mjs && python tests/test_st_power_plant_display.py`.

  Expected: FAIL because the display descriptor/card is not present in the current source.

- [ ] **Step 3: Add the exact ST display descriptor and Plant View card**

  Create the small immutable descriptor and render a prominent but compact Plant View card labeled `ST POWER`, `vppSTGridPowerMW`, and `MW`, with a `로직 연결 보기` link to the existing logic route. Do not render a numeric value or a prominent runtime-status disclaimer.

- [ ] **Step 4: Run the focused ST tests and verify they pass**

  Run `node --test apps/web/lib/stPowerDisplay.test.mjs && python tests/test_st_power_plant_display.py`.

  Expected: all focused ST display tests pass.

- [ ] **Step 5: Commit the ST display task**

  ```bash
  git add apps/web/lib/stPowerDisplay.mjs apps/web/lib/stPowerDisplay.test.mjs apps/web/components/PlantDrawingMaster.js tests/test_st_power_plant_display.py
  git commit -m "feat(web): surface ST power in plant view"
  ```

### Task 3: Verify the combined web change

**Files:**
- No additional production files.
- Verify: Task 1 and Task 2 files, existing Drawing Master and ST release tests, and the Next build.

- [ ] **Step 1: Run focused Node and unittest tests together**

  Run `node --test apps/web/lib/workspaceSession.test.mjs apps/web/lib/stPowerDisplay.test.mjs && python tests/test_workspace_persistence_contract.py && python tests/test_st_power_plant_display.py && PYTHONPATH=tests python -m unittest tests.test_st_power_web_release tests.test_drawing_master_restoration`.

- [ ] **Step 2: Run the web build**

  From `apps/web`, run `npm ci` if dependencies are absent, then `npm run build`.

  Expected: Next production build exits 0.

- [ ] **Step 3: Inspect the final diff and worktree boundaries**

  Run `git diff --check`, `git diff --stat HEAD~2..HEAD`, and `git status --short`. Confirm the two task commits contain only the planned web/helper/test files and that pre-existing user changes remain untouched.

- [ ] **Step 4: Record the verification result and hand off deployment**

  If all commands pass, report the local implementation and explain that pushing/redeploying the Vercel preview is a separate external write requiring explicit permission.

## Review Focus Mapping

- Session round-trip and file restoration: Task 1 Steps 1, 7, and 8.
- Mode/version isolation: Task 1 Steps 1 and 4.
- Clear-button deletion race: Task 1 Steps 5–8 and source contract assertion.
- ST exact tag/unit/link: Task 2 Steps 1–4.
- No fabricated numeric value or unwanted visible disclaimer: Task 2 Step 1 and source contract test.
