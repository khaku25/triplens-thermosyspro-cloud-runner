import {DEFAULT_ANALYSIS_PROVIDER,normalizeAnalysisProvider} from './analysisProvider.mjs';

export const ANALYSIS_PROVIDER_PREFERENCE_KEY='triplens.analysis-provider.v1';

function resolveStorage(storage){
  if(storage!==undefined)return storage;
  if(typeof window==='undefined')return null;
  return window.localStorage;
}

export function loadAnalysisProviderPreference(storage){
  try{
    const value=resolveStorage(storage)?.getItem(ANALYSIS_PROVIDER_PREFERENCE_KEY);
    if(value===null||value===undefined||value==='')return null;
    return normalizeAnalysisProvider(value);
  }catch{
    return null;
  }
}

export function saveAnalysisProviderPreference(provider,storage){
  try{
    const target=resolveStorage(storage);
    if(!target)return false;
    target.setItem(ANALYSIS_PROVIDER_PREFERENCE_KEY,normalizeAnalysisProvider(provider));
    return true;
  }catch{
    return false;
  }
}
