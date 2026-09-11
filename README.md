# TripLens ThermoSysPro RAW Runner / ECMS VPP Reference

GitHub Actions에서 ThermoSysPro/OpenModelica 물리 원천을 생성하는 저장소입니다.
Action의 공식 산출물은 `thermosyspro-raw.csv`와 `raw-manifest.json`뿐입니다.
ProcessBus 변환, DCS 알람 판정, ECMS 사건 생성과 원인 추론은 수행하지 않습니다.

저장소에 함께 있는 MATLAB ECMS VPP와 Python 변환기는 웹 변환부 이관 및
예제 검증을 위한 실행 가능한 기준 구현입니다. Action 실행 경로와는 분리되어
있으며, RAW를 변경하지 않고 네 관측 계층으로 변환합니다.
확정된 전체 책임 경계는
[`docs/TRIPLENS_WORKFLOW_BOUNDARY.md`](docs/TRIPLENS_WORKFLOW_BOUNDARY.md)를
기준으로 합니다.

## MATLAB Online에서 가장 빠른 시작

ZIP을 MATLAB Drive에 압축 해제한 뒤 **압축 해제된 패키지 최상위 폴더**에서
다음 한 줄을 실행합니다.

```matlab
ECMSVPP
```

큰 버튼 다섯 개가 있는 시작 화면이 열립니다.

| 버튼/명령 | 하는 일 |
|---|---|
| `ECMS_START` | ECMS 배선·A 설정·Command를 편집 |
| `ECMS_RUN` | 현재 기본 CSV로 새 MATLAB VPP Run을 생성 |
| `ECMS_RESULT` | 마지막으로 완전히 생성된 Run을 열고, 없으면 번들 예제를 열기 |
| `ECMS_GITHUB` | GitHub의 MATLAB→OPC UA→ThermoSysPro 3.1 실행을 호출하고 물리 결과를 Cloud ECMS로 가져오기 |
| `ECMS_DIAGNOSE` | 누락 파일·구형 함수 가림·6.9 kV 계약을 읽기 전용으로 점검 |
| `ECMS_SELF_TEST` | 정상·계통상실·펌프 Trip을 임시 폴더에서 자체 시험 |

`run_cloud_result`는 계산기가 아니라 **이미 생성된 결과를 그리는 내부
뷰어**입니다. 새 계산을 만들려면 `ECMS_RUN` 또는 Editor의
`현재 A/Command로 실행`을 누릅니다.

### GitHub OPC UA와 Cloud ECMS 연결

`ECMS_GITHUB`은 `khaku25/triplens-matlab-cosim-runner`의 검증된
`matlab-native-opcua-ecms.yml`을 호출합니다. GitHub에서는 Simulink가 운전 중
52GT OPEN 명령과 실제 `52GT.CLOSED=1→0` 피드백을 순서대로 만든 뒤, 그 피드백에서
도출된 GT Trip 요청만 OPC UA로 native OpenModelica/ThermoSysPro 3.1에 씁니다.
같은 연결로 바이패스를 포함한 물리 피드백을 읽습니다. 내려받은 수신 CSV는 변경하지
않으며, ProcessBus, DCS1/DCS2, ECMS 계산은 이 Cloud 패키지에서만 수행합니다.

먼저 GitHub fine-grained token에 해당 저장소의 **Actions read/write** 권한을 주고,
토큰을 파일이나 MATLAB 코드에 적지 말고 환경변수로만 설정합니다.

```matlab
setenv("TRIPLENS_GITHUB_TOKEN","github에서 만든 토큰")
ECMS_GITHUB
```

실행 후 `runs/MATLAB_GITHUB_OPCUA_*`에 원본 OPC UA 수신 CSV, 증명 JSON,
ProcessBus, DCS1/DCS2 및 ECMS 결과가 함께 저장되고 `ECMS_RESULT`가 같은 결과를
다시 엽니다. Editor의 `GitHub OPC UA 52GT 개방→GT Trip 실행` 버튼은 현재 A
설정과 설비표를 후단 Cloud 계산에 적용합니다. 원격 원인 입력은 현재 검증 계약대로
0.25초의 운전 중 52GT 개방 한 종류이며, 현장 ECMS 로직은 사용하지 않습니다.
`GT_IN_SERVICE AND NOT 52GT.CLOSED`는 VPP 잠정 정책으로 명시됩니다. Editor의
임의 Command 큐를 원격 물리에 보내지는 않습니다.

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
- 잠긴 M 물리 태그 201개와 실행 설비 M 연결 5개 조회
- 24개 설비 ID의 Command 87개를 버튼으로 시간 예약
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

