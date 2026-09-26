# ---------------------------------------------------------------------------
# CODE READING GUIDE
# File role: allowlist and server-side readiness checks for analysis providers.
# Read in this order: provider configuration -> availability -> selected runner.
# It routes the agent only; evidence validation remains in the shared analysis contract.
# ---------------------------------------------------------------------------
"""Allowlisted model selection for the TripLens incident-analysis agent."""
from __future__ import annotations

import os

from gemini_agent import DEFAULT_MODEL as DEFAULT_GEMINI_MODEL, run_gemini_analysis
from openai_agent import DEFAULT_MODEL as DEFAULT_OPENAI_MODEL, run_openai_analysis

DEFAULT_ANALYSIS_PROVIDER='gemini'
OPENAI_MODEL_LABELS={
    'gpt-5.6-luna':'GPT-5.6 Luna',
    'gpt-6-luna':'GPT-6 Luna',
}


class UnknownAnalysisProvider(ValueError):
    """The request asked for a model provider not offered by this service."""


class AnalysisProviderNotConfigured(RuntimeError):
    """A selected provider has no server-side API key configured."""


def provider_configuration(provider=DEFAULT_ANALYSIS_PROVIDER):
    selected=str(provider or DEFAULT_ANALYSIS_PROVIDER).strip().lower()
    if selected=='gemini':
        return {
            'id':'gemini',
            'label':'Gemini Flash',
            'model':os.getenv('TRIPLENS_GEMINI_MODEL',DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL,
            'available':bool(os.getenv('GEMINI_API_KEY','').strip()),
        }
    if selected=='openai':
        model=os.getenv('TRIPLENS_OPENAI_MODEL',DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
        return {
            'id':'openai',
            'label':OPENAI_MODEL_LABELS.get(model,model),
            'model':model,
            'available':bool(os.getenv('OPENAI_API_KEY','').strip()),
        }
    raise UnknownAnalysisProvider('지원하지 않는 분석 모델입니다.')


def available_analysis_providers():
    return [provider_configuration('gemini'),provider_configuration('openai')]


def run_selected_analysis(provider,store,**kwargs):
    configuration=provider_configuration(provider)
    if not configuration['available']:
        variable='OPENAI_API_KEY' if configuration['id']=='openai' else 'GEMINI_API_KEY'
        raise AnalysisProviderNotConfigured(f'{variable} is not configured')
    runner=run_openai_analysis if configuration['id']=='openai' else run_gemini_analysis
    return runner(store,model=configuration['model'],**kwargs)
