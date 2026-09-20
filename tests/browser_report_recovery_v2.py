"""Real workspace recovery/export regression. HTTP analysis is mocked, not live Gemini."""
import csv
import io
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from browser_v8_review import fixture, OUT


def recovery_fixture():
    event, raw, data = fixture()
    with event.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields, uploaded = reader.fieldnames, list(reader)
    enriched = data['events'][:]
    for number in range(5, 22):
        source = (number - 1) % 4
        uploaded.append({**uploaded[source], 'event_id': f'E-{number}', 'event_sequence': number})
        enriched.append({**enriched[source], 'event_id': f'E-{number}', 'evidence_id': f'E-{number}'})
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(uploaded)
    raw_entries = [row for row in data['evidence_catalog'] if row.get('source_kind') != 'EVENT']
    data.update(events=enriched, evidence_catalog=enriched[:14] + raw_entries)
    # HOLD deliberately proves human approval cannot silently certify a cause.
    data['analysis']['verification_gate'] = 'HOLD'
    return {'name': 'RECOVERY-EVENT.csv', 'mimeType': 'text/csv', 'buffer': buffer.getvalue().encode()}, raw, data


def patch_saved_recovery(page, evidence_ids):
    page.evaluate('''async ids => {
      const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open('triplens-v8-review', 1);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      await new Promise((resolve, reject) => {
        const tx = db.transaction('session', 'readwrite');
        const store = tx.objectStore('session');
        const request = store.get('active');
        request.onsuccess = () => store.put({...request.result,
          recovery: {...request.result.recovery, evidence_ids: ids}}, 'active');
        tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
      });
      db.close();
    }''', evidence_ids)


def remove_legacy_row_ids(page):
    page.evaluate('''async () => {
      const db = await new Promise(resolve => {
        const request = indexedDB.open('triplens-v8-review', 1);
        request.onsuccess = () => resolve(request.result);
      });
      await new Promise(resolve => {
        const tx = db.transaction('session', 'readwrite');
        const store = tx.objectStore('session');
        const request = store.get('active');
        request.onsuccess = () => {
          const saved = request.result;
          saved.reportRows = saved.reportRows.map(({row_id, ...row}) => row);
          store.put(saved, 'active');
        };
        tx.oncomplete = resolve;
      });
      db.close();
    }''')


