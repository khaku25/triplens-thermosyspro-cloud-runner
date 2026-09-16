# TripLens 기술문서
## 발전소 EVENT + RAW 기반 Agentic AI 사고분석 시스템
### KIEE 2026 Agentic AI 경진대회 — RC0 Draft

---

## 1. 개요

발전소 Trip 또는 주요 설비고장 발생 시 DCS, ECMS, Protection, Historian 등 여러 계층에서 Alarm, Event, 상태변화, 공정값 변동이 짧은 시간에 집중된다. 운전원은 이 많은 정보 중에서 **무엇이 최초 사건인지, 무엇이 직접 계기인지, 무엇이 후속 파급인지, 그리고 지금 무엇을 확인해야 하는지**를 빠르게 구분해야 한다.

TripLens는 이 초기 사고분석 구간을 지원하기 위한 **READ-ONLY Agentic AI 사고분석 시스템**이다.

TripLens의 핵심은 단순 Alarm 요약이 아니다. `EVENT.csv`와 `RAW.csv`를 함께 읽고, 시간축과 설비 관계를 기준으로 근거를 구조화한 뒤, Gemini 기반 Agent가 그 근거를 사용하여 사고 흐름과 확인사항을 제시한다.

핵심 입력과 출력은 다음과 같다.

```text
EVENT.csv + RAW.csv
        ↓
입력 검증 / 시간 정렬
        ↓
핵심 사건 및 관련 Evidence 추출
        ↓
설비·보호·상태 관계 구성
        ↓
Gemini Agent 분석
        ↓
Verification / Fail-Closed
        ↓
Incident Summary
Critical Events
Causal Timeline
Key Evidence
Affected Equipment
Recovery Check
```

---

## 2. 해결하려는 문제

### 2.1 Alarm Flood보다 어려운 것은 '정보의 우선순위'다

사고 직후에는 많은 Alarm과 상태변화가 거의 동시에 발생한다. 단순히 Alarm 개수를 줄이는 것만으로는 다음 질문에 답하기 어렵다.

- 최초로 확인해야 할 Event는 무엇인가?
- Trip의 직접 계기와 후속 결과는 어떻게 구분되는가?
- 실제 RAW 값은 Event와 일치하는가?
- 어떤 설비가 영향을 받았는가?
- 현재 복구 전에 확인해야 할 항목은 무엇인가?

TripLens는 이 질문을 하나의 사고분석 흐름으로 묶는다.

### 2.2 기존 화면을 대체하지 않고, 그 위에서 정보를 재구성한다

TripLens는 DCS, ECMS, Historian을 대체하는 새로운 제어시스템이 아니다. 기존 시스템에서 추출된 Event와 RAW 데이터를 읽어 **사고 초기 의사결정을 위한 정보 계층**을 추가한다.

따라서 TripLens의 권한은 다음과 같이 제한된다.

- READ-ONLY
- OT Write 없음
- 자동 복전 없음
- Breaker 자동조작 없음
- Protection Logic 변경 없음
- 운전원 최종판단 대체 없음

---

## 3. TripLens 입력 구조

TripLens는 `EVENT.csv`와 `RAW.csv`를 서로 다른 역할의 증거로 취급한다.

### 3.1 EVENT.csv — "무슨 일이 언제 발생했는가"

EVENT에는 사고 흐름에서 의미 있는 사건을 기록한다.

예시:

- Alarm ACTIVE / RETURN
- Protection Event
- Breaker 상태변화
- 설비 Running Lost / Deenergized
- Operator Action
- Recovery Event

EVENT의 목적은 원인 정답을 제공하는 것이 아니라, 사람이 읽을 수 있는 사고 시퀀스를 제공하는 것이다.

### 3.2 RAW.csv — "그때 실제 설비가 어떻게 움직였는가"

RAW에는 Event의 원인과 결과를 교차확인할 수 있는 시계열 근거를 보존한다.

예시:

