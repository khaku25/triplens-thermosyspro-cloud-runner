# TripLens Multi-Scenario Blind Validation Report
## Current Validation Baseline

## 1. 목적

TripLens가 한 개 GT Trip 예시에 맞춘 분석기가 아니라, **원인과 보호결과가 서로 다른 사고 입력을 동일 분석구조로 처리할 수 있는지** 확인한다.

이번 결과는 실제 발전소 현장 성능시험이 아니라 동일 Current V8 합성환경 안의 반복 검증이다.

## 2. Blind 원칙

- Scenario ID / Name을 Agent 판단근거로 제공하지 않음
- Expected Cause / Ground Truth / Answer Label을 Agent 판단근거로 제공하지 않음
- 시뮬레이터 시험자만 아는 Fault Injection 내부 metadata를 Agent 근거에서 제외
- 실제 관측 Process / Alarm / Protection / Logic 상태는 Evidence로 사용 가능
- 사고별 전용 원인 답안표를 분석엔진에 제공하지 않음
- 실패·결측·불확실 결과를 삭제하지 않음

## 3. 검증 규모

- Distinct scenarios: **12**
- Cumulative analysis executions including re-validation: **21** (프로젝트 실행기록 기준)
- Inspection items: **20 per scenario**
- Final site-analysis failure reports: **12**
- Synthetic environment: **Windows Local Current V8**

## 4. 사고 시나리오

| # | Scenario | Category |
|---:|---|---|
| 01 | Direct GT Trip | Turbine / Protection |
| 02 | Direct ST Trip | Turbine / Protection |
| 03 | GT Breaker | Electrical / Breaker |
| 04 | IP BFP | BFP / Motor / VCB |
| 05 | HP Drum LL | HRSG / Drum Low |
| 06 | IP Drum LL | HRSG / Drum Low |
| 07 | IP Drum HH | HRSG / Drum High |
| 08 | HP Drum HH | HRSG / Drum High |
| 09 | HP BFP | BFP / Missing Evidence |
| 10 | LP BFP | BFP / Motor / VCB |
| 11 | LP Drum HH | HRSG / Drum High |
| 12 | LP Drum LL | HRSG / Drum Low |

## 5. 동일 평가기준

각 시나리오는 A01~A20 동일한 검사 항목을 사용한다.

| 영역 | 배점 |
|---|---:|
| 입력·데이터 | 10 |
| 사건·원인 인식 | 15 |
| 보호·파급 인과 | 30 |
| 근거·추적성 | 20 |
| 운전 대응 | 15 |
| 산출물 | 10 |

상태:
- GREEN: 기대결과 정확히 충족
- YELLOW: 부분 충족 또는 추가 확인 필요
- RED: 핵심 기능/분석 실패
- NOT TESTED: 실제 검증하지 않음

## 6. 9/21 내부 종합점수 기준선

당시 12개 시나리오 점수:

| Scenario | Score |
|---|---:|
| Direct GT | 88.0 |
| Direct ST | 88.0 |
| GT Breaker | 88.0 |
| IP BFP | 88.0 |
| HP Drum LL | 90.5 |
| IP Drum LL | 90.5 |
| IP Drum HH | 88.0 |
| HP Drum HH | 88.0 |
| HP BFP | 80.5 |
| LP BFP | 88.0 |
| LP Drum HH | 88.0 |
| LP Drum LL | 90.5 |

Mean: **88.0/100**

이 점수는 **AI 원인 정확도 88%가 아니다.** 입력, 원인/사건 인식, 보호·파급 인과, 근거추적, 운전대응, 산출물을 함께 평가한 내부 Engineering Inspection Score다.

이후 9/22~23 사이트 실분석 최종 PDF와 재검증이 추가되었으므로 위 점수는 당시 기준선으로 유지한다.

## 7. 대표 Fail-Closed 사례 — HP BFP

HP BFP 사례에서는 RAW 결측 구간 때문에 사고 개시시각과 일부 Trip Latch / 보호연쇄를 직접 확인할 수 없었다.

TripLens는:
- 원인을 후보 수준으로 유지
- 일부 인과항목 YELLOW/RED 처리
- 직접 확인하지 못한 항목 NOT TESTED 유지
- 추가 인터록/현장 확인을 요구

즉 근거 부족을 성공으로 덮지 않았다.

## 8. Evidence Traceability

각 분석에서:
- EVENT ID 또는 RAW 원본행+Tag Evidence ID를 유지
- Primary Cause / Direct Trigger / Propagation과 Evidence를 연결
- Tag Detail → Logic → Drawing/Equipment 탐색 가능
- 표본 사이 변화는 exact timestamp로 조작하지 않고 interval로 표현

## 9. 산출물

Drive에 01~12 각각의 `사이트실분석_최종` 고장상보가 보존되어 있다.

보고서에는:
- Primary Cause / Candidate
- Direct Trigger
- Propagation
- Critical Event
- Evidence IDs
- 상태(관측/후보/미확인)
- 추가 확인사항
- 시간대별 사건

을 포함한다.

## 10. 현재 남은 검증

- Critical Event Precision / Recall / F1 별도 정량계산
- Causal Edge Precision / Recall / F1 또는 오연결 수
- Time-to-Insight 최종 정량 측정
- 웹 UI CSV·근거 export 재확인
- PINPOINT download
- 모바일 전체 Acceptance / 세션 초기화
- 실제 발전소 현장 데이터 검증

## 11. 결론

TripLens는 현재 **동일 합성 복합화력 환경의 12개 서로 다른 사고 시나리오에서 반복 분석·근거추적·보고서 산출을 수행한 Validated Engineering Prototype 수준**으로 설명할 수 있다.

단, 이 결과를 실제 발전소 전체, 다른 topology, 모든 제조사 설비에 대한 일반화 성능으로 확대하지 않는다.
