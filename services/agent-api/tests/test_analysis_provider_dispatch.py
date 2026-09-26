"""Tests for selected analysis-provider routing and server-side key readiness."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVICE))
import analysis_providers


class AnalysisProviderTests(unittest.TestCase):
    @patch.dict(os.environ,{'GEMINI_API_KEY':'gem-test','OPENAI_API_KEY':'openai-test'},clear=True)
    def test_catalog_lists_both_models_and_reports_only_key_readiness(self):
        options=analysis_providers.available_analysis_providers()
        self.assertEqual(options,[
            {'id':'gemini','label':'Gemini Flash','model':'gemini-3.8-flash','available':True},
            {'id':'openai','label':'GPT-5.6 Luna','model':'gpt-5.6-luna','available':True},
        ])
        self.assertNotIn('api_key',str(options).lower())

    @patch.dict(os.environ,{'OPENAI_API_KEY':'openai-test','TRIPLENS_OPENAI_MODEL':'gpt-6-luna-canary'},clear=True)
    def test_selected_openai_provider_calls_luna_runner_with_server_configured_model(self):
        store=object()
        with patch.object(analysis_providers,'run_openai_analysis',return_value={'agent_execution':{'provider':'openai'}}) as runner:
            result=analysis_providers.run_selected_analysis('openai',store,run_id='RUN-1',data_digest='DIGEST')
        self.assertEqual(result['agent_execution']['provider'],'openai')
        runner.assert_called_once_with(store,run_id='RUN-1',data_digest='DIGEST',model='gpt-6-luna-canary')

    def test_unknown_provider_is_rejected_before_any_model_call(self):
        with patch.object(analysis_providers,'run_openai_analysis') as runner:
            with self.assertRaises(analysis_providers.UnknownAnalysisProvider):
                analysis_providers.run_selected_analysis('arbitrary-model',object(),run_id='R',data_digest='D')
        runner.assert_not_called()

    @patch.dict(os.environ,{},clear=True)
    def test_openai_provider_requires_a_server_side_api_key(self):
        with self.assertRaises(analysis_providers.AnalysisProviderNotConfigured):
            analysis_providers.run_selected_analysis('openai',object(),run_id='R',data_digest='D')


if __name__=='__main__':
    unittest.main()
