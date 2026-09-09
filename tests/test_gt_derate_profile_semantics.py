from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GtDerateProfileSemanticsTests(unittest.TestCase):
    def test_legacy_gt_trip_sampling_profile_is_removed(self) -> None:
        paths = [
            ROOT / ".github" / "workflows" / "run-thermosyspro.yml",
            ROOT / "scripts" / "run_pipeline.sh",
            ROOT / "scripts" / "build_raw_manifest.py",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("gt_trip_3min_10ms", text, str(path))
            self.assertIn("gt_derate_3min_10ms", text, str(path))

    def test_derate_profile_suppresses_embedded_st_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "render_modelica.py"),
                    "--trip-time", "2",
                    "--trip-ramp-duration", "1",
                    "--stop-time", "5",
                    "--intervals", "50",
                    "--derate-only",
                    "--template-dir", str(ROOT / "modelica"),
                    "--output-dir", str(output_dir),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            model = (output_dir / "TripLens_CombinedCycle_TripTAC.mo").read_text(
                encoding="utf-8"
            )
            self.assertIn('parameter Real eventTime(unit="s") = 2;', model)
            self.assertIn('parameter Real boundaryRampDuration(unit="s") = 1;', model)
            self.assertIn('parameter Real exhaustFlowDerated(unit="kg/s") = 150.0;', model)
            self.assertIn('parameter Real exhaustTemperatureDerated(unit="K") = 550.0;', model)
            self.assertIn("vppTripTime=6,", model)
            self.assertIn(
                "eventTime + boundaryRampDuration,exhaustFlowDerated", model
            )
            self.assertIn(
                "eventTime + boundaryRampDuration,exhaustTemperatureDerated", model
            )

    def test_true_gt_trip_remains_on_separate_vpp_ecms_path(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "run-vpp-gt-trip.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("name: Run VPP GT Trip Scenario", workflow)
        self.assertIn("scripts/run_vpp_gt_trip.py", workflow)
        self.assertIn("ECMS_EVENT.csv", workflow)
        self.assertIn("VPP_EVENT.csv", workflow)

        with (ROOT / "config" / "ecms_command_catalog.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))
        gt_trip = next(
            row for row in rows
            if row["equipment_id"] == "GTG" and row["command"] == "TRIP"
        )
        gt_derate = next(
            row for row in rows
            if row["equipment_id"] == "GTG" and row["command"] == "DERATE"
        )
        self.assertEqual(gt_trip["model_input"], "GT_TRIP")
        self.assertEqual(gt_trip["feedback_tag"], "ECMS.52GT.CLOSED")
        self.assertIn("CLOSED=0", gt_trip["notes"])
        self.assertNotIn("150/550", gt_trip["notes"])
        self.assertEqual(gt_derate["model_input"], "GT_DERATE_CMD")
        self.assertIn("150/550", gt_derate["notes"])
        self.assertIn("breaker", gt_derate["notes"].lower())


if __name__ == "__main__":
    unittest.main()
