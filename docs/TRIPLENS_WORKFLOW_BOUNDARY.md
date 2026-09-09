# TripLens 확정 데이터 경계

이 문서는 GitHub Action, 웹 변환부, 알람발생기, TripLens의 책임을 고정한다.
구현 편의를 위해 이 경계를 다시 합치지 않는다.

## 1. GitHub Action — 물리 원천 생성

입력된 물리 시나리오를 ThermoSysPro/OpenModelica로 계산하고 다음 두 파일만
Blind-test artifact로 게시한다.

- `thermosyspro-raw.csv`: OpenModelica 결과의 바이트 단위 원본 복사본
- `raw-manifest.json`: 해시, 행 수, 열, 시간범위, 실행엔진, 표본주기 및 책임 경계

Action은 다음 작업을 하지 않는다.

- ProcessBus 표준화 또는 태그명 변환
- 중복시각 행 제거, 보간, 재표본화, 사고구간 추출
- DCS1/DCS2 threshold 또는 logic 평가
- ECMS/Relay/차단기 사건 합성
- `gt_trip_cmd` 같은 관측되지 않은 명령 열 추가
- 사고명, 원인, 정답, ground truth를 Blind artifact에 포함

시뮬레이터가 물리 시나리오 입력을 아는 것은 필요하다. 다만 시나리오 입력과
평가 정답은 Blind artifact와 분리하며 TripLens 입력으로 전달하지 않는다. 모델이
실제로 출력한 명령·상태·`when` 변수는 정답 라벨이 아니라 원본 관측이므로
이름과 값을 바꾸지 않고 보존한다.

현재 등록된 물리 어댑터는 GT 배기경계 변화와 FWP-HP 속도경계 변화 두 개다.
기존 Workflow/파일명의 BFP는 legacy 표시 alias이며 실행 설비 ID는 FWP-HP다.
이들은 각각 특정 물리 모델이며 임의 사고를 자동 생성하는 범용 모델은 아니다.
새 사고는 해당 설비의 물리 어댑터를 추가한 뒤 같은 RAW-only 출력 계약을 쓴다.

## 2. 웹앱 RAW 변환부 — 표준화 및 관측 생성

웹앱은 매 실행마다 새 RAW를 읽고 승인된 버전의 Tag mapping, DCS Logic,
Alarm rule, ECMS Cause & Effect를 적용한다.

| 출력 | 의미 |
|---|---|
| `ProcessBus.csv` | 압력·온도·유량·RPM·출력·밸브개도·실제 디지털 상태의 표준 process stream |
| `DCS1.csv` | GT/ST 영역의 threshold·logic 결과와 복귀 이력 |
| `DCS2.csv` | HRSG/BOP 영역의 threshold·logic 결과와 복귀 이력 |
| `ECMS.csv` | 원본 전기 상태 또는 승인된 ECMS C&E가 뒷받침하는 사건 |

ProcessBus는 알람이 아니다. ECMS 로직이나 필요한 전기 입력이 없으면 ECMS 사건을
추측하지 않고 미생성/보류한다. 예제용 합성 규칙은 Blind 실행과 분리한다.

현재 기준 구현은 `scripts/convert_raw_observations.py`이며 RAW SHA-256을 전후
비교한다. `config/tag_alias_contract.csv`로 명칭·소유권을 정규화하고 1 ms 논리
timer에는 source sample zero-order hold를 적용한다. 공통 GT/ST Trip은
`config/common_trip_matrix.csv`를 실행한다.

## 3. 알람발생기 — 운전 화면 재생

- DCS1, DCS2, ECMS는 각 콘솔의 알람·이벤트로 시간순 재생한다.
- ProcessBus는 알람 스택에 섞지 않고 별도 Trend/공정값 화면에 표시한다.
- 원본시각, 논리동작시각, 플랫폼시각을 구분해 보존한다.

## 4. TripLens — 관측 기반 분석

입력은 `ProcessBus.csv`, `DCS1.csv`, `DCS2.csv`, `ECMS.csv` 네 종류다.

TripLens는 시간정렬, 변화량 분석, 알람 축약, 상관관계, 원인 후보, 검증 gate,
타임라인 및 보고서를 수행한다. 사고 유형·원인·설비를 입력 전에 선택하거나
정답 라벨에서 읽지 않는다. 필수 근거가 없으면 원인을 확정하지 않는다.

## 구현 상태

| 계층 | 확정 목표 | 현재 단계 |
|---|---|---|
| GitHub Action | RAW-only | GT·FWP-HP Workflow에 적용 |
| 웹 RAW 변환부 | RAW → ProcessBus/DCS1/DCS2/ECMS | 기준 Python 구현 및 회귀시험 완료; 웹 이관 대기 |
| 알람발생기 | 3개 알람 + 별도 Process Trend | 다음 변경 대상 |
| TripLens | 4종 관측 입력 | 입력 계약 확정; 제품 연결 대기 |

Action 저장소의 변환·DCS·ECMS Python 파일은 웹 변환부 이관을 위한 검증된 기준
구현이다. 두 RAW Action 실행 경로에서는 계속 호출하거나 업로드하지 않는다.
