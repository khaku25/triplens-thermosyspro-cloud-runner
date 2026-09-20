"""Behavioural tests for master -> draw.io -> first-party viewer publishing."""
import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import base64
import zlib
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
try:
    api = importlib.import_module('scripts.logic_assets')
except ImportError:
    api = None


def fixture():
    tags = [dict(raw_tag_id='vppLevel', description_ko='드럼 수위', unit='m',
                 scope_class='CURRENT_OPERATIONAL_EVIDENCE'),
            dict(raw_tag_id='vppTrip', description_ko='Trip 상태', unit='BOOL',
                 scope_class='CURRENT_OPERATIONAL_EVIDENCE')]
    rule = dict(rule_id='AL-LEVEL-H', group='HP Drum', logic_name='HP 수위 H',
                logic_type='ALARM', input_nodes='vppLevel', condition='value > 1.25 m',
                delay='0.5 s', reset_hysteresis='0.02 m', output_nodes_or_tags='HRSG.HP.LEVEL.H',
                output_class='DERIVED_ALARM', input_group_id='IG-003', validation_status='PARTIAL',
                source_basis='Test fixture')
    census = [dict(browse_name=t['raw_tag_id'], live_validated='Y', numeric='Y', finite='Y',
                   variant_type='Double', node_id='ns=1;s='+t['raw_tag_id']) for t in tags]
    return tags, [rule], census


class AssetsTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(api is not None and hasattr(api, 'make_repository'), 'logic_assets implementation is not installed')
        self.tags, self.rules, self.census = fixture()

    def build(self, **kw):
        return api.make_repository(self.tags, self.rules, self.census, **kw)

    def test_counts_and_native_derived_separation(self):
        repo = self.build()
        self.assertEqual(repo['index']['counts']['source_tags'], 2)
        self.assertEqual(repo['index']['counts']['rules'], 1)
        self.assertEqual(repo['index']['counts']['derived_outputs'], 1)
        self.assertFalse(repo['index']['entities']['HRSG.HP.LEVEL.H']['is_native'])
        self.assertEqual(repo['index']['tags']['vppTrip']['rule_ids'], [])

    def test_schema_two_separates_signal_path_and_additional_information(self):
        repo = self.build()
        root = ET.fromstring(repo['xml'])
        self.assertEqual(root.get('triplens_schema'), '2')
        self.assertEqual(repo['index']['schema_version'], 2)
        for page in root.findall('diagram'):
            for rid in json.loads(page.get('rule_ids')):
                graph = page.find('mxGraphModel/root')
                for kind in ('condition', 'operation', 'additional'):
                    self.assertEqual(len(graph.findall(f"object[@id='{kind}:{rid}'][@kind='{kind}']")), 1)
                operation = graph.find(f"object[@id='operation:{rid}']")
                additional = graph.find(f"object[@id='additional:{rid}']")
                self.assertNotIn('0.02 m', operation.get('label'))
                for value in ('0.5 s', '0.02 m', 'PARTIAL', 'DERIVED_ALARM'):
                    self.assertIn(value, additional.get('label'))
                edges = graph.findall("mxCell[@edge='1']")
                self.assertEqual(len(edges), 3)
                self.assertEqual({(e.get('source').split(':')[0], e.get('target').split(':')[0]) for e in edges},
                                 {('source', 'condition'), ('condition', 'operation'), ('operation', 'output')})
                columns = [('source', 40, 320), ('condition', 410, 320), ('operation', 780, 320), ('output', 1150, 360)]
                for prefix, x, width in columns:
                    obj = next(o for o in graph.findall('object') if o.get('id').startswith(prefix+':'))
                    geometry = obj.find('mxCell/mxGeometry')
                    self.assertEqual((float(geometry.get('x')), float(geometry.get('width'))), (x, width))
                og = operation.find('mxCell/mxGeometry'); ag = additional.find('mxCell/mxGeometry')
                self.assertGreater(float(ag.get('y')), float(og.get('y'))+float(og.get('height')))

    def test_schema_one_central_geometry_migrates_once(self):
        legacy = '<mxfile triplens_schema="1"><diagram id="IG-003"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><object id="logic:AL-LEVEL-H"><mxCell vertex="1" parent="1"><mxGeometry x="911" y="300" width="380" height="164" as="geometry"/></mxCell></object></root></mxGraphModel></diagram></mxfile>'
        v1_logic_geometry = ET.fromstring(legacy).find('.//mxGeometry').attrib
        migrated = ET.fromstring(self.build(layout_xml=legacy)['xml'])
        operation = migrated.find("./diagram[@id='IG-003']/mxGraphModel/root/object[@id='operation:AL-LEVEL-H']/mxCell/mxGeometry")
        self.assertIsNotNone(operation)
        v2_operation_geometry = dict(operation.attrib)
        self.assertNotEqual(v1_logic_geometry, v2_operation_geometry)
        operation.set('x', '888')
        v2_saved_operation_geometry = dict(operation.attrib)
        regenerated = ET.fromstring(self.build(layout_xml=ET.tostring(migrated, encoding='unicode'))['xml'])
        v2_regenerated_operation_geometry = regenerated.find("./diagram[@id='IG-003']/mxGraphModel/root/object[@id='operation:AL-LEVEL-H']/mxCell/mxGeometry").attrib
        self.assertEqual(v2_saved_operation_geometry, v2_regenerated_operation_geometry)

    def test_exact_tag_and_rule_navigation(self):
        repo = self.build()
        self.assertEqual(repo['index']['tags']['vppLevel']['rule_ids'], ['AL-LEVEL-H'])
        self.assertEqual(repo['index']['rules']['AL-LEVEL-H']['group_page'], 'IG-003')
        self.assertIn('rule:AL-LEVEL-H', repo['index']['pages'])

    def test_unknown_input_is_rejected(self):
        self.rules[0]['input_nodes'] = 'vppMadeUp'
        with self.assertRaisesRegex(ValueError, 'live|source|존재'):
            self.build()

    def test_new_tag_needs_live_census(self):
        self.tags.append(dict(raw_tag_id='vppNew', unit='m'))
        with self.assertRaisesRegex(ValueError, 'census|live'):
            self.build()

    def test_duplicate_rule_is_rejected(self):
        self.rules.append(dict(self.rules[0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.build()

    def test_duplicate_tag_is_rejected(self):
        self.tags.append(dict(self.tags[0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.build()

    def test_duplicate_live_identity_is_rejected(self):
        self.census.append(dict(self.census[0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.build()

    def test_lab_only_input_blocked(self):
        self.tags[0]['scope_class'] = 'SCENARIO_LAB_ONLY_LEGACY'
        with self.assertRaisesRegex(ValueError, 'Lab|lab|LAB'):
            self.build()

    def test_undefined_output_blocked(self):
        self.rules[0]['output_class']='RAW_NODE'
        with self.assertRaisesRegex(ValueError, 'output'):
            self.build()

    def test_two_rules_share_input_without_losing_branches(self):
        second = dict(self.rules[0], rule_id='AL-LEVEL-HH', condition='value > 1.30 m',
                      output_nodes_or_tags='HRSG.HP.LEVEL.HH')
        self.rules.append(second)
        repo = self.build()
        page=repo['index']['pages']['IG-003']
        self.assertEqual(page['rule_ids'], ['AL-LEVEL-H', 'AL-LEVEL-HH'])
        graph = ET.fromstring(repo['xml']).find("./diagram[@id='IG-003']/mxGraphModel/root")
        self.assertEqual(len(graph.findall("object[@kind='source'][@tag_id='vppLevel']")), 1)

    def test_branch_spacing_expands_for_multiple_outputs(self):
        self.rules.extend([dict(self.rules[0],rule_id='AL-LEVEL-HH',output_nodes_or_tags='HRSG.HP.LEVEL.HH | HRSG.HP.LEVEL.X | HRSG.HP.LEVEL.Y'),
                           dict(self.rules[0],rule_id='AL-LEVEL-L',output_nodes_or_tags='HRSG.HP.LEVEL.L')])
        graph=ET.fromstring(self.build()['xml']).find("./diagram[@id='IG-003']/mxGraphModel/root")
        positions=[float(graph.find(f"object[@id='operation:{rid}']/mxCell/mxGeometry").get('y'))
                   for rid in ('AL-LEVEL-H','AL-LEVEL-HH','AL-LEVEL-L')]
        self.assertEqual(positions[1]-positions[0],250)
        self.assertEqual(positions[2]-positions[1],366)
        for geometry in graph.findall("object[@rule_id='AL-LEVEL-HH']/mxCell/mxGeometry"):
            self.assertLess(float(geometry.get('y'))+float(geometry.get('height')),positions[2])

    def test_schema_two_preserves_all_managed_vertex_geometry(self):
        root=ET.fromstring(self.build()['xml'])
        graph=root.find("./diagram[@id='IG-003']/mxGraphModel/root")
        saved={}
        for obj in graph.findall('object'):
            geometry=obj.find('mxCell/mxGeometry')
            geometry.set('x',str(float(geometry.get('x'))+5))
            geometry.set('y',str(float(geometry.get('y'))+7))
            saved[obj.get('id')]=dict(geometry.attrib)
        regenerated=ET.fromstring(self.build(layout_xml=ET.tostring(root,encoding='unicode'))['xml'])
        graph=regenerated.find("./diagram[@id='IG-003']/mxGraphModel/root")
        self.assertEqual({obj.get('id'):obj.find('mxCell/mxGeometry').attrib for obj in graph.findall('object')},saved)

    def test_threshold_update_preserves_geometry_and_updates_labels(self):
        old = self.build()
        xml = ET.fromstring(old['xml'])
        cell = xml.find("./diagram[@id='IG-003']/mxGraphModel/root/object[@rule_id='AL-LEVEL-H'][@kind='condition']")
        cell.find('mxCell/mxGeometry').set('x','911')
        self.rules[0]['condition']='value > 1.30 m'
        new=self.build(layout_xml=ET.tostring(xml,encoding='unicode'))
        result=ET.fromstring(new['xml']).find("./diagram[@id='IG-003']/mxGraphModel/root/object[@rule_id='AL-LEVEL-H'][@kind='condition']")
        self.assertEqual(result.find('mxCell/mxGeometry').get('x'),'911')
        self.assertIn('1.30 m',result.get('label'))
        self.assertNotEqual(old['index']['semantic_sha256'],new['index']['semantic_sha256'])

    def test_description_changes_propagate_to_diagram(self):
        self.tags[0]['description_ko']='HP 드럼 실제 수위'
        repo=self.build()
        self.assertIn('HP 드럼 실제 수위',repo['xml'])
        self.assertEqual(repo['index']['tags']['vppLevel']['description_ko'],'HP 드럼 실제 수위')

    def test_regeneration_is_idempotent(self):
        first=self.build()
        second=self.build(layout_xml=first['xml'])
        self.assertEqual(first['xml'],second['xml'])
        self.assertEqual(first['index'],second['index'])

    def test_edge_waypoints_are_preserved(self):
        old=ET.fromstring(self.build()['xml'])
        edge=old.find("./diagram[@id='IG-003']/mxGraphModel/root/mxCell[@edge='1']")
        geom=edge.find('mxGeometry')
        arr=ET.SubElement(geom,'Array',{'as':'points'})
        ET.SubElement(arr,'mxPoint',{'x':'700','y':'500'})
        new=ET.fromstring(self.build(layout_xml=ET.tostring(old,encoding='unicode'))['xml'])
        point=new.find(f"./diagram[@id='IG-003']/mxGraphModel/root/mxCell[@id='{edge.get('id')}']/mxGeometry/Array/mxPoint")
        self.assertEqual(point.get('x'),'700')

    def test_compressed_drawio_supported(self):
        old=ET.fromstring(self.build()['xml'])
        for d in old.findall('diagram'):
            model=ET.tostring(d[0],encoding='unicode')
            payload=quote(model,safe='').encode()
            comp=zlib.compressobj(wbits=-15)
            d.remove(d[0]); d.text=base64.b64encode(comp.compress(payload)+comp.flush()).decode()
        self.assertEqual(self.build()['xml'],self.build(layout_xml=ET.tostring(old,encoding='unicode'))['xml'])

    def test_xml_entity_payload_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'XML|DTD|entity'):
            self.build(layout_xml='<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><mxfile/>')

    def test_duplicate_cell_ids_rejected(self):
        old=ET.fromstring(self.build()['xml'])
        root=old.find("./diagram[@id='IG-003']/mxGraphModel/root")
        root.append(copy.deepcopy(root.find('object')))
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.build(layout_xml=ET.tostring(old,encoding='unicode'))

    def test_runtime_text_does_not_become_fake_timer(self):
        self.rules[0].update(logic_type='LATCH', delay='event-driven', output_class='RAW_NODE',
                            output_nodes_or_tags='vppTrip')
        root=ET.fromstring(self.build()['xml'])
        self.assertEqual(root.findall(".//object[@kind='delay']"),[])
        self.assertIn('event-driven',self.build()['xml'])

    def test_hysteresis_is_property_not_serial_fake_gate(self):
        root=ET.fromstring(self.build()['xml'])
        self.assertEqual(root.findall(".//object[@kind='hysteresis']"),[])
        logic=root.find(".//object[@kind='additional']")
        self.assertEqual(logic.get('reset_hysteresis'),'0.02 m')

    def test_live_existence_does_not_promote_behaviour_status(self):
        repo=self.build()
        self.assertEqual(repo['index']['rules']['AL-LEVEL-H']['validation_status'],'PARTIAL')

    def test_master_unsupported_expression_remains_literal(self):
        self.rules[0]['condition']='<script>alert(1)</script> literal'
        repo=self.build()
        root=ET.fromstring(repo['xml'])
        self.assertIn('<script>alert(1)</script>',root.find(".//object[@kind='condition']").get('condition'))
        self.assertNotIn('<script>alert(1)</script>', repo['xml'])

    def test_invalid_geometry_is_rejected(self):
        root=ET.fromstring(self.build()['xml'])
        root.find(".//object[@kind='operation']/mxCell/mxGeometry").set('x','nan')
        with self.assertRaisesRegex(ValueError,'geometry|finite'):
            self.build(layout_xml=ET.tostring(root,encoding='unicode'))

    def test_derived_views_and_repository_agree(self):
        repo=self.build()
        self.assertEqual(repo['derived']['ports'][0]['node_or_tag'],'vppLevel')
        self.assertEqual(repo['derived']['ports'][1]['kind'],'DERIVED_TAG')
        self.assertEqual(repo['derived']['links'][0]['missing_inputs'],'')

    def test_failed_publish_keeps_previous_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'release'
            api.publish_repository(self.build(),path)
            before=(path/'TripLens_Logic_Master_Current_V8.drawio').read_bytes()
            self.rules[0]['input_nodes']='vppMissing'
            with self.assertRaises(ValueError):
                api.publish_repository(self.build(),path)
            self.assertEqual((path/'TripLens_Logic_Master_Current_V8.drawio').read_bytes(),before)


if __name__=='__main__':
    unittest.main()
