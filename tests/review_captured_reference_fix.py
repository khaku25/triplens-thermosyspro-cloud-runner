"""Re-review a captured actual analysis once; do not call the analyzer again."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/agent-api'))
from triplens.engineering_reviewer import run_engineering_review, review_matches_report
from triplens.review_evidence import build_review_evidence


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--sha256',required=True);args=parser.parse_args()
    assert hashlib.sha256(args.capture.read_bytes()).hexdigest()==args.sha256,'Captured archive digest mismatch'
    out=ROOT/'outputs/review-reference-fix/actual';out.mkdir(parents=True,exist_ok=True)
    prefix='review-reference-fix/actual/'
    with zipfile.ZipFile(args.capture) as z:
        for name in ('EVENT.csv','RAW.csv','analysis.json','envelope.json','report_rows.json','reviewer_input.json'):
            (out/name).write_bytes(z.read(prefix+name))
        (out/'prior_review.json').write_bytes(z.read(prefix+'review.json'))
        original_summary=json.loads(z.read(prefix+'summary.json'))
    package=json.loads((out/'reviewer_input.json').read_text())
    before=hashlib.sha256((out/'analysis.json').read_bytes()).hexdigest()
    catalog,scope=build_review_evidence(package,package['report_rows'])
    assert len({e['evidence_id'] for e in package['events']})==scope['original_event_count']
    review=run_engineering_review(package)
    (out/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2))
    summary={**original_summary,'mode':'CAPTURED_ACTUAL_ANALYSIS_WITH_ONE_NEW_REVIEWER_CALL',
        'reviewer_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'capture_archive_sha256':args.sha256,'captured_analysis_sha256':before,
        'analyzer_called_again':False,'reviewer_calls':1,'report_reference_validation':scope,
        'review_reference_validation':review['reference_validation'],'review_status':review['review_status'],
        'reviewed_report_sha256':review['reviewed_report_sha256']}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    assert before==hashlib.sha256((out/'analysis.json').read_bytes()).hexdigest()
    assert review_matches_report(review,package['report_rows'])
    assert review['reference_validation']['status']=='PASS','Invalid reviewer references quarantined'
    assert review['review_status']!='FAIL','Serious reviewer findings must be examined'
    print('CAPTURED_ANALYSIS_REVIEW_REFERENCE_PASS')

if __name__=='__main__':main()
