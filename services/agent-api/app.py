"""TripLens READ-ONLY Dual Log API. No plant-control routes."""
from __future__ import annotations
import csv
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from fastapi import FastAPI,File,Form,HTTPException,UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from bridge import build_store,public_contract,sha256_files
from analysis_providers import (DEFAULT_ANALYSIS_PROVIDER,AnalysisProviderNotConfigured,
    UnknownAnalysisProvider,available_analysis_providers,provider_configuration,run_selected_analysis)
from triplens.evidence_context import VERSION
MAX_DIRECT_UPLOAD_BYTES=4_000_000
app=FastAPI(title='TripLens Agent API',version='0.3.0')
origins=['http://localhost:3000','http://127.0.0.1:3000','https://triplens-web-preview.vercel.app']
configured=os.getenv('TRIPLENS_WEB_ORIGIN','').strip()
if configured:origins.append(configured)
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,allow_methods=['GET','POST'],allow_headers=['Content-Type'])

def effective_contract(provider=DEFAULT_ANALYSIS_PROVIDER):
    selected=provider_configuration(provider)
    value=public_contract();value['model']=selected['model'];value['analysis_provider']=selected['id']
    value['analysis_models']=available_analysis_providers()
    if selected['id']=='openai':value['decision_authority']='OPENAI_AGENT'
    root=Path(__file__).resolve().parent
    value['tool_contract_version']=sha256_files(root/'gemini_agent.py',root/'openai_agent.py',root/'analysis_providers.py',root/'triplens'/'agent_tools.py',root/'triplens'/'evidence_context.py',root/'triplens'/'analysis_contract.py')
    return value

@app.get('/health')
def health():return {'status':'ok','service':'triplens-agent-api','read_only':True,'gemini_configured':bool(os.getenv('GEMINI_API_KEY','').strip()),'openai_configured':bool(os.getenv('OPENAI_API_KEY','').strip()),'integration_version':VERSION,'deployment_sha':os.getenv('VERCEL_GIT_COMMIT_SHA','unknown')}
@app.get('/contract')
def contract():return effective_contract()

async def save_upload(upload,path,budget):
    size=0
    with path.open('wb') as f:
        while chunk:=await upload.read(1024*1024):
            size+=len(chunk)
            if size>budget:raise HTTPException(413,detail='EVENT와 RAW 합계는 현재 4 MB 이하여야 합니다.')
            f.write(chunk)
    return size

async def prepare(event,raw,provider=DEFAULT_ANALYSIS_PROVIDER):
    temp=tempfile.TemporaryDirectory(prefix='triplens-');ep=Path(temp.name)/'EVENT.csv';rp=Path(temp.name)/'RAW.csv'
    try:
        used=await save_upload(event,ep,MAX_DIRECT_UPLOAD_BYTES);await save_upload(raw,rp,MAX_DIRECT_UPLOAD_BYTES-used)
        store=build_store(ep,rp);meta=effective_contract(provider);digest=sha256_files(ep,rp)
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
async def analyze(event:UploadFile=File(...),raw:UploadFile=File(...),provider:str=Form(DEFAULT_ANALYSIS_PROVIDER)):
    try:configuration=provider_configuration(provider)
    except UnknownAnalysisProvider as exc:raise HTTPException(422,detail=str(exc)) from exc
    if not configuration['available']:
        key_name='OPENAI_API_KEY' if configuration['id']=='openai' else 'GEMINI_API_KEY'
        raise HTTPException(503,detail=f"{configuration['label']} 분석을 사용하려면 서버에 {key_name}를 설정해야 합니다.")
    temp,store,run=await prepare(event,raw,configuration['id'])
    try:
        if store.readiness()['status']!='PASS':raise HTTPException(422,detail={'stage':'time_alignment','message':'조회 가능한 EVENT와 최소 2시점의 RAW 및 공통 시간구간이 필요합니다.','validation':store.validation})
        try:analysis=await run_in_threadpool(run_selected_analysis,configuration['id'],store,run_id=run['run_id'],data_digest=run['data_digest'])
        except AnalysisProviderNotConfigured as exc:raise HTTPException(503,detail=f"{configuration['label']} 서버 API 키가 설정되지 않았습니다.") from exc
        except Exception as exc:raise HTTPException(502,detail={'stage':f"{configuration['id']}_agent",'error_type':type(exc).__name__,'message':f"{configuration['label']} 분석이 완료되지 않았습니다. 입력은 유지됩니다. 서버 API 인증·한도·응답 형식을 확인하세요."}) from exc
        run.update(analysis=analysis,evidence_catalog=store.evidence_catalog(),events=[store.describe_event(r) for r in store.event_rows[:1000]],events_truncated=len(store.event_rows)>1000,tool_contract=store.tool_manifest());return run
    finally:temp.cleanup()
