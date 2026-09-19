# TripLens — 태그·로직·draw.io 한 번에 갱신하기

## 사용자가 수정하는 곳은 두 원장입니다

`data/current_v8/masters/06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx`의 `01_Live_OPCUA_Tag_Master`와
`07_LOGIC_MASTER_CURRENT_V8_VERIFIED.xlsx`의 `01_Logic_Master_Current`를 수정합니다.
06의 태그 설명/단위/분류와 07의 조건/지연/복귀/입출력이 편집 원본입니다.
08 연결표, 09 도면 정의, 10 입력·설비 그룹은 **자동 생성물**입니다. 이 셋을 따로 고치지 않습니다.

Google Drive 원본 ID는 유지합니다. 로컬 파일을 편집하거나 `-FromDrive`로 최신 원본을 내려받습니다.
공유 파일 다운로드가 허용되지 않을 때는 인증 없는 HTML 응답을 엑셀로 오인하지 않고 중단합니다.

## 평소 실행

Windows PowerShell, 저장소 폴더에서:

```powershell
.\UPDATE_TRIPLENS_LOGIC.ps1
```

Drive에서 최신 06/07을 가져온 뒤 갱신:

```powershell
.\UPDATE_TRIPLENS_LOGIC.ps1 -FromDrive
```

draw.io에서 위치·크기를 다듬은 파일도 함께 반영:

```powershell
.\UPDATE_TRIPLENS_LOGIC.ps1 -FromDrive -Layout "C:\TripLens\TripLens_Logic_Master_Current_V8.drawio"
```

검증 후 GitHub로 commit/push까지 실행(해당 PC의 Git 인증 필요):

```powershell
.\UPDATE_TRIPLENS_LOGIC.ps1 -FromDrive -Publish
```

Linux/macOS:

```sh
./UPDATE_TRIPLENS_LOGIC.sh --from-drive
```

`--check`는 기존 산출물의 일치 여부만 검사하며 쓰지 않습니다.

## 생성되는 것

- `logic_diagrams/TripLens_Logic_Master_Current_V8.drawio`: 편집 가능한 통합 도면.
- `logic_diagrams/logic_diagram_index.json`: 태그/Rule/페이지/cell exact 색인.
- `generated/logic/08…xlsx`, `09…xlsx`, `10…xlsx`: 같은 데이터로 생성된 원장 뷰.
- `apps/web/public/logic-assets/viewer.html`: 같은 draw.io XML을 읽는 자체 웹 뷰어. 인터넷 draw.io 사이트가 없어도 열립니다.
- `data/current_v8/` 및 `services/agent-api/triplens/current_v8/`: 동일 runtime 자료와 manifest.
- `apps/web/lib/current-logic-summary.json`: 원장 변경에 맞춰 갱신되는 웹 요약.

초기 입력 snapshot에서 603 Source Tag, 53 Rule, 35 입력 그룹, 9 설비 화면입니다.
전체 도면은 목차 1 + 설비 9 + 입력 그룹 35 + 개별 Rule 53 = 98페이지입니다.
이 숫자는 미래 버전을 강제로 제한하는 상수가 아닙니다. 실제 입력으로 다시 계산합니다.

## 웹에서 보는 법

기존 TripLens의 **Event Logic Master** 버튼이 도면 상세 창을 엽니다.
분석 결과의 태그를 누르면 동일 상세 창에서 해당 태그의 관련 로직으로 이동합니다.
창을 닫으면 업로드 파일/분석 결과를 유지한 기존 화면으로 돌아옵니다.
별도 페이지는 `/logic`, 직접 연결은 `/logic?tag=vppHPDrumLevelM` 또는 `/logic?rule=AL-HP-LEVEL-HH`입니다.
근거 상세에서는 Evidence Catalog의 `source_node`와 `logic_ids`를 각각 태그 도면/Rule 도면 버튼으로 표시합니다.
운영 분석 전에 `/testbench`에서 GT·ST·52GT·52ST·HP/IP/LP FWP·HP/IP/LP Drum의 exact 연결을 독립적으로 확인할 수 있습니다.
도면 입력/출력을 누르면 태그 상세로, 로직 블록을 누르면 Rule 상세로 이동합니다.
등록되지 않은 식별자는 임의로 비슷한 태그에 매칭하지 않습니다.

## draw.io에서 수정 가능한 범위

