"""Display captured actual provider output; browser requests are replay, not a live Vercel test."""
import csv
import json
import os
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
ACTUAL=ROOT/'outputs/review-reference-fix/actual'
OUT=ROOT/'outputs/review-reference-fix/browser';OUT.mkdir(parents=True,exist_ok=True)
data=json.loads((ACTUAL/'envelope.json').read_text())
expected_rows=json.loads((ACTUAL/'report_rows.json').read_text())
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    for width,name in ((1440,'desktop'),(390,'mobile')):
        context=browser.new_context(viewport={'width':width,'height':1000},accept_downloads=True)
        def replay(route):
            path=route.request.url.rsplit('/',1)[-1]
            if route.request.method=='OPTIONS':
                route.fulfill(status=204,headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'Content-Type'});return
            if path=='contract':body=data['contract']
            elif path in ('bootstrap','analyze'):body=data
            else:route.abort();return
            route.fulfill(json=body,headers={'Access-Control-Allow-Origin':'*'})
        context.route('https://triplens-agent-api-preview.vercel.app/**',replay)
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(os.getenv('TRIPLENS_UI_URL','http://127.0.0.1:3000/'))
        expect(page.get_by_label('EVENT 파일')).to_be_enabled()
        page.get_by_label('EVENT 파일').set_input_files(str(ACTUAL/'EVENT.csv'))
        page.get_by_label('RAW 파일').set_input_files(str(ACTUAL/'RAW.csv'))
        page.get_by_role('button',name='이 Dual Log 분석하기',exact=True).click()
        expect(page.get_by_text(re.compile('Run ID: '+data['run_id']))).to_be_visible(timeout=15000)
        assert page.locator('.status-badge').filter(has_text='CONFIRMED').count()==0
        tag=next(t for key in ('direct_trigger','primary_cause') for t in data['analysis'][key]['related_tags'] if t.startswith('vpp'))
        page.get_by_role('button',name=tag,exact=True).first.click()
        page.get_by_role('button',name='관련 로직·도면 보기',exact=True).click()
        frame=page.frame_locator('dialog iframe');frame.locator('body[data-ready="true"]').wait_for()
        page.screenshot(path=str(OUT/f'{name}-actual-tag-logic.png'),full_page=True)
        page.get_by_role('button',name=re.compile('분석 화면으로 돌아가기')).click()
        page.get_by_role('button',name='대시보드로 돌아가기',exact=True).click()
        page.get_by_role('button',name='고장보고서 초안 보기',exact=True).click()
        rows=page.locator('.editable-report tbody tr');expect(rows).to_have_count(len(expected_rows))
        ids=[r['row_id'] for r in expected_rows]
        assert all(ids) and len(set(ids))==len(ids)
        report_text=page.locator('.editable-report').inner_text()
        assert not any('인용 근거에 없는 태그:' in r['content'] for r in expected_rows)
        page.get_by_label('보고서 1 content',exact=True).fill('담당자 확인용 편집')
        with page.expect_download() as dl:page.get_by_role('button',name='고장보고서 초안 CSV',exact=True).click()
        path=OUT/f'{name}-report.csv';dl.value.save_as(str(path))
        with path.open(encoding='utf-8-sig',newline='') as f:exported=list(csv.reader(f))
        assert len(exported)==len(expected_rows)+1 and all(len(r)==8 for r in exported)
        assert '담당자 확인용 편집' in path.read_text(encoding='utf-8-sig')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert not errors,errors
        page.screenshot(path=str(OUT/f'{name}-actual-report.png'),full_page=True)
        results.append({'viewport':name,'row_ids':len(ids),'CSV_columns':8,'page_errors':errors,'result':'PASS','live_gemini_in_browser':False})
        context.close()
    browser.close()
(OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(results)
