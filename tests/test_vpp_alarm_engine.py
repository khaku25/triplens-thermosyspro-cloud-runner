from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VppAlarmEngineTests(unittest.TestCase):
    @staticmethod
    def write_processbus(path: Path) -> None:
        fields = [
            "scenario_id", "time_s", "gt_trip_cmd", "stg_power_w",
            "gt_exhaust_mass_flow_t_h", "gt_exhaust_temperature_k",
            "hp_drum_level_m", "hp_drum_pressure_pa", "hp_steam_flow_t_h",
        ]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for index in range(61):
                time_s = index / 10
                elapsed = max(0.0, time_s - 2.0)
                writer.writerow({
                    "scenario_id": "RUN_0001",
                    "time_s": f"{time_s:.1f}",
                    "gt_trip_cmd": int(time_s >= 2.0),
                    "stg_power_w": f"{250_000_000 * max(0.1, 1 - elapsed / 3):.3f}",
                    "gt_exhaust_mass_flow_t_h": f"{max(180, 2185.2 - 648 * elapsed):.3f}",
                    "gt_exhaust_temperature_k": f"{max(450, 894 - 160 * elapsed):.3f}",
                    "hp_drum_level_m": f"{max(0.8, 1.05 - 0.07 * elapsed):.3f}",
                    "hp_drum_pressure_pa": f"{max(8_000_000, 12_700_000 - 1_100_000 * elapsed):.3f}",
                    "hp_steam_flow_t_h": f"{max(72, 547.2 - 144 * elapsed):.3f}",
                })

    @staticmethod
    def rows(path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_processbus_run_generates_owned_deduplicated_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            source = target / "generator-output.csv"
            output = target / "bundle"
            self.write_processbus(source)
            before = self.digest(source)
            completed = subprocess.run([
                sys.executable, str(ROOT / "scripts/vpp_alarm_engine.py"),
                "--raw", str(source),
                "--event-time", "2",
                "--output-dir", str(output),
            ], cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(self.digest(source), before)
            self.assertEqual((output / "VPP.RAW.csv").read_bytes(), source.read_bytes())
            for name in ("VPP.EVENT.csv", "DCS1.csv", "DCS2.csv", "ECMS.csv", "VPP.MANIFEST.json"):
                self.assertTrue((output / name).is_file(), name)

            events = self.rows(output / "VPP.EVENT.csv")
            self.assertTrue(events)
            self.assertEqual(
                [int(row["source_time_ms"]) for row in events],
                sorted(int(row["source_time_ms"]) for row in events),
            )
            self.assertEqual({row["source_system"] for row in events}, {"DCS1", "DCS2", "ECMS"})
            keys = [(
                row["source_time_ms"], row["source_system"], row["canonical_tag"],
                row["event_state"], row["event_class"], row["old_value"], row["new_value"],
            ) for row in events]
            self.assertEqual(len(keys), len(set(keys)))
            self.assertTrue(any(row["canonical_tag"] == "CMD.GTG.TRIP" for row in events))
            self.assertFalse(any("root_cause" in value.lower() for row in events for value in row.values()))

            manifest = json.loads((output / "VPP.MANIFEST.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["source_mutated"])
            self.assertFalse(manifest["root_cause_label_injected"])
            self.assertEqual(manifest["event_count"], len(events))
            self.assertEqual(manifest["source_sha256"], before)
            self.assertEqual(manifest["baseline"]["id"], "VPP_BASELINE_V1")
            self.assertNotIn("scenario_id", manifest)

    def test_rejects_mismatched_dcs_ownership(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import vpp_alarm_engine
            with self.assertRaisesRegex(ValueError, "owned by DCS2"):
                vpp_alarm_engine.normalize_dcs_event({
                    "system": "DCS2", "source_time_ms": "1", "event_time_ms": "1",
                }, "DCS1.csv", 0.0)
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
