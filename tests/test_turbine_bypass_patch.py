from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_turbine_bypass_model import (  # noqa: E402
    MARKER,
    patch_model,
)
from patch_stodola_turbine import patch_text as patch_stodola_text  # noqa: E402


UPSTREAM_STUB = """within ThermoSysPro.Examples.CombinedCyclePowerPlant;
model CombinedCycle_TripTAC
  parameter Real CstHP(fixed=false,start=7618660.65374636);
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_entree_TurbineHP(
    mode=0,
    Cvmax=1);
  ThermoSysPro.WaterSteam.PressureLosses.ControlValve vanne_entree_TurbineMP(
    mode=0,
    Cvmax=1);
equation
  connect(Temperature.y,SourceFumees. ITemperature);
  connect(Debit.y,SourceFumees. IMassFlow);
  connect(ConstantVanneTurbineHP.y, vanne_entree_TurbineHP.Ouv);
  connect(ConstantVanneTurbineMP.y, vanne_entree_TurbineMP.Ouv);
  connect(regulation_Niveau_BP.SortieReelle1, vanne_vapeurBP.Ouv);
  connect(DoubleDebitHP.Cs, vanne_entree_TurbineHP.C1);
  connect(TurbineHP.Cs, MoitieDebitHP.Ce);
  connect(DoubleDebitMP.Cs, vanne_entree_TurbineMP.C1);
  connect(perteChargeK1.C2, CapteurDebitVapCondenseur.C1);
end CombinedCycle_TripTAC;
"""


