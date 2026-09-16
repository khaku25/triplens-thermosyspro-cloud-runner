# TripLens 기술문서
## 발전소 EVENT + RAW 기반 Agentic AI 사고분석 시스템
### KIEE 2026 Agentic AI 경진대회 — RC0 Draft

---

## 1. 개요

발전소 Trip 또는 주요 설비고장 발생 시 DCS, ECMS, Protection, Historian에서 다수의 Alarm과 상태변화가 짧은 시간에 집중된다. 이때 운전원은 단순히 Alarm 개수를 줄이는 것보다 **최초 사건과 후속 파급을 구분하고, 실제 설비 응답을 근거로 현재 상황을 빠르게 구조화**해야 한다.

TripLens는 이를 위해 `EVENT.csv`와 `RAW.csv`를 결합한다.

- EVENT는 “무슨 일이 언제 발생했는가”를 표현한다.
- RAW는 “그 시점에 실제 설비와 공정이 어떻게 움직였는가”를 표현한다.

TripLens는 두 자료를 교차검증하고 Gemini 기반 Agentic AI가 근거 중심으로 사고 흐름을 설명하도록 설계되었다.

---

## 2. 목표와 범위

### 2.1 목표

1. 사고 직후 핵심 사건을 빠르게 식별
2. 최초 원인 후보와 후속 파급 분리
3. 판단에 사용한 Tag/Event 근거 제공
4. 복구 시 우선 확인사항 정리
5. 서로 다른 사고를 동일 분석엔진으로 처리
6. 근거 부족 시 확정판정을 회피

### 2.2 비목표

TripLens는 다음 기능을 수행하지 않는다.

- 보호계전 동작 대체
- DCS/ECMS 자동제어
- 자동복전
- 운전원 조작명령 생성
- 실제 발전소 승인 Logic 대체
- 합성검증 결과를 현장 정확도로 일반화

---

## 3. 현재 구현 기준

본 제출문서의 현재 구현 기준은 **Windows Local V8 Runtime**이다.

현재 로컬 기준의 핵심 구성은 다음과 같다.

- Native OPC UA
- ECMS / Protection / Alarm Runtime
- 9-cause GT/ST protection matrix
- independent GT/ST latch
- HP/IP BFP logical protection chain
- Plant-wide Alarm binding
- Live Historian
- EVENT.csv + RAW.csv Dual Log
- Gemini 사고분석 UI

최신 로컬 V8.5.2 검증 계약에서는 66개 writable Real input, 67개 live alarm rule binding, Dual Log E2E 등을 검증 대상으로 포함한다.

---

## 4. 데이터 계약

### 4.1 EVENT.csv

EVENT에는 사고 해석상 의미 있는 사건을 기록한다.

예시:
- Alarm ACTIVE / RETURN
- Protection Event
- Breaker Open
- Motor Deenergized
- Running Lost
- Operator PB
- Recovery Event

### 4.2 RAW.csv

RAW에는 수치·상태·명령·Logic의 원시 근거를 보존한다.

예시:
- Pressure / Temperature / Flow / Level
- Speed / Power
- Breaker state
- Trip Command
- Latch
- Logic state
- Internal command
- Quality / timestamp

### 4.3 V8.5.2 Dual Log 정책

정상적인 Alarm/Protection 사건은 EVENT에 남기며 내부 command 계열은 RAW evidence로 유지한다. 이를 통해 EVENT를 원인 정답표처럼 만들지 않고, 사람에게 의미 있는 SOE/Event로 유지한다.

---

## 5. Local V8 Virtual Plant / OPC UA / ECMS

### 5.1 Local Runtime

TripLens의 검증환경은 실제 발전소 Digital Twin으로 주장하지 않는다. 발전소 사고분석 Pipeline을 시험하기 위한 **검증용 Virtual Plant / Runtime**이다.

### 5.2 Native OPC UA