표준 소유권은 `CommandBus → 보호/제어`, `ECMS → 차단기·Relay·전기상태`,
`DCS1/DCS2 → 운전·공정 알람`, `ProcessBus → RPM·유량·압력·수위`입니다.
공정 물리량을 `ECMS.*.PHYS`로 복제하지 않습니다.

유량의 공개 단위는 전 계층에서 `t/h`입니다. Tag Master, ProcessBus의
`*_t_h` 필드, DCS 임계값·히스테리시스, VPP/ECMS 이벤트와 GitHub RAW alias가
같은 계약을 사용합니다. 물리 솔버 내부 값은 출력 경계에서 정확히 3.6배로 한 번만
변환됩니다.

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

공통 Trip은 `config/common_trip_matrix.csv`가 실행 원본입니다. GT Trip은 GT와
ST를 함께 요청하고, Drum HH는 ST만, Drum LL은 GT와 ST를 함께 요청합니다.
STG Active Power는 추세·전류계산용 측정값만 유지하며 H/HH/L/LL 및
`stg_low_state`를 만들지 않습니다. FWP 정상 STOP은
VCB를 닫힌 상태로 유지하고, TRIP만 latch와 VCB 개방을 발생시키며 RESET만으로는
재투입되지 않습니다.

### ThermoSysPro Cloud Action (RAW-only)

두 Workflow가 현재 등록되어 있습니다.

| Workflow | 물리 어댑터 | Action 산출물 |
|---|---|---|
| `Generate ThermoSysPro RAW (GT physical adapter)` | GT 배기 유량·온도 경계 변화 | RAW CSV + 무라벨 manifest |
| `Generate ThermoSysPro RAW (BFP physical adapter)` | FWP-HP 회전속도 경계 변화(Workflow명은 legacy) | RAW CSV + 무라벨 manifest |

두 Workflow 모두 고정 ThermoSysPro commit과 OpenModelica 이미지를 사용합니다.
OpenModelica 결과를 바이트 그대로 복사한 뒤 해시와 구조를 검증하며, 실패한
실행은 artifact를 게시하지 않습니다. `fault_preset`, ECMS Command, DCS 규칙,
사고 정답은 Action 입력 또는 산출물에 포함하지 않습니다.

### CSV 시간 해상도 선택

GT 물리 어댑터의 `sampling_profile`에서 세 RAW 출력 방식을 선택할 수 있습니다.

| 프로필 | ThermoSysPro RAW CSV | 용도 |
|---|---:|---|
| `causal_100ms` (기본값) | 전체 0.1 s | 사고 전·후 물리 변화 검토 |
| `standard` | 입력한 종료시간/구간 수 | 임의 장시간 해상도 |
| `incident_1ms` | 0~10 s 전체 1 ms | 짧은 물리 변화 정밀 확인 |

`causal_100ms`는 기본 입력인 사건시각 600 s, 종료 1000 s를 유지하면서 물리
CSV를 0.1 s 간격으로 출력합니다. FWP-HP 어댑터(legacy BFP 파일명)는 `stop_time_s / output_intervals`
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
Action artifact가 아니다. 관련 Python 코드는 웹 변환부가 그대로 이관·대조할 수
있는 실행 가능한 기준 구현으로 유지한다.

Action에서 내려받은 RAW는 로컬 기준 변환기로 다음처럼 분리할 수 있습니다.

```bash
python3 scripts/convert_raw_observations.py \
  --input svgBFP_TRIP_ECMS_RAW_5s_1ms.csv \
  --event-time 1 \
  --output-dir outputs/fwp_hp_observations
```

출력은 `ProcessBus.csv`, `DCS1.csv`, `DCS2.csv`, `ECMS.csv`와 추세·피더·매핑
검토·manifest입니다. 원본 SHA-256을 전후 비교하며 사고명이나 원인 정답을 넣지
않습니다. 1 ms DCS timer는 RAW 표본 사이를 선형보간하지 않고 zero-order hold로
평가합니다.

현재 GT 어댑터는 독립적인 GT 내부고장을 계산하는 모델이 아니라 배기 경계가
변하는 물리 예제이고, FWP-HP 어댑터도 HP FWP 속도 경계 변화 예제다. 따라서 어느
Workflow도 임의 사고 범용 생성기로 표시하지 않는다.

## 등록된 VPP Baseline 및 GT Trip 통합 실행

