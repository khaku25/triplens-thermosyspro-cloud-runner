"""Run the current TripLens analyzer and an independent semantic reviewer in CI.

This uses archived original V8 EVENT/RAW bytes. Hidden scenario directory names and expected
answer labels are used only by deterministic CI assertions and are never sent to Gemini.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVICE=ROOT/'services'/'agent-api'
sys.path.insert(0,str(SERVICE))
import bridge
from gemini_agent import run_gemini_analysis
from triplens.engineering_reviewer import run_engineering_review, REPORT_SECTIONS

OUT=ROOT/'outputs'/'semantic-engineering-review'

def assert_analysis(analysis, catalog):
    assert analysis['agent_execution']['tool_calls_used'] <= 8
    assert any(t.get('raw_evidence_count',0)>0 for t in analysis['tool_trace']), 'analysis did not retrieve RAW evidence'
    assert any(t.get('name')=='get_logic_context' and t.get('status')=='OK' for t in analysis['tool_trace']), 'analysis did not inspect logic context'
    for key in ('primary_cause','direct_trigger','critical_events','propagation','causal_chain','counter_evidence'):
        items=analysis[key] if isinstance(analysis[key],list) else [analysis[key]]
        for item in items:
            assert isinstance(item,dict) and item.get('claim','').strip(),(key,item)
            assert re.search('[가-힣]',item['claim']),(key,'Korean claim required')
            assert item['status'] in {'CANDIDATE','OBSERVED','UNKNOWN'}
            assert all(eid in catalog for eid in item.get('evidence_ids',[])),(key,'unlinked evidence',item)
            assert '86GT' not in item['claim']
            assert not any('86GT' in tag for tag in item.get('related_tags',[]))
    # Hidden regression expectation. This is deliberately never added to the reviewer package.
    assert set(analysis['primary_cause']['related_tags']) & {'vppExternalTripCommandNative','vppCauseDirectGTTrip'}, analysis['primary_cause']
    assert set(analysis['direct_trigger']['related_tags']) & {'vppGTTripLatch'}, analysis['direct_trigger']
    assert analysis['propagation'], 'Propagation must be structured and non-empty'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,required=True)
    args=parser.parse_args()
    if not os.getenv('GEMINI_API_KEY','').strip():
        raise RuntimeError('GEMINI_API_KEY secret is not available to this workflow')
    OUT.mkdir(parents=True,exist_ok=True)
    case=OUT/'direct-gt'
    case.mkdir(parents=True,exist_ok=True)

    with zipfile.ZipFile(args.archive) as archive:
        for name in ('EVENT.csv','RAW.csv'):
            data=archive.read(f'outputs/all-trip-matrix/direct_gt/{name}')
            (case/name).write_bytes(data)

    event=case/'EVENT.csv'; raw=case/'RAW.csv'
    event_digest=hashlib.sha256(event.read_bytes()).hexdigest()
    raw_digest=hashlib.sha256(raw.read_bytes()).hexdigest()

    store=bridge.build_store(event,raw)
    started=time.monotonic()
    analysis=run_gemini_analysis(store,run_id='CI-'+event_digest[:12].upper(),data_digest=bridge.sha256_files(event,raw))
    catalog={e['evidence_id']:e for e in store.evidence_catalog()}
    assert_analysis(analysis,catalog)

    envelope={
        'analysis':analysis,
        'events':[store.describe_event(e) for e in store.event_rows],
        'evidence_catalog':store.evidence_catalog(),
        'validation':store.validation,
        'run_id':'CI-'+event_digest[:12].upper(),
        'event_digest':event_digest,
        'raw_digest':raw_digest,
    }
    envelope_path=case/'envelope.json'
    envelope_path.write_text(json.dumps(envelope,ensure_ascii=False,indent=2),encoding='utf-8')
    report_path=case/'report_rows.json'
    subprocess.run(['node',str(ROOT/'tests'/'build_report_rows.mjs'),str(envelope_path),str(report_path)],check=True)
    report_rows=json.loads(report_path.read_text(encoding='utf-8'))
    sections=list(dict.fromkeys(r['section'] for r in report_rows))
    assert sections==REPORT_SECTIONS,(sections,REPORT_SECTIONS)

    reviewer_package={
        'analysis':analysis,
        'report_rows':report_rows,
        'evidence_catalog':store.evidence_catalog(),
        'events':[store.describe_event(e) for e in store.event_rows],
        'logic_rows':store.logic_rows,
        'validation':store.validation,
    }
    review=run_engineering_review(reviewer_package)
    (case/'analysis.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2),encoding='utf-8')
    (case/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')

    # Semantic reviewer may legitimately request human review. FAIL means the generated draft
    # has a serious content/placement/evidence defect and the workflow must stop.
    if review['review_status']=='FAIL':
        raise AssertionError('Independent Engineering Reviewer returned FAIL')
    if review.get('missing_required_sections'):
        raise AssertionError(f"Reviewer found missing sections: {review['missing_required_sections']}")

    summary={
        'basis':'ARCHIVED_ORIGINAL_V8_DIRECT_GT',
        'event_digest':event_digest,
        'raw_digest':raw_digest,
        'duration_s':round(time.monotonic()-started,2),
        'analysis_gate':analysis['verification_gate'],
        'analysis_model':analysis['agent_execution']['model'],
        'tool_calls':analysis['agent_execution']['tool_calls_used'],
        'primary_cause':analysis['primary_cause'],
        'direct_trigger':analysis['direct_trigger'],
        'propagation_count':len(analysis['propagation']),
        'report_sections':sections,
        'review_status':review['review_status'],
        'review_summary':review['summary_ko'],
        'content_score':review['content_score'],
        'placement_score':review['placement_score'],
        'evidence_score':review['evidence_score'],
        'findings':review['findings'],
        'human_review_focus':review['human_review_focus'],
        'note':'Reviewer is a separate Gemini interaction, not final human engineering approval.'
    }
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
