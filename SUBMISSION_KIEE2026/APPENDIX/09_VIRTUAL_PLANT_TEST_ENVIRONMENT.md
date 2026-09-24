# TripLens 검증용 Virtual Plant / Runtime 기술부록

> 이 문서는 TripLens 분석기 자체가 아니라 **TripLens 검증용 사고데이터 생성환경**을 설명한다.

## 1. 역할

Windows Local V8 Virtual Plant의 목적은 TripLens에게 정답을 제공하는 것이 아니라 사고 전후의 설비·보호·공정 상태변화를 생성하고 `EVENT.csv + RAW.csv`를 반복 가능하게 제공하는 것이다.

```text
ThermoSysPro / OpenModelica
          ↓ Native OPC UA
ECMS / Protection / Alarm Runtime
          ↓
EVENT.csv + RAW.csv
          ↓
TripLens
```

## 2. 현재 검증환경

주요 구성:
- ThermoSysPro/OpenModelica 기반 합성 Plant
- Native OPC UA
- ECMS / Protection / Alarm Runtime
- GT/ST independent latch
- Breaker / BFP / Drum protection paths
- Plant-wide Alarm binding
- Historian-style RAW
- EVENT + RAW Dual Log

이 항목은 **TripLens 분석 정확도 자체가 아니라 Test Harness의 구현범위**다.

## 3. 실제 분석에 사용된 시나리오

현재 Drive에는 다음 12개 distinct scenario의 TripLens 실제 사이트 분석과 최종 고장상보가 존재한다.

```text
Direct GT
Direct ST
GT Breaker
IP BFP
HP Drum LL
IP Drum LL
IP Drum HH
HP Drum HH
HP BFP
LP BFP
LP Drum HH
LP Drum LL
```

재검증을 포함한 누적 분석 실행은 21회(프로젝트 실행기록 기준)이다.

## 4. TripLens와의 경계

### Validation Environment

- 공정·보호·Alarm 상태 생성
- OPC UA signal exchange
- Fault/Scenario operation
- EVENT/RAW generation

### TripLens

- Input / Session / Time Validation
- Evidence Store
- Evidence Tool Calling
- Gemini causal interpretation
- Citation Check / Verification Gate
- Evidence Navigation
- Failure Report

시나리오를 발생시키는 Fault Injection 정보와 분석 Agent의 Evidence를 분리한다.

## 5. 태그 수 해석 주의

Run #54 기준 Current Live OPC UA Source BrowseName은 603개다.

Blind scenario RAW 파일에서는 관측·파생 열을 포함해 693~700개 수준의 열/태그가 표시될 수 있다.

따라서:
- **603 = Current Live OPC UA Source identity baseline**
- **693~700 수준 = 특정 RAW CSV의 전체 관측/파생 열 규모**

로 구분한다.

## 6. 물리모델 한계

Virtual Plant를 실제 발전소와 동일한 고정밀 Digital Twin이라고 주장하지 않는다.

- 합성 사고 데이터 생성·검증환경
- 모든 electromechanical/process transient의 현장 재현성을 주장하지 않음
- 특정 보호·Alarm 연쇄가 동작한다고 해서 모든 실제 발전소 setting과 동일한 것은 아님
- 현장 적용에는 실제 DCS/ECMS/Historian 및 승인 Logic/도면 검증이 필요

## 7. Blind Validation 경계

Agent에 제공하지 않는 정보:
- Scenario ID / Name
- Expected Cause
- Ground Truth / Answer Label
- Simulation-only Fault Injection internal metadata

실제 관측 가능한 Process/Alarm/Protection/Logic state는 Evidence로 사용할 수 있다.

## 8. 현재 검증결과의 의미

현재 입증한 것:
- 하나의 V8 합성환경 안에서 원인과 보호결과가 다른 12개 시나리오 분석
- 동일 분석구조로 Cause/Trigger/Propagation 구분
- EVENT/RAW Evidence traceability
- 결측 사례에서 Fail-Closed
- 12개 Failure Report 산출

입증하지 않은 것:
- 실제 발전소 Field Accuracy
- 모든 발전소 topology 일반화
- 모든 제조사의 실설비와 즉시 호환
- Production-grade Digital Twin 정확도
