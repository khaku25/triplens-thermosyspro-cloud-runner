from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BFPBlindTests(unittest.TestCase):
    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def read_csv(path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def fixture_processbus(self) -> list[dict[str, object]]:
        rows = []
        for second in range(21):
            after = max(0.0, min(1.0, (second - 10) / 3))
            rows.append({
                "incident_id": "BLIND-INCIDENT-001",
                "time_s": second,
                "bfp_hp_speed_rpm": 1400 - 700 * after,
                "bfp_hp_mass_flow_kg_s": 100 - 75 * after,
                "bfp_hp_mechanical_power_w": 1_000_000 * (1 - after),
                "hp_drum_level_m": 1.05 - 0.15 * after,
                "ip_drum_level_m": 1.05,
                "lp_drum_level_m": 1.75,
                "hp_drum_pressure_pa": 12_000_000 - 1_000_000 * after,
                "ip_drum_pressure_pa": 2_700_000,
                "lp_drum_pressure_pa": 530_000,
                "hp_steam_flow_kg_s": 150 - 20 * after,
                "ip_steam_flow_kg_s": 175,
                "lp_steam_flow_kg_s": 195,
                "hp_feedwater_valve_pu": 0.8 + 0.15 * after,
                "ip_feedwater_valve_pu": 0.8,
                "stg_power_w": 260_000_000 - 20_000_000 * after,
                "gt_exhaust_mass_flow_kg_s": 606.94,
                "gt_exhaust_temperature_k": 893.75,
            })
        return rows

    def test_renderer_keeps_gt_normal_and_changes_only_hp_bfp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_script(
                "render_bfp_modelica.py",
                "--trip-time", "10",
                "--coastdown-duration", "3",
                "--stop-time", "20",
                "--intervals", "200",
                "--final-rpm", "700",
                "--output-dir", directory,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            model = (Path(directory) / "TripLens_CombinedCycle_BFPTrip.mo").read_text()
            self.assertIn('bfpTripTime(unit="s") = 10', model)
            self.assertIn("Finalvalue=bfpResidualSpeed", model)
            self.assertIn("20,exhaustFlowNormal", model)
            self.assertNotIn("@BFP_TRIP_TIME@", model)
            mos = (Path(directory) / "run_bfp.mos").read_text()
            self.assertIn("numberOfIntervals=200", mos)
            self.assertIn('simflags="-noEventEmit"', mos)

    def test_blind_bundle_has_three_sources_and_separate_answer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            processbus = target / "engineering" / "processbus-bfp.csv"
            self.write_csv(processbus, self.fixture_processbus())
            generate = self.run_script(
                "generate_bfp_blind.py",
                "--processbus", str(processbus),
                "--trip-time", "10",
                "--stop-time", "20",
                "--final-rpm", "700",
                "--output-dir", str(target),
            )
            self.assertEqual(generate.returncode, 0, generate.stderr)
            dcs1 = self.read_csv(target / "blind-input" / "DCS1.csv")
            dcs2 = self.read_csv(target / "blind-input" / "DCS2.csv")
            ecms = self.read_csv(target / "blind-input" / "ECMS.csv")
            self.assertIn("HP.FW.FLOW_LOW", {row["tag"] for row in dcs1})
            self.assertIn("STG.ACTIVE_POWER_LOW", {row["tag"] for row in dcs2})
            self.assertEqual(ecms[0]["tag"], "50BFP-HP.PICKUP")
            self.assertEqual(int(ecms[0]["source_time_ms"]), 10015)
            self.assertEqual(int(dcs1[0]["event_time_ms"]) - int(dcs1[0]["source_time_ms"]), 120)
            blind_text = "\n".join(path.read_text() for path in (target / "blind-input").glob("*.csv"))
            self.assertNotIn("expected_root_cause", blind_text)
            answer = json.loads((target / "ground-truth" / "answer-key.json").read_text())
            self.assertEqual(answer["source_clock_offsets_ms"]["DCS2"], -80)

            validate = self.run_script(
                "validate_bfp_blind.py",
                "--output-dir", str(target),
                "--trip-time", "10",
                "--stop-time", "20",
                "--final-rpm", "700",
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)


if __name__ == "__main__":
    unittest.main()
