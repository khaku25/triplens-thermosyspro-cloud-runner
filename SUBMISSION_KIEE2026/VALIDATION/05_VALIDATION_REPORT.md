# TripLens Blind Validation Report
## 제출 전용 Working Draft

> 실제 Run ID + Input Hash + 동일 RC Version + Ground Truth 대조가 있어야 공식 PASS로 기록한다.

## 1. 목적

TripLens가 특정 GT Trip 예시에 맞춘 분석기가 아니라, 서로 다른 사고 입력을 **동일 분석엔진으로** 처리할 수 있는지 검증한다.

## 2. 원칙

- 동일 RC 버전 사용
- 사고별 Engine code change = 0
- Scenario ID 비공개
- Expected Cause 비공개
- Ground Truth 비공개
- 결과 생성 후 외부 Validator 비교
- 실패 Run도 보존

## 3. 사고군

| Incident Family | 목적 | 상태 |
|---|---|---|
| GT Trip | 공정/보호 파급 분석 | NOT TESTED |
| 6.6 kV Feeder Fault | 전기고장 일반화 | NOT TESTED |
| Third Case | 다른 사고군 일반화 | NOT TESTED |
| Corrupted/Missing Evidence | Fail-Closed | NOT TESTED |

## 4. Scorecard

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
| Time-to-Insight | NOT TESTED |

## 5. Run Evidence 계약

각 Run은 최소 다음을 남긴다.

```text
RUN_ID/
├─ EVENT.csv
├─ RAW.csv
├─ manifest.json
├─ hashes.sha256
├─ TripLens_result.json
└─ metrics.json
```

Ground Truth는 TripLens 입력과 분리한다.

## 6. Fail-Closed 시험 후보

- Missing critical event
- Timestamp offset
- Duplicate event
- Out-of-order event
- BAD/Uncertain quality
- Missing breaker feedback

PASS 기준은 근거가 부족한 상황에서 부당하게 CONFIRMED하지 않는 것이다.
