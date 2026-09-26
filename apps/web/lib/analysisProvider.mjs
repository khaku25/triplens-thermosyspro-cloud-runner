export const DEFAULT_ANALYSIS_PROVIDER='gemini';

const FALLBACK_PROVIDERS=[
  {id:'gemini',label:'Gemini Flash',model:'gemini-3.8-flash'},
  {id:'openai',label:'GPT-5.6 Luna',model:'gpt-5.6-luna'},
];

export function normalizeAnalysisProvider(value){
  return value==='openai'?'openai':'gemini';
}

export function analysisProviderChoices(contract){
  const configured=Array.isArray(contract?.analysis_models)?contract.analysis_models:[];
  const hasAvailability=Array.isArray(contract?.analysis_models);
  return FALLBACK_PROVIDERS.map(fallback=>{
    const server=configured.find(option=>option?.id===fallback.id);
    const available=hasAvailability?Boolean(server?.available):Boolean(contract)&&fallback.id==='gemini';
    const suffix=contract?'API 키 설정 필요':'설정 확인 중';
    return {
      ...fallback,
      label:server?.label||fallback.label,
      model:server?.model||fallback.model,
      available,
      disabled:!available,
      displayLabel:available?(server?.label||fallback.label):`${server?.label||fallback.label} · ${suffix}`,
    };
  });
}

export function analysisProviderLabel(provider,contract){
  const id=normalizeAnalysisProvider(provider);
  return analysisProviderChoices(contract).find(option=>option.id===id)?.label||id;
}

export function appendAnalysisProvider(form,provider){
  form.set('provider',normalizeAnalysisProvider(provider));
  return form;
}
