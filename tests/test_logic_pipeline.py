"""One-command publishing and metadata invariants (stdlib only)."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

try:
    pipeline=importlib.import_module('scripts.logic_assets.pipeline')
except ImportError:
    pipeline=None
from scripts.logic_assets import make_repository
from scripts.logic_assets.xmlio import read_table,write_xlsx
from test_logic_assets import fixture
ROOT=Path(__file__).resolve().parents[1]

class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(pipeline,'one-command pipeline is not implemented')
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.tags,self.rules,self.census=fixture()

    def repo(self):
        return make_repository(self.tags,self.rules,self.census)

    def test_runtime_preserves_semantics_and_source_status_separately(self):
        runtime=pipeline.runtime_assets(self.repo())
        p=self.root/'runtime.csv'; p.write_bytes(runtime['live_logic_runtime.csv'])
        row=read_table(p)[0]
        self.assertEqual(row['condition'],'value > 1.25 m')
        self.assertEqual(row['delay'],'0.5 s')
        self.assertEqual(row['reset_hysteresis'],'0.02 m')
        self.assertEqual(row['verification_status'],'PARTIAL')
        self.assertEqual(row['source_existence_status'],'LIVE_CENSUS_RESOLVED')
        self.assertIn('vppLevel',row['linked_tag_ids'])

    def test_manifest_hashes_and_dynamic_counts(self):
        assets=pipeline.runtime_assets(self.repo())
        manifest=json.loads(assets['live_validation_manifest.json'])
        self.assertEqual(manifest['counts']['live_tags'],2)
        self.assertEqual(manifest['counts']['logic_rules'],1)
        for name,info in manifest['files'].items():
            self.assertEqual(info['sha256'],hashlib.sha256(assets[name]).hexdigest())

    def test_new_rule_appears_everywhere_in_single_update(self):
        second=dict(self.rules[0],rule_id='AL-LEVEL-HH',condition='value > 1.30 m',output_nodes_or_tags='HRSG.HP.LEVEL.HH')
        self.rules.append(second)
        result=pipeline.publish_project(self.repo(),self.root)
        self.assertEqual(result['counts']['rules'],2)
        self.assertTrue((self.root/'apps/web/public/logic-assets/viewer.html').exists())
        raw=(self.root/'logic_diagrams/TripLens_Logic_Master_Current_V8.drawio').read_bytes()
        self.assertIn(b'1.30',raw)
        for prefix in ['data/current_v8','services/agent-api/triplens/current_v8']:
            m=json.loads((self.root/prefix/'live_validation_manifest.json').read_bytes())
            self.assertEqual(m['counts']['logic_rules'],2)
            self.assertEqual((self.root/prefix/'live_logic_runtime.csv').read_bytes(),(self.root/'data/current_v8/live_logic_runtime.csv').read_bytes())
        ports=read_table(self.root/'generated/logic/09_LOGIC_DEFINITION_MASTER_CURRENT_V8.xlsx','02_Ports','rule_id')
        self.assertEqual(len(ports),4)
        self.assertNotIn('MISSING',{p['kind'] for p in ports})

    def test_check_mode_does_not_write(self):
        pipeline.publish_project(self.repo(),self.root)
        result=pipeline.check_project(self.repo(),self.root)
        self.assertEqual(result,[])
        path=self.root/'data/current_v8/live_logic_runtime.csv'
        path.write_text('tampered')
        failed=pipeline.check_project(self.repo(),self.root)
        self.assertIn('data/current_v8/live_logic_runtime.csv',failed)
        self.assertEqual(path.read_text(),'tampered')

    def test_read_existing_xlsx_matches_actual_rows(self):
        if not (ROOT/'data/current_v8/masters/06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx').exists():
            self.skipTest('snapshot bootstrap required')
        model=pipeline.load_authoring(ROOT/'data/current_v8/masters',ROOT/'data/current_v8/live_opcua_census.csv')
        self.assertEqual(len(model['model']['tags']),603)
        self.assertEqual(len(model['model']['rules']),53)

    def test_formula_in_authoring_rejected(self):
        import zipfile
        file=self.root/'07.xlsx'
        write_xlsx(file,{'Rules':[{'rule_id':'R','condition':'value > 1'}]})
        with zipfile.ZipFile(file) as z: contents={n:z.read(n) for n in z.namelist()}
        contents['xl/worksheets/sheet1.xml']=contents['xl/worksheets/sheet1.xml'].replace(b'<is><t xml:space="preserve">value &gt; 1</t></is>',b'<f>1+1</f><v>2</v>')
        with zipfile.ZipFile(file,'w') as z:
            for n,data in contents.items(): z.writestr(n,data)
        with self.assertRaisesRegex(ValueError,'Formula'):
            read_table(file,'Rules')

    def test_equipment_sheet_keeps_grouped_rules(self):
        pipeline.publish_project(self.repo(),self.root)
        rows=read_table(self.root/'generated/logic/10_OPERATIONAL_LOGIC_GROUP_CURRENT_V8.xlsx','03_HP_Drum','rule_id')
        self.assertEqual([r['rule_id'] for r in rows],['AL-LEVEL-H'])

    def test_same_update_is_byte_idempotent(self):
        pipeline.publish_project(self.repo(),self.root)
        hashes={str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        pipeline.publish_project(self.repo(),self.root)
        now={str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(hashes,now)

if __name__=='__main__': unittest.main()
