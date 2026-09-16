# TripLens 10분 발표 구성안
## KIEE 2026 Agentic AI

> 목표: VPP 자체를 자랑하는 발표가 아니라, **서로 다른 발전소 사고의 EVENT+RAW를 동일 Agentic AI 분석기로 처리하고 근거까지 제시한다**는 것을 보여준다.

## Slide 1 — 문제 (0:00~0:50)

**발전소 사고 직후 가장 부족한 것은 데이터가 아니라 정리된 핵심정보다.**

보여줄 것:
- Alarm/Event 폭주
- DCS / ECMS / Historian 분산
- 최초 사건 vs 후속파급 구분 어려움

## Slide 2 — TripLens 한 문장 (0:50~1:30)

`EVENT.csv + RAW.csv → Evidence → Gemini → Verified Incident Brief`

핵심 출력:
- Critical Events
- Causal Timeline
- Key Evidence
- Affected Equipment
- Recovery Check

## Slide 3 — 현재 V8 시스템 (1:30~2:30)

Local V8 Runtime:
- Native OPC UA
- ECMS / Protection
- Alarm Runtime
- Dual Log
- Live Historian
- Gemini Analysis

강조:
**READ ONLY / Authority NONE**

## Slide 4 — EVENT와 RAW를 왜 둘 다 쓰는가 (2:30~3:20)

EVENT:
“무슨 일이 언제 일어났나”

RAW:
“실제로 무엇이 어떻게 움직였나”

두 자료의 교차검증이 TripLens의 핵심.

## Slide 5 — Agentic AI가 실제로 하는 일 (3:20~4:20)

Gemini가:
- 관련 Evidence 확인
- 원인/직접계기/파급 구분
- 근거 부족 표시
- Recovery Check 구성

AI가 하지 않는 것:
- 데이터 수정
- Ground Truth 접근
- OT 제어

## Slide 6 — Demo (4:20~6:20)

대표 사고 1건:
1. EVENT + RAW 준비
2. TripLens 입력
3. Critical Event
4. Causal flow
5. Evidence
6. Gemini interpretation
7. Recovery Check

Live는 짧게, 필요 시 Verified Replay 사용.

## Slide 7 — “GT Trip 전용 아닙니까?” (6:20~7:30)

Blind Validation 구조:
- Same Engine
- Scenario ID 없음
- Expected Cause 없음
- Ground Truth 없음
- Code Change = 0

GT / Feeder / Third Case 비교.

## Slide 8 — Scorecard (7:30~8:30)

최종 실측값으로 교체:
- N/N Blind PASS
- Critical Event F1
- Causal Accuracy
- Evidence Grounding
- Unsupported Claim
- Fail-Closed

현재 초안 단계에서는 NOT TESTED.

## Slide 9 — 실용성과 한계 (8:30~9:20)

실용성:
- 초기 핵심정보 탐색시간 감소
- 근거 기반 판단지원
- 사고기록 표준화

한계:
- Synthetic/Virtual Plant
- 현장 정확도 미검증
- 자동운전/복전 없음

## Slide 10 — 결론 (9:20~10:00)

**“TripLens는 Alarm 목록을 하나 더 만드는 시스템이 아니라, 사고 직후 흩어진 EVENT와 RAW를 근거 있는 인과 흐름으로 바꾸는 Agentic AI 분석계층입니다.”**

마지막 숫자:
- Incident Families
- Blind Runs
- Engine Code Changes
- Unsupported Claims
