"""Provider errors expose safe diagnostics and a log correlation ID."""
import io
import json
import logging
import sys
import unittest
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

SERVICE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVICE))
try:
    from analysis_trace import build_provider_failure_detail,log_provider_failure
except ImportError:
    build_provider_failure_detail=None
    log_provider_failure=None


class AnalysisTraceTests(unittest.TestCase):
    def test_upstream_error_is_correlated_and_only_safe_fields_are_logged(self):
        self.assertIsNotNone(build_provider_failure_detail,'provider trace builder is missing')
        self.assertIsNotNone(log_provider_failure,'provider trace logger is missing')
        headers=Message()
        headers['x-request-id']='req-openai-123'
        body=json.dumps({'error':{
            'type':'invalid_request_error',
            'code':'model_not_found',
            'message':'private upstream detail must not be returned',
        }}).encode()
        error=HTTPError('https://api.openai.com/v1/responses',404,'Not Found',headers,io.BytesIO(body))

        detail=build_provider_failure_detail('openai','GPT-6 Luna',error,trace_id='TL-ABCDEF123456')
        logger=logging.getLogger('test.triplens.analysis')
        with self.assertLogs(logger,level='ERROR') as captured:
            log_provider_failure(logger,detail)

        self.assertEqual(detail['stage'],'openai_agent')
        self.assertEqual(detail['upstream_status'],404)
        self.assertEqual(detail['upstream_error_code'],'model_not_found')
        self.assertEqual(detail['upstream_request_id'],'req-openai-123')
        self.assertEqual(detail['trace_id'],'TL-ABCDEF123456')
        self.assertIn('TL-ABCDEF123456',detail['message'])
        self.assertIn('model_not_found',detail['message'])
        self.assertIn('TL-ABCDEF123456',captured.output[0])
        self.assertNotIn('private upstream detail',str(detail))
        self.assertNotIn('private upstream detail',captured.output[0])


if __name__=='__main__':
    unittest.main()
