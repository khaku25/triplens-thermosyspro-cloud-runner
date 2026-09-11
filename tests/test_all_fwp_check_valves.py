from __future__ import annotations

import csv
import importlib.util
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
PATCHER = ROOT / "scripts" / "patch_all_fwp_check_valves.py"
GENERATOR = ROOT / "scripts" / "generate_fwp_check_valve_svg_assets.py"
NODE_CONTRACT = ROOT / "data" / "opcua_fwp_check_valve_nodes_v1.csv"
VISUAL_INVENTORY = ROOT / "config" / "opcua_fwp_check_valves_v1.csv"
MANIFEST = ROOT / "topology" / "opcua" / "check_valves" / "fwp_check_valve_svg_manifest.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AllFWPCheckValveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with NODE_CONTRACT.open(encoding="utf-8-sig", newline="") as stream:
            cls.nodes = list(csv.DictReader(stream))
        with VISUAL_INVENTORY.open(encoding="utf-8", newline="") as stream:
            cls.assets = list(csv.DictReader(stream))

    def test_model_patcher_rewires_all_three_physical_fwp_discharges(self):
        patcher = load_module("patch_all_fwp_check_valves", PATCHER)
        source = '''within ThermoSysPro.Examples.CombinedCyclePowerPlant;
model CombinedCycle_TripTAC
  // TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V13
  // TRIPLENS_LP_FWP_OPCUA_ADAPTER_V1
  TripLens_PumpPhysics.SpringLoadedCheckValve vppLPFWPCheckValve;
  output Boolean vppLPFWPCheckValveOpen;
  output Real vppLPFWPCheckValveOpening;
  parameter Real CstHP(fixed=false,start=7618660.65374636);
equation
  connect(Vanne_alimentationMPHP1.C1, PompeAlimHP.C2);
  connect(PompeAlimMP.C2, Vanne_alimentationMPHP2.C1);
  connect(PompeAlimBP.C2, vppLPFWPCheckValve.C1);
  connect(vppLPFWPCheckValve.C2, vanne_extraction.C1);
  // The native OPC UA server permits writes to continuous states.
end CombinedCycle_TripTAC;
'''
        patched = patcher.patch_model(source)
        self.assertNotIn(
            "connect(Vanne_alimentationMPHP1.C1, PompeAlimHP.C2);", patched
        )
        self.assertNotIn(
            "connect(PompeAlimMP.C2, Vanne_alimentationMPHP2.C1);", patched
        )
        for level in ("HP", "IP", "LP"):
            for suffix in (
                "Open", "Opening", "MassFlowTH", "DeltaPPa", "InletPressurePa",
                "OutletPressurePa", "ResistancePaSPerKg",
            ):
                self.assertIn(f"vpp{level}FWPCheckValve{suffix}", patched)

    def test_contract_has_three_valves_and_all_21_physical_read_nodes(self):
        self.assertEqual(len(self.nodes), 21)
        self.assertEqual(len({row["canonical_tag"] for row in self.nodes}), 21)
        self.assertEqual(len({row["opcua_browse_name"] for row in self.nodes}), 21)
        self.assertEqual({row["direction"] for row in self.nodes}, {"READ"})
        self.assertEqual({row["layer"] for row in self.nodes}, {"PHYSICAL"})
        for level in ("HP", "IP", "LP"):
            scoped = [row for row in self.nodes if f"FWP-{level}" in row["canonical_tag"]]
            self.assertEqual(len(scoped), 7)

    def test_runtime_client_reads_every_check_valve_node(self):
        client = load_module("native_ecms_opcua_client_all_fwp", ROOT / "scripts" / "native_ecms_opcua_client.py")
        runtime_nodes = {signal.node_name for signal in client.SIGNALS}
        contract_nodes = {row["opcua_browse_name"] for row in self.nodes}
        self.assertTrue(contract_nodes <= runtime_nodes)

    def test_signal_map_covers_every_canonical_and_browse_name(self):
        signal_map = json.loads((ROOT / "config" / "signal_map.json").read_text(encoding="utf-8"))
        aliases = {
            alias
            for definition in signal_map["signals"].values()
            for alias in definition.get("aliases", [])
        }
        for row in self.nodes:
            self.assertIn(row["canonical_tag"], aliases)
            self.assertIn(row["opcua_browse_name"], aliases)

    def test_svg_assets_are_current_opcua_only_and_bind_all_values(self):
        generator = load_module("generate_fwp_check_valve_svg_assets", GENERATOR)
        generator.generate(check=True)
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["check_valve_count"], 3)
        self.assertEqual(manifest["feedback_node_count"], 21)
        for asset in self.assets:
            path = ROOT / asset["svg"]
            ET.parse(path)
            content = path.read_text(encoding="utf-8")
            self.assertIn("OPC UA", content)
            self.assertNotIn("FMU", content)
            self.assertIn('data-symbol-type="SPRING_CHECK_VALVE"', content)
            self.assertIn('data-symbol-convention="ISO-10628-style"', content)
            for key in (
                "open_node", "opening_node", "flow_node", "delta_p_node",
                "inlet_p_node", "outlet_p_node", "resistance_node",
            ):
                self.assertIn(asset[key], content)
            self.assertEqual(content.count('data-opcua-access="READ_ONLY"'), 1)
            self.assertNotIn("<text", content)
            self.assertIn('width="512" height="512"', content)


if __name__ == "__main__":
    unittest.main()
