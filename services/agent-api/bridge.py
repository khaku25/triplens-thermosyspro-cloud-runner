"""Self-contained Current V8 sources for the read-only Agent API."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
from typing import Any
from triplens.evidence_context import GroundedEvidenceStore as EvidenceStore, VERSION

SERVICE_ROOT=Path(__file__).resolve().parent
PACKAGE_ROOT=SERVICE_ROOT/'triplens'
CURRENT_V8_ROOT=PACKAGE_ROOT/'current_v8'
LIVE_LOGIC=CURRENT_V8_ROOT/'live_logic_runtime.csv'
LIVE_TAG_ALLOWLIST=CURRENT_V8_ROOT/'live_tag_allowlist.csv'
LIVE_MANIFEST=CURRENT_V8_ROOT/'live_validation_manifest.json'
EVENT_REGISTRY=PACKAGE_ROOT/'alarm_registry_v1.csv'
PROTECTION_LOGIC_TYPES={'PROTECTION_CAUSE','TRIP_REQUEST','LATCH','BREAKER_SEQUENCE'}

def sha256_files(*paths: Path)->str:
    digest=hashlib.sha256(b'TripLens ordered files v2\0')
    for path in paths:
        data=Path(path).read_bytes()
        digest.update(len(data).to_bytes(8,'big')); digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()

def current_v8_manifest()->dict[str,Any]:
    if not LIVE_MANIFEST.exists(): raise RuntimeError('Current V8 manifest missing')
    return json.loads(LIVE_MANIFEST.read_text(encoding='utf-8-sig'))

def live_tag_allowlist()->set[str]:
    with LIVE_TAG_ALLOWLIST.open(encoding='utf-8-sig',newline='') as f:
        tags={r['raw_tag_id'].strip() for r in csv.DictReader(f)}-{''}
    if len(tags)!=603: raise RuntimeError('Current V8 live tag count mismatch')
    return tags

def runtime_logic_rows()->list[dict[str,Any]]:
    allowed=live_tag_allowlist(); rows=[]
    with LIVE_LOGIC.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row.get('status','').upper()!='ACTIVE': continue
            linked=[t.strip() for t in row.get('linked_tag_ids','').replace(',',';').split(';') if t.strip()]
            missing=[t for t in linked if t.startswith('vpp') and t not in allowed]
            if missing: raise RuntimeError(f"Current V8 logic references non-live OPC UA tags: {row.get('logic_id')}: {missing}")
            lt=row.get('logic_type','').upper()
            row.update(event_class='ALARM' if lt=='ALARM' else 'PROTECTION' if lt in PROTECTION_LOGIC_TYPES else 'OPERATOR_ACTION' if lt=='COMMAND_INTERFACE' else 'SYSTEM',canonical_tag=row.get('event_tag',''),verification_status='LIVE_OPCUA_VALIDATED')
            rows.append(row)
    if len(rows)!=53: raise RuntimeError('Current V8 logic rule count mismatch')
    return rows

def logic_summary()->dict[str,Any]:
    rows=runtime_logic_rows()
    return {'live_rules':len(rows),'alarm':sum(r['logic_type']=='ALARM' for r in rows),'protection':sum(r['logic_type'] in PROTECTION_LOGIC_TYPES for r in rows),'commands':sum(r['logic_type']=='COMMAND_INTERFACE' for r in rows),'physical_response':sum(r['logic_type']=='PHYSICAL_RESPONSE' for r in rows),'active_logic_core':len(rows),'source':'Current V8 Live OPC UA Verified SOT'}

def build_store(event_path:Path,raw_path:Path)->EvidenceStore:
    with EVENT_REGISTRY.open(encoding='utf-8-sig',newline='') as f: registry=list(csv.DictReader(f))
    return EvidenceStore(event_path,raw_path,logic_rows=runtime_logic_rows(),event_registry=registry,live_tags=live_tag_allowlist())

def evidence_readiness(event_path:Path,raw_path:Path)->dict[str,Any]:
    return build_store(event_path,raw_path).readiness()

def public_contract()->dict[str,Any]:
    manifest=current_v8_manifest()
    return {'version':'CURRENT_V8_LIVE_SOT_V1','integration_version':VERSION,'output_contract_version':'GROUNDED_ANALYSIS_V3',
            'runtime_baseline':manifest.get('baseline','Current V8 Live OPC UA Verified'),'validation_run':manifest.get('validation_run',{}),'current_v8_counts':manifest.get('counts',{}),
            'source_identity_policy':manifest.get('policy',{}).get('source_identity','exact live OPC UA BrowseName'),
            'input':['EVENT.csv','RAW.csv'],'read_only':True,'python_role':'EVIDENCE_PROVIDER_AND_VERIFIER','decision_authority':'GEMINI_AGENT','status_scope':'EVIDENCE_READINESS_ONLY',
            'reserved_agent_decisions':['critical_events','primary_cause','direct_trigger','propagation','causal_chain'],
            'logic_summary':logic_summary(),'live_tag_allowlist_count':len(live_tag_allowlist()),
            'logic_master_version':sha256_files(LIVE_LOGIC,LIVE_TAG_ALLOWLIST,EVENT_REGISTRY),
            'prompt_version':sha256_files(PACKAGE_ROOT/'hybrid_agent_prompt.md'),
            'evidence_readiness_version':'GENERIC_DUAL_LOG_EVIDENCE_V2',
            'direct_trigger_definition':'FIRST_DOWNSTREAM_PROTECTION_ACTUATION_NOT_TRIP_REQUEST','direct_upload_soft_limit_bytes':4_000_000}