def main():
    event, raw, data = recovery_fixture()
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height, name in [(1440, 1000, 'desktop'), (390, 844, 'mobile')]:
            context = browser.new_context(viewport={'width': width, 'height': height}, accept_downloads=True)
            def handle(route):
                if route.request.method == 'OPTIONS':
                    route.fulfill(status=204, headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type'})
                    return
                endpoint = route.request.url.rsplit('/', 1)[-1]
                body = data['contract'] if endpoint == 'contract' else data
                route.fulfill(json=body, headers={'Access-Control-Allow-Origin': '*'})
            context.route('https://triplens-agent-api-preview.vercel.app/**', handle)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(os.getenv('TRIPLENS_UI_URL', 'http://127.0.0.1:3000/'))
            expect(page.get_by_label('EVENT 파일')).to_be_enabled()
            page.get_by_label('EVENT 파일').set_input_files(event)
            page.get_by_label('RAW 파일').set_input_files(str(raw))
            page.get_by_role('button', name='이 Dual Log 분석하기', exact=True).click()
            cards = page.get_by_role('region', name='분석 진행 상태', exact=True)
            expect(cards).to_be_visible(timeout=30000)
            for label in ['입력 근거', '원인 검증', '복구 기록', '문서']:
                expect(cards.get_by_role('group', name=label, exact=True)).to_be_visible()
            recovery_card = cards.get_by_role('group', name='복구 기록', exact=True)
            expect(recovery_card).to_contain_text('입력 대기')
            expect(recovery_card).not_to_contain_text('UNKNOWN')
            expect(cards.get_by_role('group', name='원인 검증', exact=True)).to_contain_text('HOLD')
            assert page.get_by_text('Run ID: RUN-UI-REGRESSION', exact=True).is_hidden()
            for label in ['Propagation · 파급 과정', 'Causal Chain · 시간순 검토', '반대 근거 / 가설 검토']:
                expect(page.locator('details').filter(has=page.locator('summary', has_text=label))).not_to_have_attribute('open', '')

            page.get_by_role('button', name='고장보고서 초안 보기', exact=True).click()
            pending_row = page.locator('.editable-report tbody tr').filter(has=page.locator('[data-label="항목"]', has_text='실제 수행 조치'))
            expect(pending_row.locator('[data-label="상태"]')).to_have_text('입력 대기')
            page.get_by_role('button', name='고장보고서 초안 보기', exact=True).click()

            page.locator('.nav-item').filter(has_text='복구').click()
            status = page.get_by_label('복구 상태', exact=True)
            expect(status).to_have_value('')
            expect(status.locator('option').first).to_have_text('선택 대기')
            status.select_option(label='복구 완료')
            page.get_by_label('기록상 승인자', exact=True).fill('검토자 Kim')
            approve = page.get_by_role('button', name='승인 기록', exact=True)
            expect(approve).to_be_disabled()
            page.get_by_label('복구 시각', exact=True).fill('2026-09-20T10:30')
            page.get_by_label('수행자', exact=True).fill('운전원 Lee')
            page.get_by_label('실제 수행 조치', exact=True).fill('현장 점검 및 복구 기록')
            page.get_by_label('재기동 조건', exact=True).fill('담당자 재기동 조건 확인')
            page.get_by_label('복구 근거 ID', exact=True).select_option(['E-21'])
            expect(recovery_card).to_contain_text('승인 대기')
            expect(approve).to_be_enabled()
            approve.click()
            expect(recovery_card).to_contain_text('승인 완료')
            expect(cards.get_by_role('group', name='문서', exact=True)).to_contain_text('초안')

            page.get_by_role('button', name='고장보고서 초안 보기', exact=True).click()
            rows = page.locator('.editable-report tbody tr')
            actions_row = rows.filter(has=page.locator('[data-label="항목"]', has_text='실제 수행 조치'))
            expect(actions_row.locator('[data-label="상태"]')).to_contain_text('승인 완료')
            assert actions_row.locator('textarea:not([readonly]), select').count() == 0
            assert all(value in ['UNKNOWN', 'OBSERVED', 'CANDIDATE'] for value in page.locator('.editable-report select option').evaluate_all('(options) => options.map(option => option.value)'))
            for label in ['구분', '항목', '내용', '상태', '근거 ID', '관련 태그', '기록 시각', '비고']:
                assert rows.first.locator(f'[data-label="{label}"]').count() == 1
            if width < 700:
                assert rows.first.evaluate('(row) => getComputedStyle(row).display') == 'grid'
                assert page.locator('.editable-report').evaluate('(table) => getComputedStyle(table).minWidth') == '0px'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'page-wide horizontal overflow'
            page.get_by_label('실제 수행 조치', exact=True).fill('현장 점검 및 복구 기록 수정')
            expect(recovery_card).to_contain_text('승인 대기')
            expect(actions_row.locator('[data-label="상태"]')).to_contain_text('승인 대기')

            with page.expect_download() as download:
                page.get_by_role('button', name='고장보고서 초안 CSV', exact=True).click()
            path = OUT / f'{name}-recovery-v2-report.csv'
            download.value.save_as(str(path))
            with path.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                assert len(reader.fieldnames) == 8
                exported = list(reader)
            evidence = {row['근거 ID']: row for row in exported if row['구분'] == '증거자료'}
            exact_tags = ['vppGTTripLatch', 'vppSTTripLatchPublished', 'vpp52GTClosed', 'vpp52STClosed']
            for number in range(1, 22):
                assert evidence[f'E-{number}']['관련 태그'] == exact_tags[(number - 1) % 4]
            assert any(row['내용'] == '현장 점검 및 복구 기록 수정' and row['상태'] == 'APPROVAL_PENDING' for row in exported)
            assert '운전원 Lee' in path.read_text() and '검토자 Kim' in path.read_text()

            # Generic edited references also block every export, without changing recovery.
            exports = [page.get_by_role('button', name=label, exact=True) for label in ['보고서 V2 PDF', 'PINPOINT.csv', '고장보고서 초안 CSV']]
            reference = page.get_by_label('보고서 1 evidence_ids', exact=True)
            original = reference.input_value()
            reference.fill('MISSING-REPORT')
            for button in exports:
                expect(button).to_be_disabled()
            expect(page.get_by_role('alert').filter(has_text='내보내기')).to_contain_text('MISSING-REPORT')
            reference.fill(original)
            for button in exports:
                expect(button).to_be_enabled()

            page.wait_for_timeout(600)
            page.reload()
            expect(page.get_by_label('실제 수행 조치', exact=True)).to_have_value('현장 점검 및 복구 기록 수정')
            expect(page.get_by_label('수행자', exact=True)).to_have_value('운전원 Lee')
            expect(page.get_by_label('복구 근거 ID', exact=True)).to_have_values(['E-21'])
            page.wait_for_timeout(600)
            remove_legacy_row_ids(page)
            page.reload()
            page.get_by_role('button', name='고장보고서 초안 보기', exact=True).click()
            untouched = page.get_by_label('보고서 2 content', exact=True).input_value()
            page.get_by_label('보고서 1 content', exact=True).fill('이전 세션 한 행만 수정')
            expect(page.get_by_label('보고서 2 content', exact=True)).to_have_value(untouched)
            page.wait_for_timeout(600)
            # Imported/stale persisted IDs must not disappear silently or be trusted.
            patch_saved_recovery(page, ['MISSING-RECOVERY'])
            page.reload()
            expect(page.get_by_label('실제 수행 조치', exact=True)).to_have_value('현장 점검 및 복구 기록 수정')
            expect(page.get_by_role('button', name='승인 기록', exact=True)).to_be_disabled()
            page.get_by_role('button', name='고장보고서 초안 보기', exact=True).click()
            for button in exports:
                expect(button).to_be_disabled()
            expect(page.get_by_role('alert').filter(has_text='내보내기')).to_contain_text('MISSING-RECOVERY')
            page.get_by_label('복구 근거 ID', exact=True).select_option(['E-21'])
            for button in exports:
                expect(button).to_be_enabled()

            for kind, replacement in [('RAW', str(raw)), ('EVENT', event)]:
                page.get_by_label(f'{kind} 파일').set_input_files(replacement)
                expect(status).to_have_value('')
                expect(page.get_by_label('실제 수행 조치', exact=True)).to_have_value('')
                page.get_by_role('button', name='이 Dual Log 분석하기', exact=True).click()
                expect(recovery_card).to_contain_text('입력 대기')
                page.locator('.nav-item').filter(has_text='복구').click()
                status.select_option(label='미복구')
                page.get_by_label('수행자', exact=True).fill('Lee')
                page.get_by_label('실제 수행 조치', exact=True).fill('추가 점검 필요')
            page.get_by_role('button', name='입력·분석 지우기', exact=True).click()
            expect(status).to_have_value('')
            expect(page.get_by_label('실제 수행 조치', exact=True)).to_have_value('')
            # A draft recovery record also survives reload before a new analysis.
            status.select_option(label='미복구')
            page.get_by_label('실제 수행 조치', exact=True).fill('분석 전 임시 복구 기록')
            page.wait_for_timeout(600)
            page.reload()
            expect(page.get_by_label('실제 수행 조치', exact=True)).to_have_value('분석 전 임시 복구 기록')
            assert not errors, errors
            checks.append({'viewport': name, 'result': 'PASS', 'event_evidence_count': 21, 'live_gemini': False})
            context.close()
        browser.close()
    print('BROWSER_REPORT_RECOVERY_V2_PASS ' + json.dumps(checks, ensure_ascii=False))


if __name__ == '__main__':
    main()
