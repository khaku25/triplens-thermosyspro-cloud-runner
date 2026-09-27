# TripLens 개발일지

> 이 기록은 GitHub `main`의 커밋 이력과 저장소 문서에서 확인되는 프로젝트 변화를 날짜순으로 요약합니다.

| 기준 | 내용 |
|---|---|
| 기간 | 2026-09-07–2026-09-27 |
| 날짜 기준 | Git 커밋 작성 시각(UTC) |
| 범위 | 데이터·실행 기반부터 웹/API, 근거 탐색, 보고서 검토 흐름까지의 주요 마일스톤 |
| 작성 원칙 | 개별 설비·고장 사례를 일반 기능이나 성능 주장으로 확대하지 않음 |

## 2026-09-07–09-09 · 실행 및 데이터 기반

- Actions의 깨끗한 checkout에서도 검증이 재현되도록 실행·검사 절차를 정리했습니다.
- 원본 출력과 manifest를 분리하고, 데이터 변환 계약을 범용화했습니다.
- 등록 참조를 실제 데이터 및 모델 소스에 연결해 Tag/Logic 색인의 근거를 분명히 했습니다.
- 참고 커밋: [깨끗한 실행 환경 검증](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/6fd1824880f97c957ba5a04013f3d789fb1dbd5d), [데이터 계약 일반화](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/4daab5d06f84773f0cff8ec56551d62718910afa), [소스 기반 참조 색인](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/37b403c23bb67da50478b7c793a118bfd7c38117)

## 2026-09-10–09-14 · 재현성과 검증 경계

- 실행 인터페이스와 출력 단위·데이터 계약을 정리했습니다.
- 반복 가능한 실행에 필요한 의존성 검사와 경계 검증을 보강했습니다.
- 참고 커밋: [공정 데이터 계약](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/8adb499f0779570f49fc4cb1fe499f5dc3775eb4), [실행 의존성 검증](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/886847c6244c649e144dbf2aa085d36c971fc347)

## 2026-09-17–09-20 · TripLens 웹/API와 보고서

- 웹 UI와 Agent API를 분리하고, 제한된 도구를 통해 필요한 근거만 조회하는 분석 구조를 마련했습니다.
- 근거 연결형 분석 출력, 보고서 V2 내보내기, 검토 흐름을 구현했습니다.
- 참고 커밋: [보고서 UX 기준선](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/1b3c54f6e700c567e4d41b638976d56e5086e0d1), [제한형 Evidence Tools](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/4d62197212ab136ffc7bbe0e59ad84805ef048aa), [읽기 전용 Agent API](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/d33396345749b7cd3e56678807ab082cebfe0b21), [보고서 V2 및 Testbench](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/64d618a593e8b7011906d1c03b9da62336aae3c1), [운영자 분석 UI](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/ff318d425543defeaa1aa74deb1e33400981b768)

## 2026-09-21–09-25 · 근거 탐색과 문맥 연결

- 등록 참조 화면과 분석 화면을 연결하고, 근거에서 관련 도면·공정 문맥으로 이동하는 흐름을 보강했습니다.
- 분석 근거 레이블과 보고서 표현을 검토하기 쉽게 다듬었습니다.
- 참고 커밋: [사용자용 참조 화면](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/9d60748dc5a7f01bc3e29b44957f8158ae0b73cb), [분석에서 도면 참조로 이동](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/d93290b1ba365d0dd3c185ffa7154d44d6920eba), [공정 화면과 도면 참조 연결](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/f509476247a96d44860e9331012b5884abeb5850), [통합 문맥 탐색](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/113fdec4be0a6c6eb06910f4a695eda7c84247ec)

## 2026-09-26–09-27 · 제공자 설정과 통합 정리

- 분석 제공자 선택을 저장하고, 여러 제공자가 일관된 보고서 요약을 만들도록 정리했습니다.
- 참조 색인과 관련 화면의 표시를 동기화하고, 제출용 설명을 최신 구현 기준으로 다듬었습니다.
- 참고 커밋: [제공자 선택 저장](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/b4dc6c1eb1d81777c1fd610c4149ae0e759b2de7), [공통 보고서 요약](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/4d7322c3a188a2a9b23b8bc67c68bb1dc579a9ba), [참조 색인 동기화](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/38c1b2a879a0ce8963924c93e67d8484f85e18f6), [제출 기준 수 정렬](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/9a0262391367baf1139f87cb8bcae8baf3bf76a5)

## 기록 해석

이 문서는 주요 이정표를 기능 흐름에 따라 요약한 선택 기록이며 모든 커밋을 나열하지 않습니다. 각 링크는 해당 변경을 확인하기 위한 원본 커밋입니다. 검증 결과는 [검증 문서](../docs/INTEGRATION_TESTBENCH_REPORT_V2.md)와 저장소의 관련 기록에서 범위별로 확인하세요.

[전체 GitHub 커밋 이력](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commits/main/) · [README](../README.md)

