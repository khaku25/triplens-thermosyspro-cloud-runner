# TripLens Blind Validation Report
## RC0 Draft — 실제 시험값 입력 전

> 원칙: 실제 Run ID + Input Hash + 동일 RC Version + Evidence + Ground Truth 대조가 있어야 공식 PASS로 인정한다.

## 1. 검증 목적

TripLens가 특정 GT Trip 예시에 맞춘 분석기가 아니라, 서로 다른 사고 입력을 **동일 분석엔진으로** 처리할 수 있는지 검증한다.

## 2. 시험 원칙

- 동일 RC 버전 사용
- 사고별 Engine code change = 0
- Scenario ID 비공개
- Expected Cause 비공개
- Ground Truth 비공개
- 결과 생성 후 외부 Validator가 비교
- 실패 Run 삭제 금지

## 3. 시험 사고군

| Incident Family | 목적 | 상태 |
|---|---|---|
| GT Trip | 공정/보호 파급 분석 | NOT TESTED |
| 6.6 kV Feeder Fault | 전기고장 일반화 | NOT TESTED |
| Third Case | 다른 사고군 일반화 | NOT TESTED |
| Missing/Corrupted Evidence | Fail-Closed 안전성 | NOT TESTED |

Third Case는 RC Freeze 시 현재 V8 topology와 데이터 계약을 기준으로 확정한다.

## 4. Metrics

### Critical Event Precision
`TP / (TP + FP)`

### Critical Event Recall
`TP / (TP + FN)`

### Critical Event F1
`2PR / (P + R)`

### Causal Chain Accuracy
Ground Truth causal edge 중 올바른 방향으로 재구성한 edge 비율.

### Evidence Grounding Rate
최종 핵심 공학 주장 중 실제 EVENT/RAW reference를 가진 비율.

### Unsupported Engineering Claims
유효한 evidence 없이 생성된 공학적 핵심 주장 수.

### Fail-Closed
불완전/교란 데이터에서 부당하게 CONFIRMED하지 않는 시험의 통과율.

### Alarm/Event Compression
전체 입력 사건 대비 최종 Critical Event 수.

### Time-to-Insight
사고 데이터 제공부터 사전 정의한 핵심정보 세트를 확보하기까지의 시간.

## 5. 공식 Scorecard

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
| Alarm/Event Compression | NOT TESTED |
| Mean Analysis Time | NOT TESTED |
| Human Time | NOT TESTED |
| Time-to-Insight Reduction | NOT TESTED |

## 6. Run Evidence 계약

각 Run은 다음을 남긴다.

```text
Run ID
├─ EVENT.csv
├─ RAW.csv
├─ manifest.json
├─ hashes.sha256
├─ TripLens_result.json
├─ metrics.json
└─ evidence/
```

Ground Truth는 입력폴더와 분리한다.

```text
ground_truth/
└─ <RUN_ID>.json
```

## 7. Corruption Test 후보

- Missing critical event
- Timestamp offset
- Duplicate event
- Out-of-order event
- BAD/Uncertain quality
- Missing breaker feedback

PASS 기준:
- 근거가 불충분한데 원인을 확정하지 않음
- 필요한 추가 evidence를 명시함
- 잘못된 Ground Truth 힌트를 사용하지 않음

## 8. 현재 로컬 Runtime의 사전 검증 근거

Blind Score와는 별개로, V8.5.2 로컬 Runtime은 다음 기능검증 계약을 가진다.

- independent GT/ST latch
- 9 protection causes
- 67-rule live alarm binding
- EVENT + RAW E2E Dual Log
- current Alarm/Protection events retained in EVENT
- command-tag leakage rejected

이 항목들은 **Blind 분석 정확도 점수와 합산하지 않는다.**

## 9. 시험 완료 후 추가할 것

각 사고군별:
- Ground Truth causal chain
- TripLens critical event set
- Precision/Recall/F1
- Causal edge 비교
- Evidence Grounding
- Unsupported Claim
- Analysis time
- 코드변경 여부
- Screenshot / result link
