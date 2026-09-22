"""Run with `python -m unittest discover -s tests -p test_logic_viewer.py`.
Requires Playwright + Chromium. Pure generator tests have no browser dependency.
"""
import os
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from threading import Thread
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


class ViewerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.logic_assets.xmlio import read_table
        from scripts.logic_assets import make_repository,publish_repository
        cls.temp=tempfile.TemporaryDirectory()
        masters=ROOT/'data/current_v8/masters'
        tags=read_table(masters/'06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx','01_Live_OPCUA_Tag_Master','raw_tag_id')
        rules=read_table(masters/'07_LOGIC_MASTER_CURRENT_V8_VERIFIED.xlsx','01_Logic_Master_Current','rule_id')
        census=read_table(ROOT/'data/current_v8/live_opcua_census.csv',key='browse_name')
        cls.output=publish_repository(make_repository(tags,rules,census),Path(cls.temp.name)/'release')
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(cls.output)))
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}/viewer.html'
        cls.pw=sync_playwright().start()
        executable=shutil.which('chromium') or shutil.which('google-chrome')
        cls.browser=cls.pw.chromium.launch(headless=True,executable_path=executable,args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.server.shutdown(); cls.server.server_close(); cls.temp.cleanup()

    def setUp(self):
        self.assertTrue((self.output/'viewer.html').exists(),'first-party viewer has not been implemented')
        self.page=self.browser.new_page(viewport={'width':1440,'height':1000})
        self.page.set_content((self.output/'viewer.html').read_text(encoding='utf-8'))
        self.page.wait_for_selector('[data-ready="true"]')

    def tearDown(self):
        if hasattr(self,'page'):
            self.page.close()

    def test_default_counts_and_no_external_network(self):
        self.assertIn('603',self.page.locator('#stats').inner_text())
        self.assertIn('53',self.page.locator('#stats').inner_text())
        self.assertEqual(self.page.evaluate('performance.getEntriesByType("resource").filter(x=>/^https?:/.test(x.name) && !x.name.startsWith(location.origin)).length'),0)

    def test_http_startup_fits_available_canvas(self):
        for suffix in ('', '#rule=AL-HP-LEVEL-HH'):
            with self.subTest(suffix=suffix):
                self.page.goto(self.url+suffix)
                self.page.wait_for_selector('[data-ready="true"]')
                initial=self.page.locator('#zoom-label').inner_text()
                diagram=self.page.locator('#diagram').bounding_box()
                canvas=self.page.locator('#canvas').bounding_box()
                self.assertGreater(diagram['width'],canvas['width']*.9)
                self.assertLessEqual(diagram['width'],canvas['width'])
                self.page.locator('#fit').click()
                self.assertEqual(self.page.locator('#zoom-label').inner_text(),initial)

    def test_tag_to_four_rules_and_group_diagram(self):
        self.page.get_by_role('button',name='태그',exact=True).click()
        self.page.locator('#search').fill('vppHPDrumLevelM')
        self.page.locator('#results button').first.click()
        self.assertEqual(self.page.locator('#related-rules button').count(),4)
        self.page.locator('#related-rules button[data-rule="AL-HP-LEVEL-HH"]').click()
        self.assertEqual(self.page.locator('#page-select').input_value(),'IG-003')
        self.assertEqual(self.page.locator('#diagram [data-tag="vppHPDrumLevelM"]').count(),1)

    def test_output_tag_is_derived_and_clickable(self):
        self.page.evaluate("TripLensLogic.openRule('AL-HP-LEVEL-HH')")
        self.page.wait_for_selector('[data-ready="true"]')
        self.page.locator('#diagram [data-tag="HRSG.HP.DRUM.LEVEL.HH"]').first.click()
        self.assertIn('파생 출력',self.page.locator('#inspector').inner_text())
        self.assertNotIn('OPC UA Node 아님',self.page.locator('#inspector').inner_text())

    def test_behaviour_status_is_not_relabelled_live_pass(self):
        self.page.evaluate("TripLensLogic.openRule('AL-HP-LEVEL-HH')")
        self.page.wait_for_selector('[data-ready="true"]')
        self.assertNotIn('PARTIAL',self.page.locator('#inspector').inner_text())
        repository=json.loads(self.page.locator('#repository-data').text_content())
        self.assertEqual(repository['index']['rules']['AL-HP-LEVEL-HH']['validation_status'],'PARTIAL')

    def test_unknown_tag_does_not_invent_rule(self):
        self.page.evaluate("TripLensLogic.openTag('vppMadeUp')")
        self.page.wait_for_selector('[data-ready="true"]')
        self.assertIn('검색 결과가 없습니다.',self.page.locator('#inspector').inner_text())
        self.assertEqual(self.page.locator('#related-rules button').count(),0)

    def test_layout_drag_and_export_changes_geometry_not_condition(self):
        self.page.evaluate("TripLensLogic.openRule('AL-HP-LEVEL-HH')")
        self.page.wait_for_selector('[data-ready="true"]')
        self.page.locator('#individual-view').click()
        self.page.locator('#layout-mode').click()
        node=self.page.locator('#diagram [data-cell-id="operation:AL-HP-LEVEL-HH"]')
        self.assertEqual(node.count(),1)
        box=node.bounding_box(); self.assertIsNotNone(box)
        self.page.mouse.move(box['x']+20,box['y']+20)
        self.page.mouse.down(); self.page.mouse.move(box['x']+70,box['y']+40,steps=5); self.page.mouse.up()
        tree=ET.ElementTree(ET.fromstring(self.page.evaluate('TripLensLogic.exportXml()')))
        obj=tree.find("./diagram[@id='rule:AL-HP-LEVEL-HH']/mxGraphModel/root/object[@id='operation:AL-HP-LEVEL-HH']")
        self.assertNotEqual(float(obj.find('mxCell/mxGeometry').get('x')),780)
        condition=tree.find("./diagram[@id='rule:AL-HP-LEVEL-HH']/mxGraphModel/root/object[@id='condition:AL-HP-LEVEL-HH']")
        self.assertEqual(condition.get('condition'),'value > 1.25 m')

    def test_four_columns_additional_placement_and_accessible_controls(self):
        self.page.evaluate("TripLensLogic.openRule('AL-HP-LEVEL-HH')")
        self.page.locator('#individual-view').click()
        boxes=[]
        for prefix in ('source:', 'condition:', 'operation:', 'output:'):
            node=self.page.locator(f'#diagram [data-cell-id^="{prefix}"]')
            self.assertEqual(node.count(),1)
            self.assertEqual(node.get_attribute('role'),'button')
            boxes.append(node.bounding_box())
        for left,right in zip(boxes,boxes[1:]):
            self.assertLess(left['x']+left['width'],right['x'])
        additional=self.page.locator('#diagram [data-cell-id="additional:AL-HP-LEVEL-HH"]')
        self.assertGreater(additional.bounding_box()['y'],boxes[2]['y']+boxes[2]['height'])
        for prefix in ('condition:', 'operation:', 'additional:'):
            self.assertEqual(self.page.locator(f'#diagram .selected[data-cell-id^="{prefix}"]').count(),1)
        for selector in ('[data-cell-id="title"]','[data-cell-id^="column:"]','[data-cell-id^="group:"]','[data-cell-id^="additional:"]'):
            nodes=self.page.locator('#diagram '+selector)
            self.assertGreater(nodes.count(),0)
            for node in nodes.all():
                self.assertIsNone(node.get_attribute('role'))
                self.assertIsNone(node.get_attribute('tabindex'))
        for word in ('조건','동작','상세 정보'):
            self.assertIn(word,self.page.locator('.legend').inner_text())
        for word in ('CONDITION','OPERATION','ADDITIONAL INFO','원장','OPC UA Node 아님'):
            self.assertNotIn(word,self.page.locator('.legend').inner_text())

    def test_schema_mismatch_and_mixed_central_ids_fail_closed(self):
        original=json.loads(self.page.locator('#repository-data').text_content())
        template=(ROOT/'scripts/logic_assets/viewer.html').read_text()
        for xml_schema,index_schema,mixed in [('1',2,False),('2',1,False),('1',1,False),('3',3,False),('2',2,True)]:
            with self.subTest(xml_schema=xml_schema,index_schema=index_schema,mixed=mixed):
                payload=json.loads(json.dumps(original))
                root=ET.fromstring(payload['xml']);root.set('triplens_schema',xml_schema)
                if mixed:
                    obj=root.find(".//object[@id='operation:AL-HP-LEVEL-HH']")
                    self.assertIsNotNone(obj)
                    obj.set('id','logic:AL-HP-LEVEL-HH')
                payload['xml']=ET.tostring(root,encoding='unicode')
                payload['index']['schema_version']=index_schema
                payload['index']['drawio_sha256']=hashlib.sha256(payload['xml'].encode()).hexdigest()
                html=template.replace('__TRIPLENS_PAYLOAD__',json.dumps(payload).replace('<','\\u003c'))
                page=self.browser.new_page()
                try:
                    page.set_content(html)
                    page.wait_for_selector('#fatal',state='visible',timeout=3000)
                    self.assertTrue(page.locator('#workspace').evaluate('(node)=>node.hidden'))
                    self.assertIsNone(page.locator('body').get_attribute('data-ready'))
                finally:
                    page.close()

    def test_mobile_no_document_horizontal_overflow(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),392)
        self.page.screenshot(path=os.getenv('TRIPLENS_MOBILE_SCREENSHOT',str(self.output/'mobile.png')),full_page=True)

    def test_snapshot_desktop(self):
        self.page.goto(self.url)
        self.page.wait_for_selector('[data-ready="true"]')
        self.page.evaluate("TripLensLogic.openRule('AL-HP-LEVEL-HH')")
        self.page.wait_for_selector('[data-ready="true"]')
        self.page.screenshot(path=os.getenv('TRIPLENS_DESKTOP_SCREENSHOT',str(self.output/'desktop.png')),full_page=True)

    def test_mobile_drawing_master_tap_opens_exact_cell(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.get_by_role('button', name='Drawing Master', exact=True).click()
        self.assertEqual(self.page.locator('#search').get_attribute('placeholder'), '태그 · 로직 · 페이지 · 셀 검색')
        self.page.locator('#search').fill('operation:CMD-FWP-HP-TRIP')
        self.page.locator('#results button').first.click()
        self.assertEqual(self.page.locator('#page-select').input_value(), 'IG-030')
        self.assertEqual(self.page.locator('#diagram [data-cell-id="operation:CMD-FWP-HP-TRIP"].selected').count(), 1)
        self.assertEqual(self.page.locator('#diagram .selected').count(), 1)
        self.assertIn('source_ref:', self.page.locator('#inspector').inner_text())

        source_ref = 'logic_diagrams/TripLens_Logic_Master_Current_V8.drawio#page=screen:09b807ee953a&cell=operation:CMD-FWP-HP-TRIP'
        self.page.locator('#search').fill(source_ref)
        self.assertEqual(self.page.locator('#results button').count(), 1)
        self.page.locator('#results button').click()
        self.assertEqual(self.page.locator('#page-select').input_value(), 'screen:09b807ee953a')
        self.assertEqual(self.page.locator('#diagram .selected').count(), 1)
        self.assertEqual(self.page.locator('#diagram [data-cell-id="operation:CMD-FWP-HP-TRIP"].selected').count(), 1)

        self.assertFalse(self.page.evaluate("TripLensLogic.openDrawing('title')"))
        self.assertIn('여러 페이지', self.page.locator('#inspector').inner_text())
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 392)


if __name__=='__main__':
    unittest.main()
