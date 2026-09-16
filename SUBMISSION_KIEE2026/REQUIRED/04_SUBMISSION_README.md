# TripLens — Submission README

## 한 문장 정의

**TripLens는 발전소 사고 직후 생성되는 EVENT와 RAW 시계열을 결합해 핵심 사건, 인과 흐름, 근거 Tag, 영향설비, 복구 확인사항을 도출하는 READ-ONLY Agentic AI 사고분석 시스템이다.**

## 핵심 입력

- `EVENT.csv`: Alarm / Protection / Operator / 상태변화 Event
- `RAW.csv`: Historian / Process / Command / Logic / State Evidence

## 핵심 출력

- Incident Summary
- Critical Events
- Causal Timeline
- Key Evidence
- Affected Equipment
- Recovery Check

## Agentic AI

Gemini Agent는 Engineering Layer가 정리한 Evidence를 바탕으로 사고흐름과 확인사항을 구성한다. 원본 RAW/EVENT, Ground Truth, Protection Logic을 수정하거나 OT 장치를 제어하지 않는다.

## 안전 경계

- READ-ONLY
- OT Write 없음
- 자동복전 없음
- Ground Truth 분석입력 미제공
- 근거 부족 시 UNKNOWN / INCONCLUSIVE 허용

## 검증원칙

TripLens의 일반화 여부는 서로 다른 사고군을 동일 RC Engine으로 분석하는 Blind Validation으로 평가한다.

- Scenario ID 미입력
- Expected Cause 미입력
- Ground Truth 미입력
- 사고별 Engine code change = 0 원칙
- 결과 생성 후 외부 Validator 비교

## 제출 전 미완료 항목

- [ ] RC 버전 Freeze
- [ ] Gemini exact model / 호출방식 확정
- [ ] Blind Multi-Incident Run 완료
- [ ] Validation Scorecard 실측값 입력
- [ ] Technical Report PDF 생성
- [ ] System Architecture PDF 생성
- [ ] Presentation PPT/PDF 생성
- [ ] 최종 ZIP clean-folder 검증
