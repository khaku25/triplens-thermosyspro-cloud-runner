"""One archived incident, one analyzer session (+ <=1 citation repair), one reviewer.

No Vercel deployment, new plant simulation, hidden answer input, or automatic report edits.
Artifacts are written before assertions so a failed validation remains inspectable.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/agent-api'))
import bridge
from gemini_agent import run_gemini_analysis
from triplens.engineering_reviewer import run_engineering_review, review_matches_report, validate_review_references, REPORT_SECTIONS


def save(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=ROOT/'outputs/review-reference-fix/actual')
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.archive) as z:
        for name in ('EVENT.csv','RAW.csv'):
            (args.out/name).write_bytes(z.read('outputs/all-trip-matrix/direct_gt/'+name))
    event,raw=args.out/'EVENT.csv',args.out/'RAW.csv'
    digests={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (event,raw)}
    store=bridge.build_store(event,raw)
    run_id='REF-FIX-'+digests['EVENT.csv'][:12].upper()
    analysis=run_gemini_analysis(store,run_id=run_id,data_digest=bridge.sha256_files(event,raw))
    save(args.out/'analysis.json',analysis)
    envelope={'analysis':analysis,'events':[store.describe_event(e) for e in store.event_rows],
        'evidence_catalog':store.evidence_catalog(),'validation':store.validation,
        'evidence_readiness':store.readiness(),'contract':bridge.public_contract(),
        'run_id':run_id,'analysis_key':bridge.sha256_files(event,raw),'data_digest':bridge.sha256_files(event,raw)}
    save(args.out/'envelope.json',envelope)
    subprocess.run(['node',str(ROOT/'tests/build_report_rows.mjs'),str(args.out/'envelope.json'),str(args.out/'report_rows.json')],check=True)
    rows=json.loads((args.out/'report_rows.json').read_text())
    package={'analysis':analysis,'report_rows':rows,'events':envelope['events'],
        'evidence_catalog':envelope['evidence_catalog'],'logic_rows':store.logic_rows,'validation':store.validation}
    save(args.out/'reviewer_input.json',package)
    review=run_engineering_review(package)
    save(args.out/'review.json',review)
    changed=copy.deepcopy(rows);changed[0]['content']+=' [edited after review]'
    # Deliberately corrupt a pointer: validator must quarantine instead of retargeting.
    bad={'review_status':'PASS','findings':[{'row_id':rows[0]['row_id'],'current_section':'발생 원인',
        'expected_section':None,'severity':'WARNING','category':'PLACEMENT','finding':'부정 대조군','evidence_ids':[]}],
        'missing_required_sections':[]}
    negative=validate_review_references(bad,rows,store.evidence_catalog())
    summary={'mode':'ACTUAL_GEMINI_WITH_ORIGINAL_ARCHIVED_BYTES','input_sha256':digests,
        'application_base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'analysis_gate':analysis['verification_gate'],'analyzer_model':analysis['agent_execution']['model'],
        'tool_calls':analysis['agent_execution']['tool_calls_used'],
        'citation_repair':{k:v for k,v in analysis.get('citation_repair',{}).items() if k!='initial_draft'},
        'report_rows':len(rows),'unique_row_ids':len({r['row_id'] for r in rows}),
        'report_sections':list(dict.fromkeys(r['section'] for r in rows)),
        'review_reference_validation':review['reference_validation'],'review_status':review['review_status'],
        'reviewed_report_sha256':review['reviewed_report_sha256'],
        'stale_review_blocked':not review_matches_report(review,changed),
        'wrong_section_blocked':not negative['findings'] and bool(negative['rejected_findings']),
        'plant_simulation_rerun':False,'vercel_test':False,'human_approval_required':True}
    save(args.out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
    assert digests=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (event,raw)},'Original data mutated'
    assert summary['tool_calls']<=8 and analysis['citation_repair']['attempts']<=1
    assert any(t.get('raw_evidence_count',0)>0 for t in analysis['tool_trace'])
    assert any(t['name']=='get_logic_context' and t['status']=='OK' for t in analysis['tool_trace'])
    assert summary['unique_row_ids']==len(rows)
    assert summary['report_sections']==REPORT_SECTIONS
    assert review_matches_report(review,rows) and summary['stale_review_blocked'] and summary['wrong_section_blocked']
    assert review['reference_validation']['status']=='PASS','Reviewer supplied invalid references (quarantined, never applied)'
    assert analysis['citation_repair']['remaining_issue_count']==0,'Claim-local citation omissions remain (HOLD required)'
    assert review['review_status']!='FAIL','Reviewer found serious content issues; inspect preserved artifacts'
    print('ACTUAL_REVIEW_REFERENCE_FIX_PASS_NOT_ENGINEERING_APPROVAL')

if __name__=='__main__':main()
