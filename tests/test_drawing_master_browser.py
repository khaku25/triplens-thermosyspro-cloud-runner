# ---------------------------------------------------------------------------
# CODE READING GUIDE
# File role: regression contract or operator review harness.
# Read in this order: fixtures/setup -> test_* or review steps -> assertions/report.
# A PASS protects only the named contract; it is not live plant, OPC UA, or field evidence
# unless the test explicitly says that it performed that external observation.
# ---------------------------------------------------------------------------
"""Actual browser checks of the restored read-only Drawing Master."""
import copy
import json
import os
from pathlib import Path
import unittest
from urllib.parse import quote
import test_logic_viewer as viewer_helpers


class DrawingBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        viewer_helpers.ViewerTest.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        viewer_helpers.ViewerTest.tearDownClass.__func__(cls)

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width':1440,'height':1000})
        self.errors = []
        self.page.on('pageerror', lambda exc: self.errors.append(str(exc)))
        self.page.set_default_timeout(3000)
        if os.getenv('DRAWING_MASTER_OFFLINE'):
            self.page.set_content((self.output/'viewer.html').read_text(encoding='utf-8'))
        else:
            self.page.goto(self.url)
        self.page.wait_for_selector('body[data-ready="true"]')
        self.payload = json.loads(self.page.locator('#repository-data').text_content())
        self.assertIn('drawing_master', self.payload)
        self.entry = next(e for e in self.payload['drawing_master']['entries']
                          if e['page_scope']=='rule' and e['logic_id']=='AL-HP-LEVEL-HH'
                          and e['object_type']=='operation')

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def select_entry(self):
        self.assertTrue(self.page.evaluate('(ref)=>TripLensLogic.openDrawing(ref)', self.entry['source_ref']))

    def test_exact_cell_highlight_not_all_cells_with_same_rule(self):
        self.select_entry()
        self.assertEqual(self.page.locator('#page-select').input_value(), self.entry['page_id'])
        self.assertEqual(self.page.locator('#diagram .selected').count(), 1)
        self.assertEqual(self.page.locator('#diagram .selected').get_attribute('data-cell-id'), self.entry['cell_id'])

    def test_deep_link_and_back_restore_same_page_cell_and_address(self):
        if os.getenv('DRAWING_MASTER_OFFLINE'):
            self.skipTest('HTTP navigation is tested in CI; local browser permits offline HTML only')
        self.page.goto(self.url+'#drawing='+quote(self.entry['source_ref'],safe=''))
        self.page.wait_for_selector('body[data-ready="true"]')
        initial_hash=self.page.evaluate('location.hash')
        self.page.evaluate("TripLensLogic.openTag('vppHPDrumLevelM')")
        self.page.locator('#back').click()
        self.assertEqual(self.page.evaluate('location.hash'), initial_hash)
        self.assertEqual(self.page.locator('#page-select').input_value(), self.entry['page_id'])
        self.assertIn(self.entry['cell_id'],self.page.locator('#inspector').inner_text())

    def test_ambiguous_bare_cell_id_and_unknown_ref_do_not_jump(self):
        before=self.page.locator('#page-select').input_value()
        self.assertFalse(self.page.evaluate('(ref)=>TripLensLogic.openDrawing(ref)', self.entry['cell_id']))
        self.assertEqual(self.page.locator('#page-select').input_value(), before)
        self.assertFalse(self.page.evaluate("TripLensLogic.openDrawing('missing-file#page=bad&cell=bad')"))
        self.assertIn('도면 위치',self.page.locator('#drawing-feedback').inner_text())

    def test_selecting_tag_opens_first_linked_drawing_and_limits_results(self):
        tag='vppHPDrumLevelM'
        expected=next(row for row in self.payload['drawing_master']['entries'] if row['tag_id']==tag)
        expected_count=sum(row['tag_id']==tag for row in self.payload['drawing_master']['entries'])
        self.page.locator('#tab-tags').click()
        self.page.locator('#search').fill(tag)
        self.page.locator('#results button').first.click()
        self.assertIn('active',self.page.locator('#tab-drawings').get_attribute('class'))
        self.assertEqual(self.page.locator('#search').input_value(),tag)
        rows=self.page.locator('#results button')
        self.assertEqual(rows.count(),expected_count)
        self.assertTrue(all(tag in text for text in rows.all_inner_texts()))
        self.assertEqual(self.page.locator('#page-select').input_value(),expected['page_id'])
        self.assertEqual(self.page.locator('#diagram .selected').count(),1)
        self.assertEqual(self.page.locator('#diagram .selected').get_attribute('data-cell-id'),expected['cell_id'])
        details=self.page.locator('#inspector').inner_text()
        self.assertIn(expected['source_ref'],details)
        self.assertIn(expected['logic_id'],details)

    def test_tag_without_drawing_clears_previous_drawing_and_shows_empty_state(self):
        self.select_entry()
        self.assertEqual(self.page.locator('#diagram .selected').count(),1)
        self.page.evaluate("TripLensLogic.openTag('vppCondenserSteamVolume.P')")
        self.assertIn('active',self.page.locator('#tab-drawings').get_attribute('class'))
        self.assertEqual(self.page.locator('#results button').count(),0)
        self.assertEqual(self.page.locator('#diagram .node').count(),0)
        self.assertEqual(self.page.locator('#diagram .selected').count(),0)
        self.assertIn('연결된 도면이 없습니다',self.page.locator('#drawing-feedback').inner_text())
        self.page.locator('#tab-tags').click()
        self.assertEqual(self.page.locator('#page-select').input_value(),'overview')
        self.page.locator('#back').click()
        self.assertEqual(self.page.locator('#page-select').input_value(),self.entry['page_id'])
        self.assertEqual(self.page.locator('#diagram .selected').get_attribute('data-cell-id'),self.entry['cell_id'])
        self.assertEqual(self.page.locator('#drawing-feedback').inner_text(),'')

    def test_tag_inspector_opens_matching_drawing_locations(self):
        self.page.evaluate("TripLensLogic.openTag('vppHPDrumLevelM')")
        self.page.get_by_role('button',name='도면 위치 보기',exact=False).click()
        self.assertIn('active',self.page.locator('#tab-drawings').get_attribute('class'))
        rows=self.page.locator('#results button')
        self.assertGreater(rows.count(),0)
        self.assertTrue(all('vppHPDrumLevelM' in text for text in rows.all_inner_texts()))
        rows.first.press('Enter')
        self.assertEqual(self.page.locator('#diagram .selected').count(),1)
        self.page.get_by_role('link',name='이 도면 위치 열기').click()
        self.assertIn('drawing=',self.page.evaluate('location.hash'))

    def test_mobile_drawing_tab_search_and_focus_fit_without_page_overflow(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.page.locator('#tab-drawings').click()
        self.page.locator('#search').fill('FWP')
        self.assertGreater(self.page.locator('#results button').count(),0)
        self.page.locator('#results button').first.click()
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),391)
        tab=self.page.locator('#tab-drawings').bounding_box()
        self.assertGreaterEqual(tab['height'],40)
        self.assertLessEqual(tab['x']+tab['width'],390)
        selected=self.page.locator('#diagram .selected').bounding_box()
        self.assertGreaterEqual(selected['width'],200,'selected mobile object must be readable, not a shrunken page overview')
        canvas=self.page.locator('#canvas').bounding_box()
        self.assertLess(selected['y'],canvas['y']+canvas['height'])
        self.assertGreater(selected['y']+selected['height'],canvas['y'])
        out=os.getenv('DRAWING_MASTER_SCREENSHOTS')
        if out:
            Path(out).mkdir(parents=True,exist_ok=True)
            self.page.screenshot(path=str(Path(out)/'drawing-master-mobile.png'),full_page=True)

    def test_large_results_are_bounded_and_can_expand(self):
        self.page.locator('#tab-drawings').click()
        self.assertEqual(self.page.locator('#results button').count(),100)
        self.page.get_by_role('button',name='검색 결과 더 보기').click()
        self.assertEqual(self.page.locator('#results button').count(),200)
        self.page.locator('#search').fill('does-not-exist')
        self.assertEqual(self.page.locator('#results button').count(),0)
        self.assertIn('검색 결과 0개',self.page.locator('#result-count').inner_text())

    def test_missing_mismatched_and_forged_index_fail_closed(self):
        template=(Path(__file__).resolve().parents[1]/'scripts/logic_assets/viewer.html').read_text()
        for mode in ['missing','hash','cell']:
            payload=copy.deepcopy(self.payload)
            if mode=='missing': del payload['drawing_master']
            elif mode=='hash': payload['drawing_master']['source_sha256']='0'*64
            else: payload['drawing_master']['entries'][0]['cell_id']='does-not-exist'
            page=self.browser.new_page()
            try:
                page.set_content(template.replace('__TRIPLENS_PAYLOAD__',json.dumps(payload).replace('<','\\u003c')))
                page.wait_for_selector('#fatal',state='visible',timeout=3000)
                self.assertTrue(page.locator('#workspace').evaluate('(el)=>el.hidden'))
                self.assertIsNone(page.locator('body').get_attribute('data-ready'))
            finally: page.close()

    def test_desktop_snapshot_and_no_external_requests(self):
        self.page.locator('#tab-drawings').click()
        self.page.locator('#search').fill('AL-HP-LEVEL-HH')
        self.select_entry()
        self.assertEqual(self.page.evaluate('performance.getEntriesByType("resource").filter(x=>/^https?:/.test(x.name)&&!x.name.startsWith(location.origin)).length'),0)
        out=os.getenv('DRAWING_MASTER_SCREENSHOTS')
        if out:
            Path(out).mkdir(parents=True,exist_ok=True)
            self.page.screenshot(path=str(Path(out)/'drawing-master-desktop.png'),full_page=True)


if __name__=='__main__': unittest.main()
