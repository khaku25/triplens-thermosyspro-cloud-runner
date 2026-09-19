# TripLens Vercel integration — Current V8 / V3

The filename is retained for existing references. This is no longer the original P0 shell. The original GPT.site, Windows simulation, Modelica, MATLAB and OPC UA control code are not modified by this integration repair.

## Repair scope

The old P0 passed HTTP tests with hand-authored GT events but omitted important real V8 boundaries: generic EVENT identity mapping, discoverable RAW tags, RAW Evidence IDs, uniform output objects and actual UI interaction. Old examples containing 86GT were not faithful to the Current V8 live source list and must not be used as evidence of the real runtime.

Current live source data remain 603 source nodes and 53 Logic Master rows. An uploaded historical RAW file can contain a different number of columns, including display aliases; CSV presence is not proof of current live source registration.

## Files and responsibilities

| File | Responsibility |
|---|---|
| `services/agent-api/app.py` | Immutable temporary uploads, validation, run/digest/version metadata and API responses |
| `services/agent-api/bridge.py` | Load the current local live SOT and instantiate the grounded evidence store |
| `services/agent-api/triplens/agent_tools.py` | Existing six bounded retrieval tools and the eight-call session budget |
| `services/agent-api/triplens/evidence_context.py` | Exact equipment+event mapping, actual RAW inventory, upstream design context, referenceable samples and validation |
| `services/agent-api/gemini_agent.py` | Stateless Gemini Interactions loop, enforced output schema, tool results and execution trace |
| `services/agent-api/triplens/analysis_contract.py` | Shape, retrieved-reference and chronology checks; no causal claim generation |
| `apps/web/lib/analysisClient.mjs` | Defensive display normalization, CSV parsing/export and browser-local persistence |
| `apps/web/components/TripLensWorkspace.js` | Five-tab workspace, evidence→logic detail, editable report V2 and export actions |
| `apps/web/components/IntegrationTestbench.js` | Static device Tag→Rule→draw.io and report-export testbench; no Agent/Gemini call |
| `apps/web/lib/integrationTestbench.mjs` | Deterministic device cases, exact index checks and report V2 adapter |
| `apps/web/lib/reportExporter.cjs` | Shared report V2 HTML/PDF and PINPOINT/8-column CSV engine |

## Six tools, unchanged decision ownership

`search_events` searches EVENT (20 rows). `get_event_window` reads chronology (30 rows, each side <=10 seconds). `get_raw_window` compares <=8 exact tags over <=20 seconds (50 rows). `get_tag_series` summarizes one tag (50 display points plus bounded transition brackets). `get_logic_context` exposes <=12 registered rules and upstream tags. `get_equipment_state` returns nearby equipment EVENT and explicitly requested, timestamped RAW states.

The total executed call budget is eight, not eight calls per function. The UI displays the actual calls and actual retrieved reference IDs. A tool existing in the manifest does not mean the agent called it.

## What is connected now

A real `GT::TRIP_LATCH` event resolves through the recorder registry to `vppGTTripLatch` while preserving the original tag. Registered design rows identify upstream request/input tags. Gemini can discover those actual RAW names, query samples and propose a cause. Python does not choose the active cause for the model.

TripLens analysis does not use a fixed `9-cause matrix` as its diagnostic frame. It follows the currently registered Logic Master upstream relationships dynamically. The physical V8 protection model may still contain the present GT/ST cause inputs and OR relationships; those model semantics remain untouched. If the registered input set changes later, the Agent follows the new registered set without changing an analysis-side fixed cause count.

All raw values cited in output have `RAW:<original-data-row>:<tag>` IDs, original record sequence, model time and audit time. Digital transition samples include bracketing times; a one-second historian interval cannot establish millisecond onset. Simultaneous GT/ST trips can share a common input and are not automatically interpreted as GT-to-ST intertrip.

## Contract and safety

All claim arrays use objects, including legacy string/description aliases at the presentation boundary. Missing evidence stays UNKNOWN. `CONFIRMED` from AI is downgraded. A PASS means only the implemented reference/shape/chronology checks passed, never engineering causality, recovery readiness or human approval. Reports remain editable drafts.

The API rejects malformed/duplicate identifiers, nonfinite model times, incompatible sessions/incidents, prohibited answer-header variants and non-overlapping analysis windows. These are implemented checks, not a claim of comprehensive prompt-injection immunity. Exact Logic registration does not itself prove that the rule caused this incident.

## Web behavior

Original EVENT rows remain available independent of AI-selected Critical Events. Evidence detail exposes exact `source_node` and every registered `logic_id` as links to the shared draw.io viewer. Browser IndexedDB preserves selected files, result and edited report across navigation/reload when storage is available. Matching backend analysis identity reuses the result without another Gemini call. Report V2 PDF and the draft CSV use the current editable eight-column rows; PINPOINT retains its fixed evidence schema. Missing sections are shown as UNKNOWN review rows rather than silently omitted.

`/testbench` verifies ten representative device connections and the report export engine from packaged static assets only. Full details and the one-promotion deployment gate are in [`INTEGRATION_TESTBENCH_REPORT_V2.md`](INTEGRATION_TESTBENCH_REPORT_V2.md).

## Deployment

Frontend root: `apps/web`. Backend root: `services/agent-api`, self-contained; no repository-external imports are required. Backend `GEMINI_API_KEY` stays server-side. Frontend uses `NEXT_PUBLIC_TRIPLENS_API_BASE`; never prefix an API key with NEXT_PUBLIC.

Endpoints: GET `/health`, GET `/contract`, POST `/bootstrap` (no Gemini call), POST `/analyze`. Direct upload limit remains 4,000,000 bytes. Large-file Blob support and production-grade authentication/rate limiting are separate hardening work, not claimed complete here.

## Verification evidence and limits

Run `python -m unittest discover -s services/agent-api/tests -p 'test_*.py' -v` and `node --test tests/test_analysis_client.mjs`, plus the existing event/report regressions. `Review V8 Evidence UI Integration` builds Next.js and tests real Chromium at desktop/mobile sizes, including evidence navigation, refresh/reuse and edited CSV. Its model HTTP responses are mocked and clearly labeled; it is not a live AI test.

`Test Deployed V8 Evidence Integration` separately replays original GT/ST EVENT+RAW from archived run 34984251101 artifact 10404407335, without modifying input bytes or sending archive path/scenario names to Gemini. A degraded synthetic input checks that missing initiating evidence remains UNKNOWN. A successful regression is not a blind-generalization benchmark or a new physics simulation.

The screenshot's session `SESSION_20260915_145125` and 48.44-second GT latch record match the archived GT case. The user-selected files were not independently byte-compared; the archive input SHA-256 values and API digests are retained for comparison.
