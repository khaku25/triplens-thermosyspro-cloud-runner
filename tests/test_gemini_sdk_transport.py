"""Check the installed Google SDK request path without network or real keys.

This is adapter compatibility validation, NOT a Google Gemini live model run.
"""
import json
import sys
import unittest
from pathlib import Path

import httpx
from google import genai

SERVICE = Path(__file__).resolve().parents[1] / 'services' / 'agent-api'
sys.path.insert(0, str(SERVICE))
from gemini_agent import TOOL_DECLARATIONS
from triplens.analysis_contract import ANALYSIS_SCHEMA


class RequestCaptured(Exception):
    pass


class SDKTransportTests(unittest.TestCase):
    def test_actual_sdk_serializes_interactions_schema_and_tools_offline(self):
        captured = []

        def intercept(request):
            captured.append(json.loads(request.content))
            raise RequestCaptured('network disabled by test transport')

        client = genai.Client(
            api_key='invalid-test-key-never-sent-to-network',
            http_options={'client_args': {'transport': httpx.MockTransport(intercept)}},
        )
        try:
            with self.assertRaises(RequestCaptured):
                client.interactions.create(
                    model='gemini-3.8-flash',
                    store=False,
                    input=[{'type': 'user_input', 'content': [{'type': 'text', 'text': 'Offline request-shape test only'}]}],
                    tools=TOOL_DECLARATIONS,
                    system_instruction='Return Korean structured evidence claims only.',
                    response_format={'type': 'text', 'mime_type': 'application/json', 'schema': ANALYSIS_SCHEMA},
                )
        finally:
            client.close()
        self.assertEqual(len(captured), 1)
        body = captured[0]
        self.assertEqual(body['response_format']['mime_type'], 'application/json')
        self.assertEqual(body['response_format']['schema'], ANALYSIS_SCHEMA)
        self.assertEqual(len(body['tools']), 6)
        self.assertFalse(body['store'])
        print('SDK_TRANSPORT_PASS: real SDK serialization, intercepted before network; no live Gemini call')


if __name__ == '__main__':
    unittest.main()
