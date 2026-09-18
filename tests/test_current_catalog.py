import importlib.util,json,tempfile,unittest
from pathlib import Path
from scripts.logic_assets import make_repository
from scripts.logic_assets.pipeline import runtime_assets
from test_logic_assets import fixture
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'services/agent-api/triplens/current_catalog.py'
class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PATH.exists(),'validated runtime reader missing')
        spec=importlib.util.spec_from_file_location('test_catalog_reader',PATH);self.mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.mod)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.assets=runtime_assets(make_repository(*fixture()))
        for n,d in self.assets.items():(self.root/n).write_bytes(d)
    def test_load_keeps_source_status_and_no_count_constants(self):
        manifest,tags,rows=self.mod.load_catalog(self.root)
        self.assertEqual(len(tags),2);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['verification_status'],'PARTIAL')
        self.assertEqual(rows[0]['event_class'],'ALARM')
    def test_tampered_runtime_is_rejected(self):
        (self.root/'live_logic_runtime.csv').write_text('modified')
        with self.assertRaisesRegex(RuntimeError,'hash'):
            self.mod.load_catalog(self.root)
    def test_missing_manifest_is_rejected_without_legacy_fallback(self):
        (self.root/'live_validation_manifest.json').unlink()
        with self.assertRaisesRegex(RuntimeError,'manifest'):
            self.mod.load_catalog(self.root)
    def test_unsafe_manifest_path_rejected(self):
        m=json.loads(self.assets['live_validation_manifest.json']);m['files']['../other']={'sha256':'0'*64}
        (self.root/'live_validation_manifest.json').write_text(json.dumps(m))
        with self.assertRaisesRegex(RuntimeError,'path'):
            self.mod.load_catalog(self.root)
if __name__=='__main__':unittest.main()
