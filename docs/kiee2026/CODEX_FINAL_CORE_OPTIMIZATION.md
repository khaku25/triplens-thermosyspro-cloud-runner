# TripLens — Codex Final Core Optimization

> 목적: 남은 Codex 사용량을 UI가 아니라 TripLens 핵심 분석 구조에 집중한다.
>
> **중요:** 현재 Source of Truth는 Windows Local 최신 TripLens 웹앱/Runtime이다. 과거 GitHub v5/v6/v7 웹앱을 현재 구현으로 간주하지 말고, Codex가 실제로 열고 있는 최신 로컬 웹앱에서만 작업한다. V8 Virtual Plant/OPC UA/물리모델은 수정하지 않는다.

## 작업 범위

이번 1회 작업에서 아래 4가지만 최소 diff로 최적화한다.

1. Gemini Tool 호출 구조
2. 대량 EVENT 처리
3. Evidence Policy 실제 필터
4. 분석 Pipeline 역할 분리

새 기능 확장, UI 전면개편, 물리모델 변경, 태그 rename, CSV 포맷 변경은 하지 않는다.

---

## 1. 목표 Architecture

```text
EVENT.csv 전체 발생 Event Stream
+ RAW.csv 전체 Historian/Logic/State
        ↓
Parser / Validation / Time Alignment
        ↓
Evidence Policy
        ↓
Searchable Evidence Store
        ↓
Gemini Agent Tool Loop
        ↓
AI-generated
- Critical Events
- Primary Cause / Cause Candidate
- Direct Trigger
- Propagation
- Causal Chain
- Missing Evidence
- Recovery Check
        ↓
Deterministic Verification Gate
        ↓
Dashboard / Result CSV·JSON
```

### 절대 원칙

- Engineering Layer가 최종 Causal Chain을 미리 만들지 않는다.
- Logic Master는 Tag/설비/Logic 의미와 **가능한 관계**만 제공한다.
- Gemini가 이번 사고에서 실제 Critical Event와 Causal Chain을 생성한다.
- Verification은 AI Chain을 대신 생성하지 않고, 각 주장/edge의 Evidence 유무와 시간 모순을 검사한다.
- `EVENT.csv`는 분석 전에 핵심 몇 건으로 잘라내지 않는다. 원본 전체 Event Stream은 보존한다.

---

## 2. Gemini Tool 구조

현재 Gemini 호출을 확인하고, 가능하면 한 번의 거대 prompt 대신 Evidence 탐색 Tool Loop로 바꾼다.

최소 Tool interface는 기존 코드/스택에 맞춰 아래 의미를 제공한다. 함수명은 기존 naming을 우선한다.

```text
get_event_stats()
search_events(query/filter, limit, cursor)
get_event_window(start, end, systems?, limit, cursor)
get_raw_window(tags, start, end, step/limit)
get_tag_series(tag, start, end)
get_logic_context(tags/events)
get_equipment_state(asset, time/window)
get_related_events(event_id, before_s, after_s)
```

### Tool 요구사항

- 모든 반환 Evidence에 stable reference를 붙인다.
  - EVENT: event_id 또는 원본 row reference
  - RAW: tag + timestamp/model_time + row/sample reference
- pagination/limit를 둬 수백~수천 EVENT를 한 번에 prompt에 넣지 않는다.
- Tool 결과는 Evidence Policy를 반드시 통과한 뒤 Gemini에 전달한다.
- Gemini는 필요한 만큼 Tool을 호출해 원인/인과를 구성한다.
- scenario별 hard-coded answer branch를 만들지 않는다.

---

## 3. 대량 EVENT 처리

### 데이터 보존

`All Events`에는 원본 EVENT의 모든 정상 발생 record를 유지한다.

분석용 내부 index에서는 다음 최적화를 허용한다.

- timestamp sort/index
- system/source index
- asset/tag index
- alarm severity/category index
- ACTIVE/RETURN pairing
- exact duplicate 탐지
- near-duplicate clustering

단, 원본 row를 삭제하지 말고 provenance를 유지한다.

### Gemini에 처음 제공할 내용

전체 EVENT 본문이 아니라 compact inventory를 먼저 제공한다.

예:

```json
{
  "event_count": 347,
  "time_range": ["T+0.0", "T+42.8"],
  "systems": {"DCS1": 211, "DCS2": 104, "ECMS": 32},
  "categories": {"alarm": 290, "protection": 18, "state": 31, "operator": 8},
  "first_events": ["references only"],
  "trip_related_count": 12
}
```

그 후 Gemini가 Tool로 필요한 구간을 탐색한다.

### Critical Event

Critical Event 선정은 최종적으로 Agent output이어야 한다.

Engineering Layer는 candidate retrieval/ranking hint는 줄 수 있지만 `Origin`, `Direct Trigger`, `Propagation`을 정답으로 확정하지 않는다.

---

## 4. Evidence Policy

### 허용 Evidence

현장 운전/보호계층에서 관측 가능한 성격의 값은 허용한다.

- Process measurement
- Alarm / EVENT
- Protection condition
- Trip request
- Trip latch
- Breaker state/feedback
- Equipment running/energized state
- Operator action
- Runtime logic state

`vppCause*` 같은 태그도 실제 Runtime Protection Condition을 나타내고 0→1로 동작하는 관측 Logic bit라면 **이름만으로 차단하지 않는다**.

### 금지 Evidence

시뮬레이터가 사고를 만들기 위해 사용하는 내부 시험정보만 차단한다.

최소 deny pattern:

