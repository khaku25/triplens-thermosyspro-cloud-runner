# TripLens 기술보고서
## 발전소 EVENT + RAW 기반 Agentic AI 사고분석 시스템
### KIEE 2026 Agentic AI 경진대회 — 제출 전용 Working Draft

> **편집 기준:** 이 파일을 제출용 Technical Report의 원본으로 사용한다. Virtual Plant/OPC UA/Protection 구현 세부는 본문에서 필요한 수준만 설명하고 기술부록으로 분리한다.

---

## 1. 문제 정의

발전소 Trip 또는 주요 설비고장 발생 시 DCS, ECMS, Historian, Protection 계층에서 다수의 Alarm, Event, 상태변화, 공정값 변동이 짧은 시간에 집중된다. 운전원은 이 가운데 **최초 사건, 직접 계기, 후속 파급, 현재 영향범위, 다음 확인사항**을 빠르게 구분해야 한다.

TripLens는 사고 직후의 이 초기 정보정리 구간을 지원하기 위한 **READ-ONLY Agentic AI 사고분석 시스템**이다.

TripLens의 목표는 사람이 미리 정리한 몇 개 Event를 AI가 다시 요약하는 것이 아니다. 사고 중 발생한 `EVENT.csv`의 Event Stream과 `RAW.csv`의 시계열 Evidence를 함께 입력받고, Gemini Agent가 필요한 근거를 탐색하여 **핵심 Event, 원인 후보, 인과 흐름을 스스로 구성**하는 것을 목표로 한다.

---

## 2. TripLens의 핵심 가치

TripLens가 답하려는 질문은 다음과 같다.

1. 수많은 Alarm/Event 중 사고를 설명하는 핵심 Event는 무엇인가?
2. 최초 원인 후보와 후속 파급은 어떻게 구분되는가?
3. Event와 실제 RAW 상태변화가 서로 일치하는가?
4. 이번 사고의 인과 Chain은 어떻게 구성되는가?
5. 어떤 설비가 영향을 받았는가?
6. 현재 복구 전에 무엇을 확인해야 하는가?

따라서 TripLens는 기존 DCS/ECMS/Historian을 대체하지 않고, 기존 시스템에서 추출된 데이터를 바탕으로 **사고 초기 의사결정을 위한 정보계층**을 추가한다.

---

## 3. 입력 데이터 구조

### 3.1 EVENT.csv — 전체 발생 Event Stream

EVENT는 사고 중 실제 발생한 Alarm, Protection Event, 상태변화, Operator Action 등을 기록한다.

예:
- Alarm ACTIVE / RETURN
- Protection Event
- Breaker 상태변화
- 설비 Running Lost / Deenergized
- Operator Action
- Recovery Event

TripLens의 핵심은 EVENT를 사람이 미리 정답에 맞게 압축해서 넣는 것이 아니다. 발생한 Event Stream을 입력으로 유지하고, **그중 어떤 Event가 Critical한지는 Agent가 분석 과정에서 판단**한다.

### 3.2 RAW.csv — 시계열 Evidence

RAW는 Event의 원인과 결과를 교차확인할 수 있는 시계열 Evidence를 제공한다.

- Pressure / Temperature / Flow / Level
- Speed / Power
- Breaker state
- Trip command
- Latch / Logic state
- Quality / timestamp

TripLens는 EVENT만으로 결론을 내리지 않고 관련 RAW 구간을 함께 조회하여 사고해석의 근거로 사용한다.

### 3.3 이기종 Source

실제 발전소에서는 GT/ST, HRSG/BOP, ECMS 등이 서로 다른 플랫폼에 존재할 수 있다. TripLens는 Source와 Tag를 구분한 뒤 공통 사고분석 구조로 정리하는 것을 목표로 한다.

현재 제출버전은 CSV 기반 입력을 사용하며, 현장 확장 시 각 플랫폼의 Export/Historian 데이터를 동일 데이터계약으로 정규화하는 구조를 전제로 한다.

---

## 4. TripLens 분석 파이프라인

```text
EVENT.csv 전체 + RAW.csv
        ↓
Input Validation
        ↓
Time Alignment / Normalization
        ↓
Event Index / Evidence Access
        ↓
Tag · Equipment · Logic Context Tools
        ↓
Gemini Agent
  - Critical Event Selection
  - Cause Hypothesis / Primary Cause
  - Causal Chain Generation
  - Affected Equipment / Recovery Check
        ↓
Verification / Fail-Closed
        ↓
Incident Summary / Critical Events / Causal Timeline
Key Evidence / Affected Equipment / Recovery Check
```

