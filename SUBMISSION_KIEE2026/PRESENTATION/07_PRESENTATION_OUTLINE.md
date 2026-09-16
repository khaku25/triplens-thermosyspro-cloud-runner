# TripLens 10분 발표 구성안

## 발표 원칙

주인공은 Virtual Plant가 아니라 **TripLens 사고분석 Agent**다. Virtual Plant는 검증데이터 생성환경으로만 짧게 설명한다.

## Slide 1 — 문제
발전소 사고 직후 Alarm/Event는 많지만, 운전원에게 필요한 것은 최초사건·직접계기·파급·현재 확인사항의 우선순위다.

## Slide 2 — TripLens
`EVENT.csv + RAW.csv → Evidence → Gemini → Verification → Incident Brief`

## Slide 3 — TripLens Architecture
Input Validation → Time Alignment → Critical Event / Evidence → Causal Context → Gemini → Fail-Closed → Output

## Slide 4 — EVENT와 RAW
EVENT는 '무슨 일이 언제', RAW는 '그때 실제 설비가 어떻게 움직였는가'를 보여준다.

## Slide 5 — Agentic AI
Gemini가 Evidence를 검토하여 사고흐름과 Recovery Check를 구성한다. 원본데이터와 OT는 수정하지 않는다.

## Slide 6 — 실제 분석 Demo
Incident Summary → Critical Events → Causal Timeline → Key Evidence → Recovery Check 순으로 보여준다.

## Slide 7 — 일반화
Same Engine / No Scenario ID / No Ground Truth / Code Change = 0 원칙으로 여러 사고군 Blind Test.

## Slide 8 — Scorecard
실제 RC Run 이후 Critical Event F1, Causal Accuracy, Evidence Grounding, Unsupported Claims, Fail-Closed, Time-to-Insight를 제시한다.

## Slide 9 — 실용성과 한계
사고 초기 정보탐색을 지원하지만 자동복전·OT 제어는 하지 않는다. 현재는 Synthetic/Virtual Plant 기반 검증이다.

## Slide 10 — 결론
**TripLens는 사고 후 흩어진 EVENT와 RAW를 근거 있는 인과흐름으로 바꾸는 READ-ONLY Agentic AI 분석계층이다.**
