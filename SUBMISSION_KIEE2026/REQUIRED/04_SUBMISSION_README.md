# TripLens — Submission README

## 한 문장 정의

**TripLens는 발전소 사고 직후의 EVENT와 RAW 시계열을 근거 저장소로 사용하고, Gemini Agent가 Evidence Tool을 통해 필요한 근거를 탐색하여 핵심 사건·원인 후보·직접 보호동작·파급·Causal Chain을 재구성하는 READ-ONLY 사고분석 시스템이다.**

## 핵심 입력

- `EVENT.csv`: Alarm / Protection / Operator Action / 상태변화 Event
- `RAW.csv`: Historian / Process / Command / Logic / Equipment State Evidence

## 실제 Agentic AI 동작

Gemini는 다음 6종의 Evidence Tool 중 필요한 것을 선택해 사용한다.

- `search_events()`
- `get_event_window()`
- `get_raw_window()`
- `get_tag_series()`
- `get_logic_context()`
- `get_equipment_state()`

Python은 입력·시간·세션·매핑·Tool 실행·Trace·검사를 담당하고 최종 원인을 미리 지정하지 않는다.

## 핵심 출력

- All Events
- Critical Events
- Primary Cause / Candidate
- Direct Trigger
- Propagation
- Causal Chain
- Counter Evidence / Additional Evidence Required
- Evidence IDs
- Affected Equipment / Operator Checks
- Failure Report

## 검증 현황

- 12개 distinct synthetic incident scenarios 실제 사이트 분석
- 재검증 포함 누적 분석 실행 21회(프로젝트 실행기록 기준)
- 각 시나리오 A01~A20 동일 20개 Engineering Inspection
- 12개 사이트 실분석 최종 고장상보 생성
- 9/21 내부 종합평가 평균 88.0/100
  - **주의: AI 정확도가 아니라 입력·인과·근거·운전대응·산출물을 합친 내부 점수**
- HP BFP RAW 결측 사례에서 후보/미검증 상태 유지

## 안전·검증 경계

- READ-ONLY
- OT Write 없음
- 자동복전·Breaker 자동조작 없음
- Scenario ID / Expected Cause / Ground Truth / Answer Label을 Agent Evidence에 제공하지 않음
- 정확히 관측되지 않은 Edge 시각은 표본구간으로 유지
- 근거 부족 시 UNKNOWN / HOLD 허용
- Gate PASS는 사람의 최종 공학 승인과 다름

## 일반화 범위

현재 검증은 **동일 Current V8 합성 복합화력 환경 안의 여러 사고유형**에 대한 반복 검증이다.

아직 주장하지 않는 것:
- 실제 발전소 현장 정확도
- 모든 발전소/모든 제조사 즉시 호환
- Field Pilot / Production 수준 성능
- MTTR 감소율

## 남은 제출 확인

- [ ] 발표자료가 12 scenarios / 21 executions / Fail-Closed 사례를 정확히 반영
- [ ] 88.0/100을 AI 정확도로 오표기하지 않음
- [ ] CSV/PINPOINT export, 모바일 전체 Acceptance 등 미완료 기능을 완료로 표시하지 않음
- [ ] Technical Report / Architecture / Validation / PPT의 용어와 수치 동기화
- [ ] 최종 ZIP clean-folder 검증
