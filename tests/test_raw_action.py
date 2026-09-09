from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RawOnlyActionTests(unittest.TestCase):
    def run_script(self, name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def build_bundle(self, target: Path) -> None:
        raw = target / "thermosyspro-raw.csv"
        shutil.copy2(ROOT / "tests" / "fixtures" / "thermosyspro-raw.csv", raw)
        result = self.run_script(
            "build_raw_manifest.py",
            "--raw-file", str(raw),
            "--output", str(target / "raw-manifest.json"),
            "--sampling-profile", "causal_100ms",
            "--stop-time", "10",
            "--output-intervals", "100",
            "--thermosyspro-commit", "test-commit",
            "--openmodelica-image", "test-image",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_raw_bundle_passes_without_scenario_or_answer_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.build_bundle(target)
            result = self.run_script(
                "validate_raw_outputs.py", "--output-dir", str(target)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(
                (target / "raw-manifest.json").read_text(encoding="utf-8")
            )
            serialized = json.dumps(manifest).lower()
            self.assertNotIn("gt_trip_tac", serialized)
            self.assertNotIn('"trip_time', serialized)
            self.assertNotIn("scenario", manifest)
            self.assertNotIn("root_cause", manifest)
            self.assertNotIn("ground_truth", manifest)
            self.assertFalse(manifest["boundary"]["scenario_label_included"])
            self.assertFalse(manifest["boundary"]["root_cause_label_included"])
            self.assertEqual(
                manifest["boundary"]["action_output"], ["MODELICA_RAW_PHYSICS"]
            )

    def test_derived_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.build_bundle(target)
            (target / "ECMS.csv").write_text("time,tag\n0,FAKE\n", encoding="utf-8")
            result = self.run_script(
                "validate_raw_outputs.py", "--output-dir", str(target)
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unexpected files", result.stderr)

    def test_native_duplicate_event_times_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "thermosyspro-raw.csv"
            raw.write_text('"time","x"\n0,1\n1,2\n1,3\n2,4\n', encoding="utf-8")
            result = self.run_script(
                "build_raw_manifest.py",
                "--raw-file", str(raw),
                "--output", str(target / "raw-manifest.json"),
                "--sampling-profile", "standard",
                "--stop-time", "2",
                "--output-intervals", "2",
                "--thermosyspro-commit", "test-commit",
                "--openmodelica-image", "test-image",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            validate = self.run_script(
                "validate_raw_outputs.py", "--output-dir", str(target)
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)
            manifest = json.loads(
                (target / "raw-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["raw"]["duplicate_native_time_rows"], 1)

    def test_both_action_runners_exclude_downstream_conversion(self) -> None:
        workflow_paths = [
            ROOT / ".github" / "workflows" / "run-thermosyspro.yml",
            ROOT / ".github" / "workflows" / "run-bfp-trip-blind.yml",
        ]
        runner_paths = [
            ROOT / "scripts" / "run_pipeline.sh",
            ROOT / "scripts" / "run_bfp_blind_pipeline.sh",
        ]
        forbidden_calls = (
            "normalize_processbus.py",
            "normalize_bfp_processbus.py",
            "extract_incident_window.py",
            "generate_dcs_alarms.py",
            "generate_ecms.py",
            "generate_bfp_blind.py",
            "GT_TRIP_RAW_DATA.csv",
            "answer-key.json",
        )
        for path in workflow_paths + runner_paths:
            content = path.read_text(encoding="utf-8")
            executable_text = "\n".join(
                line for line in content.splitlines()
                if not line.lstrip().startswith("#")
            )
            for forbidden in forbidden_calls:
                self.assertNotIn(forbidden, executable_text, f"{path}: {forbidden}")

        for workflow_path in workflow_paths:
            workflow = workflow_path.read_text(encoding="utf-8")
            self.assertNotIn("fault_preset", workflow.lower())
            self.assertNotIn("command_scenario", workflow.lower())
            upload_block = workflow.split("path: |", 1)[1].split(
                "if-no-files-found", 1
            )[0]
            self.assertEqual(
                [line.strip() for line in upload_block.splitlines() if line.strip()],
                ["outputs/thermosyspro-raw.csv", "outputs/raw-manifest.json"],
            )

    def test_gt_physical_runner_applies_dynamic_bypass_patch(self) -> None:
        runner = (ROOT / "scripts" / "run_pipeline.sh").read_text(encoding="utf-8")
        model = (
            ROOT / "modelica" / "TripLens_CombinedCycle_TripTAC.mo.tpl"
        ).read_text(encoding="utf-8")
        mos = (ROOT / "modelica" / "run.mos.tpl").read_text(encoding="utf-8")

        self.assertIn("patch_turbine_bypass_model.py", runner)
        self.assertIn("HPBP_LPBP_DYNAMIC_V9", runner)
        self.assertIn("TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V9", runner)
        self.assertIn("vppTripTime=tripTime", model)
        self.assertIn("HPBypassMassFlow", mos)
        self.assertIn("LPBypassMassFlow", mos)
        self.assertNotIn("nlssMaxDensity=0", mos)
        self.assertNotIn("nls=hybrid", mos)
        self.assertNotIn("iim=none", mos)
        self.assertIn("LOG_NLS", mos)
        self.assertNotIn("LOG_NLS_V", mos)
        self.assertIn("CondenserPressure", mos)

    def test_one_ms_dynamic_bypass_raw_meets_stroke_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "thermosyspro-raw.csv"
            columns = [
                "time",
                "vppSTTripLatch",
                "vppHPAdmissionPos",
                "vppIPAdmissionPos",
                "vppLPDrumAdmissionMultiplier",
                "vppHPBypassCmd",
                "vppLPBypassCmd",
                "vppHPBypassPos",
                "vppLPBypassPos",
                "vppHPSprayPos",
                "vppLPSprayPos",
                "vppHPBypassOpenLS",
                "vppHPBypassCloseLS",
                "vppLPBypassOpenLS",
                "vppLPBypassCloseLS",
                "vppHPBypassMassFlow",
                "vppLPBypassMassFlow",
                "vppHPSprayMassFlow",
                "vppLPSprayMassFlow",
                "vppHPBypassInletPressure",
                "vppLPBypassInletPressure",
                "vppHPBypassOutletPressure",
                "vppLPBypassOutletPressure",
                "vppHPBypassInletTemperature",
                "vppLPBypassInletTemperature",
                "vppHPBypassOutletTemperature",
                "vppLPBypassOutletTemperature",
                "vppCondenserPressure",
                "vppCondenserLevel",
            ]
            leakage = 0.0
            trip_time = 0.1

            def opening(elapsed: float, stroke95: float) -> float:
                if elapsed < 0:
                    return leakage
                tau = stroke95 / -math.log(0.05)
                return 1 - (1 - leakage)*math.exp(-elapsed/tau)

            def closing(elapsed: float, initial: float, stroke95: float) -> float:
                if elapsed < 0:
                    return initial
                tau = stroke95 / -math.log(0.05)
                return initial*math.exp(-elapsed/tau)

            with raw.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(columns)
                for index in range(1001):
                    time_s = index / 1000
                    elapsed = time_s - trip_time
                    tripped = elapsed >= 0
                    hp_pos = opening(elapsed, 0.300)
                    lp_pos = opening(elapsed, 0.400)
                    spray_pos = opening(elapsed, 0.050) if tripped else 0.0
                    hp_admission = closing(elapsed, 0.8, 0.150)
                    lp_drum = closing(elapsed, 1.0, 0.150)
                    writer.writerow(
                        [
                            time_s,
                            tripped,
                            hp_admission,
                            hp_admission,
                            lp_drum,
                            1 if tripped else leakage,
                            1 if tripped else leakage,
                            hp_pos,
                            lp_pos,
                            spray_pos,
                            spray_pos,
                            hp_pos >= 0.95,
                            hp_pos <= 0.01,
                            lp_pos >= 0.95,
                            lp_pos <= 0.01,
                            hp_pos*151.696,
                            lp_pos*176.758,
                            spray_pos*10,
                            spray_pos*20,
                            12681000,
                            2548600,
                            2726700,
                            6136,
                            813,
                            813,
                            723,
                            373,
                            6136,
                            1.5,
                        ]
                    )
            build = self.run_script(
                "build_raw_manifest.py",
                "--raw-file", str(raw),
                "--output", str(target / "raw-manifest.json"),
                "--sampling-profile", "incident_1ms",
                "--stop-time", "1",
                "--output-intervals", "1000",
                "--thermosyspro-commit", "test-commit",
                "--openmodelica-image", "test-image",
                "--model-variant", "HPBP_LPBP_DYNAMIC_V9",
                "--source-patch-marker", "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V9",
                "--patched-model-sha256", "a"*64,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            validate = self.run_script(
                "validate_raw_outputs.py", "--output-dir", str(target)
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)
            self.assertIn("DYNAMIC_BYPASS_VALIDATION_PASS", validate.stdout)

    def test_raw_validator_rejects_answer_metadata_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "thermosyspro-raw.csv"
            raw.write_text(
                '"time","x","root_cause"\n0,1,KNOWN\n1,2,KNOWN\n',
                encoding="utf-8",
            )
            result = self.run_script(
                "build_raw_manifest.py",
                "--raw-file", str(raw),
                "--output", str(target / "raw-manifest.json"),
                "--sampling-profile", "standard",
                "--stop-time", "1",
                "--output-intervals", "1",
                "--thermosyspro-commit", "test-commit",
                "--openmodelica-image", "test-image",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            validate = self.run_script(
                "validate_raw_outputs.py", "--output-dir", str(target)
            )
            self.assertNotEqual(validate.returncode, 0)
            self.assertIn("answer/scenario metadata", validate.stderr)


if __name__ == "__main__":
    unittest.main()
