import importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'scripts/install_logic_web.py'
class InstallTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PATH.exists(),'web integration installer missing')
        spec=importlib.util.spec_from_file_location('install_logic',PATH);self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
    def test_workspace_preserves_existing_ui_and_links_tags(self):
        src="""'use client';
import { useEffect, useMemo, useState } from 'react';
function ClaimCard({item}) {return <span>태그: {(item?.related_tags || []).join(', ') || '—'}</span>}
function Evidence(){return <span>{row.tags || '—'}</span>}
export default function App(){return (<main><button onClick={() => setDrawer(true)}><b>LM</b><span>Event Logic Master</span></button><div>untouched</div></main>);}
"""
        out=self.m.patch_workspace(src)
        self.assertIn('openLogicLibrary()',out);self.assertIn('untouched',out)
        self.assertIn('<LogicLibraryDialog />',out);self.assertIn('<LogicLinks tags={item?.related_tags || []}',out)
        self.assertEqual(self.m.patch_workspace(out),out)
    def test_unexpected_workspace_blocks_instead_of_guessing(self):
        with self.assertRaisesRegex(ValueError,'workspace'):
            self.m.patch_workspace('unrecognized source')
    def test_contract_summary_uses_generated_json(self):
        src="export const DEFAULT_LOGIC_SUMMARY = { live_rules: 53 };\nexport const X=2;"
        out=self.m.patch_contracts(src)
        self.assertIn('current-logic-summary.json',out);self.assertIn('export const X=2;',out)
    def test_bridge_uses_hash_checked_catalog(self):
        src="from triplens.agent_tools import EvidenceStore\n\ndef current_v8_manifest():\n    return {}\n\ndef live_tag_allowlist():\n    pass\n\ndef runtime_logic_rows():\n    pass\n\ndef logic_summary():\n    return {'good': True}\n"
        out=self.m.patch_bridge(src)
        self.assertIn('load_catalog(CURRENT_V8_ROOT)',out)
        self.assertIn("return {'good': True}",out)
        self.assertEqual(self.m.patch_bridge(out),out)
if __name__=='__main__':unittest.main()
