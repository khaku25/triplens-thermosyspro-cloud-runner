"""Regression checks for the published Logic/Drawing Master geometry."""
import hashlib
import itertools
import json
import os
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('TRIPLENS_LAYOUT_SOURCE', str(ROOT / 'logic_diagrams/TripLens_Logic_Master_Current_V8.drawio')))


def vertices(page):
    result = []
    for obj in page.find('mxGraphModel/root'):
        cell = obj if obj.tag == 'mxCell' else obj.find('mxCell')
        if cell is None or cell.get('vertex') != '1':
            continue
        geo = cell.find('mxGeometry')
        result.append((obj.get('id'), tuple(float(geo.get(k, '0')) for k in ('x', 'y', 'width', 'height'))))
    return result


class LogicLayoutTest(unittest.TestCase):
    def test_all_pages_have_no_overlapping_vertices(self):
        pages = ET.parse(SOURCE).getroot().findall('diagram')
        self.assertGreater(len(pages), 0)
        collisions = []
        for page in pages:
            for (aid, a), (bid, b) in itertools.combinations(vertices(page), 2):
                dx = min(a[0]+a[2], b[0]+b[2])-max(a[0], b[0])
                dy = min(a[1]+a[3], b[1]+b[3])-max(a[1], b[1])
                if dx > .01 and dy > .01:
                    collisions.append((page.get('id'), aid, bid))
        self.assertEqual(collisions, [], 'Overlapping diagram vertices: ' + repr(collisions[:24]))

    def test_vertices_and_edges_remain_inside_valid_pages(self):
        for page in ET.parse(SOURCE).getroot().findall('diagram'):
            graph = page.find('mxGraphModel')
            width, height = float(graph.get('pageWidth')), float(graph.get('pageHeight'))
            ids = {obj.get('id') for obj in graph.find('root')}
            for cid, (x,y,w,h) in vertices(page):
                with self.subTest(page=page.get('id'), cell=cid):
                    self.assertGreater(w, 0); self.assertGreater(h, 0)
                    self.assertGreaterEqual(x, 0); self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x+w, width); self.assertLessEqual(y+h, height)
            for edge in graph.findall('root/mxCell'):
                if edge.get('edge') == '1':
                    self.assertIn(edge.get('source'), ids)
                    self.assertIn(edge.get('target'), ids)

    def test_both_st_power_inputs_exist_on_all_three_views(self):
        pages = {d.get('id'):d for d in ET.parse(SOURCE).getroot().findall('diagram')}
        for pid in ('screen:09254a48d627', 'IG-036', 'rule:RESP-ST-GRID-POWER'):
            inputs = {o.get('tag_id') for o in pages[pid].findall('mxGraphModel/root/object') if o.get('id','').startswith('source:IG-036:')}
            self.assertEqual(inputs, {'vppSTGeneratorPowerMW', 'vpp52STClosed'})

    def test_drawing_index_matches_source_geometry(self):
        index = json.loads((SOURCE.parent/'drawing_master_index.json').read_text(encoding='utf-8'))
        self.assertEqual(index['source_sha256'], hashlib.sha256(SOURCE.read_bytes()).hexdigest())
        by_id = {(d.get('id'), cid):box for d in ET.parse(SOURCE).getroot().findall('diagram') for cid,box in vertices(d)}
        for entry in index['entries']:
            key = (entry['page_id'], entry['cell_id'])
            self.assertEqual(tuple(float(entry[k]) for k in ('x','y','width','height')), by_id[key], key)


if __name__ == '__main__':
    unittest.main()
