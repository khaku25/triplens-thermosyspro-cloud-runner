# TripLens 검증용 Virtual Plant / Runtime 기술부록

> 이 문서는 TripLens 분석기 자체가 아니라 **TripLens 검증용 사고데이터 생성환경**을 설명한다.

## 1. 역할

Virtual Plant / Local V8 Runtime의 목적은 TripLens에게 정답을 제공하는 것이 아니라 사고 전후의 설비·보호·공정 상태변화를 생성하고 `EVENT.csv + RAW.csv`를 반복 가능하게 제공하는 것이다.

```text
Virtual Plant / Protection / Alarm Runtime
                 ↓
          EVENT.csv + RAW.csv
                 ↓
             TripLens
```

## 2. 현재 검증환경 범위

현재 제출용 검증환경은 Windows Local V8 계열을 기준으로 한다.

주요 구성:
- Native OPC UA
- ECMS / Protection / Alarm Runtime
- GT/ST independent latch
- protection cause matrix
- HP/IP BFP logical protection chain
- Plant-wide Alarm binding
- Live Historian
- EVENT.csv + RAW.csv Dual Log

이 항목은 **TripLens 분석 정확도 자체가 아니라 Test Harness의 구현범위**다.

## 3. TripLens와의 경계

검증환경 기술:
- OPC UA node / writable input
- Protection matrix
- Alarm rule binding
- Pump/Valve physics
- Virtual Plant solver/runtime

TripLens 기술:
- EVENT/RAW Input Validation
- Time Alignment
- Critical Event Extraction
- Evidence Extraction
- Causal Context
- Gemini Agent Analysis
- Verification / Fail-Closed
- Incident Summary / Timeline / Recovery Check
- Blind Validation Scorecard

## 4. 물리모델 한계

Virtual Plant는 실제 발전소의 완전한 Digital Twin으로 주장하지 않는다. 일부 Protection/Breaker/Alarm chain은 검증되었지만, 모든 electromechanical/process transient를 고정밀로 재현했다고 주장하지 않는다.

## 5. Blind Validation 원칙

- Scenario metadata를 TripLens 입력에 포함하지 않음
- Ground Truth 별도 보관
- Event/RAW 생성 후 TripLens 분석
- 사고별 TripLens Engine code 변경 금지
- Virtual Plant regression PASS와 TripLens 분석 PASS 분리

## 6. 제출 전 보강할 내용

- [ ] 현재 RC 기준 실제 Runtime 버전명
- [ ] 최신 검증 Run ID
- [ ] Virtual Plant에서 직접 생성한 대표 EVENT/RAW 예시
- [ ] 고정밀 물리 미구현 범위 명시
