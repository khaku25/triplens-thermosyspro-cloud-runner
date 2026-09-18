import hashlib,json,subprocess,sys,tempfile,unittest
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
        summary=json.loads(r.stdout);self.assertEqual(summary['counts']['rules'],53)
        self.assertEqual(self.run_cmd('--check').returncode,0)
        self.assertTrue((self.out/'apps/web/public/logic-assets/viewer.html').exists())
    def test_wrong_census_proof_does_not_publish(self):
        p=self.out/'bad.json';p.write_text(json.dumps({'census_sha256':'0'*64}))
        r=self.run_cmd('--census-provenance',str(p))
        self.assertNotEqual(r.returncode,0)
        self.assertIn('census',r.stderr.lower())
        self.assertFalse((self.out/'generated/logic').exists())
    def test_help_has_drive_and_layout_options(self):
        r=subprocess.run([sys.executable,str(SCRIPT),'--help'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0)
        self.assertIn('--from-drive',r.stdout);self.assertIn('--layout',r.stdout)
if __name__=='__main__':unittest.main()
