# Drawing Master restoration on the current TripLens baseline

Base: `0a57ecfeea8b34f1328a2df6b6e825aae562d055`.
Restored implementation reference: `53b7c8d0b4ccf9058b583d00073bbb740093e472`.

## Scope

A read-only location index of the existing `TripLens_Logic_Master_Current_V8.drawio`.
The Tag Master, Logic Master, model, OPC UA inputs, Agent API and operator report
are unchanged. This is not a plant P&ID repository or an interactive co-simulation
controller. An indexed location does not prove engineering or physical correctness.

The current source contains 98 pages and 1,551 indexed objects, with 53 distinct
logic IDs and 86 distinct tag IDs appearing in the drawing. The Tag Master still
contains 603 source tags: this must not be reported as 603 tags all drawn.
Numbers are calculated from the source and are not enforced as permanent limits.

## Usage

Open the existing Logic / TAG Master dialog, then select **Drawing Master**.
Search by source tag, canonical tag, rule ID, page name or cell ID.
Tag and Rule inspectors also offer **도면 위치 보기**, which opens matching locations.
Selecting a result opens its exact page and highlights only that object. On mobile,
the selected object is magnified and centered instead of fitting all text too small.

Each result retains the source file, page, cell and source XML SHA-256.
The **이 도면 위치 열기** link addresses the same viewer with `#drawing=<encoded source_ref>`.
A bare cell ID present on multiple pages is rejected instead of choosing the first.
Unknown references and mismatching index/XML identities never create guessed links.

Search initially renders 100 Drawing Master results. **검색 결과 더 보기** exposes
additional results without discarding the full index.

## Regeneration

Run the existing `python scripts/update_triplens_logic.py` command. The index is
published to `generated/logic/`, `logic_diagrams/`, and `apps/web/public/logic-assets/`.
The same payload is embedded in the offline viewer and covered by the asset manifest.
`python scripts/update_triplens_logic.py --check` verifies byte consistency.
The source draw.io and existing logic index retain their original bytes.

## Verification and known baseline failures

Run the existing `test_logic_*.py` suite and the new `test_drawing_master*.py` suite.
The latter covers exact references, all-object coverage, publication, hash mismatch,
missing or forged index rejection, bounded search, mobile readability, keyboard
selection, and deep-link/back navigation. Tests execute a real Chromium browser,
not Gemini, plant controls or paid browser automation.

The broad Node suite (`node --test tests/test*.mjs`) at the starting baseline has
101 passes and four failures. The restored branch has the same four failures:

- `operator phrase converts polite AI prose into concise report style`
- `screen 04 uses a fixed GT BOP HRSG ST permissive frame`
- `operator summaries remove raw field names and source tags from core trip events`
- `overflow analysis items and extra evidence tags stay available in disclosures`

These are retained and reported, not rewritten as part of Drawing Master. CI compares
baseline and restored failure names and publishes both logs. A green comparison means
**no additional Node failures**, not that the full Node suite is green.

Local Chromium in the ChatGPT container permits offline HTML but blocks HTTP navigation;
the dedicated GitHub Actions browser checks exercise the HTTP deep links as well.
Production main remains separate until this feature is explicitly promoted.

## Preview deployment request

This branch is intentionally kept separate from production `main`. A branch-only push may be used to request a Vercel Preview deployment for manual phone/browser validation. Production aliases must not be changed by this step.
