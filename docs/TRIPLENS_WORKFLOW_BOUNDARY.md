# TripLens 확정 데이터 경계

최종 외부 인터페이스는 `TRIPLENS_EVENT_V1`의 `EVENT.csv` 하나다.
상세 구조와 실행 계약은
[`VPP_EVENT_ARCHITECTURE_V1.md`](VPP_EVENT_ARCHITECTURE_V1.md)를 기준으로 한다.

## 고정 원칙

1. ThermoSysPro RAW와 ECMS RAW는 VPP 내부 검증·재현에만 사용한다.
2. H/HH/L/LL, Trip, Breaker, Run Feedback은 VPP 내부의 결정론적 Logic이 판정한다.
3. Event Observer는 판정된 상태의 변화만 `public/EVENT.csv`로 기록한다.
4. 알람발생기는 `EVENT.csv`를 그대로 재생하며 RAW를 읽지 않는다.
5. TripLens AI도 동일한 `EVENT.csv`만 읽는다.
6. 시나리오명, 원인, 정답, ground truth는 `EVENT.csv`에 넣지 않는다.
7. 같은 시각의 상태변화는 시간을 이동시키지 않고 `same_time_order`로 보존한다.

## 구현 상태

| 항목 | 상태 |
|---|---|
| Event V1 스키마와 금지열 | 구현 |
| ECMS RAW Boolean 상태변화 Observer | 구현 |
| DCS1/DCS2/ECMS 단일 Event 병합기 | 구현 |
| public Event / internal RAW 물리 분리 gate | 구현 |
| 알람발생기·AI 공용 Event-only reader | 구현 |
| 실제 30,001행 FWP-HP ECMS RAW 회귀검증 | 구현 |
| ThermoSysPro FWP-HP 물리 E2E Event 추가 | 물리 E2E 완료 후 동일 인터페이스로 연결 |
| 기존 웹앱의 4파일 입력 제거 | 웹앱 migration 단계 |

과거의 `ProcessBus.csv + DCS1.csv + DCS2.csv + ECMS.csv` 외부 입력 계약은
이 문서로 대체한다. 필요한 RAW와 분할 Event는 VPP 내부 증빙으로 남길 수 있지만,
알람발생기와 AI의 공식 입력으로 사용하지 않는다.
