import csv
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from triplens_agent_tools import EvidenceStore, AgentToolSession, DEFAULT_LIMITS, load_logic_rows  # noqa: E402

EVENT_FIELDS = [
    'event_id','event_sequence','session_id','incident_id','model_time_s','wall_time_utc',
    'priority','event_class','equipment','tag','state','value','unit','message','source','acknowledged'
]
RAW_FIELDS = ['record_sequence','session_id','incident_id','model_time_s','wall_time_utc','quality','TAG_A','TAG_B']


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


class AgentToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        event_rows = []
        for i in range(40):
            event_rows.append({
                'event_id': f'EV-{i:03d}', 'event_sequence': i+1, 'session_id':'S1', 'incident_id':'I1',
                'model_time_s': f'{i * 0.5:.3f}', 'wall_time_utc':'2026-09-18T00:00:00.000+00:00',
                'priority':'HIGH' if i % 5 == 0 else 'MEDIUM',
                'event_class':'PROTECTION' if i % 3 == 0 else 'ALARM',
                'equipment':'LP BFP' if i < 25 else 'ST',
                'tag':'SPEED_PROVEN_LOST' if i == 10 else f'TAG_{i}',
                'state':'ACTIVE','value':1,'unit':'BOOL','message':f'event message {i}','source':'SIM','acknowledged':False,
            })
        raw_rows = []
        for i in range(200):
            raw_rows.append({
                'record_sequence':i+1,'session_id':'S1','incident_id':'I1','model_time_s':f'{i*0.1:.3f}',
                'wall_time_utc':'2026-09-18T00:00:00.000+00:00','quality':'GOOD',
                'TAG_A':100-i*0.25,'TAG_B':i,
            })
        self.event = self.dir/'EVENT.csv'; self.raw = self.dir/'RAW.csv'
        write_csv(self.event, EVENT_FIELDS, event_rows); write_csv(self.raw, RAW_FIELDS, raw_rows)
        logic = [
            {'logic_id':'L-001','tag_id':'TAG_A','equipment':'LP BFP','condition':'TAG_A < 80','status':'ACTIVE'},
            {'logic_id':'L-002','tag_id':'SPEED_PROVEN_LOST','equipment':'LP BFP','condition':'SPEED_PROVEN == 0','status':'ACTIVE'},
        ]
        self.store = EvidenceStore(self.event, self.raw, logic_rows=logic)

    def tearDown(self):
        self.tmp.cleanup()

    def test_search_events_is_bounded_and_evidence_linked(self):
        rows = self.store.search_events('event', limit=999)
        self.assertEqual(len(rows), DEFAULT_LIMITS['search_events'])
        self.assertTrue(all(r['evidence_id'].startswith('EV-') for r in rows))
        self.assertNotIn('root_cause', rows[0])

    def test_event_window_is_bounded_and_chronological(self):
        rows = self.store.get_event_window(10.0, before_s=10, after_s=10, limit=999)
        self.assertLessEqual(len(rows), DEFAULT_LIMITS['event_window'])
        times = [r['model_time_s'] for r in rows]
        self.assertEqual(times, sorted(times))

    def test_tag_series_downsamples_and_returns_summary(self):
        out = self.store.get_tag_series('TAG_A', 0, 20, max_points=999)
        self.assertLessEqual(len(out['points']), DEFAULT_LIMITS['tag_series_points'])
        self.assertAlmostEqual(out['summary']['first'], 100.0)
        self.assertLess(out['summary']['last'], out['summary']['first'])
        self.assertLess(out['summary']['delta'], 0)

    def test_logic_rows_can_load_from_trip_lens_sqlite(self):
        import sqlite3
        db_path = self.dir/'logic.sqlite'
        db = sqlite3.connect(db_path)
        db.executescript('''
        CREATE TABLE logic_rule(logic_id TEXT PRIMARY KEY,equipment TEXT,alarm_text_ko TEXT,enabled_default INTEGER);
        CREATE TABLE logic_tag_link(logic_id TEXT,tag_id TEXT);
        INSERT INTO logic_rule VALUES('L-DB','LP BFP','Speed lost',1);
        INSERT INTO logic_tag_link VALUES('L-DB','TAG_A');
        ''')
        db.commit(); db.close()
        rows = load_logic_rows(db_path)
        self.assertEqual(rows[0]['logic_id'],'L-DB')
        self.assertEqual(rows[0]['linked_tag_ids'],'TAG_A')

    def test_logic_context_is_exact_and_fail_closed(self):
        known = self.store.get_logic_context(['TAG_A'])
        self.assertEqual(known['items'][0]['logic_id'], 'L-001')
        unknown = self.store.get_logic_context(['NOT_REGISTERED'])
        self.assertEqual(unknown['unregistered_tags'], ['NOT_REGISTERED'])
        self.assertFalse(unknown['infer_unregistered_logic'])

    def test_equipment_state_does_not_infer_raw_tags(self):
        no_tags = self.store.get_equipment_state('LP BFP', 5.0)
        self.assertEqual(no_tags['raw_values'], {})
        with_tags = self.store.get_equipment_state('LP BFP', 5.0, tags=['TAG_A'])
        self.assertIn('TAG_A', with_tags['raw_values'])

    def test_tool_call_budget_stops_after_eight_calls(self):
        session = AgentToolSession(self.store)
        for _ in range(8):
            session.call('search_events', {'query':'event','limit':1})
        with self.assertRaises(RuntimeError):
            session.call('search_events', {'query':'event','limit':1})

    def test_bootstrap_is_small_and_does_not_embed_bulk_event_or_raw_rows(self):
        boot = self.store.build_agent_bootstrap(run_id='RUN-1', data_digest='abc')
        self.assertEqual(boot['run_id'],'RUN-1')
        self.assertEqual(boot['data_digest'],'abc')
        self.assertEqual(boot['event_row_count'],40)
        self.assertEqual(boot['raw_row_count'],200)
        self.assertNotIn('event_rows',boot)
        self.assertNotIn('raw_rows',boot)
        self.assertIn('tool_manifest',boot)

    def test_tool_manifest_enforces_token_budget_guards(self):
        manifest = self.store.tool_manifest()
        self.assertEqual(manifest['max_tool_calls_per_analysis'], 8)
        names = [t['name'] for t in manifest['tools']]
        self.assertEqual(names, [
            'search_events','get_event_window','get_raw_window','get_tag_series','get_logic_context','get_equipment_state'
        ])
        self.assertEqual(manifest['response_limits']['search_events'], 20)
        self.assertEqual(manifest['response_limits']['tag_series_points'], 50)


if __name__ == '__main__':
    unittest.main()
