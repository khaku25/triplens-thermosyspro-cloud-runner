# TripLens GPT.site → GitHub Main → Vercel Migration Map v1

**Status:** CURRENT MIGRATION BASELINE  
**Date:** 2026-09-18  
**Current UI source:** `https://triplens-agent.junsic25.chatgpt.site/`  
**Current code source of truth:** `khaku25/triplens-thermosyspro-cloud-runner@main`  
**Current main merge:** `9c8545dbcc595c7f80f1e71bf141c7180f32fd86`

---

## 0. Migration rule

The Vercel version must **not** copy the old GPT.site backend semantics as-is.

Use:

> **GPT.site = UX/layout reference**  
> **GitHub main = analysis/data-contract source of truth**  
> **Vercel = new delivery/runtime target**

Therefore, when GPT.site and GitHub main disagree, the latest GitHub `main` analysis contract wins.

---

## 1. Current-state mismatch that must be resolved

### 1.1 Causal-analysis ownership

Current GPT.site demo text says:

> TripLens rule engine determines cause first, then AI adds review.

Current GitHub main now says:

```text
Python = EVIDENCE_PROVIDER_ONLY
decision_authority = GEMINI_AGENT
status_scope = EVIDENCE_READINESS_ONLY
decision_fields_generated_by_python = []
```

**Migration decision:**  
The old GPT.site causal engine behavior is **replaced**.  
Python may provide candidates/evidence only. Gemini selects/interprets causal fields. Verification Gate checks the result.

### 1.2 Event Logic Master count

Current GPT.site drawer shows:

```text
Event Logic Master
구현 94 · 발생 0
```

The current GitHub runtime registry is:

```text
67 enabled runtime EVENT rules
- 54 ALARM
- 13 PROTECTION
```

Operator Actions are present in EVENT handling but are **not** part of the 67 live alarm/protection registry.

**Migration decision:**
- Keep the Logic Master drawer UX.
- Remove the hard-coded `94`.
- Populate counts dynamically from current sources.
- Show separate categories instead of conflating operator actions with live alarm/protection rules.

Recommended UI:

```text
Live Alarm / Protection: 67
Operator Event Types: dynamic / separate
Active Logic Rules: 440
```

Do not preserve `94` as a product invariant.

---

## 2. Screen-by-screen migration map

| Current GPT.site area | Current role | Target Vercel state | Source of truth | Action |
|---|---|---|---|---|
| Header / brand | TripLens identity | Same overall shell | GPT.site UX | KEEP |
| Input Status rail | Dual Log state + event counts | Dynamic run state | EVENT/RAW parser | KEEP + REWIRE |
| DCS EVENT / ECMS EVENT / TRIP counters | Status summary | Compute from uploaded EVENT | EvidenceStore / event parser | KEEP + REWIRE |
| `DUAL LOG = EVENT + RAW` badge | Data-contract explanation | Same | Current V8 contract | KEEP |
| Left 5-tab navigation | Analysis workspace | Same basic navigation | GPT.site UX | KEEP |
| 01 사고 진행 과정 | Combined chronology | Evidence-first timeline | EVENT + RAW + Gemini selected critical events | REWIRE |
| 02 원인 분석 | Old Python-precomputed cause view | Gemini Hybrid Agent causal view | AI Output Contract | REPLACE ENGINE |
| 03 즉시 확인·대응 | Event-based priority checks | Read-only evidence checklist | EVENT + Logic Master | KEEP + REWIRE |
| 04 복구 판단 | Restart approval gate | Recovery **review** state; human approval required | deterministic gate + human | REDEFINE |
| 05 Event 근거 | DCS/ECMS evidence | Evidence explorer with IDs | EVENT/RAW EvidenceStore | KEEP + REWIRE |
| Event Logic Master drawer | 94-rule display | Current dynamic Logic Master | Logic DB / registry | KEEP UI, REPLACE DATA |
| Notion 현황판 | External docs | External link | existing Notion | KEEP |
| 알림발생기 | External synthetic log helper | External link initially | current alarm console | KEEP LINK |
| `/demo` shell | Synthetic demo | Preserve read-only demo | synthetic fixtures | KEEP |
| Demo `AI Agent` tab | Old OpenAI/Luna/Terra review UI | Integrate agent result into 원인 분석 / 검증 상세 | Gemini Hybrid Agent | REPLACE |
| Demo 고장보고서 | Old generated report draft | v2 industrial report | report exporter | REPLACE GENERATOR |
| 가져온 CSV | CSV viewer | Local/read-only file viewer | uploaded files | KEEP |
| 태그 연결 검토 | mapping review | Exact Tag/Logic mapping status | Tag Master / Logic Master | KEEP + REWIRE |
| P&ID·전기·로직 | reference view | Preserve as reference-only | static/reference assets | KEEP |
| 분석 기록·내보내기 | exports | Run ID + Digest + report/CSV export | output contract | KEEP + REWIRE |

