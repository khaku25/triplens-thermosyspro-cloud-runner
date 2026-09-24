#!/usr/bin/env python3
"""Apply the reviewed ST master artifact delta and regenerate web assets.

The payload was produced from the exact existing 06/07 workbooks using
artifact_tool. This is a guarded byte-level ZIP delta, not a second spreadsheet
editor. No physical model, OPC UA client, or Plant Control file is written.
"""
from __future__ import annotations
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_digest(z: zipfile.ZipFile) -> str:
    h = hashlib.sha256()
    for name in sorted(z.namelist()):
        h.update(name.encode() + b'\0' + hashlib.sha256(z.read(name)).digest())
    return h.hexdigest()


def apply_workbook_delta(spec: dict) -> bytes | None:
    path = ROOT / spec['path']
    raw = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as old:
        if archive_digest(old) == spec['after_content']:
            return None
        if digest(raw) != spec['before']:
            raise ValueError('Authoring workbook changed; refusing to overwrite: ' + spec['path'])
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as new:
            for info in old.infolist():
                value = old.read(info.filename)
                entry = spec['entries'].get(info.filename)
                if entry:
                    if digest(value) != entry['before']:
                        raise ValueError('ZIP source part mismatch: ' + info.filename)
                    for start, end, replacement in reversed(entry['edits']):
                        if not 0 <= start <= end <= len(value):
                            raise ValueError('Invalid artifact byte range')
                        value = value[:start] + replacement.encode('utf-8') + value[end:]
                    if digest(value) != entry['after']:
                        raise ValueError('ZIP output part mismatch: ' + info.filename)
                new.writestr(info, value)
        result = out.getvalue()
        with zipfile.ZipFile(io.BytesIO(result)) as check:
            if archive_digest(check) != spec['after_content']:
                raise ValueError('Reconstructed artifact content mismatch')
        return result


def replace_exact(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    if new in text:
        return
    if text.count(old) != 1:
        raise ValueError('Code contract changed; inspect before updating: ' + path)
    p.write_text(text.replace(old, new), encoding='utf-8')


def main() -> None:
    encoded = (ROOT / 'data/migrations/st_power_masters_20260924.b64').read_text()
    payload = json.loads(zlib.decompress(base64.b64decode(encoded, validate=False)))
    if payload['schema'] != 1:
        raise ValueError('Unsupported artifact delta schema')
    # Validate both source workbooks before replacing either one.
    prepared = [(s['path'], apply_workbook_delta(s)) for s in payload['workbooks']]
    for name, data in prepared:
        if data is not None:
            p = ROOT / name
            tmp = p.with_suffix('.tmp.xlsx')
            tmp.write_bytes(data)
            tmp.replace(p)

    evidence = payload['evidence']
    if evidence['behavior_validation'] != 'PARTIAL' or evidence['open_breaker_samples'] != 0:
        raise ValueError('Unexpected evidence scope')
    evidence_name = 'st_power_evidence_20260924.json'
    evidence_path = ROOT / 'data/current_v8' / evidence_name
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    census = ROOT / 'data/current_v8/live_opcua_census.csv'
    proof_path = ROOT / 'data/current_v8/live_census_provenance.json'
    proof = json.loads(proof_path.read_text(encoding='utf-8-sig'))
    if digest(census.read_bytes()) != proof['census_sha256']:
        raise ValueError('Existing census proof mismatch')
    with census.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    existing = {r['browse_name']: r for r in rows}
    tags = ['vppSTGeneratorPowerMW', 'vppSTGridPowerMW']
    missing = [tag for tag in tags if tag not in existing]
    if missing:
        if len(missing) != 2:
            raise ValueError('Partially registered ST signals; reconcile explicitly')
        baseline_hash = proof['census_sha256']
        fields += [f for f in ('evidence_kind', 'evidence_ref') if f not in fields]
        for tag in tags:
            stats = evidence['signals'][tag]
            if stats['finite_samples'] != evidence['rows']:
                raise ValueError('Non-finite RAW evidence: ' + tag)
            row = dict.fromkeys(fields, '')
            row.update(browse_name=tag,
                       current_value=str(evidence['observations'][0][tag]),
                       numeric='Y', finite='Y', live_validated='Y',
                       evidence_kind='RAW_SESSION_OBSERVED',
                       evidence_ref='data/current_v8/' + evidence_name)
            rows.append(row)
        with census.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
        proof.update(census_sha256=digest(census.read_bytes()),
                     baseline_census_sha256=baseline_hash,
                     expected_vpp_count=sum(r['browse_name'].startswith('vpp') for r in rows),
                     scope='Unchanged Run 54 browse/read baseline plus two separately identified later RAW-session signals. No new plant/protection behavioral validation.',
                     supplemental_evidence=dict(file='data/current_v8/' + evidence_name,
                         sha256=digest(evidence_path.read_bytes()), source_sha256=evidence['source_sha256'],
                         tags=tags, session_id=evidence['session_id'], rows=evidence['rows'],
                         behavior_validation='PARTIAL', node_id_and_variant_type='NOT_CAPTURED'))
        proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    # Preserve the distinction between a native browse census and recorded RAW evidence.
    replace_exact('scripts/logic_assets/model.py',
        "live_existence='CENSUS_OBSERVED',",
        "live_existence=text(live[tag].get('evidence_kind')) or 'CENSUS_OBSERVED',")
    replace_exact('scripts/logic_assets/pipeline.py',
        "source_existence_status='LIVE_CENSUS_RESOLVED',",
        "source_existence_status=('RAW_SESSION_AND_CENSUS_RESOLVED' if any(model['tags'].get(t,{}).get('live_existence')=='RAW_SESSION_OBSERVED' for t in inputs+outputs) else 'LIVE_CENSUS_RESOLVED'),")
    replace_exact('tests/test_logic_pipeline.py',
        "self.assertEqual(len(model['model']['tags']),603)",
        "self.assertEqual(len(model['model']['tags']),605)")
    replace_exact('tests/test_logic_pipeline.py',
        "self.assertEqual(len(model['model']['rules']),53)",
        "self.assertEqual(len(model['model']['rules']),54)")
    replace_exact('tests/test_logic_update_command.py',
        "self.assertEqual(summary['counts']['rules'],53)",
        "self.assertEqual(summary['counts']['rules'],54)")
    replace_exact('tests/test_logic_viewer.py',
        "self.assertIn('603',self.page.locator('#stats').inner_text())",
        "self.assertIn('605',self.page.locator('#stats').inner_text())")
    replace_exact('tests/test_logic_viewer.py',
        "self.assertIn('53',self.page.locator('#stats').inner_text())",
        "self.assertIn('54',self.page.locator('#stats').inner_text())")
    subprocess.run([sys.executable, str(ROOT / 'scripts/update_triplens_logic.py')], check=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/update_triplens_logic.py'), '--check'], check=True)
    print('ST_POWER_MASTERS_AND_WEB_ASSETS_READY; physical_runtime_changed=False')


if __name__ == '__main__':
    main()