```text
scenario_id
expected_root_cause
expected_cause
ground_truth
answer_label
*FaultInjector*
*FaultSource*
*FaultFlowCommand*
*FaultEnthalpyCommand*
```

실제 코드에 존재하는 동등한 simulator-only metadata도 동일 원칙으로 추가한다.

### 구현 위치

Prompt 규칙만으로 끝내지 않는다.

```text
RAW/EVENT Store
   ↓
Evidence Policy Filter
   ↓
Gemini Tool response
```

즉 Gemini Tool 반환 직전에 programmatic deny가 적용되어야 한다.

가능하면 blocked evidence 접근 시:

```json
{"status":"BLOCKED_BY_EVIDENCE_POLICY","reason":"SIMULATION_ONLY_METADATA"}
```

를 남기고 audit count를 기록한다.

---

## 5. Gemini Agent Output Contract

가능하면 최종 Gemini 결과를 구조화 JSON으로 고정한다.

```json
{
  "incident_summary": "...",
  "primary_cause": {
    "label": "...",
    "status": "SUPPORTED|CANDIDATE|INCONCLUSIVE",
    "confidence": 0.0,
    "evidence_refs": []
  },
  "critical_events": [
    {
      "event_ref": "...",
      "role": "ORIGIN|DIRECT_TRIGGER|PROTECTION|PROPAGATION|SECONDARY|OPERATOR|RECOVERY",
      "reason": "..."
    }
  ],
  "causal_chain": [
    {
      "from_ref": "...",
      "to_ref": "...",
      "relation": "...",
      "evidence_refs": [],
      "confidence": 0.0
    }
  ],
  "missing_evidence": [],
  "affected_equipment": [],
  "recovery_checks": []
}
```

중요:
- `causal_chain`은 Agent가 생성한다.
- 각 chain edge에 Evidence reference가 있어야 한다.
- 근거가 부족하면 `INCONCLUSIVE` 허용.
- 반드시 원인 하나를 억지로 확정하지 않는다.

---

## 6. Verification Gate

Deterministic verification은 최소 아래를 검사한다.

1. Gemini가 반환한 모든 `evidence_refs`가 실제 입력에 존재하는가
2. blocked simulator-only evidence가 결과 근거에 사용되지 않았는가
3. causal edge의 시간방향이 명백하게 역전되지 않았는가
4. Critical Event가 실제 EVENT reference 또는 명시적인 RAW evidence를 갖는가
5. 근거 없는 핵심 공학 주장을 unsupported로 표시하는가

검증 실패 시 AI 결과를 조용히 수정하지 말고 상태를 내린다.

```text
SUPPORTED
PARTIAL
INCONCLUSIVE
REVIEW_REQUIRED
```

---

## 7. 기존 기능 보존

회귀 금지:

- EVENT.csv + RAW.csv Dual Log intake
- 모바일 Dashboard
- Logic Master 조회/복귀
- Gemini 분석 실행
- EVENT Evidence / RAW Evidence 표시
- 결과 CSV/JSON Export가 현재 있다면 유지
- 기존 성공 테스트 유지

특히 `DUAL_LOG_ANALYSIS_CONTRACT_REQUIRED` 같은 계약오류가 이미 해결된 최신 로컬판이라면 다시 만들지 않는다.

---

## 8. 테스트

새 테스트는 최소한으로 추가한다.

### A. Evidence Policy
- `vppCauseLPDrumLL` 같은 Runtime Protection bit → ALLOW
- `...FaultInjector...` → BLOCK
- `scenario_id`, `ground_truth` → BLOCK

### B. Large EVENT
- 300~500 synthetic events 입력
- 전체 Event count 보존
- Tool pagination 정상
- Gemini request에 전체 raw 500줄을 그대로 직렬화하지 않음

### C. Causal Ownership
- Engineering Layer output에 완성된 정답 causal chain이 없음
- Gemini structured result에 `causal_chain` 존재
- 각 edge가 evidence refs를 가짐

### D. Fail-Closed
- 핵심 Evidence 제거 시 원인 강제확정 대신 `INCONCLUSIVE` 또는 `REVIEW_REQUIRED`

기존 전체 regression이 있다면 마지막에 1회만 실행한다.

---

## 9. 작업 순서 — 토큰 절약용

1. 현재 최신 로컬 웹앱의 Gemini 호출/분석 entrypoint만 찾는다.
2. 관련 파일 3~6개만 읽는다. 저장소 전체 리팩터링 금지.
3. 현재 구조를 최대한 유지한 최소 diff로 위 4개 항목을 구현한다.
4. focused tests 실행.
5. 기존 regression 1회 실행.
6. 변경 파일/테스트결과/남은 위험만 짧게 보고하고 종료한다.

### STOP 조건

- 현재 열려 있는 workspace가 최신 Local TripLens 웹앱이 아니면 **수정하지 말고 즉시 중단**하고 정확한 경로만 요구한다.
- 과거 v5/v6/v7 HTML을 최신 구현 대신 수정하지 않는다.
- V8 Virtual Plant/Modelica/OPC UA 물리코드는 수정하지 않는다.

---

## 완료 기준

다음 6개가 모두 만족되면 작업 종료한다.

- [ ] 수백 EVENT 원본이 보존되고 검색형 Tool 접근 가능
- [ ] Gemini가 Tool을 이용해 Critical Event를 선정
- [ ] Gemini가 Causal Chain을 직접 생성
- [ ] Simulator-only fault injection metadata는 programmatic filter로 차단
- [ ] Runtime Protection condition/logic bit는 허용
- [ ] 기존 Dual Log/Gemini/UI 회귀 없음
