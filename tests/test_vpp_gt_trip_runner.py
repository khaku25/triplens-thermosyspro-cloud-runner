from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VppGtTripRunnerTests(unittest.TestCase):
    @staticmethod
    def rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_one_command_generates_complete_registered_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "GT_TRIP_01"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_vpp_gt_trip.py"),
                    "--output-dir", str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            required = {
                "VPP.RAW.csv", "ProcessBus.csv", "VPP.EVENT.csv", "DCS1.csv",
                "DCS2.csv", "ECMS.csv", "VPP.MANIFEST.json",
                "ECMS_EVENT.csv", "VPP_EVENT.csv",
                "GT_TRIP_01.raw-manifest.json", "GT_TRIP_01.expected.json",
            }
            self.assertTrue(required.issubset({path.name for path in output.iterdir()}))

            raw = self.rows(output / "VPP.RAW.csv")
            self.assertEqual(len(raw), 5001)
            self.assertEqual(raw[999]["gt_trip_cmd"], "0")
            self.assertEqual(raw[1000]["gt_trip_cmd"], "1")
            self.assertNotIn("scenario_id", raw[0])
            self.assertNotIn("root_cause", raw[0])

            events = self.rows(output / "VPP.EVENT.csv")
            event_keys = {(row["source_time_ms"], row["canonical_tag"]) for row in events}
            self.assertIn(("1000", "CMD.GTG.TRIP"), event_keys)
            self.assertIn(("1000", "CTRL.GTG.TRIP_LATCH"), event_keys)
            self.assertIn(("1000", "CTRL.STG.TRIP_LATCH"), event_keys)
            self.assertIn(("1080", "ECMS.52GT.CLOSED"), event_keys)
            self.assertIn(("1100", "ECMS.52ST.CLOSED"), event_keys)
            self.assertEqual(
                [int(row["source_time_ms"]) for row in events],
                sorted(int(row["source_time_ms"]) for row in events),
            )

            manifest = json.loads((output / "VPP.MANIFEST.json").read_text())
            self.assertEqual(manifest["baseline"]["id"], "VPP_BASELINE_V1")
            self.assertFalse(manifest["root_cause_label_injected"])
            self.assertEqual(
                manifest["presentation_exports"]["ECMS_EVENT.csv"]["source"],
                "ECMS.csv",
            )
            self.assertIn("VPP_EVENT.csv", manifest["products"])
            self.assertEqual(
                (output / "ECMS_EVENT.csv").read_bytes(),
                (output / "ECMS.csv").read_bytes(),
            )
            self.assertEqual(
                (output / "VPP_EVENT.csv").read_bytes(),
                (output / "VPP.EVENT.csv").read_bytes(),
            )
            self.assertLess(len(self.rows(output / "VPP_EVENT.csv")), len(raw))


if __name__ == "__main__":
    unittest.main()
