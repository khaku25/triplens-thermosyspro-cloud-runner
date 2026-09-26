# ---------------------------------------------------------------------------
# CODE READING GUIDE
# File role: regression contract or operator review harness.
# Read in this order: fixtures/setup -> test_* or review steps -> assertions/report.
# A PASS protects only the named contract; it is not live plant, OPC UA, or field evidence
# unless the test explicitly says that it performed that external observation.
# ---------------------------------------------------------------------------
"""Real Chromium UI test with mocked HTTP analysis; NOT a live Gemini result."""
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
SERVICE=ROOT/'services'/'agent-api'
sys.path[:0]=[str(SERVICE),str(SERVICE/'tests')]
from test_live_integration import make_fixture
import bridge
from triplens.analysis_contract import normalize_analysis

OUT=ROOT/'outputs'/'integration-review';OUT.mkdir(parents=True,exist_ok=True)

def fixture():
    directory=OUT/'fixture';directory.mkdir(exist_ok=True)
    event,raw=make_fixture(directory)
    store=bridge.build_store(event,raw)
    store.search_events();series=store.get_tag_series('vppExternalTripCommandNative',48,49)
    raw_ids=series['summary']['evidence_ids']
    trace=[{'name':'get_tag_series','arguments':{'tag':'vppExternalTripCommandNative','start_time_s':48,'end_time_s':49},'status':'OK','executed':True,'evidence_ids':raw_ids,'evidence_count':len(raw_ids),'raw_evidence_count':len(raw_ids),'duration_ms':2},{'name':'get_logic_context','arguments':{'tags':['GT::TRIP_LATCH']},'status':'OK','executed':True,'evidence_ids':[],'evidence_count':0,'raw_evidence_count':0,'duration_ms':1}]
    obj=lambda claim,ids,t,tags:dict(claim=claim,evidence_ids=ids,model_time_s=t,related_tags=tags,status='CANDIDATE',ai_confidence=.8)
    result=normalize_analysis({'primary_cause':obj('외부 GT Trip 명령 입력이 관측되었습니다. 운전 의도는 미확인입니다.',raw_ids,48.4,['vppExternalTripCommandNative']),
        'direct_trigger':obj('GT Trip Latch 동작이 기록되었습니다.',['E-1'],48.44,['vppGTTripLatch']),
        'critical_events':[obj('GT Trip Latch 관측',['E-1'],48.44,['vppGTTripLatch'])],
        'propagation':[
            obj('52GT 차단기 개방 관측',['E-3'],48.52,['vpp52GTClosed']),
            obj('52ST 차단기 개방 관측',['E-4'],48.54,['vpp52STClosed']),
            *[obj(f'후속 설비 상태 {index}',['E-3'],48.54+index/100,[]) for index in range(1,6)],
        ],
        'causal_chain':[obj('외부 명령 입력 관측',raw_ids,48.4,['vppExternalTripCommandNative']),obj('GT Latch 관측',['E-1'],48.44,['vppGTTripLatch']),obj('GT 차단기 개방',['E-3'],48.52,['vpp52GTClosed'])],
        'counter_evidence':[],'additional_evidence_required':['동일 입력에 의한 GT/ST 병렬 보호동작 여부를 검토하세요.'],'review_recommendations':['운전 일지에서 명령 입력 경위를 확인하세요.']},store,trace)
    result['agent_execution']={'tool_calls_used':2,'tool_budget':8,'model':'MOCK_FOR_UI_TEST_ONLY'}
    contract=bridge.public_contract()
    envelope={'run_id':'RUN-UI-REGRESSION','data_digest':'fixture-digest','analysis_key':'same-fixture-v3','contract':contract,'analysis':result,'events':[store.describe_event(e) for e in store.event_rows],'evidence_catalog':store.evidence_catalog(),'validation':store.validation,'evidence_readiness':store.readiness()}
    return event,raw,envelope

