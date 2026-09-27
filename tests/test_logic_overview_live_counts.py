"""The overview uses the frozen live model, not a filtered searchable overlay."""
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from scripts.logic_assets.pipeline import load_authoring
ROOT = Path(__file__).resolve().parents[1]
class OverviewLiveCountsTest(unittest.TestCase):
    def test_overview_uses_exact_live_model_counts(self):
        repo = load_authoring(ROOT/'data/current_v8/masters', ROOT/'data/current_v8/live_opcua_census.csv', ROOT/'logic_diagrams/TripLens_Logic_Master_Current_V8.drawio')
        label = ET.fromstring(repo['xml']).find("./diagram[@id='overview']/mxGraphModel/root/object[@id='overview-policy']").get('label')
        actual = int(re.search(r'live (\d+)개 로직', label).group(1))
        self.assertEqual(actual, len(repo['model']['rules']), 'Overview live count differs from frozen live model')
        self.assertEqual(actual, repo['index']['counts']['live_rules'])
        self.assertIn(f"census {len(repo['model']['tags'])}개 태그", label)
        self.assertIn(f"검색 {len(repo['search_model']['rules'])}개 로직", label)