- Pressure / Temperature / Flow / Level
- Speed / Power
- Breaker state
- Trip command
- Latch / Logic state
- 품질정보 및 timestamp

TripLens는 EVENT를 그대로 믿는 것이 아니라, 관련 RAW 구간을 함께 확인하여 사고 해석의 근거로 사용한다.

### 3.3 이기종 데이터 수용

실제 발전소에서는 GT/ST, HRSG/BOP, ECMS 등이 서로 다른 플랫폼에 존재할 수 있다. TripLens는 입력 단계에서 Source와 Tag를 구분하고, 공통 사고분석 구조로 정리하는 것을 목표로 한다.

현재 제출버전은 CSV 기반 입력을 사용하며, 현장 확장 시 Historian 또는 시스템별 Export 결과를 동일 데이터 계약으로 변환하는 방식을 전제로 한다.

---

## 4. TripLens 분석 파이프라인

### 4.1 Input Validation

분석 전에 입력 자체가 신뢰 가능한지 확인한다.

- 필수 열 존재 여부
- timestamp parsing
- Source/System 구분
- 빈 값 및 품질 이상
- Event/RAW 파일 존재 여부

입력 조건을 만족하지 못하면 분석을 계속하지 않고 오류 또는 검토 필요 상태로 전환한다.

### 4.2 Time Alignment

EVENT와 RAW는 서로 다른 시스템 또는 기록방식에서 생성될 수 있으므로 동일 시간축에서 비교해야 한다.

TripLens는 원래 timestamp를 보존하면서 Event 주변 RAW 변화를 확인할 수 있도록 정렬한다.

핵심 목적은 단순 timestamp 정렬이 아니라 다음 관계를 확인하는 것이다.

```text
Event 발생
   ↓
Command / Logic 변화
   ↓
Equipment State 변화
   ↓
Process Response
   ↓
후속 Alarm / Event
```

### 4.3 Critical Event Extraction

모든 Event를 동일 중요도로 보여주지 않는다.

TripLens는 사고 흐름을 이해하는 데 필요한 Event를 우선적으로 추출하고 다음처럼 분류한다.

- Origin candidate
- Direct trigger
- Protection / Trip action
- Propagation
- Secondary alarm
- Operator action
- Recovery / unresolved state

이 단계의 목적은 Alarm을 단순히 삭제하는 것이 아니라 **사고 이해에 필요한 Event의 우선순위를 재구성하는 것**이다.

### 4.4 Evidence Extraction

각 핵심 주장에는 실제 입력 데이터의 근거가 연결되어야 한다.

예:

```text
주장: GT가 Trip 상태로 전환됨
Evidence:
- EVENT: GT TRIP EVENT
- RAW: GT_TRIP_CMD = 1
- RAW: 52GT CLOSED = 0
- Timestamp relationship
```

TripLens는 가능한 경우 최종 설명이 원본 Event 또는 RAW Tag까지 추적될 수 있도록 구성한다.

### 4.5 Causal Context 구성

TripLens는 '동시에 나타난 값'과 '사고 흐름상 연결된 값'을 구분하려고 한다.

이를 위해 Event 순서, 설비 관계, Logic/Protection 관계, 실제 Process response를 함께 본다.

최종 결과에서는 다음 세 층을 구분하는 것을 목표로 한다.

1. 원인 후보 / Origin
2. 직접 계기 / Direct Trigger
3. 후속 파급 / Propagation

---

## 5. Agentic AI — Gemini의 역할

### 5.1 왜 Agent가 필요한가

발전소 사고는 고정된 문장 Template만으로 설명하기 어렵다. 사고마다 관련 설비, Event 조합, RAW 변화, 누락된 근거가 달라지기 때문이다.

TripLens의 Gemini Agent는 이미 구조화된 Evidence를 바탕으로 다음 작업을 수행한다.

- 핵심 사건 요약
- 사고 진행순서 설명
- 원인 후보와 후속현상 구분
- 서로 다른 Evidence의 연결
- 상충하거나 부족한 근거 표시
- 추가 확인이 필요한 Tag/Event 제시
- Recovery Check 정리

