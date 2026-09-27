# TripLens — README

## 0. 문서 기준

| 항목 | 기준 |
|---|---|
| 문서 목적 | GitHub 저장소 및 제출용 웹앱 안내 |
| 확인 기준 | `main` 브랜치 소스와 TripLens 시스템 명세, 2026-09-27 기준 |
| 적용 범위 | 제품 기능, 데이터 흐름, 검증 경계, 저장소 구성 |
| 원칙 | 개별 설비·고장 사례를 제품의 일반 기능이나 성능으로 확대 해석하지 않음 |

## 1. 목적과 범위

TripLens는 산업 운영의 이벤트 및 공정 데이터를 검토하고, 분석 결과를 원본 근거와 연결해 보여주는 읽기 전용 분석·보고 도구입니다. 본 저장소는 TripLens 웹 애플리케이션, Agent API, 데이터 계약, 검증 도구와 공학 참고 자산을 포함합니다.

| 구분 | 내용 |
|---|---|
| 웹 앱 | [현재 TripLens 배포](https://triplens-web-preview-cmxrp0x82-junsic-s-projects.vercel.app) |
| 소스 저장소 | [khaku25/triplens-thermosyspro-cloud-runner](https://github.com/khaku25/triplens-thermosyspro-cloud-runner) |
| 워크플로 계약 | [TripLens 데이터 및 책임 경계](docs/TRIPLENS_WORKFLOW_BOUNDARY.md) |
| 저장소 구성 | [소스 및 자산 안내](docs/repository-map.md) |

## 2. 시스템 아키텍처

| 구성 요소 | 주요 역할 | 책임 경계 |
|---|---|---|
| Web Frontend | 파일 입력, 분석·근거 탐색, Tag/Logic/Drawing 참조, 보고서 편집 | 분석 결과를 표시하고 편집하며 원인 정답을 지정하지 않음 |
| Python Agent API | 입력·시간 검증, Evidence Store, Tool 실행·Trace, Citation Check, Verification Gate | 근거 조회와 형식 검증을 수행하며 공학적 결론을 자동 승인하지 않음 |
| Evidence Store | EVENT/RAW 정렬, 색인, 등록 ID 매핑 | 판단 대신 조회 가능한 관측 근거 제공 |
| 선택 분석 제공자 | 근거 조회 요청 및 구조화된 분석 결과 생성 | Python이 반환한 근거를 해석 |
| Human Reviewer | 결론 검토, 보고서 승인 | 최종 공학 판단 수행 |

### 2.1 실행 경계

- Frontend는 파일 선택, 분석 결과와 근거 탐색, Tag/Logic/Drawing 이동, 보고서 편집을 담당합니다.
- Agent API는 입력 검증, 근거 구성, 제한된 Tool 실행, 인용 검사와 Gate를 담당합니다.
- 분석 제공자 API 키는 서버 환경에서만 사용하며 Frontend에 전달하지 않습니다.
- 브라우저 저장소가 사용되는 경우 현재 파일·분석·편집 상태를 보존하며, 서버의 영구 사고 데이터베이스를 의미하지 않습니다.

## 3. 입력과 데이터 계약

| 입력 | 내용 | 처리 기준 |
|---|---|---|
| `EVENT.csv` | Alarm, Operator Action, Protection, Breaker 등 사건 기록 | 원본 사건 및 Evidence ID 보존 |
| `RAW.csv` | 공정·전기·설비 상태의 시계열 관측값 | `model_time_s` 기준 정렬, 필요한 구간만 조회 |
| Tag / Logic Catalog | 등록 Source Tag, Logic, upstream, Drawing 참조 | exact match 사용, 미등록 ID를 추론하지 않음 |

- 동일 분석에 연결된 EVENT/RAW 입력을 함께 사용합니다.
- 직접 업로드 크기는 EVENT.csv와 RAW.csv 합계 4,000,000 bytes 이하입니다.
- `model_time_s`는 인과 순서와 분석 구간에 사용합니다. `wall_time_utc`는 감사·전송 시각으로 구분합니다.
- 분석 입력에서 정답성 Metadata를 제외하고, 별도 AI 재학습은 수행하지 않습니다.
- 원본 EVENT/RAW 관측값은 분석 과정에서 변경하지 않습니다.

## 4. 분석 Workflow

1. **입력 검증** — 파일 형식, 시간 필드, 입력 계약을 확인합니다.
2. **Evidence 구성** — 원본 행, Tag ID, 시간 참조를 보존해 조회 가능한 근거를 구성합니다.
3. **근거 조회** — 선택 분석 제공자가 Python Tool을 통해 필요한 범위의 근거를 요청합니다.
4. **구조화 분석** — 조회된 근거를 사용해 핵심 사건, 원인 후보, 직접 트리거, 후속 변화, 반대 근거를 정리합니다.
5. **Citation / Gate 검사** — 실제 조회된 근거 ID, Tag, 시간, 출력 형식을 확인합니다.
6. **보고서 검토** — 보고서 초안을 사람이 검토하고 승인합니다.

Tool은 여섯 종류이며 정해진 고정 순서로 실행되지 않습니다. 분석당 Tool 호출 예산은 합계 최대 8회입니다. 근거가 부족하면 결과를 `UNKNOWN` 또는 `HOLD`로 남깁니다.

## 5. Evidence Tools

| Tool | 목적 | 제한 |
|---|---|---|
| `search_events` | 사건 및 Alarm 검색 | 최대 20 EVENT |
| `get_event_window` | 특정 시각 전후 사건 순서 확인 | 최대 30 EVENT, ±10초 |
| `get_raw_window` | 여러 RAW Tag의 제한 구간 비교 | 최대 8 Tag, 50 Row, 20초 |
| `get_tag_series` | 단일 Tag 추세 확인 | 최대 50 Point |
| `get_logic_context` | 등록 Logic 및 upstream 관계 조회 | 최대 12 Logic Row |
| `get_equipment_state` | 주변 EVENT와 요청된 RAW Tag 상태 확인 | 최대 10 EVENT, 8 RAW Tag |

RAW 전체를 초기 Prompt에 전달하지 않습니다. 등록 Tag/Logic은 exact match로 조회하며, 유사한 항목으로 대체하지 않습니다.

## 6. 분석 출력과 상태

| 출력/상태 | 의미 | 해석 경계 |
|---|---|---|
| Critical Events | 사고 이해에 필요한 핵심 사건 | 원본 chronology를 대체하지 않음 |
| Primary Cause / Direct Trigger | 원인 후보와 직접 보호동작 | 기본 상태는 `CANDIDATE` 또는 `OBSERVED` |
| Propagation / Counter Evidence | 후속 변화와 반대 근거 | 후속 Alarm을 원인으로 자동 승격하지 않음 |
| Incident Report | 편집 가능한 8열×10섹션 보고서 초안 | Human Review 전 최종 승인 아님 |
| Claim | `OBSERVED` / `CANDIDATE` / `UNKNOWN` | 주장에 대한 관측·불확실성 상태 |
| Verification Gate | `PASS` / `HOLD` | 근거·시간·출력 형식 검증 상태 |

`PASS`는 설정된 Gate 검사를 통과했다는 뜻이며 원인 확정이나 사람의 승인을 뜻하지 않습니다. `Logic VERIFIED`도 등록 관계가 확인됐다는 의미이며 특정 상황의 공학적 인과를 확정하지 않습니다.

## 7. Web 기능

- **Evidence Explorer** — 인용된 EVENT/RAW 원본 근거를 열고 분석 화면으로 돌아갑니다.
- **Tag Master / Logic Master** — 등록 정보와 관련 로직·도면을 탐색합니다.
- **Logic Drawing / Plant Process View** — 설비·로직·도면 관점의 보조 탐색을 제공합니다.
- **Incident Report** — 동일 분석 객체의 근거와 연결된 편집 가능한 보고서 초안을 제공합니다.
- **Engineering Reviewer** — 선택적으로 별도 실행되며 보고서 Snapshot을 검토합니다.
- **PINPOINT / CSV / Evidence Export** — 관련 형식과 일부 정적 검증이 마련되어 있습니다. 전체 브라우저 Acceptance는 별도로 관리합니다.

## 8. 보고서와 리뷰 경계

- Engineering Reviewer는 `/analyze`의 자동 필수 단계가 아닙니다.
- Reviewer는 `row_id`, `current_section`, `evidence_ids`와 보고서 SHA-256 Snapshot을 확인합니다.
- 보고서를 편집하거나 재정렬해 Snapshot이 달라지면 기존 Review를 새 버전에 적용하지 않습니다.
- Reviewer와 Verification Gate는 운전 승인 또는 재기동 승인을 수행하지 않습니다.

## 9. READ-ONLY 및 보안 경계

- TripLens에서 발전소 OT로 제어명령을 반환하는 경로가 없습니다.
- EVENT/RAW 원본을 변경하거나 자동복전·재기동 명령을 수행하지 않습니다.
- AI Confidence, 등록 Logic, Gate `PASS`만으로 공학적 원인을 자동 확정하지 않습니다.
- API 키는 서버 환경변수에서만 읽으며 Frontend 코드에 전달하지 않습니다.

## 10. 현재 구현·검증 상태

아래 결과는 2026-09-27 기준 시스템 명세에 기록되어 있습니다. 서로 다른 검증 범위이므로 하나의 통과율로 합산하지 않습니다.

| 항목 | 기록된 결과 | 범위 및 제한 |
|---|---:|---|
| 기존 웹 분석 실행 | 12/12 실행 PASS | 업로드→분석→Evidence→보고서 기록 흐름. 정확도·일반화 점수가 아님 |
| Preview Tag 색인 | 606/606 searchable | 정적 ID 색인 무결성. 전체 UI 재실행과 구분 |
| Preview Logic 색인 | 55/55 searchable | 등록 ID 대조. 클릭·도면 렌더링 재검증과 구분 |
| Report QA | 48/48 페이지, 12개 산출물 | 보고서 산출물 검사. 각 결론의 승인 여부와 구분 |
| 남은 Acceptance | `PARTIAL` / `NOT TESTED` | CSV/PINPOINT, 전체 모바일, 세션 초기화 등 |

현장 정확도, 시설별 공학적 타당성, 미관측 데이터에 대한 일반화는 별도 평가가 필요합니다. 소스와 정적 검증은 해당 코드 또는 색인의 존재를 보여주며, 현장 유효성을 단독으로 입증하지 않습니다.

## 11. Software / AI Runtime Specification

| 구성 | 현재 명세 | 역할 |
|---|---|---|
| Web Frontend | Next.js 16.3.5 · React 19.2.0 | 브라우저 UI, 입력, 탐색, 보고서 편집 |
| Agent API | Python 3.12+ · FastAPI | 입력·근거·Tool·Gate 처리 |
| Analysis Provider | 기본 Gemini · 선택형 OpenAI | 근거 선택 요청 및 구조화 분석 |
| Deployment | Vercel · `main` 기준 | Web / Agent API 배포 |

Provider와 모델 설정은 변경될 수 있습니다. API 키 설정 여부는 키 유효성, 잔액 또는 실제 모델 응답을 보장하지 않습니다.

## 12. 저장소 구성 및 Source of Truth

| 경로 | 내용 |
|---|---|
| `apps/web/` | TripLens 웹 애플리케이션 |
| `services/agent-api/` | Agent API와 Provider Adapter |
| `config/`, `data/`, `logic_db/`, `logic_diagrams/` | 데이터 계약과 등록 참조 자산 |
| `scripts/`, `tests/` | 변환·검증·회귀 확인 코드 |
| `matlab/`, `modelica/`, `examples/` | 재현 가능한 공학 참고 구현과 지원 자산 |
| `docs/` | 워크플로 계약, 설계 참고자료, 검증 기록 |

웹 애플리케이션 구현의 기준은 저장소 소스와 실행 설정입니다. Google Drive 시스템 명세는 시스템 범위·데이터 계약·현재 검증 상태를 설명하는 제출용 기준 문서입니다. 지원 자산이 저장소에 있다는 사실만으로 모든 자산이 배포 앱에서 활성화되거나 모든 시설·운전 조건에 대해 검증됐다고 보지 않습니다.

## 13. 제한 및 추가 문서

TripLens는 분석·보고 지원 도구입니다. 검토자의 공학적 판단과 승인 없이 분석 결과를 운전 지시, 보호 설정, 복구 또는 재기동 결정으로 사용하지 않습니다.

- [워크플로 및 데이터 경계](docs/TRIPLENS_WORKFLOW_BOUNDARY.md)
- [간결한 보고서 작성 정책](docs/CONCISE_REPORT_POLICY.md)
- [통합 Testbench 및 보고서 흐름](docs/INTEGRATION_TESTBENCH_REPORT_V2.md)
- [저장소 구성 안내](docs/repository-map.md)

