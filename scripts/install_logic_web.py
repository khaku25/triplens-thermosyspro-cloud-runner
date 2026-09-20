#!/usr/bin/env python3
"""Guarded, idempotent integration into the existing TripLens application.

Preserves the current evidence/report UI and GroundedEvidenceStore. Only adds
logic navigation and the hash-checked catalog loader. No plant/runtime changes.
"""
from pathlib import Path
import re

def once(source,old,new,label):
    if old not in source:
        if new in source:return source
        raise ValueError(f'{label}: expected integration anchor is missing')
    if source.count(old)!=1:raise ValueError(f'{label}: ambiguous integration anchor')
    return source.replace(old,new,1)

def patch_workspace(source):
    if re.search(r'<LogicLibraryDialog\b[^>]*/>', source) and 'openLogicLibrary()' in source:
        return source
    modern = "import {useEffect,useMemo,useRef,useState} from 'react';"
    if modern in source:
        source=once(source,modern,modern+"\nimport { LogicLibraryDialog, openLogicLibrary } from './LogicLibrary';",'workspace import')
        source=once(source,'<button onClick={()=>setDrawer(true)}><b>LM</b>',
                    '<button onClick={()=>openLogicLibrary()}><b>LM</b>','workspace navigation')
        anchor='<code className="wrap-code">{detail.value}</code>'
        detail=anchor+"{detail.kind==='tag'&&<button type=\"button\" className=\"back-button\" onClick={()=>openLogicLibrary({tag:detail.value})}>관련 로직·도면 보기</button>}"
        source=once(source,anchor,detail,'workspace tag detail')
    else:
        source=once(source,"import { useEffect, useMemo, useState } from 'react';", "import { useEffect, useMemo, useState } from 'react';\nimport { LogicLibraryDialog, LogicLinks, openLogicLibrary } from './LogicLibrary';",'workspace import')
        source=once(source,'<button onClick={() => setDrawer(true)}><b>LM</b>', '<button onClick={() => openLogicLibrary()}><b>LM</b>','workspace navigation')
        source=once(source,"<span>태그: {(item?.related_tags || []).join(', ') || '—'}</span>","<span>태그: <LogicLinks tags={item?.related_tags || []} /></span>",'workspace claim tags')
        source=once(source,"<span>{row.tags || '—'}</span>","<span><LogicLinks tags={row.tags} /></span>",'workspace evidence tags')
    source=once(source,'</main>','<LogicLibraryDialog />\n    </main>','workspace dialog')
    return source

def patch_contracts(source):
    if "from './current-logic-summary.json'" in source:return source
    source,count=re.subn(r'export const DEFAULT_LOGIC_SUMMARY\s*=\s*\{.*?\};', 'export const DEFAULT_LOGIC_SUMMARY = CURRENT_LOGIC_SUMMARY;',source,count=1,flags=re.S)
    if count!=1:raise ValueError('contracts summary integration anchor missing')
    return "import CURRENT_LOGIC_SUMMARY from './current-logic-summary.json';\n\n"+source

def patch_bridge(source):
    if 'load_catalog(CURRENT_V8_ROOT)' in source:return source
    grounded='from triplens.evidence_context import GroundedEvidenceStore as EvidenceStore, VERSION'
    original=grounded if grounded in source else 'from triplens.agent_tools import EvidenceStore'
    source=once(source,original,original+'\nfrom triplens.current_catalog import load_catalog','bridge import')
    start=source.find('def current_v8_manifest(');end=source.find('def logic_summary(')
    if start<0 or end<start:raise ValueError('bridge catalog function boundary missing')
    return source[:start]+'''def current_v8_manifest() -> dict[str, Any]:
    return load_catalog(CURRENT_V8_ROOT)[0]


def live_tag_allowlist() -> set[str]:
    return load_catalog(CURRENT_V8_ROOT)[1]


def runtime_logic_rows() -> list[dict[str, Any]]:
    # Hash-checked source identities and original semantic status stay separate.
    return load_catalog(CURRENT_V8_ROOT)[2]


'''+source[end:]

def main(root=None):
    root=Path(root) if root else Path(__file__).resolve().parents[1]
    files={'apps/web/components/TripLensWorkspace.js':patch_workspace,
           'apps/web/lib/contracts.js':patch_contracts,
           'services/agent-api/bridge.py':patch_bridge}
    updates={}
    for rel,func in files.items():
        p=root/rel
        if not p.is_file():raise ValueError(f'Existing project file missing: {rel}')
        updates[p]=func(p.read_text(encoding='utf-8'))
    for p,text in updates.items():p.write_text(text,encoding='utf-8')
    print('Existing TripLens workspace, summary and Agent API catalog integrated')
if __name__=='__main__':main()
