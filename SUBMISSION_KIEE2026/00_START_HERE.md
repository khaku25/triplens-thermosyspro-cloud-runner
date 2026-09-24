# TripLens — KIEE 2026 제출 전용 폴더

> **이 폴더만 제출 준비에 사용한다.**
>
> 기존 `docs/kiee2026/` 및 저장소 루트 문서는 개발이력·참고자료이며, 현재 제출본의 편집 기준으로 사용하지 않는다.

## 제출 기준

- 결과물 제출: **2026-09-27 자정까지(연장 공고 기준)**
- 현재 물리 기준: **Windows Local V8**
- 현재 분석 기준: **EVENT.csv + RAW.csv + Gemini Agent + Evidence Tools + Verification Gate**
- 현재 검증 기준: **12개 distinct synthetic incident scenarios / 누적 21회 분석 실행(재검증 포함, 프로젝트 실행기록 기준)**

## 제출용 트리

```text
SUBMISSION_KIEE2026/
├─ 00_START_HERE.md
├─ REQUIRED/
│  ├─ 01_SYSTEM_ARCHITECTURE.md
│  ├─ 02_TECHNICAL_REPORT.md
│  ├─ 03_WORKFLOW_DEFINITION.json
│  └─ 04_SUBMISSION_README.md
├─ VALIDATION/
│  ├─ 05_VALIDATION_REPORT.md
│  └─ 06_VALIDATION_RESULTS.csv
├─ PRESENTATION/
│  ├─ 07_PRESENTATION_OUTLINE.md
│  └─ 08_DEMO_GUIDE.md
└─ APPENDIX/
   └─ 09_VIRTUAL_PLANT_TEST_ENVIRONMENT.md
```

## 핵심 구분

### 출품작 본체 = TripLens

```text
EVENT.csv + RAW.csv
        ↓
Input / Session / Time Validation
        ↓
Evidence Store
        ↓
6 Evidence Tools
        ↓
Gemini Agent
  - Critical Events
  - Primary Cause / Candidate
  - Direct Trigger
  - Propagation
  - Causal Chain
  - Counter Evidence
        ↓
Citation Check / Verification Gate
        ↓
Dashboard / Evidence Navigation / Failure Report
```

### 검증환경 = Virtual Plant / Local V8

Virtual Plant, OPC UA, ECMS, Protection/Alarm Runtime은 TripLens에 정답을 제공하는 제품 본체가 아니라 **재현 가능한 EVENT/RAW를 생성하는 Test Harness**다.

## 현재 검증 완료 범위

Drive 기준으로 다음 12개 시나리오의 실제 사이트 분석과 최종 고장상보가 존재한다.

1. Direct GT Trip
2. Direct ST Trip
3. GT Breaker
4. IP BFP
5. HP Drum LL
6. IP Drum LL
7. IP Drum HH
8. HP Drum HH
9. HP BFP
10. LP BFP
11. LP Drum HH
12. LP Drum LL

각 시나리오는 A01~A20의 동일한 20개 Engineering Inspection 항목으로 점검한다. 9/21 요약표 기준 내부 종합점수 평균은 88.0/100이며, 이는 **AI 정확도 88%가 아니라 입력·인과·근거·운전대응·산출물을 함께 본 내부 점수**다.

HP BFP RAW 결측과 같이 근거가 부족한 사례는 후보/미검증 상태를 유지해 Fail-Closed 동작을 확인한다.

## 제출 문서 작성 원칙

- TripLens 본체 설명을 중심으로 한다.
- Virtual Plant는 검증환경으로 분리한다.
- 12개 시나리오 검증 결과는 실제 발전소 현장 검증으로 확대하지 않는다.
- 603 live OPC UA Source Tags와 시나리오 RAW의 693~700개 수준 전체 열/태그 수를 같은 의미로 쓰지 않는다.
- `Gate PASS`는 공학적 원인 확정이나 재기동 승인이 아니다.
- 미확인 항목은 YELLOW / RED / NOT TESTED / UNKNOWN으로 그대로 보존한다.
- “모든 발전소/모든 제조사 호환”이라고 단정하지 않는다. 구조상 제조사 비종속을 지향하되 실제 호환은 별도 현장 검증 대상이다.

## 지금 해야 할 일

1. REQUIRED 문서와 Drive Current V8 기술문서의 표현을 동일하게 유지
2. 발표용 Validation 슬라이드에 12 distinct scenarios / 21 executions / Fail-Closed 사례를 정확히 반영
3. 88.0/100을 AI 정확도로 표기하지 않기
4. CSV/PINPOINT export, 모바일 전체 Acceptance 등 미완료 기능은 완료로 승격하지 않기
5. 최종 ZIP에서 기술문서·Validation·PPT·Demo가 같은 기준을 사용하도록 확인
