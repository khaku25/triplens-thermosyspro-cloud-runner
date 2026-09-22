# Blind Test 2 Production Reports Design

## Goal

Deploy the current Drawing Master and report-layout fixes to the production
TripLens Vercel application, then submit each of the twelve Blind Test 2
`EVENT.csv` and `RAW.csv` pairs through the deployed browser UI and collect
the PDF failure report produced by the site for every scenario.

## Source scenarios

The source set is the twelve numbered Blind Test 2 scenarios:

1. `01_direct_gt`
2. `02_direct_st`
3. `03_gt_breaker`
4. `04_ip_bfp`
5. `05_hp_drum_ll`
6. `06_ip_drum_ll`
7. `07_ip_drum_hh`
8. `08_hp_drum_hh`
9. `09_hp_bfp`
10. `10_lp_bfp`
11. `11_lp_drum_hh`
12. `12_lp_drum_ll`

Each scenario must use its original paired files. Scenario names, expected
causes, prior summaries, prior reports, and answer labels must not be passed
to the analyzer. They may be used only outside the analyzer to name the
collected output file and its Drive folder.

## Required flow

For each scenario, use the production browser UI exactly as an operator would:

1. Select that scenario's `EVENT.csv`.
2. Select that scenario's `RAW.csv`.
3. Wait for input readiness/bootstrap to complete.
4. Start the actual analysis and wait for a terminal result.
5. Confirm the UI rendered the analysis and evidence-backed report controls.
6. Open the site's PDF failure-report view and save the printed PDF.
7. Reset the workspace before loading the next pair so state cannot leak.

## Acceptance criteria

- The deployment commit includes the approved report-grid containment fix and
  Drawing Master work already present on the feature branch.
- Production web and agent API deployments correspond to the same reviewed
  main-branch commit and pass health/smoke checks.
- All twelve source pairs are present, independently hashed, and matched by
  scenario before the first browser run.
- All twelve scenarios reach a terminal analysis state in production.
- A site-produced PDF exists for every scenario; a handcrafted or summary-only
  substitute does not count.
- Each PDF is non-empty, opens successfully, has the expected four-page report
  structure, contains its run-specific evidence, and has no clipped approval
  grid or horizontally overflowing table.
- Existing analysis status is reported honestly. A scenario may be HOLD or
  partially verified; collecting its report must not relabel it PASS.
- The twelve verified PDFs are uploaded into their corresponding scenario
  folders under the existing `5. BLIND TEST` Drive folder, using a new final
  filename so the older second-pass files remain recoverable.
- The technical documentation records the production commit, execution date,
  input hashes, per-scenario outcome, PDF verification, and Drive link.

## Failure behavior

Stop at the first broken boundary in a scenario's browser-to-API-to-report
flow, preserve the browser and response evidence, fix the defect with a
regression test, redeploy through the same main-branch gate, and restart that
scenario from fresh file selection. Do not manufacture a report from prior
markdown or spreadsheet summaries.