### 5.2 AI와 Engineering Layer의 역할 분리

TripLens의 구조는 다음과 같이 분리한다.

```text
Engineering Layer
- Input validation
- Time alignment
- Evidence extraction
- Tag / Logic context

        ↓

Gemini Agent
- Evidence review
- Incident interpretation
- Causal explanation
- Recovery check generation

        ↓

Verification Boundary
- Evidence presence
- Missing evidence
- Unsupported claim
- Fail-Closed
```

따라서 Gemini가 원본 데이터를 바꾸거나, Ground Truth를 읽고 정답을 재현하는 구조가 아니다.

### 5.3 Gemini가 할 수 없는 것

Gemini는 다음을 수정할 권한이 없다.

- RAW 값
- EVENT timestamp
- Protection Logic
- Ground Truth
- 승인된 공학 설정
- OT 장치 상태

---

## 6. TripLens 출력

TripLens의 결과는 긴 AI 답변 하나가 아니라, 사고 초기 판단에 필요한 항목으로 분리한다.

### 6.1 Incident Summary

사고를 짧게 요약한다.

### 6.2 Critical Events

전체 Event 중 사고흐름을 이해하는 데 필요한 핵심 Event를 우선순위와 함께 보여준다.

### 6.3 Causal Timeline

Origin → Direct Trigger → Protection/Trip → Propagation 순으로 사고흐름을 정리한다.

### 6.4 Key Evidence

결론에 사용된 EVENT/RAW Tag와 timestamp를 제시한다.

### 6.5 Affected Equipment

영향을 받은 설비를 사고흐름과 함께 정리한다.

### 6.6 Recovery Check

자동복구 명령이 아니라, 운전원이 다음으로 확인해야 할 항목을 제시한다.

예:

- Breaker 실제 상태 확인
- Trip latch 잔류 여부
- Essential auxiliary 상태
- 공정값 안정 여부
- 후속 Alarm 미복귀 여부

---

## 7. Verification 및 Fail-Closed

TripLens는 AI가 반드시 하나의 원인을 확정하도록 강제하지 않는다.

근거가 부족하거나 서로 충돌할 경우 다음 상태를 허용한다.

- `UNKNOWN`
- `INCONCLUSIVE`
- `REVIEW REQUIRED`
- `ADDITIONAL EVIDENCE REQUIRED`

최종 분석에서 확인할 항목은 다음과 같다.

1. 주요 주장에 실제 EVENT/RAW 근거가 있는가?
2. 사건 순서가 timestamp와 모순되지 않는가?
3. 필요한 근거가 누락되어 있지 않은가?
4. 상충하는 설비상태가 존재하는가?
5. Ground Truth 또는 정답 metadata가 입력에 포함되지 않았는가?

이 구조는 생성형 AI가 부족한 정보를 임의로 메우는 문제를 줄이기 위한 안전장치다.

---

## 8. 일반화와 Blind Validation

### 8.1 검증 질문

TripLens의 핵심 검증 질문은 다음과 같다.

> **GT Trip 하나를 잘 설명하는가가 아니라, 서로 다른 사고 입력을 동일 TripLens Engine이 분석할 수 있는가?**

### 8.2 Blind 원칙

Blind Validation에서는 다음 정보를 TripLens에 제공하지 않는다.

- Scenario ID
- Expected Cause
- Root Cause answer label
- Ground Truth
- Fault injection metadata

TripLens 분석이 완료된 후 외부 Validator가 Ground Truth와 결과를 비교한다.

또한 사고군별로 Engine 코드를 수정하지 않는 것을 원칙으로 한다.

### 8.3 평가 지표

공식 Scorecard는 실제 RC Run 이후 채운다.