---

## 3. Target behavior by main tab

### 3.1 Tab 01 — 사고 진행 과정

**Keep the current UX position and purpose.**

Target data:

```text
Full SOE chronology
+ selected Critical Events
+ RAW process change markers
+ evidence status
```

Rules:

- Full EVENT chronology is never reduced to only AI-selected events.
- Critical Events are a highlighted subset selected by Gemini.
- Clicking an Evidence ID opens EVENT/RAW detail.
- No fixed 5-row chronology limit.

Target component:

```text
<AccidentTimeline />
```

### 3.2 Tab 02 — 원인 분석

This is the largest semantic replacement.

**Do not port the current Python cause generator.**

Target object:

```json
{
  "critical_events": [],
  "primary_cause": {},
  "direct_trigger": {},
  "propagation": [],
  "causal_chain": [],
  "counter_evidence": [],
  "additional_evidence_required": []
}
```

Display priority:

```text
Primary Cause
Direct Trigger
Propagation
Causal Chain
Counter Evidence
Additional Evidence Required
```

Status:

```text
■ 확인 (CONFIRMED)
△ 후보 (CANDIDATE)
○ 관측 (OBSERVED)
— 미확인 (UNKNOWN)
```

Primary Cause defaults to `CANDIDATE`.

Target component:

```text
<CauseAnalysis />
```

### 3.3 Tab 03 — 즉시 확인·대응

Keep the current wording that these are **priority checks, not operator commands**.

Target behavior:

```text
EVENT evidence
+ Logic Master context
+ equipment state observations
→ read-only verification checklist
```

Forbidden:

- automatic equipment commands
- restart command
- valve/breaker operation instruction generated by AI

Target component:

```text
<ImmediateEvidenceChecks />
```

### 3.4 Tab 04 — 복구 판단

Current GPT.site wording implies a restart approval gate.

For Vercel, preserve the tab but make the READ-ONLY boundary explicit.

Recommended target wording:

```text
복구 검토 상태
재기동 조건 확인
담당자 최종 승인 필요
```

The application may show:

```text
Verification Gate: PASS / HOLD
Evidence complete: YES / NO
Outstanding checks
Human approval: REQUIRED
```

It must not automatically issue a restart authorization or control command.

Target component:

```text
<RecoveryReview />
```

### 3.5 Tab 05 — Event 근거

Preserve strongly.

Target evidence record:

```text
Evidence ID
Source
Original tag
Canonical tag
Time
State/value
Mapping status
Logic status
```

Target component:

```text
<EvidenceExplorer />
```

Evidence IDs must be directly reusable by the report layer.

---

## 4. Event Logic Master migration

### Current GPT.site

```text
hard/displayed count: 94
D1 / D2 / OP / PROT families
```

### GitHub main current runtime

```text
config/alarm_registry_v1.csv
67 enabled rows
54 ALARM
13 PROTECTION
```

Current normalized Logic Core also contains approximately:

```text
440 active logic rules
```

### Vercel target

Use a dynamic drawer:

```text
Event Logic Master
├─ Live Alarm / Protection
│  ├─ ALARM 54
│  └─ PROTECTION 13
├─ Operator Events
│  └─ observed EVENT types / separate registry
└─ Logic Core
   └─ active rule lookup
```

No fuzzy Logic Master inference.

Unregistered tags:

```text
미등록 관측 태그
로직 조건식 추론 금지
```

---

## 5. AI migration map

### Remove / deprecate

The following GPT.site demo semantics are stale:

```text
OPENAI RESPONSES API
절약 검토 · Luna
최종 검토 · Terra
AI reviews after rule engine already decides cause
```

### Target

```text
Python evidence/search layer
        ↓
Gemini Agent tool calling
        ↓
structured AI result
        ↓
Python Verification Gate
        ↓
web/report presentation
```