물리값, 상태값, 보호 Logic, 시험 Command가 OPC UA를 통해 전달된다.

현재 Runtime은 값 자체뿐 아니라 실행 중 주소공간을 기준으로 연결상태를 검증하도록 구성한다.

### 5.3 Protection

최신 V8 계열에서 다음이 핵심이다.

- GT/ST independent latch
- 9-cause common protection matrix
- GT breaker/open chain
- HP/IP BFP logical trip chain
- reset/reclose 구분

### 5.4 물리범위 제한

HP/IP BFP에 대해서는 Trip 이후 실제 축 coastdown을 완전 구현했다고 주장하지 않는다. 현재 안정판은 V7 물리경계를 보존하면서 Protection/Breaker 논리와 Historian 결과를 분리해 보여준다.

---

## 6. Engineering Core

TripLens의 Engineering Core는 AI 이전에 작동한다.

### 6.1 Input Validation
- 필수 열 존재 여부
- timestamp parsing
- source/system 확인
- 빈 값 / 품질 이상 탐지

### 6.2 Time Alignment
- EVENT와 RAW의 시간축 정렬
- 원시 timestamp 보존
- 보정 시 근거 기록

### 6.3 Evidence Extraction
- 사건 주변의 관련 Tag 추출
- Protection / Breaker / Process response 연결
- 원인 후보와 후속현상 후보 분리

### 6.4 Logic Context
- 등록된 Logic/Protection 관계 확인
- 입력 → 조건 → 출력 → 후속응답 구조화

### 6.5 Fail-Closed
근거가 부족하면 AI가 억지로 CONFIRMED하지 않도록 한다.

허용 상태:
- UNKNOWN
- INCONCLUSIVE
- REVIEW REQUIRED
- ADDITIONAL EVIDENCE REQUIRED

---

## 7. Gemini Agent

### 7.1 역할

Gemini는 Engineering Core가 제공하는 근거를 바탕으로 사고 흐름을 해석한다.

주요 역할:
- 핵심 사건 요약
- 원인 / 직접 계기 / 파급과정 설명
- Evidence 근거 연결
- 상충 근거 및 불확실성 설명
- Recovery Check 정리

### 7.2 금지사항

Gemini는 다음을 수정할 수 없다.

- RAW 값
- EVENT timestamp
- Protection Logic
- Ground Truth
- 승인된 엔지니어링 설정
- Verification 결과

### 7.3 모델 정보

- Provider: Google Gemini
- Exact model: **TBD — RC Freeze 시 Runtime 설정에서 확정**
- Invocation method: **TBD — 현재 실제 Runtime 방식 기준으로 기술**
- Prompt / Tool details: **RC Freeze 이후 제출본에 고정**

---

## 8. Verification Boundary

최종 결과는 AI 문장 자체가 아니라 **근거가 있는지**를 중심으로 평가한다.

검증 질문:
1. 주장에 실제 EVENT/RAW evidence가 있는가?
2. 사건 순서가 timestamp와 일치하는가?
3. 필수 근거가 누락되었는가?
4. 상충하는 상태가 있는가?
5. Ground Truth가 입력으로 누출되지 않았는가?

---

## 9. Blind Validation 방법

### 9.1 목적

GT Trip 하나에 맞춘 Demo가 아니라, 서로 다른 사고 입력을 동일 엔진으로 분석할 수 있는지 검증한다.

### 9.2 원칙

- 사고별 엔진 코드 수정 0
- Scenario ID 미입력
- Expected Cause 미입력
- Ground Truth 미입력
- 결과 생성 이후에만 외부 Validator가 정답과 대조
- 실패 Run도 보존

### 9.3 후보 사고군

1. GT Trip
2. 6.6 kV Feeder Fault
3. Third Case — RC Freeze 시 현재 V8 데이터 계약과 가장 잘 맞는 사고로 확정
4. Corrupted / Missing Evidence Case

