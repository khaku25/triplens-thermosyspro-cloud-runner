from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PhysicalHandoffTests(unittest.TestCase):
    def run_script(self, name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def write_raw(path: Path) -> None:
        fields = [
            "time", "vppGTTripCmd", "vppGTTripLatch", "vppSTTripLatch",
            "vpp52GTTripCmd", "vpp52GTClosed", "vpp52STTripCmd",
            "vpp52STClosed", "vppGTGPowerMW", "vppGTGSpeedRPM",
            "Alternateur.Welec", "vppGTExhaustMassFlowTH",
            "Temperature.y.signal", "BallonHP.yLevel.signal",
            "BallonMP.yLevel.signal", "BallonBP.yLevel.signal",
            "BallonHP.P", "BallonMP.P", "BallonBP.P",
            "vppHPTurbineSteamFlowTH", "vppIPTurbineSteamFlowTH",
            "vppLPTurbineSteamFlowTH", "vppHPAdmissionPos",
            "vppIPAdmissionPos", "vppLPDrumAdmissionMultiplier",
            "vppHPBypassPos", "vppLPBypassPos", "vppHPBypassMassFlowTH",
            "vppLPBypassMassFlowTH", "vppCondenserPressure",
            "vppCondenserLevel",
        ]
        samples = [
            # time, GT trip, GT latch, ST latch, 52GT cmd/closed, 52ST cmd/closed,
            # GT MW, speed, ST W
            (0.000, 0, 0, 0, 0, 1, 0, 1, 137.125, 3600, 241_250_000),
            (2.000, 1, 1, 1, 0, 1, 1, 1, 137.125, 3600, 241_250_000),
            (2.055, 1, 1, 1, 1, 1, 1, 1, 117.250, 3600, 220_000_000),
            (2.080, 1, 1, 1, 1, 0, 1, 1, 0.0, 3600, 210_000_000),
            (2.100, 1, 1, 1, 1, 0, 1, 0, 0.0, 3540, 205_000_000),
            (3.000, 1, 1, 1, 1, 0, 1, 0, 0.0, 1600, 75_000_000),
        ]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for sample in samples:
                time_s, gt, gt_latch, st_latch, gt_cmd, gt_closed, st_cmd, st_closed, gt_mw, speed, st_w = sample
                elapsed = max(0.0, time_s - 2.0)
                writer.writerow({
                    "time": f"{time_s:.3f}",
                    "vppGTTripCmd": gt,
                    "vppGTTripLatch": gt_latch,
                    "vppSTTripLatch": st_latch,
                    "vpp52GTTripCmd": gt_cmd,
                    "vpp52GTClosed": gt_closed,
                    "vpp52STTripCmd": st_cmd,
                    "vpp52STClosed": st_closed,
                    "vppGTGPowerMW": f"{gt_mw:.6f}",
                    "vppGTGSpeedRPM": f"{speed:.6f}",
                    "Alternateur.Welec": f"{st_w:.6f}",
                    "vppGTExhaustMassFlowTH": f"{max(0, 2184.984 - elapsed*1000):.6f}",
                    "Temperature.y.signal": f"{max(400, 893.75 - elapsed*200):.6f}",
                    "BallonHP.yLevel.signal": f"{1.05 - elapsed*0.02:.6f}",
                    "BallonMP.yLevel.signal": f"{1.05 - elapsed*0.02:.6f}",
                    "BallonBP.yLevel.signal": f"{1.75 - elapsed*0.05:.6f}",
                    "BallonHP.P": "12681000",
                    "BallonMP.P": "2548600",
                    "BallonBP.P": "563775",
                    "vppHPTurbineSteamFlowTH": f"{max(0, 546 - elapsed*200):.6f}",
                    "vppIPTurbineSteamFlowTH": f"{max(0, 636 - elapsed*220):.6f}",
                    "vppLPTurbineSteamFlowTH": f"{max(0, 708 - elapsed*250):.6f}",
                    "vppHPAdmissionPos": f"{max(0.001, 0.8 - elapsed):.6f}",
                    "vppIPAdmissionPos": f"{max(0.001, 0.8 - elapsed):.6f}",
                    "vppLPDrumAdmissionMultiplier": f"{max(0.001, 1 - elapsed):.6f}",
                    "vppHPBypassPos": f"{min(1, elapsed):.6f}",
                    "vppLPBypassPos": f"{min(1, elapsed):.6f}",
                    "vppHPBypassMassFlowTH": f"{max(0, elapsed*100):.6f}",
                    "vppLPBypassMassFlowTH": f"{max(0, elapsed*120):.6f}",
                    "vppCondenserPressure": f"{6136 + elapsed*100:.6f}",
                    "vppCondenserLevel": f"{1.5 + elapsed*0.01:.6f}",
                })

    def prepare(self, target: Path) -> tuple[Path, Path, Path]:
        raw = target / "raw.csv"
        processbus = target / "ProcessBus.csv"
        review = target / "review.json"
        self.write_raw(raw)
        result = self.run_script(
            "normalize_processbus.py",
            "--input", str(raw),
            "--output", str(processbus),
            "--mapping-review", str(review),
            "--event-time", "2",
            "--no-legacy-gt-trip-cmd",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return raw, processbus, review

    def test_ecms_handoff_is_an_exact_processbus_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw, processbus, review = self.prepare(target)
            handoff = target / "ECMS-physical.csv"
            manifest = target / "ECMS-PHYSICAL-MANIFEST.json"
            result = self.run_script(
                "build_ecms_physical_handoff.py",
                "--raw", str(raw), "--processbus", str(processbus),
                "--mapping-review", str(review), "--output", str(handoff),
                "--manifest-output", str(manifest),
                "--require-signal", "gtg_power_mw",
                "--require-signal", "cb_52gt_closed",
                "--require-signal", "lp_drum_level_m",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = target / "report.json"
            verify = self.run_script(
                "validate_physical_handoff.py",
                "--raw", str(raw), "--processbus", str(processbus),
                "--handoff", str(handoff), "--manifest", str(manifest),
                "--report", str(report),
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)
            evidence = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "PASS")
            self.assertEqual(evidence["value_mismatch_count"], 0)
            self.assertEqual(evidence["max_source_time_offset_ms"], 0)

    def test_ecms_trend_uses_observed_generator_and_breaker_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            _raw, processbus, _review = self.prepare(target)
            trend = target / "trend.csv"
            events = target / "events.csv"
            result = self.run_script(
                "generate_ecms.py",
                "--processbus", str(processbus),
                "--event-time", "2",
                "--no-scenario-gt-trip",
                "--physical-source-policy", "require-observed",
                "--trend-output", str(trend),
                "--event-output", str(events),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with trend.open(encoding="utf-8-sig", newline="") as stream:
                by_time = {row["source_time_ms"]: row for row in csv.DictReader(stream)}
            self.assertEqual(by_time["0"]["gtg_power_mw"], "137.125000")
            self.assertEqual(by_time["2080"]["cb_52gt_closed"], "0")
            self.assertEqual(by_time["2080"]["gtg_power_mw"], "0.000000")
            self.assertEqual(by_time["2100"]["cb_52st_closed"], "0")
            self.assertGreater(float(by_time["2100"]["stg_power_mw"]), 0)

    def test_required_observed_policy_fails_when_gt_generator_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            _raw, processbus, _review = self.prepare(target)
            with processbus.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                fields = [field for field in (reader.fieldnames or []) if field != "gtg_power_mw"]
                rows = list(reader)
            with processbus.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows({field: row.get(field, "") for field in fields} for row in rows)
            result = self.run_script(
                "generate_ecms.py", "--processbus", str(processbus),
                "--event-time", "2", "--no-scenario-gt-trip",
                "--physical-source-policy", "require-observed",
                "--trend-output", str(target / "trend.csv"),
                "--event-output", str(target / "events.csv"),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("gtg_power_mw", result.stderr)

    def test_alarm_engine_publishes_verified_physical_dashboard_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "openmodelica-raw.csv"
            self.write_raw(raw)
            output = target / "integration"
            result = self.run_script(
                "vpp_alarm_engine.py",
                "--raw", str(raw),
                "--input-kind", "raw",
                "--event-time", "2",
                "--output-dir", str(output),
                "--physical-source-policy", "require-observed",
                "--physical-handoff",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = {
                "ECMS-physical.csv", "ECMS-PHYSICAL-MANIFEST.json",
                "PHYSICAL-HANDOFF-REPORT.json", "ECMS-physical-dashboard.html",
                "ECMS-physical-dashboard.svg",
                "ECMS-trend.csv", "ECMS.csv", "DCS1.csv", "DCS2.csv",
                "VPP.EVENT.csv", "VPP.MANIFEST.json",
            }
            self.assertTrue(expected.issubset({path.name for path in output.iterdir()}))
            report = json.loads(
                (output / "PHYSICAL-HANDOFF-REPORT.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["value_mismatch_count"], 0)
            manifest = json.loads(
                (output / "VPP.MANIFEST.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["physical_handoff"]["value_policy"],
                "NO_ECMS_RECALCULATION_NO_INTERPOLATION",
            )


if __name__ == "__main__":
    unittest.main()
