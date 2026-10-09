from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NORMAL_BP_PRESSURE_PA = "501850"
NORMAL_BP_ENTHALPY_J_PER_KG = "2919992.1127030067"


def component_block(model: str, name: str) -> str:
    start = model.index(f"{name}(")
    depth = 0
    for index in range(start + len(name), len(model)):
        if model[index] == "(":
            depth += 1
        elif model[index] == ")":
            depth -= 1
            if depth == 0:
                return model[start:index + 1]
    raise AssertionError(f"unterminated {name} modification")


class BpInitializationSeedTests(unittest.TestCase):
    def test_render_seeds_bp_multiplier_and_pressure_loss_from_operating_point(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "render_modelica.py"),
                    "--normal-operation",
                    "--stop-time",
                    "10",
                    "--intervals",
                    "10",
                    "--output-dir",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            model = (output / "TripLens_CombinedCycle_TripTAC.mo").read_text()

        self.assertIn("DoubleDebitBP(", model)
        multiplier = component_block(model, "DoubleDebitBP")
        self.assertIn(f"P(start={NORMAL_BP_PRESSURE_PA}, nominal=5e5)", multiplier)
        self.assertIn(
            f"h(start={NORMAL_BP_ENTHALPY_J_PER_KG}, nominal=3e6)",
            multiplier,
        )
        for connector in ("Ce", "Cs"):
            self.assertIn(f"{connector}(P(start={NORMAL_BP_PRESSURE_PA})", multiplier)
        self.assertGreaterEqual(
            multiplier.count(f"h_vol(start={NORMAL_BP_ENTHALPY_J_PER_KG})"),
            2,
        )

        self.assertIn("PerteChargeZero2(", model)
        pressure_loss = component_block(model, "PerteChargeZero2")
        self.assertIn(
            f"h(start={NORMAL_BP_ENTHALPY_J_PER_KG}, nominal=3e6)",
            pressure_loss,
        )
        self.assertIn(
            f"h_vol(start={NORMAL_BP_ENTHALPY_J_PER_KG})",
            pressure_loss,
        )


    def test_render_seeds_bp_evaporator_from_saved_triptac_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "render_modelica.py"),
                    "--normal-operation",
                    "--stop-time",
                    "10",
                    "--intervals",
                    "10",
                    "--output-dir",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            model = (output / "TripLens_CombinedCycle_TripTAC.mo").read_text()

        evaporator = component_block(model, "EvaporateurBP")
        for expected in (
            "h(start={550075.0,765243.011613326,912673.256542569,1013555.73710231,550075.0})",
            "hb(start={550075.0,765243.011613326,912673.256542569,1013555.73710231})",
            "Q(start={49.787311368631,49.787311368631,49.787311368631,49.787311368631})",
            "P(start={512583.375,488000,487000,486000,485588.46875})",
        ):
            self.assertIn(expected, evaporator)

        volume = component_block(model, "VolumeEvapBP")
        self.assertIn("h(start=549249.519022482)", volume)
        drum = component_block(model, "BallonBP")
        self.assertIn("hl(fixed=false,start=549249.519022482)", drum)
        feed_valve = component_block(model, "vanne_alimentationBP")
        self.assertIn("Pm(fixed=false,start=969800)", feed_valve)


if __name__ == "__main__":
    unittest.main()
