from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.render_pump_fleet_model import PUMP_TARGETS, transform


ROOT = Path(__file__).resolve().parents[1]


MINIMAL_UPSTREAM = '''within ThermoSysPro.Examples.CombinedCyclePowerPlant;
model CombinedCycle_TripTAC
  "CCPP model to simulate a load variation from 100% to 50%"
  ThermoSysPro.WaterSteam.Machines.StaticCentrifugalPump PompeAlimMP(
    a3=350);
  ThermoSysPro.WaterSteam.Machines.StaticCentrifugalPump PompeAlimHP(
    a3=1600);
  ThermoSysPro.WaterSteam.Machines.StaticCentrifugalPump PompeAlimBP(
    a3=400);
  Control.Drum_LevelControl regulation_Niveau_BP;
  FlueGases.BoundaryConditions.SourceQ SourceFumees;
  InstrumentationAndControl.Blocks.Tables.Table1DTemps Debit;
  InstrumentationAndControl.Blocks.Tables.Table1DTemps Temperature;
equation
  connect(Vanne_alimentationMPHP1.C1, PompeAlimHP.C2);
  connect(PompeAlimMP.C2, Vanne_alimentationMPHP2.C1);
  connect(PompeAlimBP.C2, vanne_extraction.C1);
  connect(PompeAlimMP.rpm_or_mpower, arretPomesMp.y);
  connect(PompeAlimHP.rpm_or_mpower, arretPomesHP.y);
  connect(PompeAlimBP.rpm_or_mpower, arretPomesBP.y);
end CombinedCycle_TripTAC;
'''


class PumpPhysicsTests(unittest.TestCase):
    def test_renderer_replaces_every_real_upstream_pump(self) -> None:
        model = transform(MINIMAL_UPSTREAM, trip_target=1, trip_time=300)
        self.assertEqual(model.count("DynamicCentrifugalPump PompeAlim"), 3)
        self.assertNotIn("StaticCentrifugalPump PompeAlim", model)
        self.assertNotIn("rpm_or_mpower", model)
        self.assertNotIn("  Control.Drum_LevelControl", model)
        self.assertIn(
            "ThermoSysPro.Examples.CombinedCyclePowerPlant.Control.Drum_LevelControl",
            model,
        )
        self.assertIn(
            "ThermoSysPro.FlueGases.BoundaryConditions.SourceQ SourceFumees",
            model,
        )
        self.assertEqual(
            model.count(
                "ThermoSysPro.InstrumentationAndControl.Blocks.Tables.Table1DTemps"
            ),
            2,
        )
        for pressure in ("HP", "IP", "LP"):
            self.assertIn(f"BreakerTorqueDrive drive{pressure}", model)
            self.assertIn(f"IdealCheckValve checkValve{pressure}", model)
            self.assertIn(f"checkValve{pressure}.C1", model)
            self.assertIn(f"checkValve{pressure}.C2", model)
        self.assertIn("connect(cwPumpDrive.massFlow, SourceCaloporteur.IMassFlow)", model)
        self.assertIn("tripTarget = 1", model)
        self.assertIn("pumpTripTime(unit=\"s\") = 300", model)

    def test_registry_accounts_for_every_ecms_pump_without_inventing_recirc(self) -> None:
        with (ROOT / "config" / "ecms_a_equipment.csv").open(
            "r", encoding="utf-8", newline=""
        ) as stream:
            equipment = {row["equipment_id"] for row in csv.DictReader(stream)}
        with (ROOT / "config" / "pump_physics_registry.csv").open(
            "r", encoding="utf-8", newline=""
        ) as stream:
            registry = {row["equipment_id"]: row for row in csv.DictReader(stream)}

        self.assertEqual(set(registry), equipment)
        self.assertEqual(PUMP_TARGETS["FWP-LP"], PUMP_TARGETS["COND-PUMP"])
        for item in ("RECIRC-HP", "RECIRC-IP", "RECIRC-LP"):
            self.assertEqual(
                registry[item]["implementation_status"],
                "NATURAL_CIRCULATION_NOT_MOTOR_PUMP",
            )
            self.assertEqual(registry[item]["trip_target"], "")

    def test_processbus_normalizer_accepts_native_modelica_booleans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "raw.csv"
            raw.write_text(
                "time,breakerHPClosed,driveHP.motorTorque,PompeAlimHP.VRot\n"
                "0,true,8000,1400\n"
                "1,false,0,1300\n",
                encoding="utf-8",
            )
            output = target / "processbus.csv"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "normalize_processbus.py"),
                    "--input", str(raw),
                    "--output", str(output),
                    "--scenario-id", "PUMP_TEST",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with output.open("r", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["fwp_hp_breaker_closed"], "1")
            self.assertEqual(rows[1]["fwp_hp_breaker_closed"], "0")
            self.assertEqual(rows[1]["fwp_hp_motor_torque_nm"], "0")
            review = json.loads((target / "signal-mapping-review.json").read_text())
            self.assertIn("fwp_hp_breaker_closed", review["canonical_signals_present"])


if __name__ == "__main__":
    unittest.main()
