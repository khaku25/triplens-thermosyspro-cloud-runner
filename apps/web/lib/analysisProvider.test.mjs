import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_ANALYSIS_PROVIDER,
  analysisProviderChoices,
  analysisProviderLabel,
  appendAnalysisProvider,
  normalizeAnalysisProvider,
} from './analysisProvider.mjs';

test('provider selection defaults safely and rejects unknown values',()=>{
  assert.equal(DEFAULT_ANALYSIS_PROVIDER,'gemini');
  assert.equal(normalizeAnalysisProvider('openai'),'openai');
  assert.equal(normalizeAnalysisProvider('unlisted'),'gemini');
});

test('model choices reflect server key availability without exposing secrets',()=>{
  const choices=analysisProviderChoices({analysis_models:[
    {id:'gemini',label:'Gemini Flash',model:'gemini-3.8-flash',available:true},
    {id:'openai',label:'GPT-5.6 Luna',model:'gpt-5.6-luna',available:false},
  ]});

  assert.deepEqual(choices.map(({id,label,disabled,displayLabel})=>({id,label,disabled,displayLabel})),[
    {id:'gemini',label:'Gemini Flash',disabled:false,displayLabel:'Gemini Flash'},
    {id:'openai',label:'GPT-5.6 Luna',disabled:true,displayLabel:'GPT-5.6 Luna · API 키 설정 필요'},
  ]);
  assert.equal(analysisProviderLabel('openai',{analysis_models:[{id:'openai',label:'GPT-5.6 Luna',model:'gpt-5.6-luna',available:true}]}),'GPT-5.6 Luna');
});

test('older API contracts keep Gemini usable while Luna stays unavailable',()=>{
  const choices=analysisProviderChoices({model:'gemini-3.8-flash'});
  assert.equal(choices[0].available,true);
  assert.equal(choices[1].label,'GPT-5.6 Luna');
  assert.equal(choices[1].model,'gpt-5.6-luna');
  assert.equal(choices[1].disabled,true);
});

test('analysis multipart request carries the selected provider',()=>{
  const form=new FormData();
  form.append('event','event-file');
  appendAnalysisProvider(form,'openai');

  assert.equal(form.get('event'),'event-file');
  assert.equal(form.get('provider'),'openai');
});
