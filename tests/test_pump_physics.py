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
  ThermoSysPro.WaterSteam.HeatExchangers.SimpleDynamicCondenser Condenseur(
    V=1);
  ThermoSysPro.WaterSteam.Machines.Generator Alternateur;
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve
    vanne_entree_TurbineHP;
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve
    vanne_entree_TurbineMP;
  InstrumentationAndControl.Blocks.Tables.Table1DTemps
    ConstantVanneTurbineHP;
  InstrumentationAndControl.Blocks.Tables.Table1DTemps
    ConstantVanneTurbineMP;
equation
  connect(ConstantVanneTurbineHP.y, vanne_entree_TurbineHP.Ouv);
  connect(ConstantVanneTurbineMP.y, vanne_entree_TurbineMP.Ouv);
  connect(Debit.y,SourceFumees. IMassFlow);
  connect(Temperature.y,SourceFumees. ITemperature);
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
        pumps = {
            1: ("PompeAlimHP", "HP"),
            2: ("PompeAlimMP", "IP"),
            3: ("PompeAlimBP", "LP"),
        }
        all_components = {component for component, _ in pumps.values()}
        for target, (component, axis) in pumps.items():
            with self.subTest(target=target):
                model = transform(MINIMAL_UPSTREAM, trip_target=target, trip_time=300)
                self.assertNotIn("DynamicCentrifugalPump PompeAlim", model)
                self.assertEqual(model.count("StaticCentrifugalPump PompeAlim"), 3)
                self.assertIn(f"StaticCentrifugalPump {component}", model)
                self.assertIn(
                    f"connect(drive{axis}.speedCommand, {component}.rpm_or_mpower)",
                    model,
                )
                self.assertIn(
                    f"drive{axis}.pumpPower.signal = {component}.Wm", model
                )
                self.assertIn(f"BreakerInertialPumpDrive drive{axis}", model)
                self.assertIn(f"SpringLoadedCheckValve checkValve{axis}", model)
                expected_resistance = "1e5" if axis == "LP" else "1e6"
                self.assertIn(
                    f"closedResistance={expected_resistance}", model
                )
                self.assertIn(f"checkValve{axis}.C1", model)
                self.assertIn(f"checkValve{axis}.C2", model)
                for normal_component in all_components.difference({component}):
                    self.assertIn(
                        f"StaticCentrifugalPump {normal_component}", model
                    )
                self.assertIn(f"tripTarget = {target}", model)
                self.assertIn("pumpTripTime(unit=\"s\") = 300", model)

        cw_model = transform(MINIMAL_UPSTREAM, trip_target=4, trip_time=300)
        self.assertNotIn("DynamicCentrifugalPump PompeAlim", cw_model)
        self.assertEqual(cw_model.count("StaticCentrifugalPump PompeAlim"), 3)
        self.assertIn(
            "connect(cwPumpDrive.massFlow, SourceCaloporteur.IMassFlow)",
            cw_model,
        )
        self.assertNotIn("  Control.Drum_LevelControl", cw_model)
        self.assertIn(
            "ThermoSysPro.Examples.CombinedCyclePowerPlant.Control.Drum_LevelControl",
            cw_model,
        )
        self.assertIn(
            "ThermoSysPro.FlueGases.BoundaryConditions.SourceQ SourceFumees",
            cw_model,
        )

    def test_registry_covers_active_ecms_pumps_and_marks_non_ecms_paths(self) -> None:
        with (ROOT / "config" / "ecms_a_equipment.csv").open(
            "r", encoding="utf-8", newline=""
        ) as stream:
            equipment = {row["equipment_id"] for row in csv.DictReader(stream)}
        with (ROOT / "config" / "pump_physics_registry.csv").open(
            "r", encoding="utf-8", newline=""
        ) as stream:
            registry = {row["equipment_id"]: row for row in csv.DictReader(stream)}

        # The active ECMS list intentionally contains only equipment grounded
        # in the simplified simulation. The broader physics registry also
        # documents shared/boundary paths and explicitly rejected fictitious
        # motor-pump interpretations.
        self.assertLessEqual(equipment, set(registry))
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

    def test_physics_validator_rejects_a_partial_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "partial.csv"
            raw.write_text(
                "time,breakerCWClosed,cwPumpDrive.motorTorque,"
                "cwPumpDrive.speedRpm,cwPumpDrive.checkValvePosition,"
                "cwPumpDrive.massFlow.signal,Condenseur.P\n"
                "0,true,1,600,1,100,100000\n"
                "300,false,0,500,1,80,99999\n"
                "304,false,0,400,1,60,99998\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "validate_pump_physics.py"),
                    "--input", str(raw),
                    "--pump-id", "CW-PUMP",
                    "--trip-time", "300",
                    "--stop-time", "420",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("RAW CSV stopped early", completed.stderr)
            self.assertIn("METRICS CW-PUMP: final_time=304", completed.stdout)

    def test_renderer_wires_regularized_condenser_and_real_st_breaker_trip(self) -> None:
        model = transform(MINIMAL_UPSTREAM, trip_target=4, trip_time=300)
        self.assertIn("TripLens_RegularizedCondenser Condenseur(", model)
        self.assertIn("BackpressureTurbineTrip stBackpressureProtection", model)
        self.assertIn("stGridElectricalPower = if st52GClosed then Alternateur.Welec else 0", model)
        self.assertIn("FastSteamTripValve stTripValveHP", model)
        self.assertIn("FastSteamTripValve stTripValveMP", model)
        self.assertIn(
            "connect(stTripValveHP.effectiveOpening, vanne_entree_TurbineHP.Ouv)",
            model,
        )
        self.assertIn(
            "connect(stTripValveMP.effectiveOpening, vanne_entree_TurbineMP.Ouv)",
            model,
        )
        self.assertNotIn(
            "vanne_entree_TurbineHP.Ouv.signal = if stTripLatched then 0", model
        )
        self.assertNotIn(
            "connect(ConstantVanneTurbineHP.y, vanne_entree_TurbineHP.Ouv)",
            model,
        )
        self.assertNotIn(
            "connect(ConstantVanneTurbineMP.y, vanne_entree_TurbineMP.Ouv)",
            model,
        )

        hp_model = transform(MINIMAL_UPSTREAM, trip_target=1, trip_time=300)
        self.assertIn(
            "ThermoSysPro.WaterSteam.HeatExchangers.SimpleDynamicCondenser Condenseur(",
            hp_model,
        )
        self.assertNotIn("TripLens_RegularizedCondenser Condenseur(", hp_model)
        self.assertNotIn("BackpressureTurbineTrip stBackpressureProtection", hp_model)
        self.assertIn(
            "EmergencyExhaustGasRamp hpFeedwaterTripRundown", hp_model
        )
        self.assertIn(
            "hpFeedwaterTripRundown.trip.signal = not breakerHPClosed", hp_model
        )
        self.assertIn(
            "connect(hpFeedwaterTripRundown.effectiveMassFlow,",
            hp_model,
        )
        self.assertNotIn(
            "connect(Debit.y,SourceFumees. IMassFlow)", hp_model
        )
        self.assertNotIn(
            "connect(Temperature.y,SourceFumees. ITemperature)", hp_model
        )

    def test_cw_validator_requires_real_st_breaker_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            raw = target / "cw-no-st-trip.csv"
            raw.write_text(
                "time,breakerCWClosed,cwPumpDrive.motorTorque,"
                "cwPumpDrive.speedRpm,cwPumpDrive.checkValvePosition,"
                "cwPumpDrive.massFlow.signal,Condenseur.P,"
                "stBackpressureTripPickup,stTripLatched,st52GClosed,"
                "stGridElectricalPower,Alternateur.Welec,"
                "stBackpressureProtection.persistenceTimer,"
                "stBackpressureProtection.tripSetpoint\n"
                "0,true,1,600,1,100,10000,false,false,true,"
                "140000000,140000000,0,11500\n"
                "299.9,true,1,600,1,100,10000,false,false,true,"
                "140000000,140000000,0,11500\n"
                "300,false,0,500,0.5,50,11000,false,false,true,"
                "139000000,139000000,0,11500\n"
                "302,false,0,250,0.05,10,12000,true,false,true,"
                "138000000,138000000,2,11500\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "validate_pump_physics.py"),
                    "--input", str(raw),
                    "--pump-id", "CW-PUMP",
                    "--trip-time", "300",
                    "--stop-time", "302",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(
                "ST trip did not latch after persistent backpressure",
                completed.stderr,
            )

    def test_regularized_condenser_removes_zero_flow_heat_singularity(self) -> None:
        source = (ROOT / "modelica" / "TripLens_RegularizedCondenser.mo").read_text(
            encoding="utf-8"
        )
        self.assertIn("coolantFlowRegularization", source)
        self.assertIn("coolantHeatCapacity", source)
        self.assertIn("heatBalanceRegularizationError", source)
        self.assertNotIn("Wout = -Cv.Q*(Cv.h - hl);", source)
        self.assertNotIn("Wout = -Cee.Q*(Cse.h - Cee.h);", source)


if __name__ == "__main__":
    unittest.main()