SST Supply Loss는 현재 Virtual Plant topology와의 일치 여부를 재검토한 뒤, 실제 VPP 구현이 아니라면 별도 synthetic electrical benchmark로만 명시한다.

---

## 10. 정량 평가

### 10.1 Critical Event Precision

TripLens가 Critical Event로 선정한 사건 중 Ground Truth 핵심사건과 일치한 비율.

### 10.2 Critical Event Recall

Ground Truth 핵심사건 중 TripLens가 놓치지 않고 선정한 비율.

### 10.3 Critical Event F1

Precision과 Recall의 조화평균.

### 10.4 Causal Chain Accuracy

Ground Truth causal edge 중 TripLens가 올바른 방향으로 재구성한 비율.

### 10.5 Evidence Grounding Rate

최종 핵심 공학 주장 중 유효한 EVENT/RAW evidence reference를 가진 비율.

### 10.6 Unsupported Engineering Claims

근거 reference가 없거나 실제 입력에 존재하지 않는 공학 주장 수.

### 10.7 Fail-Closed

Missing evidence, timestamp offset, duplicate, out-of-order, BAD quality 등에서 부당하게 원인을 확정하지 않는지 평가한다.

### 10.8 Time-to-Insight

사고 데이터가 주어진 시점부터 사전에 정의한 핵심정보 세트를 확보하기까지의 시간.

**MTTR 전체 감소율로 표현하지 않는다.**

---

## 11. 현재 Scorecard

| Metric | Current |
|---|---:|
| Blind Runs | NOT TESTED |
| Engine Code Changes | NOT TESTED |
| Critical Event Precision | NOT TESTED |
| Critical Event Recall | NOT TESTED |
| Critical Event F1 | NOT TESTED |
| Causal Chain Accuracy | NOT TESTED |
| Evidence Grounding | NOT TESTED |
| Unsupported Claims | NOT TESTED |
| Fail-Closed | NOT TESTED |
| Alarm/Event Compression | NOT TESTED |
| Time-to-Insight | NOT TESTED |

실측 Run이 생성될 때마다 `06_VALIDATION_RESULTS.csv`와 Validation Report를 갱신한다.

---

## 12. 실용성

TripLens의 목표는 사고 복구작업 자체를 자동화하는 것이 아니라 **사고 초기 정보탐색과 판단지원 시간을 줄이는 것**이다.

기대효과:
- Alarm Flood에서 핵심 사건 우선 제시
- EVENT와 RAW 교차검증
- 근거 Tag 기반 설명
- 사고보고서 초안 구조화
- 반복 사고 비교를 위한 표준화

---

## 13. AI 활용 및 사용자 기여

자세한 내용은 `04_AI_USAGE_AND_LIMITATIONS.md`에 기록한다.

핵심 원칙:
- 문제 정의와 공학적 검증기준은 사용자 주도
- AI는 분석·설명·개발보조에 활용
- 실제 Runtime 결과와 검증근거를 사람이 확인
- AI가 임의로 정답/데이터를 만들어 성능을 주장하지 않음

---

## 14. 한계

- 합성/가상 환경 검증이며 현장 정확도 검증이 아님
- 실제 발전소 수천~수만 태그 확장은 향후 과제
- 일부 물리 transient는 검증범위가 제한됨
- 승인 P&ID/SLD/C&E/정정값을 대체하지 않음
- 실제 현장 데이터의 클라우드 AI 활용은 별도 보안/거버넌스 필요

---

## 15. 결론

TripLens는 Virtual Plant와 Local V8 Runtime에서 생성된 EVENT/RAW evidence를 바탕으로 발전소 사고를 구조화하고, Gemini Agent가 근거 중심의 원인·파급·복구 정보를 설명하는 READ-ONLY 사고분석 시스템이다.

제출 전 핵심 과제는 기능추가가 아니라 **동일 RC 버전으로 다중사고 Blind Validation을 수행하고 정량 Scorecard를 확정하는 것**이다.
