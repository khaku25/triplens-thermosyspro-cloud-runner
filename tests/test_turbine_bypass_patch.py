from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_turbine_bypass_model import MARKER, patch_model  # noqa: E402


UPSTREAM_STUB = """within ThermoSysPro.Examples.CombinedCyclePowerPlant;
model CombinedCycle_TripTAC
  parameter Real CstHP(fixed=false,start=7618660.65374636);
equation
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
    def test_patch_adds_only_hp_and_hot_reheat_lp_bypass(self) -> None:
        patched = patch_model(UPSTREAM_STUB)

        self.assertIn(MARKER, patched)
        self.assertIn("vppHPBypassValve", patched)
        self.assertIn("vppLPBypassValve", patched)
        self.assertNotIn("vppIPBypass", patched)
        self.assertIn("connect(DoubleDebitHP.Cs, vppHPSplitter.Ce)", patched)
        self.assertIn("connect(TurbineHP.Cs, vppHPColdReheatVolume.Ce1)", patched)
        self.assertIn(
            "ThermoSysPro.WaterSteam.Volumes.VolumeC vppHPColdReheatVolume",
            patched,
        )
        self.assertIn(
            "connect(vppHPBypassValve.C2, vppHPColdReheatVolume.Ce2)",
            patched,
        )
        self.assertIn(
            "connect(vppHPSpraySource.C, vppHPColdReheatVolume.Ce3)",
            patched,
        )
        self.assertIn("connect(DoubleDebitMP.Cs, vppLPSplitter.Ce)", patched)
        self.assertIn(
            "ThermoSysPro.WaterSteam.Volumes.VolumeC vppCondenserSteamVolume",
            patched,
        )
        self.assertIn(
            "connect(vppLPBypassValve.C2, vppCondenserSteamVolume.Ce2)",
            patched,
        )
        self.assertIn(
            "connect(vppLPSpraySource.C, vppCondenserSteamVolume.Ce3)",
            patched,
        )
        self.assertIn("dynamic_mass_balance=true", patched)
        self.assertIn("steady_state=false", patched)
        self.assertIn("parameter Real vppValveLeak = 0", patched)
        self.assertIn("continuous_flow_reversal=false", patched)
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
        self.assertIn("vppHPBypassMassFlow = vppHPBypassValve.Q", patched)
        self.assertIn("vppCondenserPressure = Condenseur.P", patched)

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