def main():
    event,raw,data=fixture();checks=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        for width,height,name in [(1440,1000,'desktop'),(390,844,'mobile')]:
            context=browser.new_context(viewport={'width':width,'height':height},accept_downloads=True,service_workers='block')
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            counts={'analyze':0,'bootstrap':0}
            def handle(route):
                path=route.request.url.rsplit('/',1)[-1]
                if route.request.method=='OPTIONS':route.fulfill(status=204,headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'Content-Type'});return
                if path=='contract':body=data['contract']
                elif path=='bootstrap':counts['bootstrap']+=1;body={k:v for k,v in data.items() if k not in {'analysis','evidence_catalog'}}
                elif path=='analyze':counts['analyze']+=1;body=data
                else:route.abort();return
                route.fulfill(status=200,json=body,headers={'Access-Control-Allow-Origin':'*'})
            context.route('https://triplens-agent-api-preview.vercel.app/**',handle)
            context.route('**/api/triplens/**',handle)
            page.goto(os.getenv('TRIPLENS_UI_URL','http://localhost:3000/'))
            expect(page.get_by_label('EVENT 파일')).to_be_enabled()
            expect(page.get_by_text('Dual Log 대기',exact=True).last).to_be_visible()
            expect(page.get_by_text('EVENT.csv와 RAW.csv를 선택해 주세요.',exact=True).last).to_be_visible()
            assert page.get_by_text('52GT 차단기 OPEN',exact=True).count()==0
            page.get_by_label('EVENT 파일').set_input_files(str(event));page.get_by_label('RAW 파일').set_input_files(str(raw))
            expect(page.get_by_text('분석 입력 준비 완료',exact=True).last).to_be_visible()
            button=page.get_by_role('button',name='이 Dual Log 분석하기',exact=True)
            expect(button).to_be_enabled();button.click()
            expect(page.locator('.analysis-list article').filter(has_text='52GT 차단기 OPEN').first).to_be_visible(timeout=30000)
            expect(page.locator('.analysis-list article').filter(has_text='52ST 차단기 OPEN').first).to_be_visible()
            expect(page.get_by_role('heading',name='발생 원인',exact=True)).to_be_visible()
            expect(page.get_by_role('heading',name='직접 보호동작',exact=True)).to_be_visible()
            expect(page.get_by_role('heading',name='파급 과정',exact=True)).to_be_visible()
            expect(page.get_by_role('heading',name='시간순 사고 경위',exact=True)).to_be_visible()
            page.get_by_role('button',name=re.compile('사고 진행 과정')).click()
            gt_event=page.locator('.operator-timeline article').filter(has_text='52GT').first
            logic_action=gt_event.get_by_role('button',name='[로직]',exact=True)
            drawing_action=gt_event.get_by_role('link',name='[드로잉]',exact=True)
            expect(logic_action).to_be_visible()
            expect(drawing_action).to_have_attribute('href',re.compile(r'/drawing\?equipment=GT&view=plant&event=vpp52GTClosed'))
            with page.expect_popup() as drawing_popup:
                drawing_action.click()
            plant_view=drawing_popup.value
            expect(plant_view).to_have_url(re.compile(r'/drawing\?equipment=GT&view=plant&event=vpp52GTClosed'))
            expect(plant_view.get_by_text('TRIPLENS PLANT VIEW',exact=True)).to_be_visible()
            plant_view.close()
            logic_action.click()
            logic_dialog=page.get_by_role('dialog',name='Logic / TAG Master · 로직 도면')
            expect(logic_dialog.locator('iframe')).to_have_attribute('src',re.compile(r'tag=vpp52GTClosed'))
            logic_dialog.get_by_role('button',name='닫기',exact=True).click()
            page.get_by_role('button',name=re.compile('원인 분석')).click()
            expect(page.get_by_text('후속 설비 상태 4',exact=True)).to_be_hidden()
            page.locator('summary',has_text='후속 분석 2건 보기').click()
            expect(page.get_by_text('후속 설비 상태 4',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='분석 완료',exact=True)).to_be_disabled()
            body_text=page.locator('body').inner_text()
            for hidden in ('Current Logic Master upstream','고정 Cause Matrix','Verification Gate','HOLD','CANDIDATE','초안','PINPOINT','Notion'):
                assert hidden not in body_text,hidden
            assert '2026-09-15T14:52:04.212+00:00s' not in page.locator('body').inner_text()
            colors=page.evaluate("""() => ({
              header:getComputedStyle(document.querySelector('.topbar')).backgroundColor,
              sidebar:getComputedStyle(document.querySelector('.sidebar')).backgroundColor,
              canvas:getComputedStyle(document.querySelector('.main-area')).backgroundColor,
              panel:getComputedStyle(document.querySelector('.analysis-surface')).backgroundColor
            })""")
            assert colors=={'header':'rgb(35, 63, 80)','sidebar':'rgb(52, 83, 99)','canvas':'rgb(227, 232, 235)','panel':'rgb(251, 252, 253)'},colors
            page.screenshot(path=str(OUT/f'{name}-analysis.png'),full_page=True)
            gt_open=page.locator('.analysis-list article').filter(has_text='52GT 차단기 OPEN').first
            gt_open.locator('summary',has_text='상세 근거 보기').click()
            gt_open.get_by_role('button',name='연결 근거 모아보기 · 1건',exact=True).click()
            expect(page.get_by_role('button',name='이전 화면',exact=True)).to_be_visible()
            expect(page.get_by_role('heading',name='근거 상세',exact=True)).to_be_visible()
            logic_button=page.locator('.logic-targets button')
            expect(logic_button).to_have_count(1)
            expect(logic_button).to_contain_text('52GT 차단기 상태 로직 보기')
            expect(logic_button).to_contain_text('관련 로직')
            logic_button.click()
            dialog=page.get_by_role('dialog',name='Logic / TAG Master · 로직 도면')
            expect(dialog).to_be_visible()
            expect(dialog.locator('iframe')).to_have_attribute('src',re.compile(r'tag=vpp52GTClosed'))
            dialog.get_by_role('button',name='닫기',exact=True).click()
            page.get_by_role('button',name='이전 화면',exact=True).click()
            expect(page.locator('.analysis-list article').filter(has_text='52GT 차단기 OPEN').first).to_be_visible()
            direct=page.locator('.cause-card').filter(has_text='직접 보호동작')
            direct.locator('summary',has_text='상세 근거 보기').click()
            direct.get_by_role('button',name='연결 근거 모아보기 · 1건',exact=True).click()
            expect(page.get_by_role('heading',name='근거 상세',exact=True)).to_be_visible()
            page.get_by_role('button',name='이전 화면',exact=True).click()
            if width>640:
                page.locator('.side-links button').click()
                logic_dialog=page.get_by_role('dialog',name='Logic / TAG Master · 로직 도면')
                expect(logic_dialog).to_be_visible()
                viewer=page.frame_locator('dialog iframe')
                expect(viewer.get_by_role('banner').get_by_text('태그 · 로직 · 도면 검색 · 상세 정보',exact=True)).to_be_visible()
                expect(viewer.get_by_role('button',name='도면',exact=True)).to_be_visible()
                viewer_text=viewer.locator('body').inner_text()
                assert 'Drawing Master' not in viewer_text
                for hidden in ('고정 Cause Matrix','등록 확인은 사고 원인 확정','미등록 관측 태그','등록 Logic: 미확인'):
                    assert hidden not in viewer_text,hidden
                logic_dialog.get_by_role('button',name='닫기',exact=True).click()
            page.get_by_role('button',name='고장분석 보고서 보기',exact=True).click()
            page.locator('summary',has_text='보고서 세부 항목 편집').click()
            page.get_by_label('보고서 1 content',exact=True).fill('담당자 검토 수정 내용')
            pdf_button=page.get_by_role('button',name='보고서 PDF 저장',exact=True)
            expect(pdf_button).to_be_visible()
            expect(pdf_button).to_be_enabled()
            page.context.add_init_script("Object.defineProperty(window,'print',{configurable:true,value:function(){document.documentElement.dataset.printRequested='true'}})")
            page.evaluate('window.open=()=>null')
            pdf_button.click()
            pdf_dialog=page.get_by_role('dialog',name='PDF 보고서 미리보기')
            expect(pdf_dialog).to_be_visible()
            pdf_report=page.frame_locator('dialog[aria-label="PDF 보고서 미리보기"] iframe')
            expect(pdf_report.locator('.report-page')).to_have_count(4)
            assert '설비 장애·고장 보고서' in pdf_report.locator('body').inner_text()
            pdf_dialog.get_by_role('button',name='PDF 저장 / 인쇄',exact=True).click()
            expect(pdf_report.locator('html')).to_have_attribute('data-print-requested','true')
            pdf_dialog.get_by_role('button',name='닫기',exact=True).click()
            expect(pdf_dialog).to_be_hidden()
            st_view=page.context.new_page()
            st_view.goto(os.getenv('TRIPLENS_UI_URL','http://localhost:3000').rstrip('/')+'/drawing?equipment=GT&view=plant')
            with st_view.expect_popup() as st_breaker_popup:
                st_view.get_by_role('link',name='52ST 차단기 위치 →',exact=True).click()
            st_breaker=st_breaker_popup.value
            expect(st_breaker.get_by_role('heading',name='ECMS Overview',exact=True)).to_be_visible()
            expect(st_breaker.locator('.triplens-highlight-layer')).to_have_count(1)
            expect(st_breaker.locator('.triplens-highlight-layer')).to_contain_text('TAG · vppSTGridPowerMW')
            assert '52ST' in st_breaker.get_by_role('region',name='설비 상세 정보').inner_text()
            st_breaker.close()
            st_view.close()
            assert page.get_by_role('button',name=re.compile('PINPOINT')).count()==0
            page.locator('summary',has_text='내보내기').click()
            with page.expect_download() as detailed_download:page.get_by_role('button',name='상세 분석 데이터 CSV',exact=True).click()
            detailed_download.value.save_as(str(OUT/f'{name}-detail.csv'))
            assert (OUT/f'{name}-detail.csv').read_text(encoding='utf-8-sig').startswith('run_id,pinpoint_rank,causal_stage,claim,disposition,')
            with page.expect_download() as d:page.get_by_role('button',name='보고서 CSV',exact=True).click()
            d.value.save_as(str(OUT/f'{name}-edited-report.csv'))
            assert '담당자 검토 수정 내용' in (OUT/f'{name}-edited-report.csv').read_text(encoding='utf-8-sig')
            page.screenshot(path=str(OUT/f'{name}-report.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), 'page-wide horizontal overflow'
            page.get_by_label('EVENT 파일').dispatch_event('click')
            page.get_by_label('EVENT 파일').set_input_files(str(event))
            expect(page.get_by_text('분석 입력 준비 완료',exact=True).last).to_be_visible()
            assert page.get_by_text('52GT 차단기 OPEN',exact=True).count()==0
            button=page.get_by_role('button',name='이 Dual Log 분석하기',exact=True)
            expect(button).to_be_enabled();button.click()
            expect(page.locator('.analysis-list article').filter(has_text='52GT 차단기 OPEN').first).to_be_visible(timeout=15000)
            assert counts['analyze']==2,counts
            page.reload()
            expect(page.get_by_text('Dual Log 대기',exact=True).last).to_be_visible()
            assert page.get_by_text('52GT 차단기 OPEN',exact=True).count()==0
            expect(page.get_by_role('button',name='이 Dual Log 분석하기',exact=True)).to_be_disabled()
            page.get_by_label('EVENT 파일').set_input_files(str(event));page.get_by_label('RAW 파일').set_input_files(str(raw))
            page.get_by_role('button',name='이 Dual Log 분석하기',exact=True).click()
            expect(page.locator('.analysis-list article').filter(has_text='52GT 차단기 OPEN').first).to_be_visible(timeout=15000)
            assert counts['analyze']==3,counts
            page.get_by_role('button',name=re.compile('사고 진행 과정')).click()
            page.locator('summary',has_text='전체 사건 기록 보기').click()
            assert page.locator('table').last.locator('tbody tr').count()==4
            page.goto(os.getenv('TRIPLENS_UI_URL','http://localhost:3000/').rstrip('/')+'/testbench')
            expect(page.get_by_role('heading',name='TripLens 연동 단위기기 테스트',exact=True)).to_be_visible()
            expect(page.get_by_text('ALL PASS',exact=True)).to_be_visible(timeout=15000)
            assert page.locator('tbody tr[data-status="PASS"]').count()==10
            page.get_by_role('button',name='Rule 도면',exact=True).first.click()
            expect(page.get_by_role('dialog',name='태그·로직 상세보기')).to_be_visible()
            page.get_by_role('dialog',name='태그·로직 상세보기').get_by_role('button',name='닫기',exact=True).click()
            page.screenshot(path=str(OUT/f'{name}-testbench.png'),full_page=True)
            page.goto(os.getenv('TRIPLENS_UI_URL','http://localhost:3000/'))
            page.locator('.side-links button').click()
            dialog=page.get_by_role('dialog',name='Logic / TAG Master · 로직 도면')
            frame=page.frame_locator('dialog iframe')
            frame.locator('#page-select').select_option(label='LP Drum')
            drawing_link=dialog.get_by_role('link',name='도면에서 LP DRUM 위치 보기')
            expect(drawing_link).to_have_attribute('href',re.compile(r'/drawing\?equipment=LP\+DRUM&view=plant'))
            drawing_link.click()
            expect(page.locator('.drawing-hotspot.is-active')).to_have_attribute('title','LP Drum')
            expect(page.locator('.drawing-canvas img')).to_be_visible()
            assert page.locator('.drawing-canvas img').evaluate('(image) => image.naturalWidth')==2044
            page.goto(os.getenv('TRIPLENS_UI_URL','http://localhost:3000/'))
            page.locator('.side-links button').click()
            dialog=page.get_by_role('dialog',name='Logic / TAG Master · 로직 도면')
            page.frame_locator('dialog iframe').locator('#page-select').select_option(label='GT Exhaust')
            drawing_link=dialog.get_by_role('link',name='도면에서 GT EXHAUST 위치 보기')
            expect(drawing_link).to_have_attribute('href',re.compile(r'/drawing\?equipment=GT\+EXHAUST&view=plant'))
            drawing_link.click()
            expect(page.locator('.drawing-hotspot.is-active')).to_have_attribute('title','GT')
            expect(page.locator('.drawing-caption')).to_contain_text('관련 설비')
            page.goto(os.getenv('TRIPLENS_UI_URL','http://localhost:3000/'))
            page.locator('.side-links button').click()
            drawing_link=page.get_by_role('dialog',name='Logic / TAG Master · 로직 도면').get_by_role('link',name='Plant Process View 열기')
            expect(drawing_link).to_have_attribute('href','/drawing?view=plant')
            drawing_link.click()
            expect(page.get_by_role('heading',name='Plant Process View',exact=True)).to_be_visible()
            expect(page.locator('.drawing-hotspot')).to_have_count(21)
            assert page.url.endswith('/drawing?view=plant'),page.url
            page.get_by_role('region',name='추가 밸브 상세도면').get_by_role('button',name='IP FWCV').click()
            expect(page.locator('.drawing-hotspot.is-active')).to_have_attribute('title','IP Drum')
            page.get_by_role('button',name='선택 설비 상세도면').first.click()
            expect(page.get_by_role('heading',name='Equipment Detail')).to_be_visible()
            expect(page.locator('object[type="image/svg+xml"]')).to_have_attribute('data','/topology/valves/ip-fwcv.svg')
            for equipment,asset in [('HP FWCV','hp-fwcv.svg'),('COND EXTRACTION VALVE','cond-extraction-vlv.svg')]:
                page.goto(os.getenv('TRIPLENS_UI_URL','http://localhost:3000/').rstrip('/')+'/drawing?equipment='+equipment.replace(' ','%20')+'&view=plant&event=TRIP')
                expect(page.locator('.drawing-hotspot.is-active')).to_have_count(1)
                expect(page.locator('.drawing-caption')).to_contain_text('관련 설비')
                expect(page.locator('.drawing-detail-zoom')).to_be_visible()
                page.get_by_role('button',name='선택 설비 상세도면').first.click()
                expect(page.get_by_role('heading',name='Equipment Detail')).to_be_visible()
                expect(page.locator('.valve-event-focus')).to_contain_text(equipment)
                expect(page.locator('object[type="image/svg+xml"]')).to_have_attribute('data',re.compile(asset+'$'))
                assert page.request.get('http://localhost:3000/topology/valves/'+asset).status==200
            page.goto(os.getenv('TRIPLENS_UI_URL','http://localhost:3000/').rstrip('/')+'/drawing?equipment=HP%20TURB%20ADM%20VALVE&view=plant&event=TRIP')
            expect(page.locator('.drawing-hotspot.is-active')).to_have_attribute('title','HP Turbine Admission Valve')
            for equipment,related in [('HP FEEDWATER','HP BFP'),('GT EXHAUST','GT')]:
                page.goto(os.getenv('TRIPLENS_UI_URL','http://localhost:3000/').rstrip('/')+'/drawing?equipment='+equipment.replace(' ','%20')+'&view=plant&event=TRIP')
                expect(page.locator('.drawing-hotspot.is-active')).to_have_attribute('title',related)
                expect(page.get_by_role('region',name='설비 상세 정보')).to_contain_text('개별 상세도면 미등록')
                expect(page.locator('.drawing-detail-zoom')).to_be_visible()
            page.goto(os.getenv('TRIPLENS_UI_URL','http://localhost:3000/').rstrip('/')+'/drawing?equipment=ST&view=ecms&event=TRIP')
            expect(page.locator('.triplens-highlight-layer')).to_be_visible()
            expect(page.get_by_role('region',name='설비 상세 정보')).to_contain_text('ECMS 원본 도면')
            assert not errors,errors
            checks.append({'viewport':name,'width':width,'checks':'PASS','analysis_requests':counts['analyze'],'bootstrap_requests':counts['bootstrap'],'page_errors':errors,'live_gemini':False})
            context.close()
        browser.close()
    (OUT/'browser-results.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print('BROWSER_REVIEW_PASS '+json.dumps(checks,ensure_ascii=False))

if __name__=='__main__':main()
