"""Regression for integrating #44 into the #43/#46 evidence UI without rollback."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class LatestMainInstallTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('installer', ROOT/'scripts/install_logic_web.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def test_preserve_evidence_ui_and_add_diagram_navigation(self):
        source = """'use client';
import {useEffect,useMemo,useRef,useState} from 'react';
import {CONTRACT_VERSION,buildDraftRows,loadSession,saveSession} from '../lib/analysisClient.mjs';
function openDetail(d){setDetail(d);}
const detailView=<code className="wrap-code">{detail.value}</code>;
function App(){return <main><button onClick={()=>setDrawer(true)}><b>LM</b><span>Logic Master</span></button><p>Current Logic Master upstream 동적 추적</p><button onClick={()=>openDetail({kind:'tag',value:t})}>tag</button></main>;}
"""
        try:
            out = self.m.patch_workspace(source)
        except ValueError as exc:
            self.fail(f'Latest main is a supported integration target: {exc}')
        for token in ('useRef','buildDraftRows','loadSession','saveSession',"function openDetail(d){setDetail(d);}", 'upstream 동적 추적', "openDetail({kind:'tag',value:t})"):
            self.assertIn(token, out)
        self.assertIn('openLogicLibrary()', out)
        self.assertIn('openLogicLibrary({tag:detail.value})', out)
        self.assertEqual(out.count('<LogicLibraryDialog />'), 1)
        self.assertEqual(self.m.patch_workspace(out), out)

    def test_preserve_grounded_store_and_report_contract(self):
        source = """from triplens.evidence_context import GroundedEvidenceStore as EvidenceStore, VERSION
from typing import Any
CURRENT_V8_ROOT = 'current'
def sha256_files(*paths):
    return 'ordered digest'
def current_v8_manifest():
    return {}
def live_tag_allowlist():
    return set()
def runtime_logic_rows():
    return []
def logic_summary():
    return {'new_summary':True}
def build_store(event_path,raw_path):
    return EvidenceStore(event_path,raw_path,event_registry=registry,live_tags=live_tag_allowlist())
def public_contract():
    return {'integration_version':VERSION, 'output_contract_version':'GROUNDED_ANALYSIS_V3'}
"""
        try:
            out = self.m.patch_bridge(source)
        except ValueError as exc:
            self.fail(f'GroundedEvidenceStore must remain the integration base: {exc}')
        self.assertIn('GroundedEvidenceStore as EvidenceStore, VERSION', out)
        self.assertIn('load_catalog(CURRENT_V8_ROOT)', out)
        self.assertIn("return 'ordered digest'", out)
        self.assertEqual(out[out.index('def logic_summary('):], source[source.index('def logic_summary('):])
        self.assertEqual(self.m.patch_bridge(out), out)

    def test_operator_workspace_with_analysis_dialog_is_already_integrated(self):
        source = """'use client';
import {LogicLibraryDialog,openLogicLibrary} from './LogicLibrary';
export default function App(){return <main><button onClick={()=>openLogicLibrary()}>Logic / TAG Master</button><LogicLibraryDialog analysisMode/></main>;}
"""
        self.assertEqual(self.m.patch_workspace(source), source)

if __name__ == '__main__':
    unittest.main()
