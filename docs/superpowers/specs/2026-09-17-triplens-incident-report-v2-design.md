# TripLens Incident Report v2 Design Specification

**Status:** FIXED BASELINE
**Date:** 2026-09-17
**Figma:** https://www.figma.com/design/j2F3TQql9I15F9760qtWe9?node-id=10-545

## Goal

TripLens should look and behave like an auditable power-plant incident-analysis and failure-reporting tool, not a generic AI dashboard. The visual result should resemble an existing industrial/public-enterprise failure-report process into which EVENT/RAW evidence is automatically populated.

## Scope

- Current baseline: Windows Local V8 TripLens.
- Standard input: `EVENT.csv + RAW.csv`.
- TripLens remains a READ-ONLY accident-analysis layer.
- Preserve existing analysis engine and data contracts where possible.
- Do not modify old v5/v6/v7 apps, V8 Virtual Plant, Modelica, OPC UA, or physical-model logic.

## Design principles

1. **Document First** — the report is the formal output; the web UI is the workspace that creates and reviews it.
2. **Evidence First** — EVENT/RAW, timestamps, tags, Evidence IDs, and verification status are more important than decorative summaries.
3. **Hierarchy over Decoration** — prefer titles, numbering, tables, lines, spacing, and typography over cards, gradients, glow, or marketing visuals.
4. **Human Authority** — AI does not finalize the engineering conclusion; retain 작성/검토/승인 and editable draft fields.
5. **Uncertainty Visible** — `UNKNOWN`, `추가 확인 필요`, and insufficient evidence remain visible instead of being filled with fluent prose.

## Visual rules

- The report must remain usable in monochrome.
- Report tables and sections use square or nearly square corners (0–2 px).
- Large rounded cards, glow, glass, gradients, emoji headings, decorative AI branding, and oversized AI-confidence visuals are not allowed in the report layer.
- Status color is a secondary cue only; the textual/symbolic state must remain explicit.

Status notation:

- `■ 확인 (CONFIRMED)`
- `△ 후보 (CANDIDATE)`
- `○ 관측 (OBSERVED)`
- `— 미확인 (UNKNOWN)`

## Report structure

1. 개요
2. 사고 발생 전 운전 현황
3. 장애 현상
4. 시간대별 조치사항
5. 발생 원인
6. 조치 결과
7. 추정 원인 및 미확인 사항
8. 재발방지 대책
9. 증거자료

Analysis-field mapping:

- Primary Cause → `발생 원인 > 선행 원인`
- Direct Trigger → `발생 원인 > 직접 Trip 원인`
- Propagation → `발생 원인 > 파급 과정`
- Causal Chain → chronological evidence table first, concise summary second

## Chronological EVENT/RAW rule

There is no arbitrary five-item limit.

- Full SOE is variable length and may contain every relevant EVENT/RAW row.
- Critical Events are a subset of the full SOE.
- Web: vertical scroll / expansion.
- A4/PDF: auto-continue into `4. 시간대별 조치사항 (계속)` pages.
- CSV: preserve all applicable rows.

## Evidence rules

Every cause or engineering claim must link to at least one Evidence ID.

Required presentation fields:

- status
- description / claim
- Evidence ID
- related tags
- recorded time
- source
- Logic Master verification
- AI confidence as separate metadata

Evidence IDs in the web UI must open the corresponding EVENT/RAW detail.

## Tag rules

Show both friendly label and raw tag.

Example:

- Display: `GT Trip 명령`
- Raw: `raw__vpp52_gttrip_cmd`
- Source: `RAW Historian`

If not registered in Logic Master, display:

- `미등록 관측 태그`
- `로직 조건식 추론 금지`

Do not invent tag meaning or infer unregistered logic conditions.

## AI / verification rules

AI confidence and engineering verification are separate concepts.

Example:

- AI Confidence: `0.91`
- Engineering Status: `CANDIDATE`
- Logic Master: `NOT VERIFIED`

If `Verification Gate = HOLD`:

- display `검증 미완료`
- draft export remains allowed
- do not use `최종 확정` or `Root Cause Confirmed`
- report remains `고장보고서 초안`

## Web workspace requirements

- Keep the existing EVENT/RAW contract and Gemini result structure where practical.
- Add an editable report-draft layer instead of mutating immutable source evidence.
- Evidence ID opens EVENT/RAW detail.
- Tag detail has an explicit `대시보드로 돌아가기` control.
- Reuse analysis when EVENT digest + RAW digest + Logic Master version + Gemini Tool version + prompt version + scenario selection are unchanged.
- Show Analysis Run ID and Data Digest.

## CSV requirements

Button label: `고장보고서 초안 CSV`

Columns:

`구분,항목,내용,상태,근거 ID,관련 태그,기록 시각,비고`

Sections include:

- 개요
- 운전 현황
- 장애 현상
- 시간대별 조치사항
- Critical Events
- Primary Cause
- Direct Trigger
- Propagation
- Causal Chain
- 조치 결과
- 반대 근거
- 추가 확인 필요
- 재발방지 대책

EVENT/RAW source files remain immutable.

## Acceptance criteria

- Removing AI/model branding still leaves a recognizable industrial incident-analysis system.
- Direct Trigger, Primary Cause, Propagation, and evidence can be found quickly.
- Cause claims are traceable to Evidence IDs.
- Raw tags remain visible beside friendly names.
- Time-ordered evidence can exceed five items without truncation.
- The report prints clearly in monochrome.
- AI confidence and engineering verification are visually separate.
- Human review/editing remains possible.
- `Verification Gate = HOLD` prevents final-confirmed wording.

## Canonical motto

**Evidence before decoration. Engineering status before AI confidence. Human review before final confirmation.**
