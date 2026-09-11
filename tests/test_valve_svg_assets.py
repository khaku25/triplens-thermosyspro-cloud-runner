from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ValveSvgAssetTests(unittest.TestCase):
    def test_every_fmu_connected_valve_has_a_bound_svg(self) -> None:
        with (ROOT / "config" / "fmu_valve_control_points_v1.csv").open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            points = list(csv.DictReader(stream))
        with (ROOT / "data" / "fmu_valve_ports_v1.csv").open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            ports = list(csv.DictReader(stream))

        self.assertEqual(len(points), 12)
        manifest = json.loads(
            (ROOT / "topology" / "valve_svg_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["asset_count"], 12)
        assets = {asset["control_point_id"]: asset for asset in manifest["assets"]}
        self.assertEqual(set(assets), {point["control_point_id"] for point in points})

        for point in points:
            control_id = point["control_point_id"]
            svg_path = ROOT / "topology" / assets[control_id]["svg"]
            content = svg_path.read_text(encoding="utf-8")
            ET.fromstring(content)
            self.assertIn(f'data-control-point-id="{control_id}"', content)
            point_ports = [p["port_name"] for p in ports if p["control_point_id"] == control_id]
            self.assertEqual(len(point_ports), 12)
            for port_name in point_ports:
                self.assertIn(f'data-bind="{port_name}"', content)

    def test_committed_assets_match_the_generator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "generate_valve_svg_assets.py"),
                    "--output-dir", str(target / "valves"),
                    "--overview", str(target / "fmu_valves_overview.svg"),
                    "--manifest", str(target / "valve_svg_manifest.json"),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (target / "fmu_valves_overview.svg").read_text(encoding="utf-8"),
                (ROOT / "topology" / "fmu_valves_overview.svg").read_text(encoding="utf-8"),
            )
            for svg in (target / "valves").glob("*.svg"):
                self.assertEqual(
                    svg.read_text(encoding="utf-8"),
                    (ROOT / "topology" / "valves" / svg.name).read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
