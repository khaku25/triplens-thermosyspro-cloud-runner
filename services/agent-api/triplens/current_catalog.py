"""Read only a complete hash-checked generated Current V8 catalog.

Source-existence validation is not a functional protection/physics PASS.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
from pathlib import Path

PROTECTION_TYPES={'PROTECTION_CAUSE','TRIP_REQUEST','LATCH','BREAKER_SEQUENCE'}

def _read(root,name):
    if not name or Path(name).name!=name or name in {'.','..'} or '\\' in name:
        raise RuntimeError('Unsafe catalog manifest path')
    path=root/name
    if not path.is_file():raise RuntimeError(f'Current catalog file missing: {name}')
    if path.stat().st_size>25_000_000:raise RuntimeError(f'Current catalog file too large: {name}')
    return path.read_bytes()

def _rows(data):
    reader=csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
    if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames):
        raise RuntimeError('Invalid current catalog CSV header')
    rows=list(reader)
    if any(None in r for r in rows):raise RuntimeError('Invalid current catalog CSV columns')
    return rows

def _parts(value):
    return [v.strip() for v in str(value or '').replace('|',';').split(';') if v.strip()]

def load_catalog(folder:Path):
    root=Path(folder)
    manifest=json.loads(_read(root,'live_validation_manifest.json').decode('utf-8-sig'))
    entries=manifest.get('files',{})
    if not {'live_tag_allowlist.csv','live_logic_runtime.csv'}<=set(entries):
        raise RuntimeError('Current catalog manifest is incomplete')
    contents={}
    for name,entry in entries.items():
        data=_read(root,name)
        if hashlib.sha256(data).hexdigest()!=entry.get('sha256'):
            raise RuntimeError(f'Current catalog hash mismatch: {name}')
        contents[name]=data
    tag_rows=_rows(contents['live_tag_allowlist.csv'])
    tags={str(r.get('raw_tag_id','')).strip() for r in tag_rows}
    if '' in tags or len(tags)!=len(tag_rows):raise RuntimeError('Duplicate/empty source tag')
    counts=manifest.get('counts',{})
    if len(tags)!=counts.get('live_tags'):raise RuntimeError('Catalog tag count mismatch')
    rows=_rows(contents['live_logic_runtime.csv']);ids=set();derived=set()
    for row in rows:
        rid=str(row.get('logic_id','')).strip()
        if not rid or rid in ids:raise RuntimeError('Duplicate/empty logic ID')
        ids.add(rid)
        if row.get('status')!='ACTIVE':raise RuntimeError('Inactive rule in Current catalog')
        for tag in _parts(row.get('output_nodes_or_tags')):
            if tag not in tags:
                if tag.startswith('vpp') or row.get('output_class')!='DERIVED_ALARM':
                    raise RuntimeError(f'Unregistered source output: {rid}: {tag}')
                if tag in derived:raise RuntimeError('Duplicate derived output')
                derived.add(tag)
    for row in rows:
        inputs=_parts(row.get('input_nodes'));outputs=_parts(row.get('output_nodes_or_tags'))
        if not inputs or not outputs:raise RuntimeError('Missing input/output definition')
        missing=set(inputs+outputs)-tags-derived
        if missing:raise RuntimeError(f'Unregistered logic link: {sorted(missing)}')
        if set(_parts(row.get('linked_tag_ids')))!=set(inputs+outputs):
            raise RuntimeError('Runtime lookup index differs from actual input/output definition')
        kind=row.get('logic_type')
        if kind=='ALARM':event_class='ALARM'
        elif kind in PROTECTION_TYPES:event_class='PROTECTION'
        elif kind=='COMMAND_INTERFACE':event_class='OPERATOR_ACTION'
        elif kind=='PHYSICAL_RESPONSE':event_class='SYSTEM'
        else:raise RuntimeError(f'Unknown Current logic type: {kind}')
        row['event_class']=event_class
        row['canonical_tag']=row.get('event_tag','')
    if len(rows)!=counts.get('logic_rules'):raise RuntimeError('Catalog rule count mismatch')
    return manifest,tags,rows
