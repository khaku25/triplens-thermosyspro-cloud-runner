# TripLens 기술보고서
## 발전소 EVENT + RAW 기반 Agentic AI 사고분석 시스템
### KIEE 2026 Agentic AI 경진대회 — 제출 전용 Working Draft

> **편집 기준:** 이 파일을 제출용 Technical Report의 원본으로 사용한다. Virtual Plant/OPC UA/Protection 구현 세부는 본문에서 필요한 수준만 설명하고 기술부록으로 분리한다.

---

## 1. 문제 정의

발전소 Trip 또는 주요 설비고장 발생 시 DCS, ECMS, Historian, Protection 계층에서 다수의 Alarm, Event, 상태변화, 공정값 변동이 짧은 시간에 집중된다. 운전원은 이 가운데 **최초 사건, 직접 계기, 후속 파급, 현재 영향범위, 다음 확인사항**을 빠르게 구분해야 한다.

TripLens는 사고 직후의 이 초기 정보정리 구간을 지원하기 위한 **READ-ONLY Agentic AI 사고분석 시스템**이다.

TripLens의 목표는 Alarm을 단순 요약하는 것이 아니다. `EVENT.csv`와 `RAW.csv`를 함께 읽고 시간축과 설비관계를 기준으로 Evidence를 구조화한 뒤, Gemini Agent가 그 근거를 사용해 사고흐름과 확인사항을 설명한다.

---

## 2. TripLens의 핵심 가치

TripLens가 답하려는 질문은 다음과 같다.

1. 사고 직후 가장 먼저 확인할 Event는 무엇인가?
2. 최초 원인 후보와 후속 파급을 어떻게 구분할 수 있는가?
3. Event와 실제 RAW 상태변화가 서로 일치하는가?
4. 어떤 설비가 영향을 받았는가?
5. 현재 복구 전에 무엇을 확인해야 하는가?

따라서 TripLens는 기존 DCS/ECMS/Historian을 대체하지 않고, 기존 시스템에서 추출된 데이터를 바탕으로 **사고 초기 의사결정을 위한 정보계층**을 추가한다.

---

## 3. 입력 데이터 구조

### 3.1 EVENT.csv

EVENT는 사고흐름상 의미 있는 사건을 표현한다.

- Alarm ACTIVE / RETURN
- Protection Event
- Breaker 상태변화
- 설비 Running Lost / Deenergized
- Operator Action
- Recovery Event

EVENT의 목적은 원인 정답을 제공하는 것이 아니라 사람이 읽을 수 있는 사고 시퀀스를 제공하는 것이다.

### 3.2 RAW.csv

RAW는 Event의 원인과 결과를 교차확인할 수 있는 시계열 Evidence를 제공한다.

- Pressure / Temperature / Flow / Level
- Speed / Power
- Breaker state
- Trip command
- Latch / Logic state
- Quality / timestamp

TripLens는 EVENT를 그대로 믿는 것이 아니라 관련 RAW 구간을 함께 확인하여 사고해석의 근거로 사용한다.

### 3.3 이기종 Source

실제 발전소에서는 GT/ST, HRSG/BOP, ECMS 등이 서로 다른 플랫폼에 존재할 수 있다. TripLens는 Source와 Tag를 구분한 뒤 공통 사고분석 구조로 정리하는 것을 목표로 한다.

현재 제출버전은 CSV 기반 입력을 사용하며, 현장 확장 시 각 플랫폼의 Export/ Historian 데이터를 동일 데이터계약으로 정규화하는 구조를 전제로 한다.

---

## 4. TripLens 분석 파이프라인

```text
EVENT.csv + RAW.csv
        ↓
Input Validation
        ↓
Time Alignment / Normalization
        ↓
Critical Event Extraction + Evidence Extraction
        ↓
Causal Context
        ↓
Gemini Agent
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

EVENT와 RAW는 서로 다른 시스템 또는 기록방식에서 생성될 수 있으므로 동일 시간축에서 비교해야 한다. 원래 timestamp는 보존하고 Event 전후의 RAW 상태변화를 연결한다.

핵심 관계는 다음과 같다.

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

모든 Event를 같은 중요도로 보여주지 않고 사고이해에 필요한 Event의 우선순위를 재구성한다.

분류 예:
- Origin candidate
- Direct trigger
- Protection / Trip action
- Propagation
- Secondary alarm
- Operator action
- Recovery / unresolved state

### 4.4 Evidence Extraction

최종 핵심 주장에는 가능한 경우 실제 입력근거가 연결되어야 한다.

예:

```text
주장: 발전기가 Trip 상태로 전환됨
Evidence:
- EVENT: 관련 Trip Event
- RAW: Trip Command / Breaker state
- Timestamp relationship
```

### 4.5 Causal Context

TripLens는 동시에 나타난 값과 사고흐름상 연결된 값을 구분하려고 한다. Event 순서, 설비관계, Protection/Logic 관계, Process response를 함께 사용하여 다음 세 층을 구분한다.

1. Origin / 원인 후보
2. Direct Trigger / 직접 계기
3. Propagation / 후속 파급

---

## 5. Agentic AI — Gemini

### 5.1 Agent의 역할

Gemini Agent는 이미 구조화된 Evidence를 바탕으로 다음 작업을 수행한다.

- 핵심 사건 요약
- 사고 진행순서 설명
- 원인 후보와 후속현상 구분
- 서로 다른 Evidence 연결
- 상충하거나 부족한 근거 표시
- 추가 확인이 필요한 Tag/Event 제시
- Recovery Check 정리

### 5.2 Engineering Layer와의 역할 분리

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
- Recovery check

        ↓
Verification Boundary
- Evidence presence
- Missing/conflicting evidence
- Unsupported claim
- Fail-Closed
```

