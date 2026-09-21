"""TripLens READ-ONLY Dual Log API. No plant-control routes."""
from __future__ import annotations
import csv
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from fastapi import FastAPI,File,HTTPException,UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from bridge import build_store,public_contract,sha256_files
from gemini_agent import run_gemini_analysis,DEFAULT_MODEL
from triplens.cors_config import web_origins
from triplens.evidence_context import VERSION
MAX_DIRECT_UPLOAD_BYTES=4_000_000
app=FastAPI(title='TripLens Agent API',version='0.3.0')
origins=web_origins(os.getenv('TRIPLENS_WEB_ORIGIN',''))
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,allow_methods=['GET','POST'],allow_headers=['Content-Type'])

def effective_contract():
    value=public_contract();value['model']=os.getenv('TRIPLENS_GEMINI_MODEL',DEFAULT_MODEL)
    root=Path(__file__).resolve().parent
    value['tool_contract_version']=sha256_files(root/'gemini_agent.py',root/'triplens'/'agent_tools.py',root/'triplens'/'evidence_context.py',root/'triplens'/'analysis_contract.py')
    return value

@app.get('/health')
def health():return {'status':'ok','service':'triplens-agent-api','read_only':True,'gemini_configured':bool(os.getenv('GEMINI_API_KEY','').strip()),'integration_version':VERSION,'deployment_sha':os.getenv('VERCEL_GIT_COMMIT_SHA','unknown')}
@app.get('/contract')
def contract():return effective_contract()

async def save_upload(upload,path,budget):
    size=0
    with path.open('wb') as f:
        while chunk:=await upload.read(1024*1024):
            size+=len(chunk)
            if size>budget:raise HTTPException(413,detail='EVENTì RAW í©ê³ë íì¬ 4 MB ì´íì¬ì¼ í©ëë¤.')
            f.write(chunk)
    return size

async def prepare(event,raw):
    temp=tempfile.TemporaryDirectory(prefix='triplens-');ep=Path(temp.name)/'EVENT.csv';rp=Path(temp.name)/'RAW.csv'
    try:
        used=await save_upload(event,ep,MAX_DIRECT_UPLOAD_BYTES);await save_upload(raw,rp,MAX_DIRECT_UPLOAD_BYTES-used)
        store=build_store(ep,rp);meta=effective_contract();digest=sha256_files(ep,rp)
        key=hashlib.sha256(json.dumps([digest,meta['logic_master_version'],meta['prompt_version'],meta['tool_contract_version'],meta['integration_version'],meta['output_contract_version'],meta['model']],separators=(',',':')).encode()).hexdigest()
        run={'run_id':'RUN-'+uuid.uuid4().hex[:12].upper(),'data_digest':digest,'analysis_key':key,'contract':meta,'event_digest':hashlib.sha256(ep.read_bytes()).hexdigest(),'raw_digest':hashlib.sha256(rp.read_bytes()).hexdigest(),'evidence_readiness':store.readiness(),'validation':store.validation}
        return temp,store,run
    except (ValueError,UnicodeError,csv.Error) as exc:
        temp.cleanup();raise HTTPException(422,detail={'stage':'validation','message':str(exc)}) from exc
    except Exception:temp.cleanup();raise

@app.post('/bootstrap')
async def bootstrap(event:UploadFile=File(...),raw:UploadFile=File(...)):
    temp,store,run=await prepare(event,raw)
    try:
        run['bootstrap']=store.build_agent_bootstrap(run_id=run['run_id'],data_digest=run['data_digest']);run['events']=[store.describe_event(r) for r in store.event_rows[:1000]];run['events_truncated']=len(store.event_rows)>1000;return run
    finally:temp.cleanup()

@app.post('/analyze')
async def analyze(event:UploadFile=File(...),raw:UploadFile=File(...)):
    if not os.getenv('GEMINI_API_KEY','').strip():raise HTTPException(503,detail='ë°±ìë Gemini API í¤ê° ì¤ì ëì§ ìììµëë¤.')
    temp,store,run=await prepare(event,raw)
    try:
        if store.readiness()['status']!='PASS':raise HTTPException(422,detail={'stage':'time_alignment','message':'ì¡°í ê°ë¥í EVENTì ìµì 2ìì ì RAW ë° ê³µíµ ìê°êµ¬ê°ì´ íìí©ëë¤.','validation':store.validation})
        try:analysis=await run_in_threadpool(run_gemini_analysis,store,run_id=run['run_id'],data_digest=run['data_digest'])
        except Exception as exc:raise HTTPException(502,detail={'stage':'gemini_agent','error_type':type(exc).__name__,'message':'Gemini ë¶ìì´ ìë£ëì§ ìììµëë¤. ìë ¥ì ì ì§ë©ëë¤. ì¸ì¦Â·íëÂ·ìëµ íìì ìë²ìì íì¸íì¸ì.'}) from exc
        run.update(analysis=analysis,evidence_catalog=store.evidence_catalog(),events=[store.describe_event(r) for r in store.event_rows[:1000]],events_truncated=len(store.event_rows)>1000,tool_contract=store.tool_manifest());return run
    finally:temp.cleanup()