class TurbineBypassPatchTests(unittest.TestCase):
    def test_stodola_patch_uses_thermosyspro_42_pressure_type(self) -> None:
        source = """within ThermoSysPro.WaterSteam.Machines;
model StodolaTurbine
  Units.SI.AbsolutePressure Pe;
protected
  parameter Units.SI.AbsolutePressure pcrit=1;
  parameter Units.SI.Temperature Tcrit=1;
equation
  if noEvent((Pe > pcrit) or (Te > Tcrit)) then
    Q = sqrt((Pe^2 - Ps^2)/(Cst*Te));
  else
    Q = sqrt((Pe^2 - Ps^2)/(Cst*Te*proe.x));
  end if;
end StodolaTurbine;
"""
        patched = patch_stodola_text(source)

        self.assertIn(
            "parameter Units.SI.AbsolutePressure pressureDifferenceRegularization=100",
            patched,
        )
        self.assertIn("input Units.SI.AbsolutePressure pressureScale;", patched)
        self.assertNotIn("Modelica.SIunits.Pressure", patched)

    def test_patch_matches_multiline_modelica_connection_annotations(self) -> None:
        source = "\n".join(
            line.replace(
                ");",
                ") annotation(\n"
                "    Line(points={{0,0},{1,1}}, color={0,0,255}));",
            )
            if "connect(" in line
            else line
            for line in UPSTREAM_STUB.splitlines()
        )

        patched = patch_model(source)

        self.assertIn(MARKER, patched)
        self.assertNotIn("annotation(\n", patched)

    def test_trip_patch_uses_modelica_4_standard_units(self) -> None:
        patched = patch_model(UPSTREAM_STUB)

        self.assertIn("Modelica.Units.SI.MassFlowRate", patched)
        self.assertIn("Modelica.Units.SI.AbsolutePressure", patched)
        self.assertNotIn("Modelica.SIunits.", patched)

    def test_trip_patch_uses_thermosyspro_42_custom_units(self) -> None:
        patched = patch_model(UPSTREAM_STUB)

        self.assertIn("ThermoSysPro.Units.xSI.Cv Cvmax", patched)
        self.assertIn("ThermoSysPro.Units.xSI.DifferentialPressure deltaP", patched)
        self.assertNotIn("ThermoSysPro.Units.Cv", patched)
        self.assertNotIn("ThermoSysPro.Units.DifferentialPressure", patched)

    def test_patch_accepts_pinned_thermosyspro_42_combined_cycle_source(self) -> None:
        upstream = (
            ROOT
            / "vendor"
            / "ThermoSysPro"
            / "ThermoSysPro"
            / "Examples"
            / "CombinedCyclePowerPlant"
            / "CombinedCycle_TripTAC.mo"
        )
        if not upstream.is_file():
            self.skipTest("pinned ThermoSysPro source is not installed")

        patched = patch_model(upstream.read_text(encoding="utf-8"))

        self.assertEqual(patched.count(MARKER), 1)
        self.assertNotIn("Modelica.SIunits.", patched)
        self.assertIn(
            "connect(vppGTExhaustTemperatureCommand, SourceFumees.ITemperature);",
            patched,
        )
        self.assertIn(
            "connect(vppHPSplitter.Cs2, vppHPBypassValve.C1);",
            patched,
        )

    def test_patch_adds_only_hp_and_hot_reheat_lp_bypass(self) -> None:
        patched = patch_model(UPSTREAM_STUB)

        self.assertIn(MARKER, patched)
        self.assertIn("vppHPBypassValve", patched)
        self.assertIn("vppLPBypassValve", patched)
        self.assertNotIn("vppIPBypass", patched)
        self.assertIn("connect(DoubleDebitHP.Cs, vppHPSplitter.Ce)", patched)
        self.assertIn("connect(TurbineHP.Cs, vppHPColdReheatVolume.Ce1)", patched)
        self.assertIn(
            "VPPRegularizedMixingVolume vppHPColdReheatVolume",
            patched,
        )
        self.assertIn(
            "connect(vppHPBypassValve.C2, vppHPColdReheatVolume.Ce2)",
            patched,
        )
        self.assertIn("VPPFixedFlowInjector vppHPSprayInjector", patched)
        self.assertIn(
            "connect(vppHPSpraySource.C, vppHPSprayInjector.C1)", patched
        )
        self.assertIn(
            "connect(vppHPSprayInjector.C2, vppHPColdReheatVolume.Ce3)",
            patched,
        )
        self.assertIn("connect(DoubleDebitMP.Cs, vppLPSplitter.Ce)", patched)
        self.assertIn(
            "VPPRegularizedMixingVolume vppCondenserSteamVolume",
            patched,
        )
        self.assertIn(
            "connect(vppLPBypassValve.C2, vppCondenserSteamVolume.Ce2)",
            patched,
        )
        self.assertIn("VPPFixedFlowInjector vppLPSprayInjector", patched)
        self.assertIn(
            "connect(vppLPSpraySource.C, vppLPSprayInjector.C1)", patched
        )
        self.assertIn(
            "connect(vppLPSprayInjector.C2, vppCondenserSteamVolume.Ce3)",
            patched,
        )
        self.assertEqual(patched.count("dynamic_mass_balance=false"), 3)
        self.assertEqual(patched.count("steady_state=true"), 3)
        self.assertIn("parameter Real vppValveLeak = 0", patched)
        self.assertIn("model VPPPressureDrivenBypassValve", patched)
        self.assertEqual(patched.count("VPPPressureDrivenBypassValve vpp"), 2)
        self.assertIn("if noEvent(Ouv.signal <= closedEpsilon)", patched)
        self.assertIn("C1.h = C1.h_vol", patched)
        self.assertIn("Q = Cv*rhoNom", patched)
        self.assertNotIn("rhoIn", patched)
        self.assertNotIn("ControlValve vppHPBypassValve", patched)
        self.assertIn("vppHPMainFlow0 = 151.7690991976083", patched)
        self.assertIn("vppIPMainFlow0 = 176.7893383342879", patched)
        self.assertIn("vppCondenserSteamFlow0 =", patched)
        self.assertIn(
            "regulation_Niveau_BP.SortieReelle1.signal*"
            "vppLPDrumAdmissionMultiplier",
            patched,
        )
        self.assertNotIn(
            "connect(regulation_Niveau_BP.SortieReelle1, vanne_vapeurBP.Ouv)",
            patched,
        )

    def test_patch_contains_first_order_actuator_and_spray_dynamics(self) -> None:
        patched = patch_model(UPSTREAM_STUB)

        for state in (
            "der(vppHPAdmissionPos)",
            "der(vppIPAdmissionPos)",
            "der(vppLPDrumAdmissionMultiplier)",
            "der(vppHPBypassPos)",
            "der(vppLPBypassPos)",
            "der(vppHPSprayPos)",
            "der(vppLPSprayPos)",
        ):
            self.assertIn(state, patched)
        self.assertIn("vppAdmissionStroke95(unit=\"s\") = 0.150", patched)
        self.assertIn("vppHPBypassStroke95(unit=\"s\") = 0.300", patched)
        self.assertIn("vppLPBypassStroke95(unit=\"s\") = 0.400", patched)
        self.assertIn("vppSprayStroke95(unit=\"s\") = 0.050", patched)
        self.assertIn("vppSpraySeatLeak = 0", patched)
        self.assertIn("vppAdmissionSeatLeak = 1e-3", patched)
        self.assertIn("vppHPBypassCvmax = 1890", patched)
        self.assertIn("vppLPBypassCvmax = 22000", patched)
        self.assertIn("vppHPSteamDensity0 = 34", patched)
        self.assertIn("vppHotReheatSteamDensity0 = 6.5", patched)
        self.assertNotIn("p_rho=vppHPSteamDensity0", patched)
        self.assertNotIn("p_rho=vppHotReheatSteamDensity0", patched)
        self.assertIn("then vppAdmissionSeatLeak else 0.8", patched)
        self.assertIn("then vppAdmissionSeatLeak else 1", patched)
        self.assertIn("max(vppSpraySeatLeak", patched)
        self.assertIn("vppHPBypassMassFlow = vppHPBypassValve.Q", patched)
        self.assertIn("vppCondenserPressure = Condenseur.P", patched)

    def test_patch_supports_model_without_legacy_csthp_anchor(self) -> None:
        source = UPSTREAM_STUB.replace(
            "  parameter Real CstHP(fixed=false,start=7618660.65374636);\n",
            "",
        )
        self.assertNotIn("CstHP", source)

        patched = patch_model(source)

        self.assertIn(MARKER, patched)
        self.assertIn("parameter Real vppAdmissionStroke95", patched)
        self.assertLess(patched.index(MARKER), patched.index("\nequation\n"))

    def test_patch_matches_upstream_connections_with_flexible_whitespace(self) -> None:
        source = UPSTREAM_STUB.replace(
            "connect(Temperature.y,SourceFumees. ITemperature);",
            "connect(Temperature.y, SourceFumees.ITemperature);",
        )

        patched = patch_model(source)

        self.assertIn(
            "connect(vppGTExhaustTemperatureCommand, SourceFumees.ITemperature);",
            patched,
        )

    def test_patch_fails_closed_when_reapplied(self) -> None:
        with self.assertRaisesRegex(ValueError, "already patched"):
            patch_model(patch_model(UPSTREAM_STUB))

    def test_check_only_does_not_modify_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "CombinedCycle_TripTAC.mo"
            source.write_text(UPSTREAM_STUB, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "patch_turbine_bypass_model.py"),
                    "--source",
                    str(source),
                    "--check-only",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(MARKER, result.stdout)
            self.assertEqual(source.read_text(encoding="utf-8"), UPSTREAM_STUB)


if __name__ == "__main__":
    unittest.main()
