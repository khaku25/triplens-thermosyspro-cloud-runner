import csv
import json
import unittest
from pathlib import Path
from scripts.logic_assets.drawing_master import search_drawing_master

ROOT = Path(__file__).resolve().parents[1]
TAGS = ('vppSTGeneratorPowerMW', 'vppSTGridPowerMW')
RULE = 'RESP-ST-GRID-POWER'

def rows(name):
    with (ROOT / 'data/current_v8' / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

class STPowerWebReleaseTest(unittest.TestCase):
    def test_both_observed_st_signals_are_registered(self):
        tags = {r['raw_tag_id']: r for r in rows('live_tag_master.csv')}
        for name in TAGS:
            self.assertIn(name, tags)
            self.assertEqual(tags[name]['unit'], 'MW')
            self.assertEqual(tags[name]['writable'], 'N')
            self.assertEqual(tags[name]['equipment_id'], 'STG')
            self.assertEqual(tags[name]['live_existence'], 'RAW_SESSION_OBSERVED')
            self.assertEqual(tags[name]['live_node_id'], '')
        self.assertEqual(tags[TAGS[1]]['local_display_alias'], 'ST_OUTPUT_MW')

    def test_response_has_generator_input_and_partial_status(self):
        rules = {r['logic_id']: r for r in rows('live_logic_runtime.csv')}
        self.assertIn(RULE, rules)
        row = rules[RULE]
        self.assertEqual(set(row['input_nodes'].split('|')), {'vpp52STClosed', TAGS[0]})
        self.assertEqual(row['output_nodes_or_tags'], TAGS[1])
        self.assertEqual(row['verification_status'], 'PARTIAL')
        self.assertEqual(row['logic_type'], 'PHYSICAL_RESPONSE')
        self.assertEqual(row['source_existence_status'], 'RAW_SESSION_AND_CENSUS_RESOLVED')

    def test_st_diagram_contains_exact_input_and_output_cells(self):
        index = json.loads((ROOT / 'logic_diagrams/drawing_master_index.json').read_text())
        for name in TAGS:
            matches = search_drawing_master(index, name)
            exact = [r for r in matches if r['tag_id'] == name and r['page_name'] == 'ST Protection']
            self.assertTrue(exact, name + ' missing from ST Protection diagram')
        self.assertFalse(search_drawing_master(index, 'vppSTGridPowerMW_NOT_REGISTERED'))

    def test_all_three_published_drawing_indexes_are_identical(self):
        paths = ['logic_diagrams', 'generated/logic', 'apps/web/public/logic-assets']
        payloads = [(ROOT / p / 'drawing_master_index.json').read_bytes() for p in paths]
        self.assertTrue(all(p == payloads[0] for p in payloads))
        self.assertIn(TAGS[1].encode(), payloads[0])

    def test_web_viewer_and_api_both_include_st_rule(self):
        viewer = (ROOT / 'apps/web/public/logic-assets/viewer.html').read_text()
        for name in (*TAGS, RULE):
            self.assertIn(name, viewer)
        for name in ['live_tag_master.csv','live_logic_runtime.csv','live_tag_allowlist.csv','live_validation_manifest.json']:
            self.assertEqual((ROOT/'data/current_v8'/name).read_bytes(), (ROOT/'services/agent-api/triplens/current_v8'/name).read_bytes())

if __name__ == '__main__':
    unittest.main()
