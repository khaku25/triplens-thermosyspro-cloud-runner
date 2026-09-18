"""Run with `python -m unittest discover -s tests -p test_logic_viewer.py`.
Requires Playwright + Chromium. Pure generator tests have no browser dependency.
"""
import os
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
        self.assertIn('파생',self.page.locator('#inspector').inner_text())
        self.assertIn('OPC UA',self.page.locator('#inspector').inner_text())

    def test_behaviour_status_is_not_relabelled_live_pass(self):
        self.page.evaluate("TripLensLogic.openRule('AL-HP-LEVEL-HH')")
        self.page.wait_for_selector('[data-ready="true"]')
        self.assertIn('PARTIAL',self.page.locator('#inspector').inner_text())

    def test_unknown_tag_does_not_invent_rule(self):
        self.page.evaluate("TripLensLogic.openTag('vppMadeUp')")
        self.page.wait_for_selector('[data-ready="true"]')
        self.assertIn('등록되지',self.page.locator('#inspector').inner_text())
        self.assertEqual(self.page.locator('#related-rules button').count(),0)

    def test_layout_drag_and_export_changes_geometry_not_condition(self):
        self.page.evaluate("TripLensLogic.openRule('AL-HP-LEVEL-HH')")
        self.page.wait_for_selector('[data-ready="true"]')
        self.page.locator('#individual-view').click()
        self.page.locator('#layout-mode').click()
        node=self.page.locator('#diagram [data-cell-id="logic:AL-HP-LEVEL-HH"]')
        box=node.bounding_box(); self.assertIsNotNone(box)
        self.page.mouse.move(box['x']+20,box['y']+20)
        self.page.mouse.down(); self.page.mouse.move(box['x']+70,box['y']+40,steps=5); self.page.mouse.up()
        tree=ET.ElementTree(ET.fromstring(self.page.evaluate('TripLensLogic.exportXml()')))
        obj=tree.find("./diagram[@id='rule:AL-HP-LEVEL-HH']/mxGraphModel/root/object[@id='logic:AL-HP-LEVEL-HH']")
        self.assertNotEqual(float(obj.find('mxCell/mxGeometry').get('x')),480)
        self.assertEqual(obj.get('condition'),'value > 1.25 m')

    def test_mobile_no_document_horizontal_overflow(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),392)
        self.page.screenshot(path=os.getenv('TRIPLENS_MOBILE_SCREENSHOT',str(self.output/'mobile.png')),full_page=True)

    def test_snapshot_desktop(self):
        self.page.evaluate("TripLensLogic.openRule('AL-HP-LEVEL-HH')")
        self.page.wait_for_selector('[data-ready="true"]')
        self.page.screenshot(path=os.getenv('TRIPLENS_DESKTOP_SCREENSHOT',str(self.output/'desktop.png')),full_page=True)


if __name__=='__main__':
    unittest.main()
