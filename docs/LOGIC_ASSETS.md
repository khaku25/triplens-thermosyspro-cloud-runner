# TripLens — 태그·로직·Drawing Master·draw.io 한 번에 갱신하기

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
위 갱신 명령은 Drawing Master도 함께 다시 생성·게시합니다. 세 `drawing_master_index.json`을
직접 편집하지 않고 06/07 원장과 선택한 stable-ID draw.io를 입력으로 사용합니다.

## 생성되는 것

- `logic_diagrams/TripLens_Logic_Master_Current_V8.drawio`: 편집 가능한 통합 도면.
- `logic_diagrams/logic_diagram_index.json`: 태그/Rule/페이지/cell exact 색인.
- `drawing_master_index.json`: 기존 draw.io의 `object` cell 위치를 읽기 전용으로 기록한 Drawing Master 색인.
- `generated/logic/08…xlsx`, `09…xlsx`, `10…xlsx`: 같은 데이터로 생성된 원장 뷰.
- `apps/web/public/logic-assets/viewer.html`: 같은 draw.io XML을 읽는 자체 웹 뷰어. 인터넷 draw.io 사이트가 없어도 열립니다.
- `data/current_v8/` 및 `services/agent-api/triplens/current_v8/`: 동일 runtime 자료와 manifest.
- `apps/web/lib/current-logic-summary.json`: 원장 변경에 맞춰 갱신되는 웹 요약.

Drawing Master는 같은 바이트로 다음 세 위치에 게시됩니다.

| 소비자 | 게시 경로 |
|---|---|
| 편집·검토 기준 | `logic_diagrams/drawing_master_index.json` |
| 생성 릴리스 | `generated/logic/drawing_master_index.json` |
| 웹 정적 자산 | `apps/web/public/logic-assets/drawing_master_index.json` |

초기 입력 snapshot에서 603 Source Tag, 53 Rule, 35 입력 그룹, 9 설비 화면입니다.
전체 도면은 목차 1 + 설비 9 + 입력 그룹 35 + 개별 Rule 53 = 98페이지입니다.
이 숫자는 미래 버전을 강제로 제한하는 상수가 아닙니다. 실제 입력으로 다시 계산합니다.

현재 생성된 Drawing Master snapshot은 draw.io 1개, 98페이지, 1,551개 `object` cell을 색인하며,
그중 53개 고유 Logic ID와 86개 고유 Tag ID가 연결되어 있습니다. 이 수도 생성 결과이지 고정 상수가 아닙니다.

## Drawing Master 계약

Drawing Master의 정책 문자열은
`READ_ONLY_INDEX_OF_EXISTING_DRAWIO; NO_LOGIC_REINTERPRETATION`입니다.
생성기는 `TripLens_Logic_Master_Current_V8.drawio`에 이미 존재하는 `object`와 그 하위 `mxCell`만 읽습니다.
도형을 새로 만들거나, 로직 조건을 재해석하거나, 유사 이름을 임의의 태그·로직에 연결하지 않습니다.
등록되지 않은 식별자는 검색 결과가 없으며 편집 거리, 접두어 추정, 의미 기반 fuzzy matching으로 대체하지 않습니다.

색인의 최상위 `schema_version`은 1이며, 기존 `logic_diagram_index.json`과 draw.io의 schema 2와는
서로 다른 파일 계약입니다. 주요 필드는 다음과 같습니다.

| 범위 | 필드 | 의미 |
|---|---|---|
| 색인 | `index_type`, `policy`, `source_sha256`, `counts` | 색인 유형, 읽기 전용 정책, 원본 draw.io 해시, 동적 집계 |
| 도면 | `drawing_id`, `file_path`, `aliases`, `sha256`, `page_count` | 원본 경로와 동일 도면의 게시 별칭 |
| 위치 | `page_id`, `page_name`, `page_scope`, `cell_id`, `x`, `y`, `width`, `height` | 기존 페이지·cell exact ID와 XML의 좌표 |
| 연결 | `canonical_tag`, `tag_id`, `logic_id`, `equipment_id`, `object_type` | XML 속성과 페이지 메타데이터에서 보존한 식별자 |
| 증거 | `source_ref`, `evidence_ref`, `verification_status` | `파일#page=<exact>&cell=<exact>` 형태의 재현 가능한 위치 |