### 4.1 Input Validation

- 필수 열 존재 여부
- timestamp parsing
- Source/System 구분
- Event/RAW 파일 존재 여부
- 빈 값 및 품질 이상

입력 조건을 만족하지 못하면 정상분석을 계속하지 않고 검토 필요 상태로 전환한다.

### 4.2 Time Alignment

EVENT와 RAW는 서로 다른 시스템 또는 기록방식에서 생성될 수 있으므로 동일 시간축에서 비교해야 한다. 원래 timestamp는 보존하고 Event 전후의 RAW 상태변화를 연결할 수 있도록 정렬한다.

Engineering Layer는 여기에서 인과관계 정답을 만들지 않는다. Agent가 실제 Event/RAW를 비교할 수 있도록 시간과 Source를 정리하는 역할을 한다.

### 4.3 Event Index / Evidence Access

TripLens는 전체 Event Stream과 RAW 전체를 그대로 긴 Prompt 한 번에 밀어 넣는 방식을 목표로 하지 않는다.

대신 Agent가 사고 분석 중 필요한 근거를 단계적으로 조회할 수 있도록 다음 종류의 접근기능을 제공하는 구조를 사용한다.

예:
- 특정 시간구간 Event 조회
- 특정 설비 관련 Event 조회
- Tag 시계열 조회
- Breaker/Equipment state 조회
- 관련 Logic/Protection 의미 조회
- 특정 Event 주변 RAW 변화 조회

실제 제출버전에서는 Runtime에 구현된 Tool/Function 명칭을 RC Freeze 시점에 확정하여 문서화한다.

### 4.4 Tag · Equipment · Logic Context

Logic Master와 Tag Master의 역할은 이번 사고의 정답 Chain을 미리 만들어주는 것이 아니다.

이 계층은 다음과 같은 **의미와 관계정보**를 제공한다.

- Tag가 어떤 설비/상태를 의미하는가
- Protection condition이 어떤 설비와 관련되는가
- Breaker/Command/Latch가 어떤 역할을 하는가
- 서로 어떤 논리적 관계를 가질 수 있는가

즉,

> Logic/Tag Master = 가능한 공학적 관계와 의미
>
> EVENT/RAW = 이번 사고에서 실제 발생한 사실
>
> Gemini Agent = 이번 사고의 실제 인과 흐름 판단

으로 역할을 분리한다.

---

## 5. Agentic AI — Gemini

### 5.1 Agent의 핵심 역할

Gemini Agent는 구조화된 입력과 조회 가능한 Evidence를 바탕으로 다음 작업을 수행한다.

- 전체 Event Stream에서 Critical Event 선정
- Origin / Direct Trigger / Propagation 구분
- 원인 후보 비교
- 근거가 충분할 경우 Primary Cause 판단
- Event와 RAW 상태변화 교차확인
- 상충하거나 부족한 Evidence 탐색
- 추가 확인이 필요한 Tag/Event 탐색
- **Causal Chain 생성**
- Affected Equipment 및 Recovery Check 구성

즉 Causal Chain은 Engineering Layer가 정답처럼 만들어 제공하는 값이 아니라 **Agent의 분석결과**다.

### 5.2 Causal Chain 생성 예

예를 들어 Agent가 다음 사실을 조회했다고 가정한다.

```text
t1: LP Drum Level 저하
t2: LP Drum LL protection condition = 1
t3: GT/ST Trip Request = 1
t4: Trip Latch = 1
t5: Breaker Open
t6: 후속 Flow/Pressure Alarm 다수 발생
```

이 사실을 바탕으로 Agent가 다음과 같은 Causal Chain을 생성할 수 있다.

```text
LP Drum Level 저하
        ↓
LP Drum LL Condition
        ↓
GT/ST Trip Request
        ↓
Trip / Breaker Open
        ↓
Secondary Process Alarms
```

이 Chain의 구성 자체가 Agent의 분석대상이며, 이후 Verification과 Ground Truth 비교의 대상이 된다.

### 5.3 Engineering Layer와 Agent의 역할 분리

