# TripLens 기술보고서
## 발전소 EVENT + RAW 기반 Evidence-grounded Agentic AI 사고분석 시스템
### KIEE 2026 Agentic AI 경진대회 — Current Validation Baseline

## 1. 문제 정의

발전소 Trip 또는 주요 설비고장 발생 시 DCS, ECMS, Historian, Protection 계층에서 다수의 Alarm, Event, 상태변화, 공정값 변동이 짧은 시간에 집중된다. 운전원은 이 가운데 **최초 사건, 직접 보호동작, 후속 파급, 영향설비, 다음 확인사항**을 빠르게 구분해야 한다.

TripLens는 이 사고 초기 정보정리 구간을 지원하기 위한 **READ-ONLY Agentic AI 사고분석 시스템**이다.

TripLens의 목표는 사람이 미리 정리한 몇 개 Event를 AI가 다시 요약하는 것이 아니다. `EVENT.csv`의 사고 Event Stream과 `RAW.csv`의 시계열 Evidence를 함께 사용하고, Gemini Agent가 필요한 근거를 Tool로 조회하여 Critical Event, 원인 후보, Direct Trigger, Propagation, Causal Chain을 구성한다.

## 2. 핵심 가치

TripLens는 다음 질문에 답하도록 설계했다.

1. 사고 중 발생한 Event 가운데 핵심 사건은 무엇인가?
2. 선행 원인 후보와 직접 보호동작, 후속 파급을 어떻게 구분하는가?
3. EVENT의 사건이 RAW 값·상태변화와 일치하는가?
4. 어떤 Evidence가 각 인과 주장을 지지하거나 반박하는가?
5. 근거가 부족하면 어디까지 판단을 보류해야 하는가?
6. 운전원이 다음으로 확인해야 할 설비·Tag·Logic은 무엇인가?

TripLens는 기존 DCS/ECMS/Historian을 대체하지 않고, 기존 기록 위에 사고 초기 의사결정을 위한 분석 계층을 추가한다.

## 3. 입력 데이터

### 3.1 EVENT.csv

- Alarm / Return
- Protection Event
- Breaker / Equipment State Change
- Operator Action
- System Event

EVENT는 원인 정답을 제공하기 위해 사전 압축한 입력이 아니라 사고 중 기록된 Event Stream이다.

### 3.2 RAW.csv

- Pressure / Temperature / Flow / Level
- Speed / Power
- Command / Trip Request
- Latch / Logic State
- Breaker / Motor / Valve State
- Quality / model time

EVENT만으로 결론을 내리지 않고, 관련 RAW 시간창과 Tag series를 함께 조회한다.

### 3.3 Data Contract

- EVENT와 RAW의 `session_id / incident_id` 일치
- 인과 정렬 기준은 `model_time_s`
- `wall_time_utc`는 감사·전송용
- RAW Evidence는 원본 행과 Tag를 역참조할 수 있는 ID 유지
- 미등록 Tag를 유사 Tag로 fuzzy substitution하지 않음
- 원본 EVENT/RAW는 분석·보고서 편집 때문에 수정하지 않음

## 4. 분석 파이프라인

```text
EVENT.csv + RAW.csv
        ↓
Input / Session / Time Validation
        ↓
Evidence Store
        ↓
6 Evidence Tools
        ↓
Gemini Agent
  - Critical Event selection
  - Primary Cause / Candidate
  - Direct Trigger
  - Propagation
  - Causal Chain
  - Counter Evidence
  - Additional Evidence Required
        ↓
Citation Check / Verification Gate
        ↓
Dashboard / Evidence Navigation / Failure Report
```

## 5. Agentic AI와 Tool Calling

현재 Evidence Tool은 다음 6종이다.

- `search_events()`
- `get_event_window()`
- `get_raw_window()`
- `get_tag_series()`
- `get_logic_context()`
- `get_equipment_state()`

Gemini는 전체 Historian을 초기 Prompt로 한 번에 받는 것이 아니라, 필요한 근거를 제한된 Tool Call로 조회한다.

Engineering Layer는 최종 원인이나 Causal Chain을 사전결정하지 않는다.

```text
Python / Engineering Layer
= validation / alignment / exact mapping / retrieval / trace / guard

Gemini
= evidence selection / comparison / causal judgment

Verification Gate
= evidence/tag/format/timing compliance

Human
= final engineering approval
```

## 6. Evidence Policy와 Blind 경계

실제 운전·보호계층에서 관측 가능한 정보는 Evidence로 사용할 수 있다.

허용 예:
- Process measurement
- Alarm/Event
- Protection condition
- Trip request/latch
- Breaker/Equipment state
- Operator action
- Runtime logic state

Agent 판단에서 제외:
- Scenario ID / Name
- Expected Cause
- Ground Truth / Answer Label
- 시뮬레이터 시험자만 아는 Fault Injection 내부 metadata

Blind Validation은 현장관측 정보를 숨기는 시험이 아니라 **시험자가 미리 알고 있는 정답성 정보만 Agent에서 분리하는 시험**이다.

## 7. 시간과 인과 판단

TripLens는 단순히 시간순으로 정렬된 모든 Event를 인과관계로 확정하지 않는다.

- RAW 0→1 변화가 두 표본 사이에서 발생하면 정확한 단일 시각 대신 관측구간으로 유지
- 동일 입력에 의한 병렬 GT/ST 동작과 GT→ST intertrip을 구분
- 후속 Alarm을 근본원인으로 자동 승격하지 않음
- Logic Master의 등록관계와 실제 Incident causality를 구분

