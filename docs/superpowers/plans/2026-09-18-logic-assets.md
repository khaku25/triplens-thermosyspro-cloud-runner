# TripLens Logic Assets Implementation Plan

> Execute inline using executing-plans. The user approved implementation in this conversation.

**Goal:** A single update regenerates the master-derived draw.io repository and web tag/logic detail without altering plant control logic.
**Architecture:** 06/07 → validated model → draw.io preserving stable-ID geometry → index and derived views → first-party web viewer and packaged API data.
**Tech Stack:** Python standard library, draw.io XML, browser JavaScript/SVG, existing Next.js route, GitHub Actions and PowerShell.
**Spec:** docs/superpowers/specs/2026-09-18-logic-assets-design.md

## Global constraints
- No physical/runtime OPC UA writes or Modelica changes.
- Source text and behavioural status retained, live existence never promoted to functional correctness.
- No guessed node names or links. No Scenario Lab-only rule inputs.
- The previous release stays intact if any validation fails.

## Tasks
- [ ] 1. Source import / validation: tests cover 603-tag census set, 53 rules, unknown/duplicate IDs, declared derived outputs, formula/cache rejection and exact input groups. Run `python -m unittest discover -s tests -p 'test_logic_assets.py'` before implementation and observe RED.
- [ ] 2. XML repository / layout merge: tests alter threshold, description, node geometry and edge route, then regenerate and assert stable identity, changed semantic content, preserved geometry, compressed input support and failed build leaves release unchanged.
- [ ] 3. Derived assets / runtime: emit links, ports/blocks/edges, equipment/input groups, runtime CSV and matching manifest hashes; tests confirm no invented source output and no fake numeric timer for runtime text.
- [ ] 4. Web viewer: exact tag/rule search, click-through, inherited status, XML parser/geometry bounds and integrity failure. Test in Chromium at desktop/mobile sizes, not only XML parsing.
- [ ] 5. One-command orchestration: PowerShell plus manual GitHub workflow, staged build, Drive import and optional credentialled output upload. Run actual masters twice and compare digests.
- [ ] 6. Integration / publication: PR, CI test/build logs, authorised Drive artefacts, deployment check. Report each destination separately and do not report a blocked deployment as live.
