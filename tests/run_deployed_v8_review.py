"""Deployed Gemini regression, NOT a blind-generalization benchmark.
Only original EVENT/RAW bytes are posted for archive cases. Scenario paths and
expectations stay in this test runner and are never sent to the analysis API.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
SERVICE=ROOT/'services'/'agent-api'
sys.path[:0]=[str(SERVICE),str(SERVICE/'tests')]
import bridge
from test_live_integration import make_fixture,write_csv,RAW_META

API='https://triplens-agent-api-preview.vercel.app'
OUT=ROOT/'outputs'/'deployed-v8-review'

def check_result(data,expected_cause,expected_trigger):
    a=data['analysis'];catalog={r['evidence_id']:r for r in data.get('evidence_catalog',[])}
    assert a.get('output_contract_version')=='GROUNDED_ANALYSIS_V3'
    assert not a['finality']['can_mark_final_confirmed']
    assert a['agent_execution']['tool_calls_used']<=8
    assert any(t.get('raw_evidence_count',0)>0 for t in a['tool_trace'])
    assert any(t['name']=='get_logic_context' and t['status']=='OK' for t in a['tool_trace'])
    for key in ('primary_cause','direct_trigger','critical_events','propagation','causal_chain','counter_evidence'):
        items=a[key] if isinstance(a[key],list) else [a[key]]
        for item in items:
            assert isinstance(item,dict) and item['claim'].strip(),(key,item)
            assert re.search('[가-힣]',item['claim']),(key,'Korean output required',item)
            assert item['status'] in {'CANDIDATE','OBSERVED','UNKNOWN'},(key,item)
            assert all(e in catalog for e in item['evidence_ids']),(key,'unlinked evidence')
            if item['status']!='UNKNOWN':assert item['evidence_ids'],(key,'missing evidence')
            assert '86GT' not in item['claim'] and not any('86GT' in t for t in item['related_tags'])
    if expected_cause is None:
        assert a['primary_cause']['status']=='UNKNOWN',a['primary_cause']
    else:
        assert a['primary_cause']['status']=='CANDIDATE',a['primary_cause']
        assert set(a['primary_cause']['related_tags'])&set(expected_cause),a['primary_cause']
    assert set(a['direct_trigger']['related_tags'])&set(expected_trigger),a['direct_trigger']
    assert a['propagation'],'Propagation must be populated, not only an essay'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path,required=True);args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    expected_contract=bridge.public_contract()
    for attempt in range(60):
        try:
            c=requests.get(API+'/contract',timeout=15).json()
            if c.get('integration_version')=='V8_EVIDENCE_INTEGRATION_V3' and c.get('prompt_version')==expected_contract['prompt_version']:break
        except (requests.RequestException,ValueError):pass
        time.sleep(5)
    else:raise RuntimeError('Expected Vercel revision did not become ready; no paid analyze call was made')
    archive=zipfile.ZipFile(args.archive)
    cases=[]
    for index,(folder,cause,trigger) in enumerate([
        ('direct_gt',['vppExternalTripCommandNative','vppCauseDirectGTTrip'],['vppGTTripLatch']),
        ('direct_st',['vppExternalSTTripCommandNative','vppCauseDirectSTTrip'],['vppSTTripLatchPublished'])
    ]):
        path=OUT/f'case-{index}';path.mkdir(exist_ok=True)
        for name in ['EVENT.csv','RAW.csv']: (path/name).write_bytes(archive.read('outputs/all-trip-matrix/'+folder+'/'+name))
        cases.append((path,cause,trigger,'ARCHIVED_ORIGINAL_V8'))
    missing=OUT/'case-2';missing.mkdir(exist_ok=True)
    ep,rp=make_fixture(missing)
    with rp.open(encoding='utf-8-sig',newline='') as f:r=csv.DictReader(f);rows=list(r)
    # Degraded synthetic control deliberately lacks every initiating input.
    fields=RAW_META+['vppGTTripLatch','vppSTTripLatchPublished','vpp52GTClosed','vpp52STClosed']
    write_csv(rp,fields,[{k:row.get(k,'') for k in fields} for row in rows])
    cases.append((missing,None,['vppGTTripLatch','vppSTTripLatchPublished'],'SYNTHETIC_MISSING_CAUSE_CONTROL'))
    summaries=[];failed=False
    for path,cause,trigger,basis in cases:
        eb=(path/'EVENT.csv').read_bytes();rb=(path/'RAW.csv').read_bytes()
        started=time.monotonic()
        try:
            response=requests.post(API+'/analyze',files={'event':('EVENT.csv',eb,'text/csv'),'raw':('RAW.csv',rb,'text/csv')},timeout=240)
            (path/'response.txt').write_text(response.text,encoding='utf-8')
            response.raise_for_status();data=response.json()
            assert data['event_digest']==hashlib.sha256(eb).hexdigest()
            assert data['raw_digest']==hashlib.sha256(rb).hexdigest()
            check_result(data,cause,trigger)
            summary={'case':path.name,'basis':basis,'status':'PASS','run_id':data['run_id'],'duration_s':round(time.monotonic()-started,2),'event_digest':data['event_digest'],'raw_digest':data['raw_digest'],'gate':data['analysis']['verification_gate'],'primary_cause':data['analysis']['primary_cause'],'direct_trigger':data['analysis']['direct_trigger'],'tool_calls':data['analysis']['agent_execution']['tool_calls_used'],'propagation_count':len(data['analysis']['propagation']),'causal_chain_count':len(data['analysis']['causal_chain'])}
        except Exception as exc:
            failed=True;summary={'case':path.name,'basis':basis,'status':'FAIL','error_type':type(exc).__name__,'message':str(exc)[:2000]}
        summaries.append(summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
    (OUT/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8')
    if failed:raise SystemExit('Deployed regression failed; inspect retained response before claiming completion.')

if __name__=='__main__':main()
