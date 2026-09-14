# V8 실패 원인 분석

## V8.5 alarm binding 실패

V8.5의 HP/IP/ST/GT live protection proof는 모두 통과했지만, 다음 단계의
`verify_alarm_coverage_live.py`에는 V7 시절의 정적
`UNPUBLISHED_DERIVED_NODES` 목록이 남아 있었다. 이 검증기는 후보 서버를
browse하기도 전에 V8.5가 새로 공개한 HP/IP MotorEnergized/SpeedProven
태그를 거부했다. 따라서 이 실패는 Modelica 보호 로직이나 OPC UA 서버의
실패가 아니라 검증 계약의 버전 불일치다.

V8.5.1은 정적 차단을 제거하고 실제 실행 중인 OPC UA 주소 공간에서
missing, duplicate, 값 읽기 가능 여부를 확인한다. HP/IP SpeedRPM과
SpeedProven도 앞 단계의 isolated proof 바인딩 대상에 포함한다.

## V8.5.1 Dual Log 검증 오탐

실제 시험 EVENT.csv에는 OPERATOR_ACTION, PROTECTION, ALARM만 있었지만
검증기의 RAW-only 목록에 MOTOR_DEENERGIZED, RUNNING_LOST,
SPEED_PROVEN_LOST, CHECK_VALVE_CLOSED가 잘못 포함되어 있었다. 이들은
일반 command가 아니라 운전원이 확인해야 하는 물리 보호·알람 사건이다.
V8.5.2는 명령 태그만 RAW-only로 검사하고 이 사건들은 EVENT에 유지한다.

## 결론

기존 V8의 `WinError 10054`는 OPC UA 지연이나 Python 클라이언트 오류가
아니라, HP BFP 시험 중 OpenModelica 물리 solver가 먼저 종료되면서 생긴
후속 오류였다.

## 확인된 실패 경로

1. V8/V8.2는 HP/IP BFP Trip Latch를 VCB 상태에 연결했다.
2. 동시에 `PompeAlimHP/MP.rpm_or_mpower`를 새 gate 출력으로 재배선했다.
3. HP BFP live proof가 speed=0, running=0까지 기다렸다.
4. 급격한 급수경계 변경 뒤 증기계통 압력관계가 유효범위를 벗어났다.
5. TurbineHP 유량식의 제곱근 인수가 음수가 되었고 비선형계가 실패했다.
6. 모델 실행 파일이 종료되어 내장 OPC UA 서버가 소켓을 닫았다.
7. 클라이언트의 다음 read/disconnect가 `WinError 10054`를 보고했다.

V8.4의 관성 drive와 hydraulic speed floor도 동일한 정적 펌프 경계를
변경했기 때문에 근본 해결이 아니었다.

## V8.5의 해결 방식

- V7의 HP/IP 펌프 속도 연결을 바이트 수준의 동일한 Modelica 문장으로 유지
- HP/IP 보호 로직과 물리 구동계의 책임을 분리
- live proof에서 speed=0을 요구하지 않음
- hp/ip/st/52GT/gt 시험을 각각 새 solver 프로세스에서 수행
- 각 시험 뒤 trajectory를 폐기하고 최종 서버는 무사고 상태로 새로 시작
- 설치 실패 시 V7 소스·클라이언트·GUI를 복구하고 이전 서버 재시작

## 기능 경계

V8.5에서 HP/IP PB, Trip Cmd, Latch, VCB Trip Cmd, 논리 Breaker Position은
실행 가능한 보호 로직이다. HP/IP 실제 축 coastdown은 아직 검증된 물리
모델이 아니므로 구현했다고 표시하지 않는다. RAW/Live Historian의 HP/IP
회전수와 유량은 보존된 V7 ThermoSysPro 물리값이다.
