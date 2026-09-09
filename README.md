# TripLens ThermoSysPro RAW Runner / ECMS VPP Reference

GitHub Actions에서 ThermoSysPro/OpenModelica 물리 원천을 생성하는 저장소입니다.
기존 검증 경로의 공식 산출물은 `thermosyspro-raw.csv`와
`raw-manifest.json`뿐입니다. 별도 `VPP Modelica Event Engine` 경로에서는
알람·Trip Boolean을 모델 내부에서 계산하고 `VPP_EVENT.csv`로 직렬화합니다.
두 경로 모두 원인 추론이나 사고 정답은 만들지 않습니다.

저장소에 함께 있는 MATLAB ECMS VPP와 기존 Python 변환기는 웹 변환부 이관 및
예제 검증을 위한 참고 구현입니다. Action 실행 경로와는 분리되어 있습니다.
확정된 전체 책임 경계는
[`docs/TRIPLENS_WORKFLOW_BOUNDARY.md`](docs/TRIPLENS_WORKFLOW_BOUNDARY.md)를
기준으로 합니다.

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

## 실행 방식과 책임 경계

### MATLAB-native VPP

`ECMS_RUN`은 MATLAB Online만으로 즉시 실행됩니다. 편집기 기능과 사고 데이터
생성을 시험하기 위한 **명시적인 합성 fallback**이며, ThermoSysPro 결과나 현장
계측값으로 표시하지 않습니다. 각 Run은 `runs/MATLAB_*`에 먼저 임시 생성되고,
필수 파일 검증이 끝난 뒤에만 `latest_run.txt`가 갱신됩니다.

```matlab
ECMS_RUN
ECMS_RUN("FaultPreset","grid_loss")
ECMS_RUN("CommandFile","examples/bfp_trip_commands.csv")
ECMS_RUN("SamplingProfile","incident_1ms")
```

MATLAB 합성 fallback에서도 마지막 명령처럼 사고 전·후 1 ms 구간을 추가할 수
있습니다. 이 결과는 계속 `MATLAB_NATIVE_SYNTHETIC_FALLBACK`으로 표시되며,
ThermoSysPro 물리 실행으로 취급되지 않습니다.

### ThermoSysPro Cloud Action

기존 RAW-only Workflow와 별도의 Modelica Event Workflow가 등록되어 있습니다.

| Workflow | 물리 어댑터 | Action 산출물 |
|---|---|---|
| `Generate ThermoSysPro RAW (GT physical adapter)` | GT 배기 유량·온도 경계 변화 | RAW CSV + 무라벨 manifest |
| `Generate ThermoSysPro RAW (BFP physical adapter)` | HP BFP 회전속도 경계 변화 | RAW CSV + 무라벨 manifest |
| `Generate VPP RAW and Modelica-owned events` | 검증된 HP BFP 속도 경계 + 모델 내부 알람·보호 | VPP RAW + VPP/DCS1/DCS2 Event |

각 Workflow는 고정 ThermoSysPro commit과 OpenModelica 이미지를 사용합니다.
OpenModelica 결과를 바이트 그대로 복사한 뒤 해시와 구조를 검증하며, 실패한
실행은 artifact를 게시하지 않습니다. `fault_preset`, ECMS Command, DCS 규칙,
사고 정답은 Action 입력 또는 산출물에 포함하지 않습니다.

VPP Event Workflow의 구조·40개 임시 규칙·교체 방법은
[`docs/VPP_EVENT_ENGINE_PROVISIONAL.md`](docs/VPP_EVENT_ENGINE_PROVISIONAL.md)를
참조합니다. 이 경로에서 CSV 변환기는 임계값을 계산하지 않고 Modelica Boolean
상태 변화만 기록하므로 알람 화면을 모니터 전용으로 연결할 수 있습니다.

### CSV 시간 해상도 선택

GT 물리 어댑터의 `sampling_profile`에서 세 RAW 출력 방식을 선택할 수 있습니다.

| 프로필 | ThermoSysPro RAW CSV | 용도 |
|---|---:|---|
| `causal_100ms` (기본값) | 전체 0.1 s | 사고 전·후 물리 변화 검토 |
| `standard` | 입력한 종료시간/구간 수 | 임의 장시간 해상도 |
| `incident_1ms` | 0~10 s 전체 1 ms | 짧은 물리 변화 정밀 확인 |

`causal_100ms`는 기본 입력인 사건시각 600 s, 종료 1000 s를 유지하면서 물리
CSV를 0.1 s 간격으로 출력합니다. BFP 어댑터는 `stop_time_s / output_intervals`
간격의 표준 RAW를 출력합니다. 어떤 프로필도 알람 시각이나 ECMS 사건을 만들지
않습니다.

`incident_1ms`는 사건시각 2 s, 경계 변화 5 s, 종료 10 s, 출력구간 10,000개인
제한된 진단용 실행입니다.

여기서 1 ms는 **CSV 출력 시각 간격**입니다. OpenModelica의 DASSL 적분기는
정확도 조건에 따라 내부 계산 간격을 자동 조절하므로 “솔버가 항상 1 ms 고정
스텝으로 계산했다”는 뜻은 아닙니다. 알람/SOE의 밀리초 시각은 이후 웹 변환부가
승인된 논리와 실제 RAW crossing을 적용해 별도로 생성해야 합니다.

## Action 결과 파일

| 파일 | 역할 |
|---|---|
| `thermosyspro-raw.csv` | OpenModelica native 결과의 바이트 단위 복사본 |
| `raw-manifest.json` | SHA-256, 행·열·시간범위, 엔진·표본 설정, RAW-only 경계 |

기존 `processbus.csv`, `DCS1.csv`, `DCS2.csv`, `ECMS.csv`, 사고창과 정답 파일은
Action artifact가 아니다. 관련 Python 코드는 다음 웹 변환부 구현 때 검토·이관할
참고자료로만 남겨 두었다.

현재 GT 어댑터는 독립적인 GT 내부고장을 계산하는 모델이 아니라 배기 경계가
변하는 물리 예제이고, BFP 어댑터도 HP BFP 속도 경계 변화 예제다. 따라서 어느
Workflow도 임의 사고 범용 생성기로 표시하지 않는다.

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
함수 계약, 표준 20 ms·사고창 1 ms·인과검토 100 ms 표본 계약과 DCS 알람의
실제 임계값 통과 여부를 검사합니다. 최종 UI·자체실행은 MATLAB Online의
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
