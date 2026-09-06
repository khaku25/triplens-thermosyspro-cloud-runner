# TripLens ECMS VPP 3.1

MATLAB Online에서 6.9 kV ECMS 계통을 직접 편집하고, A 설정과 Command를
실행해 새 결과를 만든 뒤 검토하는 통합 패키지입니다. GitHub Actions에서는
ThermoSysPro/OpenModelica 물리 결과를 같은 ECMS 계약에 연결할 수 있습니다.

## MATLAB Online에서 가장 빠른 시작

ZIP을 MATLAB Drive에 압축 해제한 뒤 **압축 해제된 패키지 최상위 폴더**에서
다음 한 줄을 실행합니다.

```matlab
ECMSVPP
```

큰 버튼 네 개가 있는 시작 화면이 열립니다.

| 버튼/명령 | 하는 일 |
|---|---|
| `ECMS_START` | ECMS 배선·A 설정·Command를 편집 |
| `ECMS_RUN` | 현재 기본 CSV로 새 MATLAB VPP Run을 생성 |
| `ECMS_RESULT` | 마지막으로 완전히 생성된 Run을 열고, 없으면 번들 예제를 열기 |
| `ECMS_DIAGNOSE` | 누락 파일·구형 함수 가림·6.9 kV 계약을 읽기 전용으로 점검 |
| `ECMS_SELF_TEST` | 정상·계통상실·펌프 Trip을 임시 폴더에서 자체 시험 |

`run_cloud_result`는 계산기가 아니라 **이미 생성된 결과를 그리는 내부
뷰어**입니다. 새 계산을 만들려면 `ECMS_RUN` 또는 Editor의
`현재 A/Command로 실행`을 누릅니다.

처음 `ECMS_RESULT`에서 열리는 번들 예제는 화면과 파일 구조 확인용
`BUNDLED_SYNTHETIC_DEMO`이며 실제 ThermoSysPro 계산으로 표시되지 않습니다.

## Editor 3.1

- Overview 설비를 드래그해 배치 변경
- 배선을 직접 눌러 선택(기본 5 px, 선택 9 px의 모바일 터치 폭)
- `가로→세로`, `세로→가로`, `세로→가로→세로`,
  `가로→세로→가로` 네 직각 경로와 꺾임 좌표 편집
- `전체 배선 자동 정리`로 대각선 없는 직각 배선 재배치
- BUS-A/B를 눌러 6.9 kV 피더 상세 열기
- A 설정·설비 BUS·피더·정격·정상 차단기 상태 편집
- 잠긴 M 물리 연결 201개와 ECMS 연결 10개 조회
- 26개 설비의 Command 94개를 버튼으로 시간 예약
- Command 큐 CSV 불러오기·저장
- 화면의 저장하지 않은 A/Command 값으로 바로 MATLAB VPP 실행
- 현재 화면값으로 Overview/6.9 kV 상세 SVG 생성

배선의 **모양과 설비 위치**는 사용자가 바꿀 수 있지만, 잘못된 계통을
사실처럼 만드는 것을 막기 위해 설비 ID와 배선 시작점·종점·계통은 잠겨 있습니다.
즉 요청한 대로 기존 접속관계는 유지하면서 모든 배선을 직각으로 편집합니다.

## 고정 ECMS 계통 골격

- 154 kV BUS-A/B
- GTG — 52GT — GT 저압측 TAP — GT 주 변압기 — 154 kV 계통
- STG — 52ST — ST 저압측 TAP — ST 주 변압기 — 154 kV 계통
- GT TAP — UAT-A — A Incoming — 6.9 kV BUS-A
- ST TAP — UAT-B — B Incoming — 6.9 kV BUS-B
- BUS-A/B 사이 모선연락차단기
- 별도 SST 없음

발전기가 정지하고 계통이 살아 있으면 GT/ST 주 변압기가 역수전 방향으로
UAT와 6.9 kV 모선에 전원을 공급할 수 있습니다. 승인된 동기검정 모델이 없으므로
두 전원의 병렬은 기본적으로 금지됩니다.

## 데이터 계층

- **M(Model)**: ThermoSysPro 물리 원본과 잠긴 태그·연결
- **A(Assumption)**: 전압·정격·보호지연·설비배치·초기상태
- **C(Calculated)**: 전압·전류·전력방향
- **E(Event/ECMS)**: 차단기·Relay·SOE·통신품질
- **CommandBus**: 시각·설비·명령·값·실행계층·피드백 태그

