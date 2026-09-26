"""Compile authoring masters into a consistent, versioned web/runtime release.

This compiler never writes OPC UA or changes plant/protection source code.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
from . import make_repository, publish_repository
from .build import DRAWIO_NAME
from .xmlio import read_table

TAG_FILE='06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx'
LOGIC_FILE='07_LOGIC_MASTER_CURRENT_V8_VERIFIED.xlsx'
VALIDATION_RUN={'number':54,'id':35309650110,'url':'https://github.com/khaku25/triplens-thermosyspro-cloud-runner/actions/runs/35309650110'}

def load_authoring(master_dir:Path,census_path:Path,layout_path:Path|None=None):
    master_dir=Path(master_dir)
    tags=read_table(master_dir/TAG_FILE,'01_Live_OPCUA_Tag_Master','raw_tag_id')
    rules=read_table(master_dir/LOGIC_FILE,'01_Logic_Master_Current','rule_id')
    def optional_table(path,sheet,key):
        try:
            return read_table(path,sheet,key)
        except ValueError as exc:
            if str(exc).startswith('Missing worksheet '):
                return []
            raise
    source_tags=optional_table(master_dir/TAG_FILE,'11_Model_Source_Observed','raw_tag_id')
    source_rules=optional_table(master_dir/LOGIC_FILE,'06_Model_Source_Observed','rule_id')
    census=read_table(Path(census_path),key='browse_name')
    xml=Path(layout_path).read_text(encoding='utf-8') if layout_path and Path(layout_path).exists() else None
    overlay_path=master_dir.parent/'runtime_overlay.json'
    overlay=json.loads(overlay_path.read_text(encoding='utf-8')) if overlay_path.is_file() else {}
    return make_repository(tags,rules,census,source_tags=source_tags,source_rules=source_rules,
                           layout_xml=xml,overlay=overlay)

def csv_bytes(rows,fields):
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
    writer.writeheader();writer.writerows(rows)
    return stream.getvalue().encode('utf-8-sig')

def json_bytes(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')

def runtime_assets(repository):
    model=repository['model']; index=repository['index']; counts=index['counts']; rows=[]
    views=repository.get('runtime_derived',repository['derived'])
    live_inputs={t for r in model['rules'] for t in r['inputs'] if t in model['tags']}
    live_outputs={t for r in model['rules'] for t in r['outputs'] if t in model['tags']}
    live_counts={'source_tags':len(model['tags']),'rules':len(model['rules']),
        'input_groups':len(model['groups']),'native_inputs':len(live_inputs),
        'native_outputs':len(live_outputs),'derived_outputs':len(model['derived'])}
    for r in model['rules']:
        outputs=r['outputs']; inputs=r['inputs']; first=outputs[0]
        rows.append(dict(logic_id=r['rule_id'],logic_type=r['logic_type'],group=r['group'],logic_name=r['logic_name'],
            tag_id=first,event_tag=first,source_node=inputs[0] if len(inputs)==1 else '',condition=r['condition'],
            delay=r['delay'],reset_hysteresis=r['reset_hysteresis'],status='ACTIVE',
            verification_status=r['validation_status'] or 'UNVERIFIED',source_existence_status=('RAW_SESSION_AND_CENSUS_RESOLVED' if any(model['tags'].get(t,{}).get('live_existence')=='RAW_SESSION_OBSERVED' for t in inputs+outputs) else 'LIVE_CENSUS_RESOLVED'),
            linked_tag_ids=';'.join(dict.fromkeys(inputs+outputs)),input_nodes='|'.join(inputs),
            output_nodes_or_tags='|'.join(outputs),output_class=r['output_class'],input_group_id=r['input_group_id'],
            source_basis=r['source_basis']))
    assets={
        'live_tag_allowlist.csv':csv_bytes([{'raw_tag_id':tag} for tag in sorted(model['tags'])],['raw_tag_id']),
        'live_logic_runtime.csv':csv_bytes(rows,list(rows[0])),
    }
    assets['live_tag_master.csv']=csv_bytes([model['tags'][tag] for tag in sorted(model['tags'])],list(next(iter(model['tags'].values()))))
    assets['live_tag_logic_links.csv']=csv_bytes(views['links'],list(views['links'][0]))
    manifest=dict(baseline='Current V8 Live OPC UA Verified',schema_version=2,
        semantic_sha256=model['semantic_sha256'],validation_run=repository.get('provenance',{}).get('validation_run',{}),
        census_provenance=repository.get('provenance',{}),
        counts=dict(live_tags=live_counts['source_tags'],logic_rules=live_counts['rules'],logic_inputs_live=live_counts['native_inputs'],
            vpp_outputs_live=live_counts['native_outputs'],derived_alarm_outputs=live_counts['derived_outputs'],input_groups=live_counts['input_groups']),
        policy=dict(source_identity='exact live OPC UA BrowseName',logic_context='exact registered rule only',
            verification_scope='Census resolves source identities; unchanged semantic status is not behavioural revalidation',
            scenario_metadata_to_agent='forbidden'),
        files={name:{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for name,data in sorted(assets.items())})
    assets['live_validation_manifest.json']=json_bytes(manifest)
    return assets

def project_files(repository):
    """Build completely in a temporary tree before exposing any changed file."""
    files={}
    with tempfile.TemporaryDirectory(prefix='triplens-assets-') as tmp:
        release=publish_repository(repository,Path(tmp)/'release')
        for p in sorted(release.iterdir()):
            if p.is_file(): files['generated/logic/'+p.name]=p.read_bytes()
    for name in [DRAWIO_NAME,'logic_diagram_index.json','drawing_master_index.json','asset_manifest.json']:
        files['logic_diagrams/'+name]=files['generated/logic/'+name]
    # The generated viewer contains the exact same XML and index and works offline.
    for name in ['viewer.html',DRAWIO_NAME,'logic_diagram_index.json','drawing_master_index.json','asset_manifest.json']:
        files['apps/web/public/logic-assets/'+name]=files['generated/logic/'+name]
    runtime=runtime_assets(repository)
    for prefix in ['data/current_v8','services/agent-api/triplens/current_v8']:
        for name,data in runtime.items(): files[prefix+'/'+name]=data
    files['data/current_v8/logic_definition.json']=json_bytes(repository['derived'])
    rules=repository['model']['rules']
    searchable=repository['search_model']['rules']
    protection={'PROTECTION_CAUSE','TRIP_REQUEST','LATCH','BREAKER_SEQUENCE'}
    files['apps/web/lib/current-logic-summary.json']=json_bytes(dict(
        live_rules=len(rules),searchable_rules=len(searchable),source_mapped_rules=sum(bool(r.get('source_mapped')) for r in searchable),
        alarm=sum(r['logic_type']=='ALARM' for r in rules),
        protection=sum(r['logic_type'] in protection for r in rules),
        commands=sum(r['logic_type']=='COMMAND_INTERFACE' for r in rules),
        physical_response=sum(r['logic_type']=='PHYSICAL_RESPONSE' for r in rules),
        searchable_physical_response=sum(r['logic_type']=='PHYSICAL_RESPONSE' for r in searchable),
        active_logic_core=len(rules),live_tags=len(repository['model']['tags']),
        searchable_tags=len(repository['search_model']['tags']),
        model_source_raw_observed_tags=sum(bool(r.get('model_source_only')) for r in repository['search_model']['tags'].values()),
        source='Generated Current V8 master snapshot',semantic_sha256=repository['index']['semantic_sha256']))
    return files

def publish_project(repository,root:Path):
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    files=project_files(repository)
    # Prepare every byte first. On a Python/OS failure, restore replaced paths.
    # Process/power-loss across files is not transactional; runtime hash checks fail closed.
    with tempfile.TemporaryDirectory(prefix='.logic-transaction-',dir=root) as tmp:
        stage=Path(tmp)/'new'; backup=Path(tmp)/'old';changed=[]
        for rel,data in files.items():
            dest=stage/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        try:
            for rel in sorted(files):
                dest=root/rel
                if dest.exists() and dest.read_bytes()==files[rel]: continue
                dest.parent.mkdir(parents=True,exist_ok=True)
                old=backup/rel
                existed=dest.exists()
                if existed:
                    old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,old)
                (stage/rel).replace(dest);changed.append((rel,existed))
        except Exception:
            for rel,existed in reversed(changed):
                if existed: (backup/rel).replace(root/rel)
                else: (root/rel).unlink(missing_ok=True)
            raise
    return {'semantic_sha256':repository['index']['semantic_sha256'],'counts':repository['index']['counts'],
            'changed_files':[rel for rel,_ in changed]}

def check_project(repository,root:Path):
    root=Path(root)
    return [rel for rel,data in sorted(project_files(repository).items()) if not (root/rel).is_file() or (root/rel).read_bytes()!=data]
