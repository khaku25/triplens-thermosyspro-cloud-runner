import csv
import hashlib
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.logic_assets.drawing_master import search_drawing_master
from scripts.logic_assets.xmlio import read_table

ROOT=Path(__file__).resolve().parents[1]
TAGS={'vppSTGeneratorPowerMW','vppSTGridPowerMW'}
RULE='RESP-ST-GRID-POWER'
BASELINE={
    'live_opcua_census.csv':'1f9dafddc23eb356e2854708d440be3385607df3548b967baa780553b33c8254',
    'live_tag_allowlist.csv':'ba5610fdc32ff22c9171bcaf016066bccea6682a5ec5dfcfbd34c0fd3c3a6f3e',
    'live_tag_master.csv':'f2277cc3d10cc317cffaf0ecf5cf74cd0ef1e46f4fd3db3a9e5fe1a189ad25b8',
    'live_logic_runtime.csv':'d79505193ef88a0f54f8d7370ed157313df079ebae9ef090ce98f148f6841ecb',
    'live_tag_logic_links.csv':'d6521353d58355a4267b76dfa9db4caef3359708673a22f2fb3bd5a1b05c4963',
    'live_validation_manifest.json':'4b793085e8f12a7e16eb1cae7d52d5acf23dce809f1802c116b3e9911d8124e7',
}

def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

class STPowerWebReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tag_live=read_table(ROOT/'data/current_v8/masters/06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx',
                                 '01_Live_OPCUA_Tag_Master','raw_tag_id')
        self.tag_source=read_table(ROOT/'data/current_v8/masters/06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx',
                                   '11_Model_Source_Observed','raw_tag_id')
        self.logic_live=read_table(ROOT/'data/current_v8/masters/07_LOGIC_MASTER_CURRENT_V8_VERIFIED.xlsx',
                                   '01_Logic_Master_Current','rule_id')
        self.logic_source=read_table(ROOT/'data/current_v8/masters/07_LOGIC_MASTER_CURRENT_V8_VERIFIED.xlsx',
                                     '06_Model_Source_Observed','rule_id')

    def test_tag_master_separates_live_census_from_later_raw_observations(self):
        self.assertEqual(len(self.tag_live),603)
        self.assertFalse(TAGS & {row['raw_tag_id'] for row in self.tag_live})
        source={row['raw_tag_id']:row for row in self.tag_source}
        self.assertEqual(set(source),TAGS)
        for row in source.values():
            self.assertEqual(row['source_kind'],'MODEL_SOURCE_RAW_OBSERVED')
            self.assertEqual(row['runtime_inclusion'],'SEARCH_ONLY')
            self.assertEqual(row['raw_session_id'],'SESSION_20260924_191347')
            self.assertEqual(row['raw_session_sha256'],'055f8a21b8f586feafaa6fe6705cfca05b4f1e833713991a0cac1f0e94ad6fd9')
            self.assertEqual(row['raw_rows'],'282')
            self.assertEqual(row['raw_closed_samples'],'282')
            self.assertEqual(row['raw_open_samples'],'0')
            self.assertEqual(row['open_behavior_test_status'],'NOT_TESTED')
            self.assertEqual(row['live_validation_status'],'NOT_TESTED_NO_OPCUA_IDENTITY')
            self.assertEqual(row['runtime_presence'],'SEARCH_ONLY')
            self.assertEqual(row['live_node_id'],'')
            self.assertEqual(row['live_variant_type'],'')

    def test_logic_master_keeps_resp_out_of_live_rules_and_includes_generator_input(self):
        self.assertEqual(len(self.logic_live),53)
        self.assertNotIn(RULE,{row['rule_id'] for row in self.logic_live})
        self.assertEqual(len(self.logic_source),1)
        row=self.logic_source[0]
        self.assertEqual(row['rule_id'],RULE)
        self.assertIn('vppSTGeneratorPowerMW',row['input_nodes'])
        self.assertIn('vpp52STClosed',row['input_nodes'])
        self.assertEqual(row['output_nodes_or_tags'],'vppSTGridPowerMW')
        self.assertEqual(row['runtime_inclusion'],'SEARCH_ONLY')
        self.assertEqual(row['model_source_status'],'MODEL_SOURCE_CONFIRMED')
        self.assertEqual(row['raw_session_status'],'RAW_SESSION_OBSERVED_CLOSED_ONLY')
        self.assertEqual(row['validation_status'],'PARTIAL')
        self.assertEqual(row['open_behavior_test_status'],'NOT_TESTED')
        self.assertIn('if not vpp52STClosed then 0 else vppSTGeneratorPowerMW',row['source_equation'])

    def test_raw_and_model_evidence_have_separate_provenance_and_no_open_pass(self):
        evidence=json.loads((ROOT/'data/current_v8/st_power_evidence_20260924.json').read_text())
        self.assertEqual(evidence['source_sha256'],'055f8a21b8f586feafaa6fe6705cfca05b4f1e833713991a0cac1f0e94ad6fd9')
        self.assertEqual(evidence['rows'],282)
        self.assertEqual(evidence['closed_breaker_samples'],282)
        self.assertEqual(evidence['open_breaker_samples'],0)
        self.assertEqual(evidence['behavior_validation'],'PARTIAL')
        self.assertEqual(evidence['model_source']['package_sha256'],'6c616330ad80e4b5aad377fd5c4875a2aba7fb15d2366bb1a239eb6dd92231c4')
        self.assertEqual(evidence['model_source']['file_sha256'],'cd454995656af9a8747efe8930d2aa0b92f98e1083acadc858eaa7959ea6d2c5')
        self.assertEqual(evidence['model_source']['equations'][1],
                         'vppSTGridPowerMW = if not vpp52STClosed then 0 else vppSTGeneratorPowerMW;')
        self.assertTrue(any('No 52ST-open sample' in note for note in evidence['limitations']))

    def test_run54_census_runtime_and_service_mirror_are_unchanged(self):
        census=ROOT/'data/current_v8/live_opcua_census.csv'
        self.assertEqual(sha(census),BASELINE['live_opcua_census.csv'])
        rows=read_csv(census)
        names={r['browse_name'] for r in rows if r['browse_name'].startswith('vpp')}
        self.assertEqual(len(names),603)
        self.assertFalse(TAGS & names)
        self.assertIn('vpp52STClosed',names)
        for name,digest in BASELINE.items():
            path=ROOT/'data/current_v8'/name
            self.assertEqual(sha(path),digest,name)
            if name!='live_opcua_census.csv':
                self.assertEqual(path.read_bytes(),(ROOT/'services/agent-api/triplens/current_v8'/name).read_bytes(),name)

    def test_static_search_index_and_links_connect_both_tags_to_resp(self):
        index=json.loads((ROOT/'apps/web/public/logic-assets/logic_diagram_index.json').read_text())
        counts=index['counts']
        self.assertEqual((counts['source_tags'],counts['searchable_tags'],counts['live_rules'],counts['rules'],counts['source_mapped_rules']),
                         (603,605,53,54,1))
        rule=index['rules'][RULE]
        self.assertEqual(rule['inputs'],['vppSTGeneratorPowerMW','vpp52STClosed'])
        self.assertEqual(rule['outputs'],['vppSTGridPowerMW'])
        self.assertEqual(rule['validation_status'],'PARTIAL')
        self.assertEqual(rule['open_behavior_test_status'],'NOT_TESTED')
        for tag in TAGS:
            self.assertEqual(index['tags'][tag]['runtime_inclusion'],'SEARCH_ONLY')
            self.assertIn(RULE,index['tags'][tag]['rule_ids'])
        links=read_csv(ROOT/'generated/logic/links.csv')
        response=next(row for row in links if row['rule_id']==RULE)
        self.assertIn('vppSTGeneratorPowerMW',response['input_nodes'])
        self.assertIn('vpp52STClosed',response['input_nodes'])
        self.assertEqual(response['source_outputs'],'vppSTGridPowerMW')
        self.assertEqual(response['link_status'],'SOURCE_MAPPED_ONLY')
        self.assertEqual(response['source_existence'],'MODEL_SOURCE_CONFIRMED_RAW_OBSERVED')
        ports=read_csv(ROOT/'generated/logic/ports.csv')
        self.assertTrue(any(p['rule_id']==RULE and p['relation']=='INPUT' and p['node_or_tag']=='vppSTGeneratorPowerMW' for p in ports))

    def test_drawing_master_and_generated_diagram_include_source_rule_and_tags(self):
        paths=['logic_diagrams','generated/logic','apps/web/public/logic-assets']
        indexes=[json.loads((ROOT/p/'drawing_master_index.json').read_text()) for p in paths]
        self.assertEqual(indexes[0],indexes[1]);self.assertEqual(indexes[0],indexes[2])
        for tag in TAGS:
            matches=search_drawing_master(indexes[0],tag)
            self.assertTrue(any(row['tag_id']==tag and 'ST Protection' in row['page_name'] for row in matches),tag)
        xml=ET.parse(ROOT/'logic_diagrams/TripLens_Logic_Master_Current_V8.drawio')
        rule=indexes[0]
        matches=[row for row in rule['entries'] if row.get('logic_id')==RULE]
        self.assertTrue(matches)
        page=xml.find(f"./diagram[@id='IG-036']")
        self.assertIsNotNone(page)
        content=' '.join(obj.get('label','') for obj in page.findall('.//object'))
        for text in ('vppSTGeneratorPowerMW','vpp52STClosed','vppSTGridPowerMW','MODEL_SOURCE_CONFIRMED','52ST OPEN: NOT_TESTED','PARTIAL'):
            self.assertIn(text,content)

    def test_web_viewer_and_summary_disclose_scope_before_navigation(self):
        viewer=(ROOT/'apps/web/public/logic-assets/viewer.html').read_text(encoding='utf-8')
        for marker in (*TAGS,RULE,'MODEL_SOURCE_CONFIRMED','RAW_SESSION_OBSERVED_CLOSED_ONLY','NOT_TESTED','SEARCH_ONLY'):
            self.assertIn(marker,viewer)
        summary=json.loads((ROOT/'apps/web/lib/current-logic-summary.json').read_text())
        self.assertEqual(summary['live_tags'],603)
        self.assertEqual(summary['searchable_tags'],605)
        self.assertEqual(summary['live_rules'],53)
        self.assertEqual(summary['searchable_rules'],54)
        self.assertEqual(summary['source_mapped_rules'],1)
        manifest=json.loads((ROOT/'apps/web/public/logic-assets/asset_manifest.json').read_text())
        for name in ('TripLens_Logic_Master_Current_V8.drawio','logic_diagram_index.json','drawing_master_index.json','viewer.html'):
            self.assertEqual(manifest['files'][name],sha(ROOT/'apps/web/public/logic-assets'/name))

if __name__=='__main__':
    unittest.main()
