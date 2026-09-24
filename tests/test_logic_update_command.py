import hashlib,json,subprocess,sys,tempfile,unittest
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts/update_triplens_logic.py'
class CommandTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(),'one-command entry point missing')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.out=Path(self.temp.name)
    def run_cmd(self,*args):
        return subprocess.run([sys.executable,str(SCRIPT),'--project-root',str(self.out),
            '--master-dir',str(ROOT/'data/current_v8/masters'),
            '--census',str(ROOT/'data/current_v8/live_opcua_census.csv'),
            '--census-provenance',str(ROOT/'data/current_v8/live_census_provenance.json'),*args],capture_output=True,text=True)
    def test_one_command_build_and_check(self):
        r=self.run_cmd();self.assertEqual(r.returncode,0,r.stderr)
        summary=json.loads(r.stdout);self.assertEqual(summary['counts']['rules'],54)
        self.assertEqual(self.run_cmd('--check').returncode,0)
        self.assertTrue((self.out/'apps/web/public/logic-assets/viewer.html').exists())
    def test_wrong_census_proof_does_not_publish(self):
        p=self.out/'bad.json';p.write_text(json.dumps({'census_sha256':'0'*64}))
        r=self.run_cmd('--census-provenance',str(p))
        self.assertNotEqual(r.returncode,0)
        self.assertIn('census',r.stderr.lower())
        self.assertFalse((self.out/'generated/logic').exists())
    def test_schema_one_migrates_then_schema_two_updates_preserving_operation(self):
        layout=self.out/'saved.drawio'
        layout.write_text('<mxfile triplens_schema="1"><diagram id="IG-003"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><object id="logic:AL-HP-LEVEL-HH"><mxCell vertex="1" parent="1"><mxGeometry x="911" y="300" width="380" height="164" as="geometry"/></mxCell></object></root></mxGraphModel></diagram></mxfile>')
        result=self.run_cmd('--layout',str(layout));self.assertEqual(result.returncode,0,result.stderr)
        generated=self.out/'logic_diagrams/TripLens_Logic_Master_Current_V8.drawio'
        root=ET.fromstring(generated.read_text())
        self.assertEqual(root.get('triplens_schema'),'2')
        geometry=root.find("./diagram[@id='IG-003']/mxGraphModel/root/object[@id='operation:AL-HP-LEVEL-HH']/mxCell/mxGeometry")
        self.assertEqual(geometry.get('x'),'780')
        geometry.set('x','888');layout.write_text(ET.tostring(root,encoding='unicode'))
        result=self.run_cmd('--layout',str(layout));self.assertEqual(result.returncode,0,result.stderr)
        saved=ET.fromstring(generated.read_text()).find("./diagram[@id='IG-003']/mxGraphModel/root/object[@id='operation:AL-HP-LEVEL-HH']/mxCell/mxGeometry")
        self.assertEqual(saved.get('x'),'888')
        self.assertEqual(self.run_cmd('--check').returncode,0)
    def test_unsupported_mixed_and_numeric_layouts_are_rejected_without_publication(self):
        for number,(schema,ids) in enumerate([('1',['operation:R']),('2',['logic:R']),('2',['operation:R','logic:S']),('1',['logic:R','operation:S']),('3',['operation:R']),('1',['42'])]):
            with self.subTest(schema=schema,ids=ids):
                layout=self.out/'invalid.drawio'
                root=ET.Element('mxfile',triplens_schema=schema)
                graph=ET.SubElement(ET.SubElement(ET.SubElement(root,'diagram',id='IG-003'),'mxGraphModel'),'root')
                for cell_id in ids: ET.SubElement(graph,'mxCell',id=cell_id)
                layout.write_text(ET.tostring(root,encoding='unicode'))
                destination=self.out/str(number)
                result=self.run_cmd('--layout',str(layout),'--project-root',str(destination))
                self.assertNotEqual(result.returncode,0,result.stdout)
                self.assertFalse((destination/'generated/logic').exists())
    def test_help_has_drive_and_layout_options(self):
        r=subprocess.run([sys.executable,str(SCRIPT),'--help'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0)
        self.assertIn('--from-drive',r.stdout);self.assertIn('--layout',r.stdout)
if __name__=='__main__':unittest.main()
