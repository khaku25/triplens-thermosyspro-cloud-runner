"""Offline transport regressions: summary repair must not become a second diagnosis."""
import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gemini_agent import run_gemini_analysis
from openai_agent import run_openai_analysis
from triplens.analysis_contract import normalize_analysis
from test_concise_report import claim, LONG, SHORT


class Store:
    def evidence_catalog(self):
        return [{'evidence_id': eid, 'tag': 'vppLPDrumInventoryDisturbanceMassFlowTH',
                 'source_node': 'vppLPDrumInventoryDisturbanceMassFlowTH', 'source_kind': 'RAW',
                 'model_time_s': when, 'value': value, 'logic_ids': ['L1']}
                for eid, when, value in zip(claim()['evidence_ids'], [47.6, 48.72], [0, -576])]
    def logic_matches(self, tags): return [{'logic_id': 'L1'}]
    def build_agent_bootstrap(self, **kwargs): return {'events': []}


class Client:
    def __init__(self, provider, outputs):
        self.provider = provider
        self.outputs = iter(outputs)
        self.requests = []
        self.responses = self.interactions = self
    def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        result = next(self.outputs)
        if isinstance(result, Exception): raise result
        tools = result == 'TOOL_CALL'
        text = json.dumps({} if tools else result, ensure_ascii=False)
        if self.provider == 'gemini':
            steps = [SimpleNamespace(type='function_call')] if tools else []
            return SimpleNamespace(steps=steps, output_text=text, usage={'total_tokens': 7})
        return {'output': [{'type': 'function_call'}] if tools else [], 'output_text': text,
                'usage': {'total_tokens': 7}}


class ConciseProviderRepairTests(unittest.TestCase):
    def run_provider(self, provider, revision, source=None):
        raw = source or {'primary_cause': claim(report_summary=LONG)}
        client = Client(provider, [raw, revision])
        fn = run_gemini_analysis if provider == 'gemini' else run_openai_analysis
        with patch(f'{provider}_agent.AgentToolSession', return_value=SimpleNamespace(calls_used=8, max_calls=8)):
            result = fn(Store(), run_id='OFFLINE-REPORT-TEST', data_digest='fixture', client=client)
        return raw, client, result

    def test_both_providers_repair_only_summary_once_without_tools(self):
        for provider in ('gemini', 'openai'):
            with self.subTest(provider=provider):
                revision = {'summaries': [{'path': 'primary_cause', 'report_summary': SHORT}]}
                raw, client, result = self.run_provider(provider, revision)
                self.assertEqual(len(client.requests), 2)
                request = client.requests[-1]
                self.assertNotIn('tools', request)
                schema = request['response_format']['schema'] if provider == 'gemini' else request['text']['format']['schema']
                self.assertEqual(set(schema['properties']), {'summaries'})
                self.assertEqual(result['primary_cause']['report_summary'], SHORT)
                before = normalize_analysis(raw, Store(), [])['primary_cause']
                for key in ('claim', 'status', 'evidence_ids', 'related_tags', 'model_time_s', 'time_interval_s', 'ai_confidence'):
                    self.assertEqual(result['primary_cause'][key], before[key], key)
                self.assertEqual(raw['primary_cause']['report_summary'], LONG)
                self.assertEqual(result['agent_execution']['model_turns'], 2)
                self.assertEqual(result['agent_execution']['tool_calls_used'], 8)
                self.assertEqual(len(result['agent_execution']['usage']), 2)
                self.assertEqual(result.get('report_presentation', {}).get('status'), 'MODEL_REVISED')

    def test_failed_or_unsafe_repair_retains_original_without_retry_loop(self):
        unsafe = {'summaries': [{'path': 'primary_cause', 'report_summary': SHORT, 'status': 'CONFIRMED'}]}
        for provider in ('gemini', 'openai'):
            for revision in (unsafe, 'TOOL_CALL', TimeoutError('offline fake timeout')):
                with self.subTest(provider=provider, revision=str(revision)):
                    raw, client, result = self.run_provider(provider, revision)
                    self.assertEqual(len(client.requests), 2)
                    self.assertEqual(result['primary_cause']['claim'], LONG)
                    self.assertIsNone(result['primary_cause']['report_summary'])
                    self.assertEqual(result.get('report_presentation', {}).get('status'), 'FAILED_RETAINED_DETAIL')
                    self.assertEqual(result['agent_execution']['model_turns'], 2)

    def test_valid_summary_does_not_add_a_provider_call(self):
        for provider in ('gemini', 'openai'):
            with self.subTest(provider=provider):
                _, client, result = self.run_provider(provider, {}, source={'primary_cause': claim()})
                self.assertEqual(len(client.requests), 1)
                self.assertEqual(result['primary_cause']['report_summary'], SHORT)
                self.assertEqual(result.get('report_presentation', {}).get('attempts'), 0)

    def test_summary_repair_respects_existing_deadline(self):
        for provider in ('gemini', 'openai'):
            with self.subTest(provider=provider):
                # Start, loop check, presentation deadline check, final duration.
                with patch(f'{provider}_agent.time.monotonic', side_effect=[0, 1, 166, 167]):
                    _, client, result = self.run_provider(provider, {})
                self.assertEqual(len(client.requests), 1)
                self.assertEqual(result.get('report_presentation', {}).get('status'), 'SKIPPED_DEADLINE')
                self.assertEqual(result['primary_cause']['claim'], LONG)


if __name__ == '__main__': unittest.main()
