# Event contract fixtures

`ecms_fwp_hp_actual_trip_transitions.csv`는 R&D 저장소의 GitHub Actions run
`34322671655`가 생성한 `ecms_fwp_hp_raw_1ms.csv` 30,001행에서 Event 경계 검증에
필요한 실제 상태 전이 행만 추출한 fixture다.

해당 Action 자체는 기존 exporter가 차단기 OPEN을 `18.080 s`로 기대해 실패했고,
RAW artifact는 `if: always()` 단계에서 보존됐다. 따라서 이 fixture는 “Action
PASS” 증거가 아니라 실제로 기록된 시뮬레이션 상태와 timestamp의 회귀 증거다.

값이나 시각을 보정하지 않았다. 이 run에서 최초 `VCB_A01_CLOSED=0`은
`18.081 s`이며, validator는 이 값을 `18.080 s`로 이동시키지 않는다.