`verification_status=INDEXED_FROM_DRAWIO_XML`은 해당 객체가 XML에서 색인되었다는 뜻입니다.
보호동작이 실기에서 검증됐거나 사고 원인이 확정됐다는 의미가 아닙니다.
명시적인 canonical mapping이 없을 때 점(`.`)이 들어간 `tag_id`는 같은 문자열을
`canonical_tag`에 그대로 보존합니다. 이는 별칭이나 의미를 추론하는 동작이 아닙니다.
`equipment_id`는 명시된 값, equipment 페이지 이름, `group_id` 순서로 기존 XML 값만 사용합니다.

Python의 `search_drawing_master()`는 `canonical_tag`, `tag_id`, `logic_id`, `page_name`,
`display_name`, `equipment_id`, `source_ref`, `keywords`를 대소문자 구분 없이 리터럴로 검색하고
필드 전체가 정확히 일치하는 결과를 먼저 둡니다. 웹의 Drawing Master 탭도 `page_name`, `page_id`,
`cell_id`, `tag_id`, `canonical_tag`, `logic_id`, `display_name`, `source_ref`에 실제 저장된 문자열만 검색합니다.
부분 문자열 검색은 허용하지만 식별자를 정규화하거나 다른 객체로 추론하지 않습니다.

## 웹에서 보는 법

기존 TripLens의 **Logic / TAG / Drawing Master** 버튼이 도면 상세 창을 엽니다.
분석 결과의 태그를 누르면 동일 상세 창에서 해당 태그의 관련 로직으로 이동합니다.
창을 닫으면 업로드 파일/분석 결과를 유지한 기존 화면으로 돌아옵니다.
별도 페이지는 `/logic`, 직접 연결은 `/logic?tag=vppHPDrumLevelM` 또는 `/logic?rule=AL-HP-LEVEL-HH`입니다.
Drawing Master 위치는 다음과 같이 exact `source_ref`를 URL 인코딩해 직접 열 수 있습니다.

```text
/logic?drawing=logic_diagrams%2FTripLens_Logic_Master_Current_V8.drawio%23page%3DIG-030%26cell%3Doperation%3ACMD-FWP-HP-TRIP
```

독립 뷰어는 같은 값을 `#drawing=...` hash로 받습니다. iframe API의
`TripLensLogic.openDrawing(sourceRefOrCellId)`는 완전한 `source_ref` 또는 전역에서 고유한 `cell_id`를 받아
해당 페이지로 이동하고 그 cell 하나만 선택 표시합니다. `cell_id`가 페이지 사이에 중복되면 첫 항목을
임의 선택하지 않고 `false`를 반환하며 완전한 `source_ref` 사용을 안내합니다. 선택 후 hash도 완전한
`source_ref`로 갱신됩니다.
근거 상세에서는 Evidence Catalog의 `source_node`와 `logic_ids`를 각각 태그 도면/Rule 도면 버튼으로 표시합니다.
운영 분석 전에 `/testbench`에서 GT·ST·52GT·52ST·HP/IP/LP FWP·HP/IP/LP Drum의 exact 연결을 독립적으로 확인할 수 있습니다.
도면 입력/출력을 누르면 태그 상세로, 로직 블록을 누르면 Rule 상세로 이동합니다.
등록되지 않은 식별자는 임의로 비슷한 태그에 매칭하지 않습니다.

모바일에서도 분석 화면의 Drawing Master 진입 버튼을 숨기지 않습니다. 뷰어의 탭은 줄바꿈되고
Drawing Master가 한 줄 전체의 터치 대상으로 표시됩니다. 390×844 브라우저 회귀시험은
`operation:CMD-FWP-HP-TRIP` 검색이 `IG-030`의 exact cell을 선택하는지와 문서 가로 overflow가 없는지 확인합니다.

## draw.io에서 수정 가능한 범위

