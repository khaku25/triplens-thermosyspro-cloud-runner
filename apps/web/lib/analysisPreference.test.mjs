import test from 'node:test';
import assert from 'node:assert/strict';
import {
  loadAnalysisProviderPreference,
  saveAnalysisProviderPreference,
} from './analysisPreference.mjs';

function createStorage(){
  const values=new Map();
  return {
    getItem(key){return values.has(key)?values.get(key):null;},
    setItem(key,value){values.set(key,String(value));},
  };
}

test('saved model preference survives a fresh workspace instance',()=>{
  const localStorage=createStorage();

  assert.equal(loadAnalysisProviderPreference(localStorage),null);
  assert.equal(saveAnalysisProviderPreference('openai',localStorage),true);
  assert.equal(loadAnalysisProviderPreference(localStorage),'openai');
});

test('unknown or unreadable saved preferences fall back safely',()=>{
  const localStorage=createStorage();
  localStorage.setItem('triplens.analysis-provider.v1','unknown-provider');
  assert.equal(loadAnalysisProviderPreference(localStorage),'gemini');

  const blockedStorage={getItem(){throw new Error('blocked');}};
  assert.equal(loadAnalysisProviderPreference(blockedStorage),null);
});

test('preference writes report storage failure without throwing',()=>{
  const blockedStorage={setItem(){throw new Error('quota exceeded');}};
  assert.equal(saveAnalysisProviderPreference('openai',blockedStorage),false);
});
