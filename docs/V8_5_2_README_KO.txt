TripLens Protection Dashboard V8.5.2 Dual Log Event Hotfix
===========================================================

목적
----
V7의 검증된 ThermoSysPro 물리계통과 OPC UA 서버를 보존하면서 V8 보호
매트릭스, BFP 운전자 제어, Plant Alarm/Event, Dual Log, Protection Logic,
Live Historian GUI를 설치한다.

기존 V8이 실패한 이유
----------------------
1. V8은 보호 논리뿐 아니라 HP/IP 정적 원심펌프의 rpm_or_mpower 연결을
   차단기 상태에 따라 1400→0 rpm으로 직접 재배선했다.
2. V8.4는 관성 모델과 속도 floor를 추가했지만 같은 물리 경계에 계속
   개입했다.
3. HP BFP live proof가 실제 펌프 정지까지 기다리는 동안 증기계통에서
   TurbineHP 입구압력²-출구압력² 항이 음수가 되었고 DASSL/비선형계가
   종료되었다.
4. OpenModelica 실행 프로세스가 죽으면서 내장 OPC UA 소켓도 닫혀
   Python에는 WinError 10054가 2차 증상으로 표시되었다.
5. 따라서 10054는 원인이 아니라 물리 solver 종료의 결과였다.

V8.5 변경점
------------
- V7의 아래 두 연결을 정확히 유지한다.
  connect(PompeAlimHP.rpm_or_mpower, arretPomesHP.y)
  connect(PompeAlimMP.rpm_or_mpower, arretPomesMp.y)
- HP/IP에 zero-speed gate, speed floor, 임의 관성 drive를 추가하지 않는다.
- HP/IP 보호 체인은 실제 OPC UA 논리로 실행한다.
  PB → Trip Cmd → Latch → VCB Trip Cmd → 논리 Breaker Open/Motor Deenergized
- HP/IP 물리 유량·회전수는 V7 모델의 실제 Historian 값 그대로 표시한다.
  이 안정판은 HP/IP 전동기-펌프 축 coastdown을 구현했다고 주장하지 않는다.
- GT/ST 독립 latch와 9-cause matrix, drum HH/LL 0.5 s persistence를 유지한다.
- 52GT-open/latch discrete algebraic loop 수정(V8.2)을 유지한다.
- live proof는 hp, ip, st, gt_breaker, gt를 각각 새 solver에서 실행한다.
- GUI에 V8.2 DPI/header layout hotfix를 내장했다.
- EVENT.csv + RAW.csv Dual Log, 전체 Alarm Coverage, Live Historian을 유지한다.

V8.5.1 핫픽스
-------------
- V8.5가 실제 OPC UA에 공개한 HP/IP MotorEnergized 및 SpeedProven 네 태그를
  구형 alarm binding 검증기가 `unpublished`라고 선차단하던 모순을 제거했다.
- 정적 제외 목록 대신 실행 중인 후보 서버의 OPC UA 주소 공간을 직접 검색해
  missing/duplicate/value-read 가능 여부를 판정한다.
- 연결 종료 중 WinError 10054가 본래의 검증 결과를 덮지 않도록 정리 경로를
  방어했다.
- 보호 로직, Modelica 물리 경계, MATLAB GUI 및 명령 지연 설정은 변경하지 않았다.

V8.5.2 핫픽스
-------------
- Dual Log live verifier가 정상 Alarm/Protection 상태를 일반 command로
  오판하던 금지 태그 목록을 수정했다.
- BREAKER_OPEN, MOTOR_DEENERGIZED, RUNNING_LOST, SPEED_PROVEN_LOST,
  CHECK_VALVE_CLOSED는 사람이 보는 EVENT 사건으로 유지한다.
- TRIP_CMD, VCB_TRIP_CMD, BREAKER_COMMAND, OPEN_CMD, CLOSE_CMD 및 LP BFP
  내부 command/latch 파생 열만 RAW 전용으로 검증한다.
- 누출이 실제로 생기면 event_class:tag를 오류에 출력하도록 개선했다.

설치 전
-------
MATLAB 명령 창에서 다음 세 줄을 실행한다.

  close all force
  clear ECMSVPP ECMS_BFP_ALARMS ECMS_LIVE
  clear functions

PowerShell에서 압축을 저장소 루트에 푼 다음 실행한다.

  cd C:\TripLens\triplens-thermosyspro-cloud-runner
  Set-ExecutionPolicy -Scope Process Bypass -Force
  .\TripLens_ProtectionDashboard_V8_5_2_DUAL_LOG_EVENT_HOTFIX\APPLY_TRIPLENS_PROTECTION_DASHBOARD_V8_5_2_DUAL_LOG_EVENT_HOTFIX.ps1

정상 완료 표시는 다음과 같다.

  PASS: TRIPLENS_PROTECTION_DASHBOARD_V8_5_2_DUAL_LOG_EVENT_HOTFIX

설치 프로그램은 현재 V7 소스/클라이언트를 백업하고, build와 smoke test가
통과하기 전에는 실행 중인 V7 서버를 종료하지 않는다. live proof 실패 시
소스·클라이언트·payload를 복원하고 이전 검증 서버를 재시작한다.

MATLAB 실행
-----------
  cd('C:\TripLens\triplens-thermosyspro-cloud-runner')
  close all force
  clear ECMSVPP ECMS_BFP_ALARMS ECMS_LIVE
  ECMSVPP

서버만 다시 켜기
----------------
  .\START_TRIPLENS_PROTECTION_V8_5_STABLE.ps1

시간 0 재시작은 GUI 위쪽의 '시간 0 재시작' 버튼을 사용한다. EVENT.csv와
RAW.csv는 삭제하지 않으며 새 incident/session만 시작한다.

검증 범위
---------
- 66 changeable Real inputs
- 48 valve + 8 breaker + 6 HP/IP/LP BFP PB + 4 GT/ST trip/reset
- 9-cause GT/ST protection matrix와 독립 latch
- HP/IP BFP 논리 체인 및 reset/reclose
- 67-rule alarm binding, EVENT/RAW 분리, combined analysis
- MATLAB table cell type guard와 넓은 상단 버튼 레이아웃

중요 제한
---------
HP/IP BFP 전동기 차단 이후 실제 축 회전수/유량 coastdown 물리는 별도의
validated plant-model 작업이다. V8.5는 서버 안정성을 위해 그 물리 입력을
V7 그대로 보존한다. Protection Logic 탭은 논리 chain을, Live Historian과
RAW.csv는 현재 V7 물리계산 값을 보여준다.
