"""Unit tests for Gemini per-run token/cost telemetry. No live Gemini call."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE = Path(__file__).resolve().parents[1] / 'services' / 'agent-api'
sys.path.insert(0, str(SERVICE))
from gemini_agent import summarize_usage


class GeminiUsageCostTests(unittest.TestCase):
    def test_sums_multi_turn_usage_and_estimates_cost(self):
        usage = [
            {
                'total_input_tokens': 1000,
                'total_output_tokens': 200,
                'total_thought_tokens': 300,
                'total_cached_tokens': 0,
                'total_tool_use_tokens': 20,
                'total_tokens': 1520,
            },
            {
                'total_input_tokens': 500,
                'total_output_tokens': 100,
                'total_thought_tokens': 100,
                'total_cached_tokens': 0,
                'total_tool_use_tokens': 10,
                'total_tokens': 710,
            },
        ]
        with patch.dict(os.environ, {'TRIPLENS_COST_USD_KRW': '1400'}, clear=False):
            result = summarize_usage(usage, 'gemini-3.8-flash')
        self.assertEqual(result['request_count'], 2)
        self.assertEqual(result['total_input_tokens'], 1500)
        self.assertEqual(result['total_output_tokens'], 300)
        self.assertEqual(result['total_thought_tokens'], 400)
        self.assertEqual(result['billable_output_tokens'], 700)
        expected_usd = round((1500 * 0.75 + 700 * 3.75) / 1_000_000, 6)
        self.assertEqual(result['estimated_cost_usd'], expected_usd)
        self.assertEqual(result['estimated_cost_krw'], round(expected_usd * 1400, 1))

    def test_unknown_model_keeps_tokens_but_no_cost_without_override(self):
        with patch.dict(os.environ, {}, clear=True):
            result = summarize_usage([{'total_input_tokens': 123}], 'unknown-model')
        self.assertEqual(result['total_input_tokens'], 123)
        self.assertIsNone(result['estimated_cost_usd'])
        self.assertIsNone(result['estimated_cost_krw'])


if __name__ == '__main__':
    unittest.main()