```text
Engineering Layer
- Input validation
- Time alignment
- Event / RAW indexing
- Evidence access
- Tag / Equipment / Logic semantics

        ↓

Gemini Agent
- Evidence navigation
- Critical Event selection
- Cause hypothesis
- Causal Chain generation
- Recovery check

        ↓

Verification Boundary
- Evidence presence
- Causal edge support
- Missing/conflicting evidence
- Unsupported claim
- Fail-Closed
```

Gemini는 RAW 값, EVENT timestamp, Ground Truth, Protection Logic, OT 상태를 수정할 수 없다.

### 5.4 실제 모델정보

- Provider: Google Gemini
- Exact model: **TBD — RC Freeze 시 실제 Runtime 설정값 기재**
- Invocation method: **TBD — 실제 Local TripLens 방식 기재**
- 실제 Tool/Function 목록: **TBD — RC Freeze 시 Runtime과 일치 여부 확인 후 기재**

---

## 6. AI Evidence Policy

Blind Validation은 현장에서 실제로 이용 가능한 정보를 의도적으로 숨기는 시험이 아니다. Process, Alarm, Protection, Logic, Breaker 상태처럼 운전/보호 계층에서 관측 가능한 정보는 Evidence로 사용할 수 있다.

허용 대상 예:
- Process measurement
- Alarm / Event
- Protection condition
- Trip request / latch
- Breaker / equipment state
- Operator action
- Runtime logic state

반대로 시험자가 알고 있는 정답 또는 시뮬레이터 내부 고장주입 정보는 Agent 판단근거로 사용하지 않는다.

차단 대상 예:
- Scenario ID
- Expected Cause / Ground Truth
- Fault Injector internal variable
- Simulation-only fault injection command / metadata

현재 제출 전에는 이 Policy가 실제 Runtime에서 Prompt 규칙뿐 아니라 Evidence 전달경로에서 어떻게 적용되는지 확인하고 최종 문서에 반영한다.

---

## 7. 출력 구조

TripLens 결과는 긴 AI 답변 하나가 아니라 다음 항목으로 분리한다.

- **All Events**: 사고 중 발생한 전체 Event Stream
- **Incident Summary**: 사고상황 요약
- **Critical Events**: Agent가 선별한 핵심 Event
- **Cause / Cause Candidate**: Agent가 Evidence를 바탕으로 판단한 원인 또는 후보
- **Causal Timeline / Chain**: Agent가 생성한 Origin → Trigger → Trip/Protection → Propagation 흐름
- **Key Evidence**: 각 판단에 사용된 EVENT/RAW 근거
- **Affected Equipment**: 영향설비
- **Recovery Check**: 다음 확인사항

Recovery Check는 자동복구 명령이 아니라 운전원이 확인해야 할 항목을 제시하는 기능이다.

Dashboard에서는 **원본 All Events와 TripLens가 선별·해석한 Critical Events를 구분해 표시**하는 것이 핵심이다.

---

## 8. Verification 및 Fail-Closed

Verification Layer는 Causal Chain을 대신 생성하지 않는다. Agent가 생성한 주장과 각 Causal Edge가 실제 Evidence에 의해 지지되는지 확인한다.

예를 들어 Agent가 다음 Edge를 만들었다면:

```text
LP Drum LL Condition → GT/ST Trip Request
GT/ST Trip Request → Breaker Open
```

Verification은 각 관계에 실제 EVENT/RAW/Logic 근거가 있는지 확인한다.

근거가 부족하거나 서로 충돌할 경우 다음 상태를 허용한다.

- `UNKNOWN`
- `INCONCLUSIVE`
- `REVIEW REQUIRED`
- `ADDITIONAL EVIDENCE REQUIRED`

검증질문:
1. 주요 주장에 실제 EVENT/RAW 근거가 있는가?
2. 각 Causal Edge가 timestamp 및 Logic 관계와 모순되지 않는가?
3. 필요한 근거가 누락되어 있지 않은가?
4. 상충하는 설비상태가 존재하는가?
5. Ground Truth 또는 정답 metadata가 Agent Evidence에 포함되지 않았는가?

---

## 9. 일반화와 Blind Validation

TripLens의 핵심 검증질문은 다음과 같다.

> **GT Trip 하나를 잘 설명하는가가 아니라, 서로 다른 사고 입력을 동일 TripLens Engine이 분석할 수 있는가?**

Blind Validation에서 Agent 판단근거로 제공하지 않는 정보:

- Scenario ID
- Expected Cause
- Root Cause answer label
- Ground Truth
- Simulation-only Fault Injection metadata

