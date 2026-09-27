# TripLens 개발일지

> GitHub `main`의 커밋 기록에서 TripLens 웹/API와 사용자 검토 흐름에 해당하는 주요 변경을 추려 정리했습니다.

| 기준 | 내용 |
|---|---|
| 기간 | 2026-09-17–2026-09-27 |
| 자료 | GitHub 커밋 기록 및 저장소 문서 |
| 날짜 기준 | 커밋 작성 시각 UTC |
| 범위 | 주요 마일스톤 요약; 모든 커밋을 나열하지 않음 |

## 2026-09-17–09-18 · 분석 기반과 근거 조회

- TripLens 웹/API의 역할을 분리하고, EVENT/RAW 근거를 제한된 단위로 조회하는 분석 기반을 구성했습니다.
- 실제 근거 조회와 형식 검사를 프로그램 경계에 두고, AI는 반환된 근거를 해석하도록 연결했습니다.
- 참고 커밋: [보고서 UX 기준선](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/1b3c54f6e700c567e4d41b638976d56e5086e0d1), [제한형 Evidence Tools](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/4d62197212ab136ffc7bbe0e59ad84805ef048aa), [읽기 전용 Agent API](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/d33396345749b7cd3e56678807ab082cebfe0b21)

## 2026-09-19–09-20 · 보고서와 검토 흐름

- 보고서 V2 내보내기와 통합 Testbench를 추가했습니다.
- 분석 결과, 근거 인용, 보고서 편집을 연결하는 운영자용 웹 화면을 정리했습니다.
- 참고 커밋: [보고서 V2 및 Testbench](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/64d618a593e8b7011906d1c03b9da62336aae3c1), [분석 UI 기준선](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/ff318d425543defeaa1aa74deb1e33400981b768)

## 2026-09-21–09-22 · 참조 탐색과 보고서 가독성

- Tag/Logic 참조 화면을 운영자 관점으로 정리하고, 분석과 도면 탐색 사이의 이동을 연결했습니다.
- 분석 근거 레이블과 보고서 문구를 검토하기 쉽게 다듬었습니다.
- 참고 커밋: [사용자용 참조 자산](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/9d60748dc5a7f01bc3e29b44957f8158ae0b73cb), [분석에서 도면 참조로 이동](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/d93290b1ba365d0dd3c185ffa7154d44d6920eba), [근거 표현 가독성](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/6b2ce128d07f6f89c532ccf261823a67b82a4440)

## 2026-09-23–09-25 · 근거와 화면 문맥 연결

- 등록된 EVENT 참조에서 관련 도면 위치를 찾고, Plant Process와 Drawing 화면 사이의 탐색을 연결했습니다.
- 같은 근거를 분석 화면에서 관련 설비·로직 문맥으로 따라갈 수 있도록 검색과 링크 동작을 보강했습니다.
- 참고 커밋: [공정 화면과 도면 참조 연결](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/f509476247a96d44860e9331012b5884abeb5850), [통합 뷰 정리](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/113fdec4be0a6c6eb06910f4a695eda7c84247ec)

## 2026-09-26–09-27 · 제공자 설정과 제출면 정리

- 분석 제공자 선택을 저장하고, 서로 다른 제공자에서 보고서 요약 형식을 공유하도록 정리했습니다.
- 검색 가능한 참조 색인과 관련 화면의 표시 상태를 동기화했습니다.
- 참고 커밋: [제공자 선택 저장](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/b4dc6c1eb1d81777c1fd610c4149ae0e759b2de7), [공통 보고서 요약](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/4d7322c3a188a2a9b23b8bc67c68bb1dc579a9ba), [색인 및 화면 동기화](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commit/38c1b2a879a0ce8963924c93e67d8484f85e18f6)

## 기록 해석

이 문서는 선택한 커밋을 기능 흐름에 따라 요약한 개발 기록입니다. 커밋 설명과 연결된 변경을 근거로 작성했으며, 검증 결과나 제품의 현장 정확도를 대신하지 않습니다. 세부 검증 범위는 저장소의 테스트·검증 문서에서 확인합니다.

[전체 GitHub 커밋 기록](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/commits/main/) · [README](../README.md)