AI model identity should be metadata, not the visual protagonist.

Recommended web metadata:

```text
Analysis Engine: Gemini
Tool Contract: HYBRID_AGENT_EVIDENCE_TOOLS_V1
Verification Gate: PASS / HOLD
Run ID
Data Digest
```

---

## 6. Six Gemini evidence tools

Vercel agent service must bind the current GitHub tools:

```text
search_events()
get_event_window()
get_raw_window()
get_tag_series()
get_logic_context()
get_equipment_state()
```

Current default limits:

```text
max tool calls: 8
search_events: 20 rows
event window: 30 rows
raw window: 8 tags / 50 rows
tag series: 50 points
logic context: 12 rows
equipment state: 10 nearby events
```

The entire historian must never be placed into the Gemini prompt.

---

## 7. Report migration map

### Web Analysis Workspace

Purpose:

```text
explore
drill down
compare
verify evidence
```

### Failure Report

Purpose:

```text
formal document
review
approval
export
```

The two UIs do **not** need to look identical.

They must share the same structured analysis object.

Report sequence:

1. 개요
2. 사고 발생 전 운전 현황
3. 장애 현상
4. 시간대별 조치사항
5. 발생 원인
6. 조치 결과
7. 추정 원인 및 미확인 사항
8. 재발방지 대책 — 검토 권고사항
9. 증거자료

Current draft CSV columns:

```text
구분
항목
내용
상태
근거 ID
관련 태그
기록 시각
비고
```

HOLD behavior:

```text
고장보고서 초안
검증 미완료
no final-confirmed wording
```

---

## 8. Target Vercel repository architecture

Recommended monorepo structure:

```text
triplens-thermosyspro-cloud-runner/
│
├─ apps/
│  └─ web/                         # Next.js UI
│     ├─ app/
│     │  ├─ page.tsx               # main blind workspace
│     │  ├─ demo/page.tsx          # synthetic demo
│     │  └─ report/[runId]/page.tsx
│     ├─ components/
│     │  ├─ TripLensShell.tsx
│     │  ├─ DualLogIntake.tsx
│     │  ├─ AccidentTimeline.tsx
│     │  ├─ CauseAnalysis.tsx
│     │  ├─ ImmediateEvidenceChecks.tsx
│     │  ├─ RecoveryReview.tsx
│     │  ├─ EvidenceExplorer.tsx
│     │  ├─ LogicMasterDrawer.tsx
│     │  └─ FailureReportView.tsx
│     └─ lib/
│        ├─ localCsv.ts
│        └─ contracts.ts
│
├─ services/
│  └─ agent-api/                   # Python / FastAPI on Vercel
│     ├─ app.py
│     ├─ pyproject.toml
│     └─ triplens/
│        ├─ agent_tools.py
│        ├─ dual_log_analyzer.py
│        └─ verification.py
│
├─ webapp/                         # existing JS reference implementation
├─ scripts/                        # current Python source of truth
├─ config/
├─ logic_db/
└─ tests/
```

Vercel currently supports Python ASGI/WSGI runtimes and recommends **Services** when a Python backend and another frontend framework run together in one project.

---

## 9. File upload strategy

Important Vercel constraint:

```text
Vercel Function request/response body limit: 4.5 MB
```

Therefore TripLens must not assume every RAW.csv can be posted directly to one Function request.

### Recommended strategy

**Small dual logs (combined <= safe request threshold):**

```text
browser
→ agent-api analyze request
→ temporary parse
→ Gemini bounded tools
→ structured result
```

**Large RAW.csv:**

```text
browser
→ direct client upload to private Vercel Blob
→ agent-api receives Blob references
→ analysis
→ delete/expire according to retention policy
```

For competition/demo mode, if 100-second RAW stays below the request limit, direct upload may be used initially; the code must still fail clearly when the limit is exceeded.

---

## 10. State and privacy strategy

Vercel functions are request-driven/stateless.

Recommended first version:

```text
Browser retains selected EVENT/RAW locally for evidence drill-down.
Server receives analysis input for one run.
Gemini receives only bounded tool responses.
Server returns structured result + Run ID + Data Digest.
Report is rendered from the returned structured object.
```

Avoid unnecessary permanent historian storage.

If server-side persistence is later required:

```text
private Vercel Blob
+ explicit retention/deletion policy
```

