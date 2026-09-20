# TripLens Final UI Implementation Plan

**Goal:** Make the production TripLens workspace show only the current dual-log analysis, recognize GT/ST Trip Latch aliases, and present a finished operator-facing light UI without changing the V8 analysis engine.

## 1. Lock the required behavior with tests

- Add presentation-state tests for pre-analysis data hiding, exact status copy, and 3–5 item evidence summaries.
- Extend EVENT tag resolver tests for GT/ST canonical tags, underscore/dotted aliases, RAW source aliases, and command/latch separation.
- Extend Agent API integration tests for the same mappings and ACTIVE value normalization.

## 2. Reset and gate workspace data

- Remove automatic browser-session restore/save from the analysis workspace.
- Reset result, evidence, recovery, report, detail, and selected tab whenever either file changes.
- Build EVENT/Evidence display data only after a successful analysis response.
- Replace the seven pipeline chips with the four requested input/analysis status states.

## 3. Normalize Trip Latch identities

- Add deterministic explicit aliases for GT/ST latch identities.
- Resolve generic `TRIP_LATCH` only with equipment/rule context, preserving GT/ST separation.
- Keep GT Trip Command and GT Trip Latch as distinct identities.
- Normalize boolean latch values to ACTIVE for 1/TRUE/ACTIVE.

## 4. Simplify the operator-facing UI

- Recompose cause analysis around Primary Cause, Direct Trigger, Propagation, and Causal Chain.
- Show only a short evidence summary by default and move complete evidence into collapsible detail.
- Remove developer validation labels, warning badges, pipeline stages, and unfinished-language status cards from default screens.
- Remove Notion references if any remain; retain Logic Master, TAG MASTER, evidence, report, and exports.
- Rename report actions and move CSV exports under an export menu.

## 5. Restore the established visual system

- Apply navy header, teal sidebar, light-gray canvas, white panels, blue titles/buttons, and restrained borders.
- Keep the existing testbench styling isolated.

## 6. Verify and deploy

- Run focused Node and Python tests, the full relevant suites, and the Next.js production build.
- Verify production UI behavior and forbidden copy.
- Merge to `main`, confirm Vercel production deployment, and smoke-test the live app.
