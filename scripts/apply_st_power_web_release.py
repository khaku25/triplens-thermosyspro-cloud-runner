#!/usr/bin/env python3
"""Validate the separated ST source evidence and run the existing asset pipeline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
BASELINE_CENSUS_SHA='1f9dafddc23eb356e2854708d440be3385607df3548b967baa780553b33c8254'

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main()->int:
    from scripts.logic_assets.xmlio import read_table

    proof=json.loads((ROOT/'data/current_v8/live_census_provenance.json').read_text(encoding='utf-8-sig'))
    census=ROOT/'data/current_v8/live_opcua_census.csv'
    if sha(census)!=proof.get('census_sha256') or sha(census)!=BASELINE_CENSUS_SHA:
        raise ValueError('Run 54 census changed or its provenance does not match')
    census_rows=read_table(census,key='browse_name')
    names={row['browse_name'] for row in census_rows if row['browse_name'].startswith('vpp')}
    if len(names)!=603 or {'vppSTGeneratorPowerMW','vppSTGridPowerMW'} & names:
        raise ValueError('ST source observations must remain outside the historical census')
    if 'vpp52STClosed' not in names:
        raise ValueError('52ST closed feedback is not present in the preserved census')

    tags=read_table(ROOT/'data/current_v8/masters/06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx',
                    '01_Live_OPCUA_Tag_Master','raw_tag_id')
    source_tags=read_table(ROOT/'data/current_v8/masters/06_TAG_MASTER_CURRENT_V8_VERIFIED.xlsx',
                           '11_Model_Source_Observed','raw_tag_id')
    rules=read_table(ROOT/'data/current_v8/masters/07_LOGIC_MASTER_CURRENT_V8_VERIFIED.xlsx',
                     '01_Logic_Master_Current','rule_id')
    source_rules=read_table(ROOT/'data/current_v8/masters/07_LOGIC_MASTER_CURRENT_V8_VERIFIED.xlsx',
                            '06_Model_Source_Observed','rule_id')
    expected_tags={'vppSTGeneratorPowerMW','vppSTGridPowerMW'}
    if len(tags)!=603 or expected_tags & {r['raw_tag_id'] for r in tags}:
        raise ValueError('Source-observed tags leaked into the live Tag Master')
    if {r['raw_tag_id'] for r in source_tags}!=expected_tags:
        raise ValueError('Model-source Tag Master sheet must contain the two ST MW tags')
    for row in source_tags:
        if row.get('runtime_inclusion')!='SEARCH_ONLY' or row.get('open_behavior_test_status')!='NOT_TESTED':
            raise ValueError(f"Unsafe source tag scope/status: {row['raw_tag_id']}")
        if row.get('live_node_id') or row.get('live_variant_type'):
            raise ValueError(f"Model-source tag claims missing OPC UA identity: {row['raw_tag_id']}")
    if len(rules)!=53 or 'RESP-ST-GRID-POWER' in {r['rule_id'] for r in rules}:
        raise ValueError('Source-mapped response rule leaked into the live Logic Master')
    if len(source_rules)!=1 or source_rules[0]['rule_id']!='RESP-ST-GRID-POWER':
        raise ValueError('Expected one source-mapped ST response rule')
    response=source_rules[0]
    inputs=set(response['input_nodes'].replace(';','|').split('|'))
    outputs=set(response['output_nodes_or_tags'].replace(';','|').split('|'))
    if not {'vppSTGeneratorPowerMW','vpp52STClosed'} <= {x.strip() for x in inputs}:
        raise ValueError('RESP-ST-GRID-POWER is missing a verified input')
    if 'vppSTGridPowerMW' not in {x.strip() for x in outputs}:
        raise ValueError('RESP-ST-GRID-POWER output does not match the source equation')
    if response.get('validation_status')!='PARTIAL' or response.get('open_behavior_test_status')!='NOT_TESTED':
        raise ValueError('52ST OPEN behavior must remain NOT_TESTED / PARTIAL')

    evidence=json.loads((ROOT/'data/current_v8/st_power_evidence_20260924.json').read_text(encoding='utf-8'))
    if evidence.get('source_sha256')!='055f8a21b8f586feafaa6fe6705cfca05b4f1e833713991a0cac1f0e94ad6fd9':
        raise ValueError('Latest RAW session hash mismatch')
    if evidence.get('rows')!=282 or evidence.get('closed_breaker_samples')!=282 or evidence.get('open_breaker_samples')!=0:
        raise ValueError('Unexpected RAW session observation counts')
    if evidence.get('behavior_validation')!='PARTIAL' or evidence.get('model_source',{}).get('package_sha256')!='6c616330ad80e4b5aad377fd5c4875a2aba7fb15d2366bb1a239eb6dd92231c4':
        raise ValueError('Source or behavior evidence status mismatch')

    # The signed Run 54 OPC UA census is immutable; derived runtime mirrors are
    # regenerated from the verified 603-tag / 53-rule master and may change hashes.
    for root in ('data/current_v8','services/agent-api/triplens/current_v8'):
        for name in ('live_tag_allowlist.csv','live_tag_master.csv','live_logic_runtime.csv',
                     'live_tag_logic_links.csv','live_validation_manifest.json'):
            if sha(ROOT/root/name)!=sha(ROOT/'data/current_v8'/name):
                raise ValueError(f'Runtime mirror mismatch: {root}/{name}')

    command=[sys.executable,str(ROOT/'scripts/update_triplens_logic.py')]
    subprocess.run(command,cwd=ROOT,check=True)
    subprocess.run(command+['--check'],cwd=ROOT,check=True)

    index=json.loads((ROOT/'logic_diagrams/logic_diagram_index.json').read_text(encoding='utf-8'))
    if index.get('counts',{}).get('live_tags')!=603 or index.get('counts',{}).get('live_rules')!=53:
        raise ValueError('Historical Run 54 live census/runtime counts changed')
    if index.get('counts',{}).get('searchable_tags')!=606 or index.get('counts',{}).get('rules')!=56:
        raise ValueError('Current searchable ST master counts are not 606 tags / 56 rules')
    current=index.get('rules',{})
    if 'PROT-ST-BRK-OPEN' not in current:
        raise ValueError('Current searchable master is missing PROT-ST-BRK-OPEN')
    if current.get('RESP-ST-GRID-POWER',{}).get('open_behavior_test_status')!='RUNTIME_VERIFIED':
        raise ValueError('52ST OPEN grid-power behavior is not marked runtime-verified')
    if '9-cause' in current.get('PROT-ST-REQUEST',{}).get('source_basis','') or '9' in current.get('PROT-ST-REQUEST',{}).get('condition',''):
        raise ValueError('Deprecated numeric cause-count wording remains in current ST request')
    print('ST_SOURCE_EVIDENCE_AND_WEB_ASSETS_READY; census=603; runtime_rules=53; searchable_tags=606; searchable_rules=56; OPEN=RUNTIME_VERIFIED')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