Gemini는 RAW 값, EVENT timestamp, Ground Truth, Protection Logic, OT 상태를 수정할 수 없다.

### 5.3 실제 모델정보

- Provider: Google Gemini
- Exact model: **TBD — RC Freeze 시 실제 Runtime 설정값 기재**
- Invocation method: **TBD — 실제 Local TripLens 방식 기재**

---

## 6. 출력 구조

TripLens 결과는 긴 AI 문장 하나가 아니라 다음 항목으로 분리한다.

- **Incident Summary**: 사고상황 요약
- **Critical Events**: 핵심 Event 우선순위
- **Causal Timeline**: Origin → Direct Trigger → Protection/Trip → Propagation
- **Key Evidence**: 결론에 사용된 EVENT/RAW 근거
- **Affected Equipment**: 영향설비
- **Recovery Check**: 다음 확인사항

Recovery Check는 자동복구 명령이 아니라 운전원이 확인해야 할 항목을 제시하는 기능이다.

---

## 7. Verification 및 Fail-Closed

TripLens는 AI가 반드시 하나의 원인을 확정하도록 강제하지 않는다.

근거가 부족하거나 서로 충돌할 경우 다음 상태를 허용한다.

- `UNKNOWN`
- `INCONCLUSIVE`
- `REVIEW REQUIRED`
- `ADDITIONAL EVIDENCE REQUIRED`

검증질문:
1. 주요 주장에 실제 EVENT/RAW 근거가 있는가?
2. 사건순서가 timestamp와 모순되지 않는가?
3. 필요한 근거가 누락되어 있지 않은가?
4. 상충하는 설비상태가 존재하는가?
5. Ground Truth 또는 정답 metadata가 입력에 포함되지 않았는가?

---

## 8. 일반화와 Blind Validation

TripLens의 핵심 검증질문은 다음과 같다.

> **GT Trip 하나를 잘 설명하는가가 아니라, 서로 다른 사고 입력을 동일 TripLens Engine이 분석할 수 있는가?**

Blind Validation에서 TripLens에 제공하지 않는 정보:

- Scenario ID
- Expected Cause
- Root Cause answer label
- Ground Truth
- Fault injection metadata

분석완료 후 외부 Validator가 Ground Truth와 결과를 비교한다. 사고군별 Engine code는 수정하지 않는 것을 원칙으로 한다.

### 평가 Metric

| Metric | 목적 |
|---|---|
| Critical Event Precision | 불필요한 핵심사건 선정 여부 |
| Critical Event Recall | 중요한 사건 누락 여부 |
| Critical Event F1 | 핵심사건 추출 종합성능 |
| Causal Chain Accuracy | 사고흐름 재구성 정확도 |
| Evidence Grounding Rate | 실제 근거 연결성 |
| Unsupported Claims | 근거 없는 공학 주장 수 |
| Fail-Closed | 불완전 데이터에서 안전한 중단 여부 |
| Alarm/Event Compression | 전체 Event 대비 핵심 Event 축약 |
| Time-to-Insight | 핵심정보 확보시간 |

실제 RC Run 전까지 수치는 `NOT TESTED`로 유지한다.

---

## 9. 검증용 데이터 생성환경

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

## 10. 정량 검증결과

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

## 11. 실용성

TripLens가 직접 줄이려는 것은 물리적 정비시간 전체가 아니라 **사고 초기 정보탐색 및 진단에 필요한 시간**이다.

기대효과:
- Alarm Flood에서 핵심정보 우선제시
- EVENT와 RAW 교차검증
- 근거 Tag 기반 설명
- 사고보고/인수인계의 구조화
- 반복사고 비교를 위한 표준화

`Time-to-Insight`는 실제 시험으로 측정하며, 전체 MTTR 감소율로 과장하지 않는다.

---

## 12. 한계 및 현장 적용조건

- 현재 검증은 Virtual Plant/Synthetic 환경 기반
- 실제 현장 정확도 검증은 별도 필요
- 실제 발전소의 대규모 Tag 적용은 추가 성능검증 필요
- 승인 P&ID/SLD/C&E/정정값을 대체하지 않음
- 실제 현장 데이터의 외부 Gemini 사용은 별도 보안·거버넌스 필요
- TripLens는 READ-ONLY이며 OT 제어권한이 없음

---

## 13. 결론

TripLens는 발전소 사고 후 흩어진 EVENT와 RAW를 시간·설비·Evidence 관점에서 구조화하고, Gemini Agent가 이를 근거 중심의 사고흐름과 확인사항으로 변환하는 READ-ONLY 사고분석 시스템이다.

제출 전 가장 중요한 과제는 기능 추가가 아니라 **동일 RC 버전에서 다중사고 Blind Validation을 수행하고 그 결과를 정량 Scorecard로 제시하는 것**이다.
