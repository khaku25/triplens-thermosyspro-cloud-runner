# TripLens Industrial Incident Design Standard v1.0

**Status:** FIXED BASELINE

## Design objective

TripLens must look and behave like a real industrial incident-analysis and failure-reporting tool, not a generic AI dashboard.

> 기존 발전소 고장보고서를 사람이 작성하던 과정에 TripLens가 EVENT·RAW 근거를 자동으로 채워 넣은 것처럼 보여야 한다.

## Governing principles

- **Document First** — formal report first, web workspace second.
- **Evidence First** — EVENT/RAW, timestamp, tag, Evidence ID, and verification status take precedence over decorative summaries.
- **Hierarchy over Decoration** — use headings, numbering, tables, rules, spacing, and font weight before cards, color, shadows, or graphics.
- **Human Authority** — AI does not finalize the engineering conclusion; 작성/검토/승인 remain visible.
- **Uncertainty Visible** — keep UNKNOWN and insufficient-evidence states visible.

## Visual rules

- Report must work in monochrome.
- Report sections/tables: square or 0–2 px radius.
- Web inputs/buttons: max 4–6 px radius.
- Large rounded cards: avoid.
- Shadows in report: avoid.
- Glow: forbidden.
- Gradient: forbidden.
- Glassmorphism: forbidden.
- Emoji headings: forbidden.
- Decorative icons: minimize.

## Status notation

- `■ 확인 (CONFIRMED)`
- `△ 후보 (CANDIDATE)`
- `○ 관측 (OBSERVED)`
- `— 미확인 (UNKNOWN)`

Never rely on color alone.

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

## Chronology rule

Time-ordered EVENT/RAW evidence has no arbitrary five-item limit.

- Full SOE: variable length.
- Critical Events: subset of SOE.
- Web: vertical scroll/expand.
- A4/PDF: `시간대별 조치사항 (계속)` continuation pages.
- CSV: preserve all applicable rows.

## Evidence rules

- A cause/engineering claim must have an Evidence ID.
- Show source, related tag, timestamp, and Logic Master verification.
- Evidence ID opens source detail in the web UI.

## Tag rules

Show both friendly and raw tag names.

Example:

- `GT Trip 명령`
- `raw__vpp52_gttrip_cmd`
- `Source: RAW Historian`

If Logic Master has no registration:

- `미등록 관측 태그`
- `로직 조건식 추론 금지`

Do not infer an unregistered logic condition.

## AI presence rules

Avoid marketing labels such as `Gemini Insight`, `AI Smart Analysis`, `AI-Powered Root Cause`, or large confidence gauges.

Prefer:

- 분석 결과
- 자동 분석 결과
- 분석 실행 정보
- 검증 상태

Model identity belongs in metadata: `Analysis Engine: Gemini`.

## Verification rules

AI confidence and engineering verification are separate.

If `Verification Gate = HOLD`:

- display `검증 미완료`
- allow draft export
- forbid `최종 확정` / `Root Cause Confirmed`
- keep output labeled `고장보고서 초안`

## Human review

Required concepts:

- 작성
- 검토
- 승인
- 담당자 수정
- 검토 의견
- 최종 판단

AI-generated report content remains editable.

## Safety and trust

- TripLens is a READ-ONLY accident-analysis layer.
- Do not show AI equipment-operation commands.
- Do not invent tags.
- Do not use scenario answer/fault-injection metadata as operational evidence.
- Do not show a cause candidate without Evidence ID.
- Evidence Policy failure data must not be promoted to Gemini input.
- UNKNOWN stays UNKNOWN when evidence is insufficient.
- Human reviewers finalize the report.
- Verification HOLD blocks final-confirmed wording.
- EVENT/RAW originals remain immutable.

## Acceptance test

A design passes only if:

- removing AI branding still leaves an industrial incident-analysis system,
- incident time / Direct Trigger / Primary Cause / Propagation / evidence are easy to find,
- claims are traceable to Evidence IDs,
- raw tags remain visible,
- uncertainty remains visible,
- AI confidence and engineering verification are separate,
- human review/editing is supported,
- chronology can exceed five items without truncation,
- monochrome print remains clear,
- Verification HOLD prevents final-confirmed wording.

## Motto

**Evidence before decoration. Engineering status before AI confidence. Human review before final confirmation.**
