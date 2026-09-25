"""Derived views and transactional release publication."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .xmlio import write_csv, write_xlsx

DRAWIO_NAME='TripLens_Logic_Master_Current_V8.drawio'
DRAWING_MASTER_NAME='drawing_master_index.json'


def derive_views(model,index):
    links=[]; ports=[]; blocks=[]; edges=[]; definitions=[]; groups=[]
    for r in model['rules']:
        rid=r['rule_id']; native_outputs=[n for n in r['outputs'] if n in model['tags']]
        derived=[n for n in r['outputs'] if n not in model['tags']]
        mapped=bool(r.get('source_mapped'))
        links.append(dict(rule_id=rid,input_group_id=r['input_group_id'],input_nodes=' | '.join(r['inputs']),
            source_outputs=' | '.join(native_outputs),derived_outputs=' | '.join(derived),
            missing_inputs='',missing_outputs='',link_status='SOURCE_MAPPED_ONLY' if mapped else 'EXACT_REGISTERED_IDENTITIES',
            source_existence=r.get('source_existence_status','LIVE_CENSUS_RESOLVED'),
            behaviour_status=r['validation_status']))
        for relation,nodes in [('INPUT',r['inputs']),('OUTPUT',r['outputs'])]:
            for n,tag in enumerate(nodes,1):
                pid=('IN' if relation=='INPUT' else 'OUT')+f'-{n:02}'
                ports.append(dict(rule_id=rid,port_id=pid,relation=relation,node_or_tag=tag,
                    kind=('MODEL_SOURCE_RAW_OBSERVED' if model['tags'].get(tag,{}).get('model_source_only')
                          else 'RAW_NODE' if tag in model['tags'] else 'DERIVED_TAG')))
        for kind,label in [('condition',r['condition']),('operation',r['logic_name']+'\n'+r['logic_type']),
                           ('additional','ADDITIONAL INFO')]:
            additional=kind=='additional'
            blocks.append(dict(rule_id=rid,block_id=kind+':'+rid,block_type='ADDITIONAL_INFO' if additional else kind.upper(),
                condition_or_label=label,delay=r['delay'] if additional else '',
                reset_hysteresis=r['reset_hysteresis'] if additional else '',
                validation_status=r['validation_status'] if additional else '',output_class=r['output_class'] if additional else ''))
        for n,_ in enumerate(r['inputs'],1):
            edges.append(dict(rule_id=rid,from_id=f'PORT:IN-{n:02}',to_id='condition:'+rid,edge_role='INPUT'))
        edges.append(dict(rule_id=rid,from_id='condition:'+rid,to_id='operation:'+rid,edge_role='CONDITION'))
        for n,_ in enumerate(r['outputs'],1):
            edges.append(dict(rule_id=rid,from_id='operation:'+rid,to_id=f'PORT:OUT-{n:02}',edge_role='OUTPUT'))
        definitions.append({**{k:r[k] for k in ('rule_id','group','logic_name','logic_type','input_nodes','condition',
            'delay','reset_hysteresis','output_nodes_or_tags','output_class','input_group_id','validation_status','source_basis')},
            'source_kind':r.get('source_kind','LIVE_OPCUA_CENSUS'),
            'source_mapped':'Y' if mapped else 'N',
            'runtime_inclusion':r.get('runtime_inclusion','LIVE_RUNTIME'),
            'model_source_status':r.get('model_source_status',''),
            'raw_session_status':r.get('raw_session_status',''),
            'raw_rows':r.get('raw_rows',''),
            'raw_closed_samples':r.get('raw_closed_samples',''),
            'raw_open_samples':r.get('raw_open_samples',''),
            'open_behavior_test_status':r.get('open_behavior_test_status','')})
    for gid,rs in model['groups'].items():
        groups.append(dict(input_group_id=gid,input_signature=rs[0]['input_signature'],branch_count=len(rs),
                           rule_ids='; '.join(r['rule_id'] for r in rs),outputs='; '.join(dict.fromkeys(t for r in rs for t in r['outputs'])),
                           page_id=gid))
    return dict(links=links,ports=ports,blocks=blocks,edges=edges,definitions=definitions,groups=groups)


def publish_repository(repository,target):
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.logic-build-',dir=target.parent))
    backup=target.with_name(target.name+'.previous')
    try:
        (staging/DRAWIO_NAME).write_text(repository['xml'],encoding='utf-8')
        def dump(name,value):
            (staging/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        dump('logic_diagram_index.json',repository['index'])
        dump(DRAWING_MASTER_NAME,repository['drawing_master'])
        for name,rows in repository['derived'].items():
            write_csv(staging/(name+'.csv'),rows)
        summary=[{'metric':k,'value':v} for k,v in repository['index']['counts'].items()]
        views=repository['derived']
        write_xlsx(staging/'08_TAG_LOGIC_LINK_MASTER_VALIDATION.xlsx',{'00_Verification':summary,'01_Link_Matrix':views['links'],'02_Ports':views['ports']})
        write_xlsx(staging/'09_LOGIC_DEFINITION_MASTER_CURRENT_V8.xlsx',{'00_ReadMe':summary,'01_Logic_Definition':views['definitions'],
            '02_Ports':views['ports'],'03_Blocks':views['blocks'],'04_Edges':views['edges']})
        equipment={'00_Scope':summary,'01_All_Current_Logic':views['definitions'],'02_Input_Groups':views['groups']}
        for number,screen in enumerate(['HP Drum','IP Drum','LP Drum','GT Exhaust','GT Protection','ST Protection','FWP HP','FWP IP','FWP LP'],3):
            matching=[r for r in repository['model']['rules'] if r['screen']==screen]
            if matching:
                equipment[f'{number:02}_{screen.replace(" ","_")}']=[{k:r[k] for k in ('rule_id','input_group_id','logic_name','input_nodes','condition','delay','reset_hysteresis','output_nodes_or_tags','validation_status')} for r in matching]
        write_xlsx(staging/'10_OPERATIONAL_LOGIC_GROUP_CURRENT_V8.xlsx',equipment)
        package=Path(__file__).parent
        viewer=package/'viewer.html'
        if viewer.exists():
            payload=json.dumps({'index':repository['index'],'xml':repository['xml'],'drawing_master':repository['drawing_master']},ensure_ascii=False,separators=(',',':'))
            payload=payload.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
            html=viewer.read_text(encoding='utf-8').replace('__TRIPLENS_PAYLOAD__',payload)
            (staging/'viewer.html').write_text(html,encoding='utf-8')
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(staging.iterdir()) if p.is_file()}
        dump('asset_manifest.json',dict(schema_version=2,semantic_sha256=repository['index']['semantic_sha256'],files=hashes,
             counts=repository['index']['counts'],verification_scope='Identity and diagram consistency; no plant execution'))
        if backup.exists():
            shutil.rmtree(backup)
        if target.exists():
            target.rename(backup)
        try:
            staging.rename(target)
        except OSError:
            if backup.exists() and not target.exists():
                backup.rename(target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return target
    finally:
        if staging.exists():
            shutil.rmtree(staging)