| Metric | 목적 |
|---|---|
| Critical Event Precision | 불필요한 핵심사건 선정 여부 |
| Critical Event Recall | 중요한 사건 누락 여부 |
| Critical Event F1 | 핵심사건 추출 종합성능 |
| Causal Chain Accuracy | 사고흐름 재구성 정확도 |
| Evidence Grounding Rate | 결론의 실제 근거 연결성 |
| Unsupported Claims | 근거 없는 공학 주장 수 |
| Fail-Closed | 불완전 데이터에서 안전한 중단 여부 |
| Alarm/Event Compression | 전체 Event 대비 핵심 Event 축약 정도 |
| Time-to-Insight | 핵심정보 확보시간 |

실제 Run이 완료되기 전에는 수치를 임의로 채우지 않는다.

---

## 9. 검증용 데이터 생성 환경

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

검증환경의 목적은 TripLens에게 정답을 알려주는 것이 아니라, 분석할 수 있는 사고 Event와 RAW 시계열을 생성하는 것이다.

GT Trip 등 일부 사고는 Local Virtual Plant와 Protection/Alarm Runtime을 통해 생성하며, 다른 사고군은 동일 입력계약을 만족하는 별도 Synthetic Benchmark를 사용할 수 있다.

Virtual Plant의 상세 Protection matrix, OPC UA node 수, Alarm binding 수, Pump/Valve 물리구현 범위 등은 TripLens 분석기 자체의 기술사양이 아니므로 별도 문서 `09_VIRTUAL_PLANT_TEST_ENVIRONMENT.md`에서 기술한다.

---

## 10. 실용성

TripLens의 목표는 물리적 수리시간 전체를 자동으로 줄이는 것이 아니라 **사고 초기 정보탐색과 판단지원 시간을 줄이는 것**이다.

예상 활용영역:

- Alarm Flood에서 핵심 사건 우선 제시
- EVENT와 RAW 교차검증
- 사고 초기 Brief 자동 구조화
- 근거 Tag 기반 원인 후보 검토
- 반복사고 분석 형식 표준화
- 사고보고서 작성 전 초기 정리

따라서 효과 측정 역시 MTTR 전체 감소율보다 `Time-to-Insight`를 우선 지표로 사용한다.

---

## 11. AI 활용 및 개발자 기여

TripLens 개발 과정에서는 생성형 AI를 코드 작성, 디버깅, 문서화, 테스트 설계 보조에 활용하였다.

그러나 다음 항목은 실제 Runtime과 검증근거로 확인한다.

- 프로그램 실행 여부
- EVENT/RAW 생성 및 입력
- 분석결과
- Ground Truth 비교
- 정량 Scorecard

문제 정의, 공학적 해석기준, 검증방법 및 최종 결과 검토는 개발자가 수행한다.

상세 내용은 `04_AI_USAGE_AND_LIMITATIONS.md`에 기록한다.

---

## 12. 한계 및 현장 적용 조건

현재 TripLens는 다음 한계를 가진다.

- Virtual Plant / Synthetic data 기반 검증 단계
- 실제 발전소 현장 정확도 미검증
- 실제 발전소 대규모 Tag 환경은 추가 확장검증 필요
- 현장 승인 P&ID / SLD / C&E / Protection setting을 대체하지 않음
- 클라우드 LLM 사용 시 사업장 보안·데이터 거버넌스 필요
- TripLens는 제어시스템이 아닌 READ-ONLY decision support layer임

---

## 13. 결론

TripLens의 핵심은 Virtual Plant 자체가 아니다.

TripLens는 발전소 사고 후 흩어진 `EVENT + RAW`를 하나의 근거 구조로 정리하고, Agentic AI가 **핵심 사건, 사고흐름, 근거, 영향설비, 복구 확인사항**을 도출하도록 하는 사고분석 계층이다.

Virtual Plant는 이 분석기를 반복적으로 시험하기 위한 검증환경이며, 실제 경쟁력은 서로 다른 사고에서도 동일 TripLens Engine이 근거 중심 결과를 생성하는지에 의해 평가한다.

제출 전 핵심 과제는 기능 추가보다 **RC Freeze → Blind Validation → Scorecard 확정 → 제출문서/발표 일치**이다.
