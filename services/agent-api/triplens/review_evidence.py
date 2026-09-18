"""Report-only original EVENT references are separate from analyzer tool coverage."""
from __future__ import annotations
import copy


def build_review_evidence(package, rows):
    retrieved = package.get('evidence_catalog', [])
    events = package.get('events', [])
    if not isinstance(retrieved, list) or not isinstance(events, list):
        raise ValueError('Invalid review evidence inventory')
    index = {}
    for record in retrieved:
        if not isinstance(record, dict):
            raise ValueError('Invalid retrieved evidence')
        eid = record.get('evidence_id')
        if not isinstance(eid, str) or not eid or eid in index:
            raise ValueError('Duplicate or empty retrieved evidence ID')
        index[eid] = copy.deepcopy(record)
    analyzer_ids = list(index)
    original_event_ids = set()
    report_only = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('Invalid original EVENT record')
        eid = event.get('evidence_id') or event.get('event_id')
        if (not isinstance(eid, str) or not eid or eid.startswith('RAW:')
                or event.get('source_kind') not in (None, 'EVENT')
                or event.get('event_id', eid) != eid or eid in original_event_ids):
            raise ValueError('Invalid or duplicate original EVENT identity')
        original_event_ids.add(eid)
        record = {**copy.deepcopy(event), 'evidence_id':eid, 'source_kind':'EVENT'}
        if eid in index:
            existing = index[eid]
            keys = ('source_kind','event_id','model_time_s','tag','source_node','value','state')
            if any(k in existing and k in record and existing[k] != record[k] for k in keys):
                raise ValueError('Conflicting original EVENT and retrieved evidence: '+eid)
        else:
            index[eid] = record
            report_only.append(eid)
    missing = []
    for row in rows:
        ids = row.get('evidence_ids', '')
        if isinstance(ids, str):
            ids = [s.strip() for s in ids.split(';') if s.strip()]
        if not isinstance(ids, list) or any(not isinstance(eid, str) for eid in ids):
            raise ValueError('Invalid report evidence ID list')
        missing.extend(eid for eid in ids if eid not in index)
    if missing:
        raise ValueError('Unknown report evidence IDs: '+', '.join(sorted(set(missing))))
    return list(index.values()), {
        'analyzer_retrieved_evidence_ids': analyzer_ids,
        'report_only_event_ids': report_only,
        'original_event_count': len(original_event_ids),
        'report_evidence_count': len(index),
        'report_references_status': 'PASS',
        'policy': 'Report EVENT chronology may use every supplied original EVENT. '
                  'Report-only EVENT IDs do not mean the analyzer retrieved or cited them. '
                  'RAW remains limited to actual tool-retrieved samples.'}
