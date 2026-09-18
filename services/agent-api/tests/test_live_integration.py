"""Regression fixtures, NOT physical-run evidence or blind-validation scores."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))
import bridge
from gemini_agent import fail_closed_contract

EVENT_FIELDS = 'event_id,event_sequence,session_id,incident_id,model_time_s,wall_time_utc,priority,event_class,equipment,tag,state,value,unit,message,source,acknowledged'.split(',')
RAW_META = 'record_sequence,session_id,incident_id,model_time_s,wall_time_utc,collector_quality'.split(',')
TAGS = ['vppExternalTripCommandNative','vppExternalSTTripCommandNative','vppCauseDirectGTTrip','vppCauseDirectSTTrip','vppGTTripRequest','vppSTTripRequest','vppGTTripLatch','vppSTTripLatchPublished','vpp52GTTripCmd','vpp52STTripCmd','vpp52GTClosed','vpp52STClosed','vppGTExhaustTemperatureK']

def write_csv(path, fields, records):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(records)

def make_fixture(root):
    """Generic EVENT names, initiating signal only in RAW; no 86GT fiction."""
    event, raw = root/'EVENT.csv', root/'RAW.csv'
    base = dict(session_id='S-REGRESSION', incident_id='I-REGRESSION', wall_time_utc='2026-09-15T14:52:04.212+00:00')
    specs = [(48.44,'GT','TRIP_LATCH',1),(48.44,'ST','TRIP_LATCH',1),(48.52,'52GT','BREAKER_OPEN',0),(48.54,'52ST','BREAKER_OPEN',0)]
    events = [dict(base,event_id=f'E-{i}',event_sequence=i,model_time_s=t,priority='HIGH',event_class='PROTECTION',equipment=equipment,tag=tag,state='ACTIVE',value=value,unit='BOOL',message=f'{equipment} {tag} ACTIVE',source='OPENMODELICA_PHYSICS',acknowledged='false') for i,(t,equipment,tag,value) in enumerate(specs,1)]
    rows=[]
    for i,t in enumerate([48.0,48.4,48.44,48.495,48.52,48.54,49.0,50.0],1):
        row=dict(base,record_sequence=i,model_time_s=t,collector_quality='GOOD')
        row.update({tag:0 for tag in TAGS})
        row.update(vppExternalTripCommandNative=int(t>=48.4),vppCauseDirectGTTrip=int(t>=48.4),vppGTTripRequest=int(t>=48.4),vppSTTripRequest=int(t>=48.4),vppGTTripLatch=int(t>=48.44),vppSTTripLatchPublished=int(t>=48.44),vpp52GTTripCmd=int(t>=48.495),vpp52STTripCmd=int(t>=48.44),vpp52GTClosed=int(t<48.52),vpp52STClosed=int(t<48.54),vppGTExhaustTemperatureK=893.75 if t<48.54 else 780.0)
        rows.append(row)
    write_csv(event,EVENT_FIELDS,events); write_csv(raw,RAW_META+TAGS,rows)
    return event,raw

class LiveIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.event,self.raw=make_fixture(self.root)
        self.store=bridge.build_store(self.event,self.raw)
    def tearDown(self): self.tmp.cleanup()

    def test_generic_event_is_resolved_by_equipment_not_tag_guessing(self):
        gt=self.store.search_events(equipment='GT',tags=['TRIP_LATCH'])[0]
        st=self.store.search_events(equipment='ST',tags=['TRIP_LATCH'])[0]
        self.assertEqual(gt.get('source_node'),'vppGTTripLatch')
        self.assertEqual(st.get('source_node'),'vppSTTripLatchPublished')
        self.assertEqual(gt['tag'],'TRIP_LATCH')
        self.assertEqual(gt.get('mapping_status'),'EQUIPMENT_TAG_EXACT')

    def test_bootstrap_exposes_actual_raw_inventory_not_values_or_answers(self):
        boot=self.store.build_agent_bootstrap(run_id='R',data_digest='D')
        self.assertIn('vppExternalTripCommandNative',boot.get('raw_tag_inventory',[]))
        self.assertNotIn('raw_rows',boot)
        self.assertNotIn('scenario_id',boot)
        self.assertNotIn('86GT.OPERATE',json.dumps(boot))

    def test_logic_lookup_accepts_explicit_equipment_tag_key(self):
        context=self.store.get_logic_context(['GT::TRIP_LATCH'])
        self.assertTrue(context.get('items'))
        self.assertTrue(any(r['logic_id']=='PROT-GT-LATCH' for r in context['items']))
        unknown=self.store.get_logic_context(['TRIP_LATCH'])
        self.assertNotEqual(unknown['status'],'VERIFIED')

    def test_raw_samples_have_dereferenceable_evidence_ids(self):
        out=self.store.get_tag_series('vppExternalTripCommandNative',48,49)
        self.assertTrue(out['points'])
        self.assertTrue(all(p.get('evidence_id') for p in out['points']))
        self.assertEqual(out['summary']['first'],0)
        self.assertEqual(out['summary']['last'],1)

    def test_nonfinite_model_time_is_rejected_before_agent(self):
        text=self.event.read_text(encoding='utf-8-sig').replace('48.44','NaN',1)
        self.event.write_text(text,encoding='utf-8')
        with self.assertRaises(ValueError): bridge.build_store(self.event,self.raw)

    def test_case_variant_answer_metadata_is_blocked(self):
        with self.raw.open(encoding='utf-8-sig',newline='') as f:
            r=csv.DictReader(f); fields=r.fieldnames+['Expected_Root_Cause']; rows=list(r)
        for row in rows: row['Expected_Root_Cause']='not-for-agent'
        write_csv(self.raw,fields,rows)
        with self.assertRaises(ValueError): bridge.build_store(self.event,self.raw)

    def test_output_aliases_are_normalized_not_blank(self):
        out=fail_closed_contract({'propagation':[{'description':'차단기 개방','evidence_id':'E-3','tag':'vpp52GTClosed','model_time_s':48.52}]})
        p=out['propagation'][0]
        self.assertEqual(p.get('claim'),'차단기 개방')
        self.assertEqual(p.get('evidence_ids'),['E-3'])
        self.assertEqual(p.get('model_time_s'),48.52)
        self.assertNotEqual(p.get('status'),'CONFIRMED')

    def test_hold_never_promotes_unverified_trigger(self):
        out=fail_closed_contract({'direct_trigger':{'status':'CONFIRMED','claim':'latch actuated','evidence_ids':['E-1'],'related_tags':['TRIP_LATCH'],'logic_master_status':'NOT_VERIFIED'}})
        self.assertEqual(out['verification_gate'],'HOLD')
        self.assertNotEqual(out['direct_trigger']['status'],'CONFIRMED')

    def test_legacy_string_rows_preserved_as_unverified_not_empty(self):
        out=fail_closed_contract({'propagation':['GT 출력 감소']})
        self.assertIsInstance(out['propagation'][0],dict)
        self.assertEqual(out['propagation'][0]['claim'],'GT 출력 감소')
        self.assertEqual(out['propagation'][0]['status'],'UNKNOWN')

    def test_iso_time_not_mislabeled_model_seconds(self):
        out=fail_closed_contract({'direct_trigger':{'claim':'latch','recorded_time':'2026-09-15T14:52:04.212+00:00','evidence_ids':['E-1']}})
        self.assertIsNone(out['direct_trigger'].get('model_time_s'))
        self.assertEqual(out['direct_trigger'].get('wall_time_utc'),'2026-09-15T14:52:04.212+00:00')

if __name__=='__main__': unittest.main()
