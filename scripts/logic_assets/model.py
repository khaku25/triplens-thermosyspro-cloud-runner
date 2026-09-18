"""Validated metadata model. This module never executes a plant rule."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from typing import Any

RULE_FIELDS = ('rule_id','group','logic_name','logic_type','input_nodes','condition','delay',
               'reset_hysteresis','output_nodes_or_tags','output_class','input_group_id',
               'validation_status','source_basis','notes')
TAG_FIELDS = ('raw_tag_id','system','equipment_id','signal_role','data_type','unit',
              'description_ko','description_en','canonical_tag','local_display_alias',
              'scope_class','writable','scenario_lab_role','analysis_policy','unit_status',
              'interpretation_method','source_url','source_commit')
TYPES = {'ALARM','PROTECTION_CAUSE','TRIP_REQUEST','LATCH','BREAKER_SEQUENCE',
         'COMMAND_INTERFACE','PHYSICAL_RESPONSE'}


def text(value: Any) -> str:
    return '' if value is None else str(value).strip()


def parts(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text(v) for v in value if text(v)]
    return [p.strip() for p in re.split(r'[|;]', text(value)) if p.strip()]


def digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def unique(rows: list[dict], field: str, description: str) -> dict[str, dict]:
    found = {}
    for row in rows:
        key = text(row.get(field))
        if not key:
            raise ValueError(f'{description}: missing {field}')
        if key in found:
            raise ValueError(f'duplicate {description} ID: {key}')
        found[key] = row
    return found


def screen_for(group: str) -> str:
    if group in {'GT Protection','GT Response'}:
        return 'GT Protection'
    for p in ('HP','IP','LP'):
        if group in {f'{p} Drum', f'{p} Steam Flow', f'{p} Drum Protection'}:
            return f'{p} Drum'
    return group or 'Unassigned'


def validate_model(tags: list[dict], rules: list[dict], census: list[dict]) -> dict:
    """Native tag existence, declared derived IDs, and grouping; not behavioural proof."""
    census_rows = [r for r in census if text(r.get('browse_name')).startswith('vpp')]
    live = unique(census_rows, 'browse_name', 'live census')
    for tag, row in live.items():
        if any(text(row.get(field)).upper() != 'Y' for field in ('live_validated','numeric','finite')):
            raise ValueError(f'Invalid live census evidence for {tag}')
    tag_by = unique(tags, 'raw_tag_id', 'source tag')
    if not tag_by:
        raise ValueError('Empty source tag master')
    for tag in tag_by:
        if tag not in live:
            raise ValueError(f'source tag has no live census evidence: {tag}')
    rule_by = unique(rules, 'rule_id', 'rule')
    if not rule_by:
        raise ValueError('Empty logic master')
    derived: dict[str,list[str]] = defaultdict(list)
    normalized = []
    for rid, row in rule_by.items():
        if not re.fullmatch(r'[A-Za-z0-9_.:-]+', rid):
            raise ValueError(f'Unsupported rule ID: {rid}')
        r = {k:text(row.get(k)) for k in RULE_FIELDS}
        if r['logic_type'] not in TYPES:
            raise ValueError(f'Unsupported logic_type: {rid}: {r["logic_type"]}')
        r['inputs'] = parts(r['input_nodes'])
        r['outputs'] = parts(r['output_nodes_or_tags'])
        if not r['inputs'] or not r['outputs']:
            raise ValueError(f'Empty input/output list: {rid}')
        if len(set(r['inputs'])) != len(r['inputs']) or len(set(r['outputs'])) != len(r['outputs']):
            raise ValueError(f'duplicate input/output port: {rid}')
        if not r['condition']:
            raise ValueError(f'Missing condition: {rid}')
        for out in r['outputs']:
            if out in tag_by:
                continue
            if out.startswith('vpp') or r['output_class'] != 'DERIVED_ALARM':
                raise ValueError(f'Unregistered output: {rid}: {out}')
            derived[out].append(rid)
        r['screen'] = screen_for(r['group'])
        normalized.append(r)
    for tag, producers in derived.items():
        if len(producers) != 1:
            raise ValueError(f'duplicate derived output producer: {tag}: {producers}')
    signatures: dict[str, str] = {}
    ids: dict[str, str] = {}
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in normalized:
        for tag in r['inputs']:
            if tag not in tag_by and tag not in derived:
                raise ValueError(f'input is not a live source or declared derived output: {r["rule_id"]}: {tag}')
            scope = text(tag_by.get(tag,{}).get('scope_class')).upper()
            if 'LAB_ONLY' in scope or scope in {'SCENARIO_LAB_CONTROL','LEGACY_LAB_RAW'}:
                raise ValueError(f'Lab-only input is forbidden in operational logic: {tag}')
        signature = ' | '.join(sorted(r['inputs']))
        group_id = r['input_group_id'] or signatures.get(signature) or ('IG-'+digest(signature)[:10])
        if group_id in ids and ids[group_id] != signature:
            raise ValueError(f'Input group ID has different source sets: {group_id}')
        if signature in signatures and signatures[signature] != group_id:
            raise ValueError(f'Same source set has conflicting input group IDs: {signature}')
        ids[group_id] = signature
        signatures[signature] = group_id
        r['input_group_id'] = group_id
        r['input_signature'] = signature
        groups[group_id].append(r)
    normal_tags = {tag:{k:text(row.get(k)) for k in TAG_FIELDS} for tag,row in tag_by.items()}
    for tag,row in normal_tags.items():
        row.update(is_native=True, live_existence='CENSUS_OBSERVED',
                   live_variant_type=text(live[tag].get('variant_type')),
                   live_node_id=text(live[tag].get('node_id')))
    normalized.sort(key=lambda r:r['rule_id'])
    groups = {gid:sorted(rs,key=lambda r:r['rule_id']) for gid,rs in sorted(groups.items())}
    version = digest({'tags':normal_tags, 'rules':normalized, 'census_names':sorted(tag_by)})
    return dict(tags=normal_tags, rules=normalized, groups=groups, derived=dict(derived),
                semantic_sha256=version, census=live)


def numeric_delay(value: str) -> float | None:
    """Recognize only an explicit non-negative seconds/milliseconds duration."""
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(ms|s)\s*', value or '')
    if not match:
        return None
    number=float(match.group(1)) / (1000 if match.group(2)=='ms' else 1)
    if not math.isfinite(number):
        raise ValueError('Non-finite delay')
    return number