통합 도면/색인/asset manifest는 schema 2입니다. 각 분기는 **INPUT → CONDITION → OPERATION → OUTPUT**
네 열로 표시합니다. 기본 x/너비는 각각 40/320, 410/320, 780/320, 1150/360px이며,
분기 높이는 최소 250px이고 출력 수에 따라 확장합니다. 지연, 복귀/히스테리시스, 동작 검증 상태,
출력 분류는 동작 아래 **ADDITIONAL INFO**에만 표시하며 신호선에 연결하지 않습니다.
중앙 블록 ID는 `condition:{rule_id}`, `operation:{rule_id}`, `additional:{rule_id}`입니다.
페이지 및 기존 입력/출력 ID와 원장 semantic hash는 바뀌지 않습니다.

schema 1의 `logic:` 레이아웃은 한 번 schema 2로 이전합니다. 이전 좌표가 새 열 제목/분기와 겹치지 않도록
이때 전체 기본 좌표를 다시 배치합니다. 이전 후 schema 2로 저장한 위치·크기·선 좌표는 다음 갱신에 유지됩니다.
선언된 schema와 중앙 ID가 다르거나 schema 1/2 중앙 ID가 섞인 파일, 지원하지 않는 schema는 차단합니다.
뷰어는 XML과 색인 모두 schema 2인 경우에만 열립니다.

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
Hysteresis와 지연은 ADDITIONAL INFO에 원장 속성으로 기록하며 별도의 하류 실행 블록을 추측해 붙이지 않습니다.

Drawing Master는 원본 XML의 SHA-256을 `source_sha256`과 도면 항목의 `sha256`에 기록합니다.
이 값은 `logic_diagram_index.json`의 `drawio_sha256`과 같아야 하며, 웹 뷰어는 다르면 fail-closed합니다.
세 게시 위치의 `asset_manifest.json`은 각 위치의 `drawing_master_index.json` SHA-256을 기록합니다.
`--check`는 원본, 색인, 세 게시 복사본과 manifest가 다시 생성한 결과와 일치하는지 쓰기 없이 검사합니다.

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

현재 Drawing Master의 입력 범위는 `logic_diagrams/TripLens_Logic_Master_Current_V8.drawio` 한 개뿐입니다.
`topology/`의 SVG/PNG, P&ID, SLD, Modelica/ThermoSysPro 모델, FMU, OPC UA node/runtime,
보호 로직 실행 코드는 색인 대상이 아니며 이 갱신으로 변경되지 않습니다. Drawing Master 생성 자체도
원본 XML을 수정하지 않습니다. 기존 뷰어의 별도 레이아웃 편집 기능으로 내보낸 파일은 사용자가
`--layout`으로 명시해 다음 갱신에 전달할 때만 채택됩니다. Drive 쓰기도 `--sync-drive`와 별도 인증 없이는 수행하지 않습니다.

## 개발 검증

```sh
python -m unittest discover -s tests -p 'test_logic_*.py'
python -m unittest tests.test_drawing_master -v
python -m unittest tests.test_logic_pipeline -v
python -m unittest discover -s tests -p test_current_catalog.py
python scripts/update_triplens_logic.py --check
npm run build --prefix apps/web
git diff --check
```

브라우저 테스트에는 Playwright 1.57.0과 Chromium이 필요합니다.
`test_drawing_master.py`는 색인 스키마, exact source reference, 원본 hash 결합, 모바일 탭 배치와
canonical tag 보존을 검사합니다. `test_logic_pipeline.py`는 세 게시 복사본의 byte equality와
각 manifest의 hash를 검사합니다. `test_logic_viewer.py`는 데스크톱/모바일 탐색과 exact cell 선택을 검사합니다.
GitHub의 **Update TripLens Logic Assets** workflow는 이 테스트와 Next.js production build를 실행한 뒤
마지막 `--check` 및 `git diff --check`를 다시 수행합니다.
생성기/엑셀 reader/도면 exporter에는 Python 3.10 이상 표준 라이브러리만 필요합니다.
Testbench, 근거 상세 매핑과 GitHub→Vercel 단일 승격 절차는 [`INTEGRATION_TESTBENCH_REPORT_V2.md`](INTEGRATION_TESTBENCH_REPORT_V2.md)를 따릅니다.
