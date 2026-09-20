#!/usr/bin/env python3
"""06/07 -> validated 08/09/10 + draw.io + tag index + web + Agent API package.

No OPC UA writes, simulation runs or plant/protection edits are performed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request

REPO=Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from scripts.logic_assets.pipeline import load_authoring,publish_project,check_project,TAG_FILE,LOGIC_FILE
from scripts.logic_assets.build import DRAWIO_NAME

DRIVE_IDS={
    TAG_FILE:'1feBcaC6wvykJEN8u3F0BZEY17Ke2G4AZ',
    LOGIC_FILE:'1NyTHr8hInhjbs3sVZ1TPvGV84Pxhc-ak',
    '08_TAG_LOGIC_LINK_MASTER_VALIDATION.xlsx':'1vaYnQeMPRgvCE4Uy6FTmxuL10djhnrK7',
    '09_LOGIC_DEFINITION_MASTER_CURRENT_V8.xlsx':'1vz-yJTFT9QW2_izXoykgsYj88BNSwN_S',
    '10_OPERATIONAL_LOGIC_GROUP_CURRENT_V8.xlsx':'19kce3v5o6x1ErVWDnUgrPT4fq-6tMFuS',
}

def request_bytes(url,token='',method='GET',body=None):
    headers={'User-Agent':'TripLens-Logic-Assets/1'}
    if token:headers['Authorization']='Bearer '+token
    if body is not None:headers['Content-Type']='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    req=urllib.request.Request(url,data=body,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=90) as response:
        data=response.read(20_000_001)
    if len(data)>20_000_000:raise ValueError('Drive download exceeds 20 MB limit')
    return data

def download_masters(target,token):
    for name in (TAG_FILE,LOGIC_FILE):
        fid=DRIVE_IDS[name]
        url=(f'https://www.googleapis.com/drive/v3/files/{fid}?alt=media' if token else
             f'https://drive.google.com/uc?export=download&id={fid}')
        data=request_bytes(url,token)
        if not data.startswith(b'PK\x03\x04'):
            raise ValueError(f'Drive did not return XLSX bytes for {name}. Use authorized TRIPLENS_DRIVE_ACCESS_TOKEN or local exported masters; do not import a login/permission HTML page.')
        (target/name).write_bytes(data)

def verify_census(path,proof_path):
    proof=json.loads(Path(proof_path).read_text(encoding='utf-8-sig'))
    actual=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if actual!=proof.get('census_sha256'):
        raise ValueError('Census provenance hash mismatch; provide the matching live census evidence, not an edited allowlist')
    if not proof.get('validation_run'):
        raise ValueError('Census provenance has no validation run identity')
    return proof

def synchronize_drive(root,token):
    if not token:raise ValueError('--sync-drive requires an authorized TRIPLENS_DRIVE_ACCESS_TOKEN; ChatGPT connector credentials are not exported to this command')
    results=[]
    for name,fid in DRIVE_IDS.items():
        if name.startswith(('06_','07_')):continue
        data=(root/'generated/logic'/name).read_bytes()
        result=request_bytes(f'https://www.googleapis.com/upload/drive/v3/files/{fid}?uploadType=media',token,'PATCH',data)
        results.append({'file':name,'drive_id':fid,'sha256':hashlib.sha256(data).hexdigest(),'response':json.loads(result)})
    return results

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project-root',type=Path,default=REPO)
    p.add_argument('--master-dir',type=Path,help='Folder containing exported 06 and 07 XLSX authoring files')
    p.add_argument('--census',type=Path,help='Native live browse/read census CSV')
    p.add_argument('--census-provenance',type=Path,help='JSON with matching census_sha256 and validation_run')
    p.add_argument('--layout',type=Path,help='Updated stable-ID draw.io file; geometry and safe styles are retained')
    p.add_argument('--from-drive',action='store_true',help='Download latest 06/07 before validation; preserve previous masters until validated')
    p.add_argument('--sync-drive',action='store_true',help='After generation, update existing 08/09/10 Drive files using an authorized access token')
    p.add_argument('--check',action='store_true',help='Compare all generated assets without writing or remote publishing')
    args=p.parse_args(argv)
    root=args.project_root.resolve();master=args.master_dir or root/'data/current_v8/masters'
    census=args.census or root/'data/current_v8/live_opcua_census.csv'
    proof_path=args.census_provenance or root/'data/current_v8/live_census_provenance.json'
    token=os.environ.get('TRIPLENS_DRIVE_ACCESS_TOKEN','').strip()
    if args.check and (args.from_drive or args.sync_drive):p.error('--check is read-only; cannot combine with Drive writes/downloads')
    if args.sync_drive and not token:p.error('--sync-drive needs authorized TRIPLENS_DRIVE_ACCESS_TOKEN')
    proof=verify_census(census,proof_path)
    layout=args.layout or root/'logic_diagrams'/DRAWIO_NAME
    if args.layout and not layout.is_file():raise ValueError('Requested draw.io layout file is missing')
    if layout.exists():
        # Validate the declared schema against decompressed stable central IDs.
        from scripts.logic_assets.drawio import decode_document,validate_layout_schema
        document=decode_document(layout.read_text(encoding='utf-8'))
        validate_layout_schema(document)
    with tempfile.TemporaryDirectory(prefix='triplens-master-import-') as tmp:
        source=Path(tmp) if args.from_drive else master
        if args.from_drive:download_masters(source,token)
        repository=load_authoring(source,census,layout if layout.exists() else None)
        repository['provenance']=proof
        if args.check:
            mismatches=check_project(repository,root)
            print(json.dumps({'status':'FAIL' if mismatches else 'PASS','mismatches':mismatches},ensure_ascii=False))
            return 1 if mismatches else 0
        result=publish_project(repository,root)
        if args.from_drive:
            master.mkdir(parents=True,exist_ok=True)
            for name in (TAG_FILE,LOGIC_FILE):shutil.copy2(source/name,master/name)
        result['status']='PASS';result['plant_runtime_changed']=False
        result['drive_status']='NOT_REQUESTED'
        if args.sync_drive:
            result['drive_updates']=synchronize_drive(root,token);result['drive_status']='UPDATED'
        print(json.dumps(result,ensure_ascii=False))
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(f'Logic update blocked: {type(exc).__name__}: {exc}',file=sys.stderr)
        raise SystemExit(1)
