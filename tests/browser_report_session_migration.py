"""Restore a captured pre-V2 session; local browser, mocked HTTP, no Gemini."""
import csv
import io
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    saved = json.loads((ROOT / 'tests/fixtures/legacy-report-session.json').read_text())
    next(row for row in saved['reportRows'] if row['item'] == '사고 전 운전 상태')['content'] = '이전 세션 담당자 편집'
    next(row for row in saved['reportRows'] if row['item'] == 'SOE 21')['note'] = '보존할 EVENT 주석'
    saved['result']['evidence_readiness'] = {'status': 'PASS'}
    saved['result']['contract'] = {}
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in [(1440, 1000), (390, 844)]:
            context = browser.new_context(viewport={'width': width, 'height': height}, accept_downloads=True)
            counts = {'bootstrap': 0, 'analyze': 0}

            def handle(route):
                endpoint = route.request.url.rsplit('/', 1)[-1]
                if route.request.method == 'OPTIONS':
                    route.fulfill(status=204, headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type'})
                    return
                if endpoint in counts:
                    counts[endpoint] += 1
                route.fulfill(json={} if endpoint == 'contract' else saved['result'], headers={'Access-Control-Allow-Origin': '*'})

            context.route('https://triplens-agent-api-preview.vercel.app/**', handle)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(os.getenv('TRIPLENS_UI_URL', 'http://127.0.0.1:3000/'))
            expect(page.get_by_label('EVENT 파일')).to_be_enabled()
            page.evaluate('''async saved => {
              const db = await new Promise(resolve => {
                const request = indexedDB.open('triplens-v8-review', 1);
                request.onsuccess = () => resolve(request.result);
              });
              const fields = Object.keys(saved.uploadedEvents[0]);
              saved.eventFile = new File([fields.join(',')+'\\n'+saved.uploadedEvents.map(row => fields.map(field => row[field]).join(',')).join('\\n')], 'EVENT.csv');
              saved.rawFile = new File(['model_time_s,vppGTTripLatch\\n1,1\\n'], 'RAW.csv');
              await new Promise((resolve, reject) => {
                const tx = db.transaction('session', 'readwrite');
                tx.objectStore('session').put(saved, 'active');
                tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
              });
              db.close();
            }''', saved)
            page.reload()
            expect(page.get_by_role('status')).to_contain_text('복원했습니다')
            page.get_by_role('button', name='고장보고서 초안 보기', exact=True).click()

            def exported_rows():
                button = page.get_by_role('button', name='고장보고서 초안 CSV', exact=True)
                expect(button).to_be_enabled()
                with page.expect_download() as download:
                    button.click()
                text = Path(download.value.path()).read_text(encoding='utf-8-sig')
                return list(csv.DictReader(io.StringIO(text)))

            rows = exported_rows()
            soe = [row for row in rows if row['구분'] == '시간대별 사건·자동동작(SOE)']
            evidence = [row for row in rows if row['구분'] == '증거자료']
            assert len(soe) == len(evidence) == 21
            assert len(dict.fromkeys(row['구분'] for row in rows)) == 10
            assert all(row['관련 태그'] == 'vppGTTripLatch' for row in soe + evidence)
            assert soe[-1]['비고'] == '보존할 EVENT 주석'
            assert rows[1]['내용'] == '이전 세션 담당자 편집'
            assert not page.get_by_role('alert').filter(has_text='내보내기').count()
            page.get_by_label('보고서 2 content', exact=True).fill('캐시 재사용 후에도 보존')
            page.get_by_role('button', name='이 Dual Log 분석하기', exact=True).click()
            expect(page.get_by_role('status')).to_contain_text('기존 분석 재사용')
            expect(page.get_by_label('보고서 2 content', exact=True)).to_have_value('캐시 재사용 후에도 보존')
            assert len([row for row in exported_rows() if row['구분'] == '증거자료']) == 21
            page.wait_for_timeout(600)
            page.reload()
            expect(page.get_by_role('status')).to_contain_text('복원했습니다')
            page.get_by_role('button', name='고장보고서 초안 보기', exact=True).click()
            expect(page.get_by_label('보고서 2 content', exact=True)).to_have_value('캐시 재사용 후에도 보존')
            assert counts == {'bootstrap': 1, 'analyze': 0}, counts
            assert not errors, errors
            checks.append({'width': width, 'result': 'PASS', 'event_evidence_count': 21, **counts})
            context.close()
        browser.close()
    print('BROWSER_REPORT_SESSION_MIGRATION_PASS ' + json.dumps(checks))


if __name__ == '__main__':
    main()