---

## 11. GitHub module reuse map

| GitHub current file | Vercel use |
|---|---|
| `scripts/triplens_agent_tools.py` | Agent API core — reuse |
| `scripts/triplens_dual_log_analyzer.py` | Evidence readiness/candidate layer — reuse, not causal authority |
| `config/triplens_hybrid_agent_v1.json` | Agent policy/config — reuse |
| `docs/triplens_hybrid_agent_prompt.md` | Gemini system/developer prompt basis |
| `webapp/triplens_ai_output_contract.js` | Port to TS/shared contract or reuse UMD initially |
| `webapp/triplens_report_export.js` | Port into report UI/export package |
| `webapp/event_tag_resolver.js` | Evidence/tag display helper |
| `config/alarm_registry_v1.csv` | 67 live alarm/protection rules |
| `logic_db/*` | Logic Master build/source |
| `tests/test_agent_tools.py` | Backend regression |
| `tests/test_ai_output_contract.mjs` | Contract regression |
| `tests/test_report_export.mjs` | Report regression |
| `tests/test_event_tag_resolver.mjs` | Evidence resolver regression |

---

## 12. Source-of-truth hierarchy

When implementing Vercel:

### Highest priority

```text
GitHub main runtime + tested contracts
```

### Second

```text
GPT.site current layout / user flow / visible UX
```

### Third

```text
historical GPT.site business logic
```

Historical GPT.site logic is only reused when it matches the current GitHub contract.

---

## 13. Migration phases

### P0 — Vercel Preview Minimum

- [ ] Create `apps/web` Next.js shell
- [ ] Reproduce header/sidebar/5-tab workspace
- [ ] Reproduce Dual Log Intake
- [ ] Create `services/agent-api`
- [ ] Bind six evidence tools
- [ ] Bind Gemini structured analysis
- [ ] Run Verification Gate
- [ ] Render Cause Analysis from the new contract
- [ ] Render Evidence Explorer
- [ ] Render v2 report
- [ ] Dynamic Logic Master count
- [ ] Preserve READ-ONLY boundary
- [ ] Add run digest/version metadata

### P1 — Demo parity

- [ ] Port `/demo`
- [ ] Preserve synthetic demo warning
- [ ] Port CSV viewer
- [ ] Port tag connection review
- [ ] Port P&ID/electrical/logic references
- [ ] Port analysis record/export
- [ ] Replace old AI Agent tab semantics
- [ ] Connect external Notion / Alarm Console links

### P2 — Production hardening

- [ ] Large-file Blob upload path
- [ ] private retention/deletion policy
- [ ] mobile layout review
- [ ] loading/error states
- [ ] Gemini timeout/retry/fail-closed
- [ ] analysis reuse cache by digest/version
- [ ] Vercel observability
- [ ] compare GPT.site vs Vercel screen-by-screen
- [ ] final production domain switch

---

## 14. Do not migrate

Do **not** move these into Vercel runtime:

```text
OpenModelica simulation executable
OPC UA live control
MATLAB ECMS control UI
plant control write paths
Modelica physical model execution
```

They remain local/Windows V8 simulation infrastructure.

Vercel receives/analyzes the resulting Dual Log evidence.

---

## 15. Acceptance criteria

The Vercel migration is considered functionally equivalent when:

1. The same `EVENT.csv + RAW.csv` can be loaded.
2. Full SOE remains available.
3. Gemini selects Critical Events using bounded tools.
4. Primary Cause / Direct Trigger / Propagation are Gemini judgments, not Python-precomputed answers.
5. Every supported claim has Evidence ID linkage.
6. Unsupported claims fail closed to UNKNOWN.
7. Logic Master lookup never invents unregistered conditions.
8. Verification Gate HOLD cannot display final confirmation.
9. Web Analysis and Report share the same normalized object.
10. Report draft CSV/PDF exports work.
11. GPT.site's five-stage user flow remains recognizable.
12. No OT write/control functionality exists in the web deployment.

---

## 16. Immediate next implementation step

Create a **new Vercel migration branch** without touching the current production GPT.site:

```text
vercel-web-v1
```

First commit should contain only:

```text
apps/web skeleton
services/agent-api skeleton
shared contract wiring
no production deployment
```

Then create a Vercel Preview deployment and compare it side-by-side with the authenticated GPT.site before any production switch.
