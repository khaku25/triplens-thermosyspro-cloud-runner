# TripLens 검증용 Virtual Plant / Runtime 기술부록
## KIEE 2026 Agentic AI — Test Environment Appendix

> 이 문서는 TripLens 분석기 자체의 기술문서가 아니라, **TripLens 검증용 사고데이터 생성환경**의 구현범위와 한계를 기록한다.

---

## 1. 역할

Virtual Plant / Local V8 Runtime의 목적은 TripLens에게 정답을 제공하는 것이 아니다.

목적은 다음과 같다.

1. 사고 전후 설비·보호·공정 상태변화를 생성
2. OPC UA를 통해 Runtime 상태를 전달
3. Alarm / Protection / Historian 데이터를 생성
4. `EVENT.csv + RAW.csv` 분석 입력을 재현 가능하게 생성
5. TripLens를 반복적으로 Blind Validation할 수 있는 시험환경 제공

즉, 구조는 다음과 같다.

```text
Virtual Plant / Protection / Alarm Runtime
                 ↓
          EVENT.csv + RAW.csv
                 ↓
             TripLens
```

---

## 2. 현재 로컬 기준

현재 제출용 검증환경의 기준은 Windows Local V8 계열이며, 최신 검증 계약은 V8.5.2 계열을 기준으로 한다.

주요 구성:

- Native OPC UA
- ECMS / Protection / Alarm Runtime
- GT/ST independent latch
- 9-cause GT/ST protection matrix
- HP/IP BFP logical protection chain
- Plant-wide Alarm binding
- Live Historian
- EVENT.csv + RAW.csv Dual Log

최신 로컬 검증계약에서 확인한 항목:

- 66 changeable Real inputs
- 67 live alarm rules bound
- EVENT/RAW E2E Dual Log
- Alarm/Protection Event는 EVENT에 유지
- command/latch 계열 evidence는 RAW로 분리

이 수치는 Virtual Plant/Runtime 검증범위를 설명하기 위한 것으로, **TripLens 분석 정확도 Score와 합산하지 않는다.**

---

## 3. Protection / Event 생성

현재 Runtime은 GT/ST 관련 Protection 상태와 주요 Trip chain을 재현하고, 이를 Event/RAW 형태로 노출한다.

핵심 검증 항목:

- GT/ST independent protection latch
- GT/ST trip request 및 breaker state 변화
- common protection cause matrix
- HP/IP BFP logical trip chain
- reset/reclose 상태 구분

이 Logic은 TripLens가 사고관계를 학습하는 정답표가 아니라, **분석할 Event와 설비상태 변화의 생성원**이다.

---

## 4. OPC UA

OPC UA는 Virtual Plant/Runtime과 ECMS/Logging 계층 사이의 데이터 인터페이스로 사용한다.

역할:

- Process value 제공
- Equipment state 제공
- Logic/protection state 제공
- 시험 command 전달
- Historian/Alarm source 제공

TripLens 최종 분석기는 OPC UA node 수 자체에 의존하지 않고 최종 `EVENT.csv + RAW.csv` 데이터계약을 입력으로 사용한다.

---

## 5. Dual Log

### EVENT.csv

사람에게 의미 있는 Alarm / Protection / Operator / State transition을 기록한다.

### RAW.csv

수치형 Historian 및 command/logic/state evidence를 보존한다.

이 분리를 통해 EVENT 파일이 내부 Logic Tag를 과도하게 노출하거나, 사고정답을 직접 포함하는 것을 방지한다.

---

## 6. 현재 물리모델 한계

Virtual Plant는 실제 발전소의 완전한 Digital Twin으로 주장하지 않는다.

특히 HP/IP BFP 관련 현재 안정판은 Protection 및 전기적/논리적 상태변화를 검증하는 데 초점을 둔다.

Trip 이후 실제 축 coastdown을 고정밀 전동기-펌프 관성모델로 완전 재현했다고 주장하지 않는다.

따라서 제출문서에서는 다음 범위를 구분한다.

- Protection Logic: 현재 Runtime 검증범위
- Breaker / running / energized 상태: 현재 Runtime 검증범위
- Event/RAW 생성: 현재 Runtime 검증범위
- 고정밀 electromechanical coastdown: 별도 고도화 범위

---

## 7. TripLens와의 경계

다음 항목은 이 검증환경의 기술사양이다.

- OPC UA node 수
- writable input 수
- Protection matrix
- Alarm rule binding 수
- Pump/Valve physics
- Virtual Plant solver/runtime

반대로 다음 항목은 TripLens 자체의 기술사양이다.

- EVENT/RAW Input Validation
- Time Alignment
- Critical Event Extraction
- Evidence Extraction
- Causal Context
- Gemini Agent Analysis
- Verification / Fail-Closed
- Incident Summary / Timeline / Recovery Check
- Blind Validation Scorecard

두 영역을 제출문서에서 혼동하지 않는다.

---

## 8. 검증자료로 사용할 때의 원칙

- Virtual Plant의 scenario metadata를 TripLens 입력에 포함하지 않음
- Ground Truth를 별도 보관
- Event/RAW가 생성된 후 TripLens 분석 수행
- 사고별 TripLens Engine code 변경 금지
- Virtual Plant regression PASS와 TripLens 분석 PASS를 별도 Score로 관리

---

## 9. 결론

Local V8 Virtual Plant는 TripLens의 핵심 제품이 아니라 **재현 가능한 사고 입력을 공급하는 Test Harness**다.

대회 제출에서 이 환경의 가치는 물리모델 자체의 복잡성보다, TripLens가 다양한 사고 데이터를 동일 방식으로 분석할 수 있도록 반복 가능한 EVENT/RAW를 제공한다는 점에 있다.
