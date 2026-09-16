# TripLens — KIEE 2026 제출 전용 폴더

> **이 폴더만 제출 준비에 사용한다.**
>
> 기존 `docs/kiee2026/` 및 저장소 루트의 문서는 개발이력·참고자료이며, 현재 제출본의 편집 기준으로 사용하지 않는다.

## 제출 마감

- 결과물 제출: **2026-09-23 자정까지**
- 현재 기준: **TripLens Local V8 + 실제 Gemini 분석 + EVENT.csv / RAW.csv**

## 지금 해야 할 일

1. `REQUIRED/02_TECHNICAL_REPORT.md` 작성 완성
2. `REQUIRED/01_SYSTEM_ARCHITECTURE.md`의 구성도 확정
3. `REQUIRED/03_WORKFLOW_DEFINITION.json`을 실제 Agent 흐름과 일치시킴
4. Blind Run 후 `VALIDATION/`의 NOT TESTED 값을 실제 측정값으로 갱신
5. `PRESENTATION/`으로 10분 발표와 시연 확정
6. 최종적으로 Technical Report와 Architecture를 PDF로 변환하고 PPT/PDF를 함께 제출 ZIP에 포함

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
Input Validation / Time Alignment
        ↓
Critical Event + Evidence Extraction
        ↓
Causal Context
        ↓
Gemini Agent
        ↓
Verification / Fail-Closed
        ↓
Incident Summary / Timeline / Evidence / Recovery Check
```

### 검증환경 = Virtual Plant / Local V8

Virtual Plant, OPC UA, ECMS, Protection Matrix, Alarm Rule 수, Pump/Valve physics 등은 **TripLens를 시험하기 위한 데이터 생성환경**이다. 기술보고서 본문에서는 필요한 만큼만 설명하고 세부 구현은 `APPENDIX/`로 보낸다.

## 문서 작성 원칙

- TripLens 본체 설명이 전체 기술문서의 약 **75~80%**가 되게 한다.
- Virtual Plant/Runtime은 검증방법 설명에만 사용한다.
- 실제 측정 전 성능값은 `NOT TESTED`로 둔다.
- GitHub 과거 이력이나 이전 v5/v6/v7 상태를 현재 구현 근거로 사용하지 않는다.
- 본선에서 예심 제출내용의 기술적 보완이 제한될 수 있으므로 9/23 제출본을 RC 기준으로 고정한다.