분석완료 후 외부 Validator가 Ground Truth와 결과를 비교한다. 사고군별 Engine code는 수정하지 않는 것을 원칙으로 한다.

### 평가 Metric

| Metric | 목적 |
|---|---|
| Critical Event Precision | Agent가 불필요한 Event를 핵심으로 선정하는지 평가 |
| Critical Event Recall | Ground Truth 핵심사건을 놓치는지 평가 |
| Critical Event F1 | Critical Event 선별 종합성능 |
| Causal Chain Accuracy | Agent가 생성한 사고 인과흐름 정확도 |
| Evidence Grounding Rate | AI 주장과 실제 입력근거 연결성 |
| Unsupported Claims | 근거 없는 공학 주장 수 |
| Fail-Closed | 불완전 데이터에서 부당하게 확정하지 않는지 평가 |
| Alarm/Event Compression | 전체 Event 대비 Critical Event 축약 정도 |
| Time-to-Insight | 핵심정보 확보시간 |

Alarm/Event Compression은 단독으로 좋은 성능을 의미하지 않으므로 Critical Event Recall/F1과 함께 평가한다.

실제 RC Run 전까지 수치는 `NOT TESTED`로 유지한다.

---

## 10. 검증용 데이터 생성환경

TripLens 자체와 검증환경은 구분한다.

```text
[Validation Environment]
Virtual Plant / OPC UA / ECMS / Alarm Logic
                ↓
          EVENT.csv + RAW.csv
                ↓
--------------------------------------
                ↓
          [TripLens System]
```

Virtual Plant의 역할은 사고 전후의 Event/RAW 데이터를 반복가능하게 생성하는 **Test Harness**다. 보호 Matrix, OPC UA node 수, writable input 수, Pump/Valve physics 같은 세부사항은 `APPENDIX/09_VIRTUAL_PLANT_TEST_ENVIRONMENT.md`에서 설명한다.

검증환경의 Regression PASS와 TripLens의 사고분석 정확도 PASS는 서로 다른 평가다.

---

## 11. 정량 검증결과

> **RC Freeze 이후 실제 Blind Run 결과만 입력한다.**

| Metric | Result |
|---|---:|
| Incident Families | NOT TESTED |
| Blind Runs | NOT TESTED |
| Engine Code Changes | NOT TESTED |
| Critical Event Precision | NOT TESTED |
| Critical Event Recall | NOT TESTED |
| Critical Event F1 | NOT TESTED |
| Causal Chain Accuracy | NOT TESTED |
| Evidence Grounding Rate | NOT TESTED |
| Unsupported Claims | NOT TESTED |
| Fail-Closed | NOT TESTED |
| Time-to-Insight | NOT TESTED |

상세 결과는 `VALIDATION/05_VALIDATION_REPORT.md`와 `06_VALIDATION_RESULTS.csv`를 사용한다.

---

## 12. 실용성

TripLens가 직접 줄이려는 것은 물리적 정비시간 전체가 아니라 **사고 초기 정보탐색 및 진단에 필요한 시간**이다.

기대효과:
- Alarm Flood에서 핵심정보 우선제시
- EVENT와 RAW 교차검증
- 근거 Tag 기반 설명
- 사고보고/인수인계의 구조화
- 반복사고 비교를 위한 표준화

`Time-to-Insight`는 실제 시험으로 측정하며, 전체 MTTR 감소율로 과장하지 않는다.

---

## 13. 한계 및 현장 적용조건

- 현재 검증은 Virtual Plant/Synthetic 환경 기반
- 실제 현장 정확도 검증은 별도 필요
- 실제 발전소의 대규모 Tag/Event 적용은 추가 성능검증 필요
- 승인 P&ID/SLD/C&E/정정값을 대체하지 않음
- 실제 현장 데이터의 외부 Gemini 사용은 별도 보안·거버넌스 필요
- TripLens는 READ-ONLY이며 OT 제어권한이 없음

---

## 14. 결론

TripLens는 발전소 사고 후 발생한 대량의 EVENT와 RAW를 입력받아, Gemini Agent가 필요한 Evidence를 탐색하고 **Critical Event, 원인 후보, Causal Chain을 생성**하는 READ-ONLY 사고분석 시스템이다.

제출 전 가장 중요한 과제는 동일 RC 버전에서 다중사고 Blind Validation을 수행하여, Agent가 생성한 Critical Event와 Causal Chain이 Ground Truth와 얼마나 일치하는지를 정량적으로 제시하는 것이다.
