# Blind Test 2 운영 실분석·고장상보 검증 기록

## 범위와 결론

2026-09-22 기준 Google Drive의 Blind Test 2 원본 12개 시나리오를 운영 웹 UI에 실제로 입력했다. 각 시나리오에서 `EVENT.csv`와 `RAW.csv` 두 파일을 직접 선택해 **Dual Log**로 업로드하고, 운영 Agent API 분석과 보고서 V2 PDF 생성을 끝까지 수행했다.

- 실제 사이트 업로드·분석·PDF 생성: **12/12 PASS**
- 생성 보고서: **12건, 총 48쪽**
- 독립 최종 시각·내용 QA: **48/48쪽 PASS**
- 페이지·본문·결재란 overflow: **전 페이지 0px**
- 표 돌출·잘림, 텍스트 겹침, 빈 페이지, 깨진 글리프: **없음**
- `분석 완료`: **7건**(04, 05, 06, 07, 08, 11, 12)
- `추가 검증 필요`: **5건**(01, 02, 03, 09, 10)

> `추가 검증 필요`는 실행 실패가 아니다. 업로드와 분석 및 PDF 생성은 정상 완료됐지만, EVENT·RAW 근거에 반증 또는 추가 확인 항목이 남아 있어 원인 확정을 보류한 보수적 Evidence Gate 결과다.

## 보고서 추적표

