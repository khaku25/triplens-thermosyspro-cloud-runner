import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class STBreakerOpenMasterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.logic_assets.pipeline import load_authoring
        cls.repo = load_authoring(
            ROOT / 'data/current_v8/masters',
            ROOT / 'data/current_v8/live_opcua_census.csv',
        )

    def test_historical_runtime_uses_hierarchical_st_request_without_cause_count(self):
        rules = {row['rule_id']: row for row in self.repo['model']['rules']}
        rule = rules['PROT-ST-REQUEST']
        self.assertEqual(rule['logic_name'], 'ST trip request')
        self.assertEqual(
            rule['inputs'],
            [
                'vppGTTripRequest',
                'vppCauseDirectSTTrip',
                'vppCauseHPDrumHH',
                'vppCauseIPDrumHH',
                'vppCauseLPDrumHH',
            ],
        )
        self.assertNotIn('9', rule['condition'])
        self.assertNotIn('9-cause', rule['source_basis'])

    def test_current_search_master_adds_verified_52st_breaker_open_cause(self):
        search = self.repo['search_model']
        rules = {row['rule_id']: row for row in search['rules']}
        self.assertIn('vppCauseSTBreakerOpenWhileRunning', search['tags'])
        tag = search['tags']['vppCauseSTBreakerOpenWhileRunning']
        self.assertTrue(tag['model_source_only'])
        self.assertEqual(tag['runtime_inclusion'], 'SEARCH_ONLY')
        self.assertEqual(tag['open_behavior_test_status'], 'RUNTIME_VERIFIED')
        self.assertEqual(tag['live_node_id'], '')

        cause = rules['PROT-ST-BRK-OPEN']
        self.assertEqual(cause['inputs'], ['vppECMS52STClosedCommandNative'])
        self.assertEqual(cause['outputs'], ['vppCauseSTBreakerOpenWhileRunning'])
        self.assertEqual(cause['validation_status'], 'PASS')

        request = rules['PROT-ST-REQUEST']
        self.assertEqual(
            request['inputs'],
            [
                'vppGTTripRequest',
                'vppCauseDirectSTTrip',
                'vppCauseSTBreakerOpenWhileRunning',
                'vppCauseHPDrumHH',
                'vppCauseIPDrumHH',
                'vppCauseLPDrumHH',
            ],
        )
        self.assertNotIn('9', request['condition'])
        self.assertNotIn('9-cause', request['source_basis'])

    def test_trip_actuation_keeps_only_hp_and_lp_bypass(self):
        rules = {row['rule_id']: row for row in self.repo['search_model']['rules']}
        rule = rules['RESP-ST-TRIP-ACTUATION']
        self.assertIn('vppHPBypassCmd', rule['outputs'])
        self.assertIn('vppLPBypassCmd', rule['outputs'])
        self.assertIn('vppSTGridPowerMW', rule['outputs'])
        self.assertFalse(any('IPBypass' in tag for tag in rule['outputs']))
        self.assertEqual(rule['validation_status'], 'PASS')

    def test_st_grid_power_open_behavior_is_runtime_verified(self):
        rules = {row['rule_id']: row for row in self.repo['search_model']['rules']}
        rule = rules['RESP-ST-GRID-POWER']
        self.assertEqual(rule['open_behavior_test_status'], 'RUNTIME_VERIFIED')
        self.assertEqual(rule['validation_status'], 'PASS')
        self.assertEqual(rule['raw_closed_samples'], '282')
        self.assertEqual(rule['raw_open_samples'], '0')
        self.assertIn('Historical', rule['notes'])


if __name__ == '__main__':
    unittest.main()
