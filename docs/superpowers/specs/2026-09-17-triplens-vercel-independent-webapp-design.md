# TripLens Independent Vercel Web App Design

Date: 2026-09-17
Status: DESIGN REVIEW

## 1. Goal

Move TripLens web execution away from `chatgpt.site` so the application continues to run, can be edited from normal source control, and can redeploy without depending on ChatGPT site editing or chat token availability.

GitHub is the Source of Truth. Vercel is the deployment target.

## 2. Scope

The independent app accepts the current V8 Dual Log contract:

- `EVENT.csv`
- `RAW.csv`

It provides:

- EVENT/RAW intake and validation
- EVENT tag resolution through the approved EVENT registry and Tag Master mapping
- RAW evidence lookup and tag-series inspection
- incident summary
- critical events
- primary cause candidate
- direct trigger
- propagation
- causal chain
- key evidence
- recovery check
- full printable incident report
- `PINPOINT.csv` export
- Gemini review through a server-side API route

The app remains READ-ONLY decision support. It does not write to OT systems, operate breakers, change protection settings, or restart plant equipment.

## 3. Deployment Architecture

```text
GitHub repository
  khaku25/triplens-thermosyspro-cloud-runner
        |
        | push / merge to main
        v
Vercel Project
        |
        +-- Static browser app
        |     - EVENT.csv parser
        |     - RAW.csv parser
        |     - Tag resolver
        |     - Evidence store
        |     - Timeline / Causal / Recovery UI
        |     - PDF report view
        |     - PINPOINT.csv export
        |
        +-- Serverless API
              - /api/analyze
              - Gemini API call
              - GEMINI_API_KEY stored only as Vercel environment variable
```

## 4. Repository Layout

The first implementation will use a small dependency-light web app rather than introduce a heavy framework unless required by deployment tooling.

```text
webapp/
  index.html
  styles.css
  app.js
  event_tag_resolver.js
  triplens_report_export.js
  event_tag_map.json
api/
  analyze.js
vercel.json
package.json
```

Existing tested modules are reused:

- `webapp/event_tag_resolver.js`
- `webapp/triplens_report_export.js`

## 5. Data Boundary

### Browser-only processing

`EVENT.csv` and `RAW.csv` are parsed in the browser. Raw files are not uploaded to Vercel merely to render deterministic evidence views.

The browser constructs a compact evidence payload only when Gemini analysis is requested.

### Gemini request boundary

The browser sends only filtered evidence to `/api/analyze`.

The request must exclude:

- scenario name
- expected root cause
- answer key
- ground truth
- fault-injection metadata used as an answer label

The server route never receives or exposes `GEMINI_API_KEY` to browser JavaScript.

## 6. EVENT Tag Resolution

The deployed EVENT resolver uses deterministic resolution order:

1. canonical tag id when supplied
2. EVENT `rule_id`
3. exact source-node alias
4. exact `(equipment, event_tag)` lookup
5. explicit `UNMAPPED_EVENT_TAG`

No fuzzy matching is permitted.

The current runtime registry has 67 enabled EVENT rules and the CI-verified mapping target is 67/67.

Examples:

- `GT + TRIP_LATCH -> GT.TRIP.LATCH`
- `ST + TRIP_LATCH -> ST.TRIP.LATCH`
- `HP TURBINE + FLOW_LOW_LOW -> HRSG.HP.STEAM.FLOW.LL`

## 7. UI

The independent app keeps the present TripLens visual intent rather than redesigning the product.

Primary layout:

1. TripLens header and run counters
2. Dual Log intake
3. validation / mapping status
4. incident summary
5. critical events
6. causal analysis
7. evidence detail
8. recovery check
9. Gemini engineering review
10. export controls

Required export controls:

- Analysis CSV
- PINPOINT.csv
- Full PDF Report

Mobile behavior must preserve a back path from evidence detail to the main analysis workspace.

## 8. PDF Export

The app must not print the visible dashboard DOM directly because scroll containers can truncate content.

`Full PDF Report` builds an isolated report document from the current analysis state, expanding all report sections before invoking browser print-to-PDF.

Included sections:

- run metadata
- Incident Summary
- Critical Events
- Primary Cause
- Direct Trigger
- Propagation
- Causal Chain
- Key Evidence
- Recovery Check
- Gemini Analysis

The PDF export does not rerun Gemini and does not regenerate conclusions independently from the visible analysis state.

## 9. PINPOINT.csv

`PINPOINT.csv` is a derived output, never a blind-analysis input.

It preserves the evidence relationship behind each claim with fields including:

- run id
- causal stage
- claim
- disposition
- source system
- event id
- original time
- aligned time
- equipment
- event tag
- canonical tag
- value / unit / state
- evidence role
- logic id
- mapping status
- counter evidence
- recovery status
- review required

## 10. Gemini API

`POST /api/analyze`

Input:

```json
{
  "run_id": "...",
  "event_evidence": [],
  "raw_evidence": [],
  "logic_context": [],
  "deterministic_summary": {}
}
```

Output is constrained to the existing TripLens analysis sections.

Server failure behavior is fail-closed:

- deterministic EVENT/RAW evidence remains visible
- AI failure is shown separately
- no empty response is treated as a successful analysis
- AI failure does not erase baseline analysis

## 11. Security

- Gemini key only in Vercel environment variables
- no API key committed to GitHub
- no OT write endpoint
- no automatic breaker/restart action
- input files processed locally where possible
- payload size is bounded before server submission
- server accepts only the defined analysis schema

## 12. Verification

Before production deployment, CI must prove:

1. EVENT Tag Master coverage test passes
2. EVENT web resolver test passes
3. PDF report export contract test passes
4. PINPOINT.csv export contract test passes
5. static app build succeeds
6. `/api/analyze` handles missing API key safely
7. application smoke test loads the production entry page

After Vercel deployment, verify on the live URL:

- `EVENT.csv` + `RAW.csv` can be selected
- GT/ST `TRIP_LATCH` is not shown as an unregistered generic event
- HP TURBINE `FLOW_LOW_LOW` resolves to `HRSG.HP.STEAM.FLOW.LL`
- PDF report contains the complete report sections rather than only the visible viewport
- PINPOINT.csv downloads
- Gemini API route returns a controlled error without a key and a structured result when a valid key is configured

## 13. Release Flow

```text
feature branch
  -> tests
  -> pull request
  -> main
  -> Vercel automatic production deployment
  -> production smoke test
```

The `chatgpt.site` version remains only as a temporary historical/demo instance until the Vercel deployment passes the production smoke test.
