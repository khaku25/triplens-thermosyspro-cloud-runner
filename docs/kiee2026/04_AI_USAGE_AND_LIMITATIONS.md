# AI Usage and Limitations
## TripLens — KIEE 2026 Agentic AI

## 1. 사용 AI

현재 제출용 TripLens의 주력 AI 분석계층은 **Google Gemini**이다.

- Provider: Google
- Model: **TBD — RC Freeze 시 실제 Runtime 설정값으로 확정**
- 역할: EVENT/RAW 기반 사고 Evidence 해석 및 설명
- 권한: READ-ONLY
- OT 제어권한: 없음

## 2. 사용자가 정의한 영역

사용자 주도:
- 발전소 사고분석 문제 정의
- EVENT/RAW 데이터 계약
- 설비/보호/운전 관점의 분석목표
- 사고 시나리오 및 Ground Truth 기준
- 검증 Metric 정의
- 최종 공학적 해석 검토
- 발표/제출 범위와 한계 설정

## 3. AI가 수행하는 영역

Gemini:
- Evidence 기반 핵심 사건 정리
- 시간순서 설명
- 원인 / 직접 계기 / 후속 파급 구분
- 근거 부족 및 추가 확인자료 표시
- Incident Brief / Recovery Check 설명

개발과정에서 사용한 생성형 AI:
- 코드 초안·디버깅 보조
- 문서화 보조
- UI/구조 아이디어 검토
- 테스트 케이스 설계 보조

단, 최종 PASS 여부는 실제 Runtime/시험근거로 판단한다.

## 4. AI가 할 수 없는 것

- RAW 값 수정
- EVENT 값/시각 수정
- Ground Truth 접근
- 보호계전 동작 변경
- 승인 Logic 변경
- 자동 복전
- Breaker 조작
- 운전원 조작 대체

## 5. 생성형 AI 의존 방지 구조

TripLens는 AI가 자유문장만 생성하는 구조가 아니다.

```text
EVENT + RAW
   ↓
Deterministic Validation / Alignment
   ↓
Engineering Evidence
   ↓
Gemini Analysis
   ↓
Verification Boundary
   ↓
Verified Incident Brief
```

따라서 AI가 근거 없는 확정판정을 하더라도 최종 결과는 Evidence/Verification 기준을 통과해야 한다.

## 6. Blind Validation

성능평가 시 다음 정보는 Gemini/TripLens 입력에서 제외한다.

- Scenario ID
- Expected root cause
- Answer label
- Ground Truth
- 원인 정답용 수동 marker

Ground Truth는 분석이 끝난 후 외부 Validator가 결과와 비교한다.

## 7. 현재 한계

- 합성/Virtual Plant 검증
- 실제 현장 정확도 미검증
- Gemini 모델/프롬프트/Runtime 호출정보는 RC Freeze 후 고정 예정
- 일부 물리 transient는 제한된 범위만 검증
- 현장 보안 데이터의 외부 AI 전송은 별도 승인/보안설계 필요

## 8. 제출 전 체크

- [ ] Gemini exact model name 기재
- [ ] Prompt/Agent workflow 최종본 기재
- [ ] 입력/출력 예시 첨부
- [ ] 실제 Blind Run 증거 첨부
- [ ] AI가 생성한 문장과 deterministic result의 경계 명시