| 시나리오 | Run ID | 분석 판정 | PDF SHA-256 | Google Drive PDF |
|---|---|---|---|---|
| 01_direct_gt | `RUN-BAAEC3040B9B` | 추가 검증 필요 | `7f9e11f9b9dea1aafb9f797814cc3d02c304af9ea546cfb52dae81dca1f11383` | [PDF](https://drive.google.com/file/d/1DBhQs7qh1hSLqMjLK0cfbsIl53VO76zp/view?usp=drivesdk) |
| 02_direct_st | `RUN-B0C52CE44299` | 추가 검증 필요 | `b6a3b50c2fc6faa263cfec77ea99b28f94828ef9b1dc090872ff966f345897f9` | [PDF](https://drive.google.com/file/d/1gEMR2a_v4SStT1L9hfAraGAyTFIxaVDM/view?usp=drivesdk) |
| 03_gt_breaker | `RUN-B57FB628AEEB` | 추가 검증 필요 | `589895f8dfc5dd335c3af6460d2ad81e30f2583ab294ce0a9f11a2119d947e58` | [PDF](https://drive.google.com/file/d/1rTE1lpoK38_tcztASU40CoCiRhxZqWBe/view?usp=drivesdk) |
| 04_ip_bfp | `RUN-8507927F6599` | 분석 완료 | `3898ff2f24ff20e02f0818089988beb4fbf648b40eb1297f75c3d133f1f5aef8` | [PDF](https://drive.google.com/file/d/1wNCDAhk2Se3RdRZ28WxPlB8LGOzFvU3K/view?usp=drivesdk) |
| 05_hp_drum_ll | `RUN-C80BE8ADC9B8` | 분석 완료 | `93e61c60a08ec594207fd03dd43d10ef65e682cf175ee7e45139089928ba32b1` | [PDF](https://drive.google.com/file/d/1J3lApw988mFXO_EHS3mWW0DAg7cOIcW_/view?usp=drivesdk) |
| 06_ip_drum_ll | `RUN-D1BABC3C2DE4` | 분석 완료 | `4857edb53ce6e53237b1e898a602348eb1ad2971366a00fb3f274f69c45e2879` | [PDF](https://drive.google.com/file/d/1j3hiu2wFhPlm9IEE5agxOkHlG3aRhwDy/view?usp=drivesdk) |
| 07_ip_drum_hh | `RUN-33ED8F7C5D45` | 분석 완료 | `6a4c201a049565baee522975c9e20559a7724ed4d405e2d454d3a56e9de2f60a` | [PDF](https://drive.google.com/file/d/13ritnYc_7I6XNMAP0FzQpr0B1s0qbFAz/view?usp=drivesdk) |
| 08_hp_drum_hh | `RUN-C0E35A3D874B` | 분석 완료 | `984f7cbefccacad83947a5801aa5e4eef0553ae4f742fbc0601e6370570ca78e` | [PDF](https://drive.google.com/file/d/1INFuTlLRAC3teQDhYqdE5V-ngiYeDKiK/view?usp=drivesdk) |
| 09_hp_bfp | `RUN-F855F43E4131` | 추가 검증 필요 | `30388ea2ab559c1cfb1b30a1a3a08ae221e9667615c3c95954dfc6ebb28864c1` | [PDF](https://drive.google.com/file/d/1xH1Wb5Fak-PKX7uw7P6kg9bQUjTra_2a/view?usp=drivesdk) |
| 10_lp_bfp | `RUN-44F6D389B0CC` | 추가 검증 필요 | `b905f0bfd3d243dc31e16ad008aeef833d8a47a1343a061c9d72c66d5f1fba39` | [PDF](https://drive.google.com/file/d/1i938oo6cixKq5rn0o0Pcv1PTg_pgj6Jr/view?usp=drivesdk) |
| 11_lp_drum_hh | `RUN-26057690E25B` | 분석 완료 | `aaee9ceec8e390d8e8ea0bf2701ccc7ddc79c29a54eb4079a237449234d94c46` | [PDF](https://drive.google.com/file/d/1ySax-8bLDn8u--PMyPBDLqX7_bwOyOU7/view?usp=drivesdk) |
| 12_lp_drum_ll | `RUN-A665DCEBC125` | 분석 완료 | `46613ce4a7337b1e47a9197e38452ab43112abbb81725552dbe1c4717db3d73a` | [PDF](https://drive.google.com/file/d/1YmUYMw9l0d5x7FNHCM8eolxOMWjbgY49/view?usp=drivesdk) |

모음 파일과 원본 폴더:

- [12건 PDF·검증 매니페스트·README ZIP](https://drive.google.com/file/d/1swt-MId1Z9u1qWeVJjm1TuIgqNVTbgvn/view?usp=drivesdk)
- ZIP SHA-256: `85774897a5c39f1629330314bd803b510a64d066076b3729a469b0810e26e5c8`
- [Blind Test 상위 폴더](https://drive.google.com/drive/folders/1CoIHKZvI-7gsdRLRtWxPUbaxRYUNoG1o)

업로드 후 13개 객체(개별 PDF 12개와 ZIP 1개)의 원격 이름, MIME type, 대상 폴더 및 바이트 크기를 다시 조회했고 모두 로컬 산출물과 일치했다.

## 실행 배치와 실증 기준 운영 배포

최종 보고서는 다음 두 실행 배치로 구성된다.

| 보고서 생성 커밋 | 대상 | 이유 |
|---|---|---|
| `295556db45590ff1229fb49290543f32c0d13f9c` | 01~07, 09~12(11건) | 이미 독립 최종 시각·내용 QA를 통과한 보고서를 고정했다. |
| `5342aab541ada7b9df984d06993a89dbe6619afe` | 08(1건) | 접속어 `및` 뒤에 조사 `의`가 붙는 라벨 문법 오류를 수정한 뒤 해당 영향 보고서만 다시 생성·검수했다. |

11건을 다시 분석하지 않은 이유는 분석 결과의 비결정적 변화를 불필요하게 만들지 않고, 검증 완료 산출물을 보존하기 위해서다. 두 배치 모두 동일한 운영 UI의 실제 Dual Log 업로드 결과이며, 두 번째 커밋은 보고서 생성·검증 기준 운영 코드다. 후속 문서-only `main` 병합은 런타임 코드를 바꾸지 않지만 Git/Vercel 배포 SHA와 deployment ID는 갱신될 수 있다.

| 항목 | 운영 값 |
|---|---|
| 보고서 생성·검증 기준 운영 코드 커밋 | `5342aab541ada7b9df984d06993a89dbe6619afe` |
| Web | [https://triplens-web-preview.vercel.app](https://triplens-web-preview.vercel.app) |
| 보고서 생성·최종 실증 당시 Web deployment ID | `dpl_GBzbBFPHGFtLgAaNx2FxDGaY7FFF` |
| Agent API | [https://triplens-agent-api-preview.vercel.app](https://triplens-agent-api-preview.vercel.app) |
| 보고서 생성·최종 실증 당시 API deployment ID | `dpl_4Ug3X9MCEsm3zMVFXU3DmyimXMuL` |

## 검증 결과

| 검증 | 결과 |
|---|---|
| Node 전체 테스트 | 144/144 PASS |
| Python Agent API 테스트 | 45/45 PASS |
| Next.js production build | PASS |
| 저장 분석 재렌더링 | 12/12 보고서, 48쪽 PASS |
| PDF 레이아웃 | 48/48쪽의 page/content/approval overflow 0px |
| PDF 내용 | 근거 ID 합집합·순서 일치, 글꼴 내장, 잘림·겹침·빈 페이지·깨진 글리프 없음 |
| Drawing Master 데스크톱/모바일 | PASS |
| Drawing Master 선택 확인 | `operation:CMD-FWP-HP-TRIP` 검색, `IG-030`, `selected=1` |
| Drawing Master 가로 overflow | document/frame 모두 0px |
| PR #65 CI | 5/5 PASS |
| PR #66 CI | 트리거된 워크플로 4/4 PASS |

PR #66의 `Verify Citation and Review References` 워크플로는 실패한 것이 아니라 변경 경로가 해당 워크플로의 path filter와 일치하지 않아 실행되지 않았다.

- [PR #65](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/pull/65)
- [PR #66](https://github.com/khaku25/triplens-thermosyspro-cloud-runner/pull/66)

## 증적 원본

검증 실행 작업공간의 다음 산출물을 이 문서의 기계 판독 가능한 근거로 사용했다.

- `output/final/Blind_Test_2_실분석_고장상보_12건_2026-09-22_검증매니페스트.json`
- `output/final/README_최종검수.md`
- `output/pdf/run-results.json`

`run-results.json`은 각 실제 실행의 PASS 상태, Run ID, PDF 해시, 내용 QA와 페이지별 레이아웃 측정을 보존한다. 검증 매니페스트는 보고서 생성 커밋과 보고서 생성·최종 실증 당시 운영 배포를 분리해 기록한다.