같은 페이지 ID와 cell ID가 유지되는 경우 위치(x/y), 크기(width/height), 선 꺾임 좌표,
안전한 기본 색/테두리/폰트 크기를 다음 생성 때 유지합니다.
내용(태그/조건/입출력)은 06/07이 우선합니다. draw.io의 문구를 고쳐도 로직 원장이 역으로 바뀌지 않습니다.
웹 뷰어에서는 위치를 끌어 바꾸고 `.drawio`로 저장할 수 있습니다. 크기와 세밀한 선 편집은 draw.io 편집기에서 합니다.
새 태그/블록은 기본 위치로 추가되고 삭제된 Rule은 다시 생성되지 않습니다.

예전 숫자 cell ID로 만든 53/35페이지 preview 두 파일은 이 새 stable-ID 저장소와 다릅니다.
예전 preview는 보존하며, **이번 통합 파일부터** 레이아웃 보존을 지원합니다.
임의의 새 draw.io 도형·스텐실·외부 이미지·수식 렌더러를 전부 지원하는 범용 draw.io 편집기를 구현한 것은 아닙니다.
이 저장소가 생성한 로직 블록/태그/연결 및 위 레이아웃 속성을 지원합니다.

## 오류를 막는 방식

중복 Tag/Rule/페이지/cell ID, 등록되지 않은 입력/출력, Lab-only 입력의 운용로직 사용,
동일 입력의 상충 그룹 ID, 수식이 남은 원장, XML DTD/ENTITY, 과도한 좌표/파일 크기를 차단합니다.
태그를 새로 등록하려면 실제 live census와 해당 census의 SHA-256/실행 정보도 제공해야 합니다.
원장에 태그 이름만 적어서는 live 증거가 생기지 않습니다.

`data/current_v8/live_census_provenance.json`은 기존 Run #54 증거를 고정합니다.
새 OPC UA 실행을 쓰려면 `--census`와 `--census-provenance`를 짝으로 지정합니다.
이 UPDATE는 시뮬레이션을 다시 실행하지 않습니다.

53개 Rule의 기존 `validation_status`는 유지합니다. Live 태그 존재성 검증과 보호동작/물리 검증을 혼동하지 않습니다.
`event-driven`, `runtime-defined`, `external runtime interface`는 타이머 초 값으로 만들지 않습니다.
Hysteresis는 Rule 복귀 속성으로 기록하며 별도의 하류 실행 블록을 추측해 붙이지 않습니다.

## 저장·배포 경계

로컬 갱신은 산출물을 staging에서 생성·검사한 뒤 반영합니다. 처리 중 예외에는 변경 파일을 복구합니다.
전원 장애나 여러 서비스(Drive/GitHub/Vercel) 전체를 한 트랜잭션으로 보장하지는 않습니다.
웹의 draw.io/index SHA와 Agent API의 CSV/manifest SHA가 어긋나면 fail-closed합니다.

GitHub의 **Update TripLens Logic Assets** workflow는 검증 후 생성 결과를 같은 branch에 commit합니다.
Vercel 반영은 그 commit의 배포가 READY인지 별도로 확인해야 합니다. build 한도/배포 실패를 저장 성공으로 포장하지 않습니다.

Drive의 08/09/10 자동 덮어쓰기는 `-SyncDrive`와 승인된 `TRIPLENS_DRIVE_ACCESS_TOKEN`이 있어야 가능합니다.
ChatGPT의 연결된 Drive 권한이 PC나 GitHub Actions에 자동 전달되지는 않습니다.
GitHub에서 지속적으로 쓰려면 해당 workflow 환경에 적절한 Drive 인증을 관리해야 합니다.
토큰/키를 파일, 원장, Git commit 또는 채팅에 넣지 않습니다.
Drive 미설정이어도 로컬/GitHub 산출물과 웹 파일 생성은 가능합니다.

## 물리모델과의 관계

이 기능은 문서·조회·도면·분석 context 갱신입니다.
예를 들어 원장의 HH 표시 조건을 1.25→1.30으로 바꿔도 실제 보호 런타임의 설정값이 바뀌지는 않습니다.
실제 플랜트/모델 변경은 별도 코드 검토와 실행 검증이 필요합니다.

## 개발 검증

```sh
python -m unittest discover -s tests -p 'test_logic_*.py'
python -m unittest discover -s tests -p test_current_catalog.py
python scripts/update_triplens_logic.py --check
```

브라우저 테스트에는 Playwright 1.57.0과 Chromium이 필요합니다.
생성기/엑셀 reader/도면 exporter에는 Python 3.10 이상 표준 라이브러리만 필요합니다.
Testbench, 근거 상세 매핑과 GitHub→Vercel 단일 승격 절차는 [`INTEGRATION_TESTBENCH_REPORT_V2.md`](INTEGRATION_TESTBENCH_REPORT_V2.md)를 따릅니다.
