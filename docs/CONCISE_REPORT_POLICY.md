# 모델 공통 간결 보고서 — CONCISE_REPORT_V1

## 범위

Gemini와 OpenAI 분석은 동일한 `hybrid_agent_prompt.md` 및 `ANALYSIS_SCHEMA`를 사용한다.
본 변경은 모델 학습이나 정답 주입이 아니라 **표현 규칙과 표시 계층**의 변경이다.

- `claim`: 상세 분석 원문. 수치, 관측/추론, 반증과 제약을 보존한다.
- `report_summary`: 본문용 한국어 한 문장 또는 짧은 완결형 표제. 목표 80자, 최대 120자(공백 포함).
- `status`, `ai_confidence`, `evidence_ids`, `related_tags`, `model_time_s`, `time_interval_s`: 요약 보정이 변경할 수 없는 필드.
- 표본 변화 구간은 구간으로 표시하며 최초 검출 표본을 정확한 개시 시각으로 표시하지 않는다.
- 결측, 불일치/반증, 설명되지 않은 지연은 짧은 요약에서도 삭제하지 않는다.

## 요청과 검증

최초 분석 요청에서 상세 claim과 별도 report_summary를 함께 생성한다. 요약에 문제가 있을 때만
동일 모델에 요약 문장만 최대 1회 재요청한다. 재요청에는 도구를 제공하지 않고,
응답의 `summaries[].path`와 `summaries[].report_summary`만 허용한다. 다른 필드의 변경,
새 경로, 중복 경로, 일부 항목만 반환한 응답은 전체 거절한다.

기존 210초 분석 예산 중 45초를 확보할 수 없는 시점(경과 165초 이상)에는 재요청하지 않는다.
실패나 시간 부족 시 상세 claim을 유지한다. 요약 실패는 분석 판정 자체를 승격하거나 낮추지 않는다.
정상 요약이 있거나 기존 짧은 응답이면 추가 모델 호출은 발생하지 않는다.

Python과 브라우저의 검사는 길이/형식, 새 수치·태그, 확정 표현, 불확실성 누락에 대한 방어 규칙이다.
**문장의 완전한 의미 동등성이나 공학적 인과관계를 자동 증명하는 검사는 아니다.**
신뢰도 수치만 다른 동일 분석 객체의 표시는 변하지 않는지를 오프라인 회귀시험으로 확인한다.

## 표시 및 기존 데이터

웹 요약 카드와 PDF 첫 페이지는 안전한 report_summary를 우선 표시한다.
웹 상세 펼침 영역과 PDF 인과관계 상세 영역은 원문을 유지한다.
PDF는 기존 4페이지 형식 및 이벤트 표시 범위를 유지한다. 전체 EVENT/RAW와 상세 CSV는 별도로 보존한다.
보고서 내보내기는 AI 분석이나 요약 API를 재실행하지 않는다.
사용자가 명시적으로 편집한 보고서 행을 새 요약으로 덮어쓰지 않는다.

기존 저장 응답에 report_summary가 없어도 호환된다. 과거 PDF/CSV는 자동 수정하지 않으며,
기존 상세 설명으로 안전하게 대체한다. 변경된 생성 규칙은 배포 후의 새 분석에 적용된다.
모델·도구 예산·물리 모델·OPC UA·보호 로직은 변경하지 않는다.

## 오프라인 확인 명령

```sh
python -m unittest discover -s services/agent-api/tests -p 'test_concise*.py' -v
node --test tests/test_concise_report.mjs
python -m unittest discover -s services/agent-api/tests -p 'test_*.py' -v
node --test tests/test_*.mjs apps/web/lib/*.test.mjs
```

변경 전 main 스냅샷 `9886e37c5718aa2fa68eee9226a826758e9bb6f1`에서 이미 실패한 항목:

- `tests/test_logic_plant_navigation.mjs`: Plant overview opens from its direct URL without an equipment selection
- `tests/test_st_grid_power_web.mjs`: published Logic/TAG assets expose the verified ST grid power signal
- `tests/test_st_grid_power_web.mjs`: published Drawing Master links ST grid power to its exact rule diagrams

이 세 항목은 본 변경 범위 밖이며, 전체 시험 결과를 통과로 표시하지 않는다.