M은 읽기 전용입니다. A와 Command를 바꾸면 C/E만 새 Run에 계산되며 기존
Run은 덮어쓰지 않습니다.

## 두 실행 방식의 차이

### MATLAB-native VPP

`ECMS_RUN`은 MATLAB Online만으로 즉시 실행됩니다. 편집기 기능과 사고 데이터
생성을 시험하기 위한 **명시적인 합성 fallback**이며, ThermoSysPro 결과나 현장
계측값으로 표시하지 않습니다. 각 Run은 `runs/MATLAB_*`에 먼저 임시 생성되고,
필수 파일 검증이 끝난 뒤에만 `latest_run.txt`가 갱신됩니다.

```matlab
ECMS_RUN
ECMS_RUN("FaultPreset","grid_loss")
ECMS_RUN("CommandFile","examples/bfp_trip_commands.csv")
```

### ThermoSysPro Cloud pipeline

GitHub Actions의 `Run ThermoSysPro GT Trip`은 고정 ThermoSysPro commit과
OpenModelica 이미지로 물리 입력을 만든 뒤 동일한 ECMS trend/event/feeder
계약을 생성합니다. 새 요청이 들어오면 같은 브랜치의 오래 대기하던 Run은
취소하며, 실패한 Run은 정상 결과 artifact로 게시하지 않습니다.

지원 FaultBus:

- `none`
- `gtg_breaker_fail`
- `uat_a_fault`, `uat_b_fault`
- `gt_transformer_receive_fail`, `st_transformer_receive_fail`
- `bus_a_fault`, `bus_b_fault`
- `grid_loss`
- `relay_fail`
- `ecms_comms_loss`

## 주요 결과 파일

| 파일 | 역할 |
|---|---|
| `processbus.csv` | 물리/합성 입력과 GT Trip 시각 |
| `ecms-trend.csv` | 전압·전류·전력방향·차단기 상태 |
| `ecms-events.csv` | 시간순 Relay·차단기·FaultBus·Command 사건 |
| `ecms-feeders.csv` | A 설비표를 반영한 피더별 차단기·충전·전압·전류 |
| `manifest.json` | 실행방식·출처·시나리오·행 수·제한사항 |
| `config/ecms_a_settings.csv` | A 정격·보호·계산 설정 |
| `config/ecms_a_equipment.csv` | A 피더·BUS·정격·초기상태 |
| `config/ecms_command_catalog.csv` | 허용 Command 94개의 계약 |

## 실행 오류 복구

다른 폴더의 구형 함수가 MATLAB 경로를 가리는지 먼저 확인합니다.

```matlab
ECMS_DIAGNOSE
which -all triplens_ecms_vpp_editor
which -all triplens_ecms_vpp_simulate
which -all run_cloud_result
```

패키지 파일을 교체한 직후라면 기존 창을 닫은 뒤 최상위 폴더에서 다시 실행합니다.

```matlab
clear functions
rehash
ECMS_DIAGNOSE
ECMS_SELF_TEST
ECMSVPP
```

`triplens_ecms_editor`는 오래된 호출을 위한 호환 래퍼일 뿐입니다. 새 작업은
항상 고유 진입점 `ECMSVPP` 또는 `ECMS_START`로 시작합니다.

## 검증

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_commands.py --commands examples/bfp_trip_commands.csv
```

Python 회귀시험은 A 설정 반영, 모든 FaultBus, Command 계약, 피더 출력,
저전압 지연, 통신품질, 산출물 SHA-256, 과거 결과 재사용 방지와 MATLAB 공개
함수 계약을 검사합니다. 최종 UI·자체실행은 MATLAB Online의
`ECMS_DIAGNOSE`와 `ECMS_SELF_TEST`로 확인합니다.

## 제한

현재 A값은 `PROVISIONAL`이며 승인된 보호정정치나 발전소 SLD가 아닙니다.
이 VPP는 EMT/RMS 전력계통 해석기나 운전·정비·LOTO 도구가 아닙니다.
MATLAB 합성 Run, ThermoSysPro Run, 현장 Raw Data를 서로 바꾸어 표기하면 안 됩니다.

고정 실행 기반:

- OpenModelica `openmodelica/openmodelica:v1.27.0-minimal`
- ThermoSysPro `Dwarf-Planet-Project/ThermoSysPro`
- ThermoSysPro commit `db81ae1b5a6a85f6c6c7693244cafa6087e18ff5`
- Modelica Standard Library `3.2.3+maint.om`
