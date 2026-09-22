"""Regression contract for restoration on the current operator UI baseline."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from scripts.logic_assets import make_repository, publish_repository
from scripts.logic_assets.pipeline import project_files
from test_logic_assets import fixture


class RestorationTest(unittest.TestCase):
    def test_repository_contains_read_only_index_for_every_existing_object(self):
        repo = make_repository(*fixture())
        self.assertTrue('drawing_master' in repo, 'Drawing Master must be restored in the source pipeline')
        dm = repo['drawing_master']
        xml = ET.fromstring(repo['xml'])
        refs = {(p.get('id'), o.get('id')) for p in xml.findall('diagram')
                for o in p.findall('mxGraphModel/root/object')}
        self.assertEqual({(e['page_id'], e['cell_id']) for e in dm['entries']}, refs)
        self.assertEqual(dm['source_sha256'], hashlib.sha256(repo['xml'].encode()).hexdigest())
        self.assertTrue(all(e['verification_status'] == 'INDEXED_FROM_DRAWIO_XML' for e in dm['entries']))
        self.assertEqual(repo['model']['rules'][0]['validation_status'], 'PARTIAL')

    def test_index_is_published_to_web_and_hash_manifest(self):
        files = project_files(make_repository(*fixture()))
        name = 'drawing_master_index.json'
        key = 'apps/web/public/logic-assets/' + name
        self.assertTrue(key in files, 'Web publication must include Drawing Master, not just generated data')
        self.assertEqual(files[key], files['generated/logic/' + name])
        self.assertEqual(files[key], files['logic_diagrams/' + name])
        manifest = json.loads(files['apps/web/public/logic-assets/asset_manifest.json'])
        self.assertEqual(manifest['files'][name], hashlib.sha256(files[key]).hexdigest())

    def test_regeneration_preserves_exact_drawing_and_identity(self):
        original = make_repository(*fixture())
        regenerated = make_repository(*fixture(), layout_xml=original['xml'])
        self.assertTrue('drawing_master' in regenerated)
        self.assertEqual(original['xml'], regenerated['xml'])
        self.assertEqual(original['index'], regenerated['index'])
        self.assertEqual(original['drawing_master'], regenerated['drawing_master'])


if __name__ == '__main__':
    unittest.main()