`config/vpp_baseline_v1.json`은 특정 발전소 복제가 아닌 공개 가능한 가상플랜트
`VPP_BASELINE_V1`의 잠긴 설계 기준입니다. 기존 CSV 설정표는 MATLAB/Python 실행
테이블로 계속 사용하며, JSON은 정격·동작시간·알람 규칙·공통 Trip 관계가 서로
갈라지지 않았는지 실행 전에 검증하는 단일 진입점입니다. `LOCKED`는 VPP 설계값을
고정했다는 뜻이고, CSV의 `PROVISIONAL`은 현장 승인값이 아니라는 뜻이므로 서로
충돌하지 않습니다.

GT Trip 생성과 내장 알람/Event 계층은 한 명령으로 실행합니다.

```bash
python3 scripts/run_vpp_gt_trip.py --output-dir outputs/GT_TRIP_01
```

기본 실행은 사고 전 1초·사고 후 4초·1 ms로 5,001행을 생성합니다. 장시간
프로필은 다음처럼 선택합니다.

```bash
python3 scripts/run_vpp_gt_trip.py \
  --output-dir outputs/GT_TRIP_01_LONG \
  --pre-seconds 300 --post-seconds 120 --step-ms 1
```

한 번의 실행으로 `VPP.RAW.csv`, `ProcessBus.csv`, `VPP.EVENT.csv`, `DCS1.csv`,
`DCS2.csv`, `ECMS.csv`, 추세·피더 및 `VPP.MANIFEST.json`을 만듭니다. 요청한
TripLens·알람표시기 입력용 `ECMS_EVENT.csv`와 `VPP_EVENT.csv`도 생성합니다.
전자는 ECMS 사건/알람만, 후자는 DCS1·DCS2·ECMS 사건/알람을 시간순으로 모은
희소 이벤트 파일이며 연속 RAW·추세 표본은 포함하지 않습니다. RAW에는
시나리오명·원인·정답 열을 넣지 않으며, 자동검증용 `GT_TRIP_01.expected.json`은
별도 파일로 격리합니다. GitHub Actions의 `Run VPP GT Trip Scenario`에서도 같은
진입점을 실행하며 Blind 재생 묶음과 검증 Oracle을 서로 다른 artifact로 게시합니다.

## 표준 명칭

- 프로젝트명은 `VPP`; `VVP`는 legacy alias입니다.
- 설비 ID는 `FWP-HP`, `FWP-IP`, `FWP-LP`; “HP BFP”는 화면 표시명으로만 허용합니다.
- ThermoSysPro native `MP`/`BP`는 RAW에서 보존하고 ProcessBus 경계에서 `IP`/`LP`로 바꿉니다.
- 차단기 표준 태그는 `ECMS.52GT.CLOSED`, `ECMS.CB-IN-A.CLOSED`,
  `ECMS.VCB-A01.CLOSED` 형식입니다.

전체 alias와 소유권은 `config/tag_alias_contract.csv`가 기준입니다.

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
python3 config/audit_trip_semantics.py
```

Python 회귀시험은 A 설정 반영, 모든 FaultBus, Command 계약, 피더 출력,
저전압 지연, 통신품질, 산출물 SHA-256, 과거 결과 재사용 방지와 MATLAB 공개
함수 계약, 표준 20 ms·사고창 1 ms·인과검토 100 ms 표본 계약과 DCS 알람의
실제 임계값 통과 여부를 검사합니다. 최종 UI·자체실행은 MATLAB Online의
`ECMS_DIAGNOSE`와 `ECMS_SELF_TEST`로 확인합니다.

## 제한

현재 A값은 `PROVISIONAL`이며 승인된 보호정정치나 발전소 SLD가 아닙니다.
피더 50/51은 설정 가능한 단순 RMS 모델일 뿐 실제 단락용량·임피던스·계전기
정정자료가 반영된 EMT/보호협조 해석이 아닙니다. 이 VPP는 운전·정비·LOTO
도구가 아닙니다.
MATLAB 합성 Run, ThermoSysPro Run, 현장 Raw Data를 서로 바꾸어 표기하면 안 됩니다.

고정 실행 기반:

- OpenModelica `openmodelica/openmodelica:v1.27.0-minimal`
- ThermoSysPro `Dwarf-Planet-Project/ThermoSysPro`
- ThermoSysPro commit `db81ae1b5a6a85f6c6c7693244cafa6087e18ff5`
- Modelica Standard Library `3.2.3+maint.om`
