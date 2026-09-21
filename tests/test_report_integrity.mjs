import test from 'node:test';
import assert from 'node:assert/strict';
import {
  eventIdentity,
  preferredSourceTag,
  mergeEvents,
  mergeEvidenceCatalog,
  validateReportReferences,
} from '../apps/web/lib/reportIntegrity.mjs';
import {buildDraftRows} from '../apps/web/lib/analysisClient.mjs';

const uploaded=Array.from({length:21},(_,i)=>({
  event_id:`E${i+1}`,
  evidence_id:`E${i+1}`,
  model_time_s:i<2?48.44:48.44+i,
  tag:i===0?'TRIP_LATCH':`EVENT_${i+1}`,
  message:`Uploaded event ${i+1}`,
}));
const enriched=uploaded.map((event,i)=>({
  ...event,
  source_node:i===0?'vppGTTripLatch':`vppEvent${i+1}`,
  canonical_tag:i===0?'vppGTTripLatch':`vppEvent${i+1}`,
  mapping_status:'VERIFIED',
  message:`Enriched event ${i+1}`,
})).reverse();
const retrieved=enriched.slice().reverse().slice(0,14).map((event,i)=>({
  ...event,
  source_kind:'EVENT',
  display_name:`Retrieved event ${i+1}`,
}));

test('complete immutable EVENT merge prevents asymmetric catalog references from dangling',()=>{
  const uploadedBefore=structuredClone(uploaded);
  const enrichedBefore=structuredClone(enriched);
  const retrievedBefore=structuredClone(retrieved);

  const events=mergeEvents(uploaded,enriched);
  const catalog=mergeEvidenceCatalog(events,retrieved);

  assert.equal(eventIdentity(events[0]),'E1');
  assert.equal(preferredSourceTag(events[0]),'vppGTTripLatch');
  assert.equal(events[0].source_node,'vppGTTripLatch');
  assert.equal(uploaded[0].source_node,undefined);
  assert.deepEqual(events.slice(0,2).map(event=>event.event_id),['E1','E2']);
  assert.equal(catalog.filter(x=>x.source_kind==='EVENT').length,21);
  assert.equal(catalog.find(x=>x.evidence_id==='E1').display_name,'Retrieved event 1');
  const withRaw=mergeEvidenceCatalog(events,[...retrieved,{evidence_id:'RAW:1:vppSignal',source_kind:'RAW',value:1}]);
  assert.equal(withRaw.find(x=>x.evidence_id==='RAW:1:vppSignal')?.value,1);
  assert.deepEqual(uploaded,uploadedBefore);
  assert.deepEqual(enriched,enrichedBefore);
  assert.deepEqual(retrieved,retrievedBefore);

  const rows=buildDraftRows({events,evidence_catalog:catalog,analysis:{}});
  assert.deepEqual(validateReportReferences(rows),{valid:true,missing:[]});
  for(const id of ['E15','E16','E17','E18','E19','E20','E21'])
    assert.ok(rows.some(r=>r.section==='증거자료'&&r.evidence_ids===id),id);

  const edited=rows.map((row,i)=>i===0?{...row,evidence_ids:'E1; MISSING-EVIDENCE'}:row);
  assert.deepEqual(validateReportReferences(edited),{valid:false,missing:['MISSING-EVIDENCE']});
});

test('preferred source tag falls back through canonical and original tag fields',()=>{
  assert.equal(preferredSourceTag({canonical_tag:'vppCanonical',tag:'GENERIC'}),'vppCanonical');
  assert.equal(preferredSourceTag({tag:'GENERIC'}),'GENERIC');
  assert.equal(eventIdentity({event_id:'E-only'}),'E-only');
});

test('merged events keep missing Model Time after timestamped events',()=>{
  const events=mergeEvents([
    {event_id:'UNKNOWN',model_time_s:null},
    {event_id:'KNOWN',model_time_s:48.44},
    {event_id:'BLANK',model_time_s:''},
  ],[]);
  assert.deepEqual(events.map(event=>event.event_id),['KNOWN','UNKNOWN','BLANK']);
});

test('real report builder unions a partial retrieved catalog with every EVENT',()=>{
  const events=mergeEvents(uploaded,enriched);
  const rows=buildDraftRows({events,evidence_catalog:retrieved,analysis:{}});
  const eventEvidence=rows.filter(row=>row.section==='증거자료'&&row.note==='EVENT');

  assert.equal(eventEvidence.length,21);
  assert.deepEqual(validateReportReferences(rows),{valid:true,missing:[]});
  for(const id of ['E15','E16','E17','E18','E19','E20','E21'])
    assert.ok(eventEvidence.some(row=>row.evidence_ids===id),id);
});
