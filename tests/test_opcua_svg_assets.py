import csv
import importlib.util
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
INVENTORY = ROOT / "config" / "opcua_visual_assets_v1.csv"
MANIFEST = ROOT / "topology" / "opcua" / "opcua_svg_manifest.json"
GENERATOR = ROOT / "scripts" / "generate_opcua_svg_assets.py"
CLIENT = ROOT / "scripts" / "native_ecms_opcua_client.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class OPCUASVGAssetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with INVENTORY.open(encoding="utf-8", newline="") as stream:
            cls.assets = list(csv.DictReader(stream))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_inventory_covers_current_opcua_actuators(self):
        expected = {
            "HP_TURB_ADM_VLV", "IP_TURB_ADM_VLV", "LP_DRUM_ADM_VLV",
            "HP_BYPASS_VLV", "LP_BYPASS_VLV", "HP_SPRAY_VLV", "LP_SPRAY_VLV",
        }
        self.assertEqual({row["asset_id"] for row in self.assets}, expected)

    def test_visual_nodes_are_in_runtime_read_contract(self):
        client = load_module("native_ecms_opcua_client", CLIENT)
        runtime_nodes = {signal.node_name for signal in client.SIGNALS}
        visual_nodes = {
            row[key]
            for row in self.assets
            for key in ("position_node", "flow_node")
        }
        self.assertTrue(visual_nodes <= runtime_nodes)
        self.assertEqual({row["command_source"] for row in self.assets}, {"vppSTTripLatch"})

    def test_generated_files_are_current(self):
        generator = load_module("generate_opcua_svg_assets", GENERATOR)
        generator.generate(check=True)

    def test_manifest_and_svg_are_opcua_only(self):
        self.assertEqual(self.manifest["node_locator"], "BrowseName")
        self.assertEqual(self.manifest["actuator_asset_count"], 7)
        self.assertEqual(
            self.manifest["write_nodes"][0]["browse_name"],
            "vppExternalTripCommandNative",
        )
        paths = [ROOT / row["svg"] for row in self.assets]
        paths.extend([
            ROOT / "topology/opcua/opcua_actuator_overview.svg",
            ROOT / "topology/opcua/opcua_process_wiring.svg",
        ])
        for path in paths:
            self.assertTrue(path.is_file(), path)
            ET.parse(path)
            content = path.read_text(encoding="utf-8")
            self.assertIn("OPC UA", content)
            self.assertNotIn("FMU", content)
            self.assertNotIn("FMI", content)

    def test_every_asset_contains_its_two_feedback_browse_names(self):
        for row in self.assets:
            content = (ROOT / row["svg"]).read_text(encoding="utf-8")
            self.assertIn(row["position_node"], content)
            self.assertIn(row["flow_node"], content)
            self.assertIn('data-opcua-access="READ_ONLY"', content)

    def test_spray_implementation_is_not_misrepresented(self):
        spray = [row for row in self.assets if row["actuator_kind"] == "SPRAY_FLOW_SOURCE"]
        self.assertEqual(len(spray), 2)
        for row in spray:
            content = (ROOT / row["svg"]).read_text(encoding="utf-8")
            self.assertIn("FLOW SOURCE + INJECTOR", content)


if __name__ == "__main__":
    unittest.main()