## 8. Verification / Fail-Closed

Verification은 Agent가 생성한 분석을 대신 만드는 계층이 아니다.

검사:
- 인용된 Evidence ID가 실제 조회결과에 존재하는가
- Claim과 관련 Tag가 연결되는가
- 구조화 출력이 계약을 만족하는가
- 명백한 시간관계 모순이 있는가
- 금지된 정답 Metadata를 사용했는가

Claim 상태와 Gate 상태를 구분한다.

```text
Claim: OBSERVED / CANDIDATE / UNKNOWN
Gate: PASS / HOLD
Reviewer: REVIEW_REQUIRED 등 별도
Human: 최종 공학 승인
```

근거 부족 시 반드시 하나의 원인을 확정하도록 강제하지 않는다.

## 9. Evidence Navigation

분석결과의 Evidence를 클릭해 원본 EVENT/RAW를 확인하고, 관련 Tag → Logic → Drawing/Equipment로 이동한 뒤 분석 화면으로 복귀할 수 있도록 연결한다.

이는 AI의 문장을 최종 정답으로 숨기지 않고 엔지니어가 원본 근거까지 역추적하기 위한 기능이다.

## 10. 현재 반복 검증

### 10.1 시나리오

동일 V8 합성환경에서 12개 distinct 사고 시나리오의 실제 사이트 분석과 최종 고장상보가 존재한다.

| # | Scenario |
|---:|---|
| 1 | Direct GT Trip |
| 2 | Direct ST Trip |
| 3 | GT Breaker |
| 4 | IP BFP |
| 5 | HP Drum LL |
| 6 | IP Drum LL |
| 7 | IP Drum HH |
| 8 | HP Drum HH |
| 9 | HP BFP |
| 10 | LP BFP |
| 11 | LP Drum HH |
| 12 | LP Drum LL |

재검증을 포함한 누적 분석 실행은 21회(프로젝트 실행기록 기준)이다.

### 10.2 평가방식

각 시나리오는 동일한 A01~A20, 총 20개 Engineering Inspection 항목으로 검사한다.

| 영역 | 배점 |
|---|---:|
| 입력·데이터 | 10 |
| 사건·원인 인식 | 15 |
| 보호·파급 인과 | 30 |
| 근거·추적성 | 20 |
| 운전 대응 | 15 |
| 산출물 | 10 |

9/21 전수검사 요약표의 12개 시나리오 내부 종합평가 평균은 **88.0/100**이다.

중요: 이 값은 **AI 원인분석 정확도 88%가 아니다.** 입력·인과·근거·운전대응·산출물을 합친 내부 Engineering Inspection Score다. 이후 재검증과 최종 PDF 생성이 추가되었기 때문에 당시 집계 기준선으로 사용한다.

### 10.3 Fail-Closed 사례

HP BFP 사례에서는 RAW 결측 때문에 사고 개시시각과 일부 Latch/보호연쇄를 직접 확인할 수 없었다. TripLens는 이를 성공으로 덮지 않고 RED / YELLOW / NOT TESTED와 후보 상태를 유지했다.

이 사례는 데이터가 불완전할 때 부당한 확정을 피하는 Fail-Closed 동작의 대표 사례다.

## 11. 현재 산출물

- 12개 시나리오 사이트 실분석 결과
- 12개 최종 고장상보 PDF
- EVENT/RAW Evidence ID 연결
- Tag/Logic/Drawing 탐색
- 원인/직접 보호동작/파급 분리
- 추가 확인사항 및 운전원 확인항목

웹 UI의 CSV·근거 내보내기, PINPOINT download, 모바일 전체 Acceptance 등은 완료로 과장하지 않고 별도 미검증/부분검증 상태를 유지한다.

## 12. 검증환경

```text
[Windows Local V8 Test Harness]
ThermoSysPro / OpenModelica
        ↓ Native OPC UA
ECMS / Protection / Alarm Runtime
        ↓
EVENT.csv + RAW.csv
        ↓
[TripLens Analysis]
```

Virtual Plant는 실제 발전소와 동일한 Digital Twin이라고 주장하지 않는다. 합성 사고 데이터 생성·검증환경이다.

## 13. 적용 범위와 한계

현재 입증:
- 동일 V8 합성환경의 12개 서로 다른 사고 입력에 같은 분석구조 적용
- 원인/보호/파급의 분리
- EVENT/RAW Evidence 추적
- 불완전 Evidence에서 판단 보류 사례
- 보고서 산출

미입증:
- 실제 발전소 현장 정확도
- 모든 발전소 topology 일반화
- ABB/Siemens 등 제조사별 실설비 호환성
- Field Pilot / Production 수준 성능
- Time-to-Insight의 최종 정량 성능
- 전체 MTTR 감소율

제조사 비종속 구조를 지향하지만, 실제 현장 적용에는 데이터 Adapter, Tag 의미, 보호/제어 Logic 매핑 및 현장별 검증이 필요하다.

## 14. 결론

TripLens는 발전소 사고 후 발생한 EVENT와 RAW를 근거 저장소로 사용하고, Gemini Agent가 제한된 Evidence Tool을 통해 필요한 근거를 탐색하여 Critical Event, 원인 후보, Direct Trigger, Propagation 및 Causal Chain을 생성하는 READ-ONLY 사고분석 시스템이다.

현재 단계는 실제 발전소 Field Pilot이 아니라 **동일 합성 복합화력 환경의 다중 사고에서 반복 검증된 Engineering Prototype**으로 정의한다.
