#!/usr/bin/env python3
"""Validate that FMI inputs alter native OpenModelica valve physics."""

from __future__ import annotations

import argparse
import csv
import math
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from patch_fmu_valve_controls import POINTS  # noqa: E402


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        result = list(csv.DictReader(stream))
    if len(result) < 2:
        raise ValueError(f"{path}: expected at least two samples")
    return result


def value(row: dict[str, str], name: str) -> float:
    if name not in row:
        raise ValueError(f"missing OpenModelica result variable: {name}")
    number = float(row[name])
    if not math.isfinite(number):
        raise ValueError(f"{name}: non-finite value")
    return number


def validate_csv(auto_path: Path, smoke_path: Path) -> None:
    auto = rows(auto_path)
    smoke = rows(smoke_path)
    a0, a1 = auto[0], auto[-1]
    s0, s1 = smoke[0], smoke[-1]

    if not math.isclose(value(a1, "fmuVlvHPSteamCmd"), 0.5, abs_tol=1e-6):
        raise ValueError("AUTO HP steam-valve command is not the native 0.5 pu")
    if not math.isclose(value(s1, "fmuVlvHPSteamCmd"), 0.2, abs_tol=1e-6):
        raise ValueError("MAN command did not reach the selected HP steam-valve CMD")
    if not math.isclose(value(s1, "fmuVlvHPSteamFb"), 0.2, abs_tol=1e-6):
        raise ValueError("MAN command did not reach the native HP steam-valve FB")

    auto_cv = value(a1, "vanne_vapeurHP.Cv")
    manual_cv = value(s1, "vanne_vapeurHP.Cv")
    if not math.isclose(manual_cv / auto_cv, 0.2 / 0.5, rel_tol=2e-3):
        raise ValueError("native HP steam-valve Cv did not follow MAN_CMD")
    if math.isclose(
        value(s1, "vanne_vapeurHP.Q"),
        value(a1, "vanne_vapeurHP.Q"),
        rel_tol=1e-4,
        abs_tol=1e-4,
    ):
        raise ValueError("HP steam-valve solved mass flow did not respond to MAN_CMD")

    if not math.isclose(value(s1, "fmuVlvIPTurbAdmCmd"), 0.8, abs_tol=1e-6):
        raise ValueError("IPCV fault rewrote CMD; command/fault separation failed")
    if value(s1, "fmuVlvIPTurbAdmFb") >= 0.05:
        raise ValueError("IPCV forced-closed fault did not close the applied position")
    if value(s1, "fmuVlvIPTurbAdmDeviation") <= 0.70:
        raise ValueError("IPCV command-feedback deviation was not exposed")
    if value(s1, "fmuVlvIPTurbAdmFaultActive") < 0.5:
        raise ValueError("IPCV fault state was not exposed")
    if value(s1, "vanne_entree_TurbineMP.Cv") >= 0.1 * value(a1, "vanne_entree_TurbineMP.Cv"):
        raise ValueError("native IPCV Cv did not follow the fault-applied FB")
    if math.isclose(
        value(s1, "vanne_entree_TurbineMP.Q"),
        value(a1, "vanne_entree_TurbineMP.Q"),
        rel_tol=1e-3,
        abs_tol=1e-3,
    ):
        raise ValueError("IPCV solved mass flow did not respond to forced closure")

    if not math.isclose(value(s0, "fmuVlvIPTurbAdmCmd"), 0.8, abs_tol=1e-6):
        raise ValueError("IPCV selected command was not present at initialization")
    if value(s1, "fmuVlvIPTurbAdmFb") >= value(s0, "fmuVlvIPTurbAdmFb"):
        raise ValueError("IPCV physical actuator state did not move toward closed")


def validate_fmu(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("modelDescription.xml"))
    variables = {
        item.attrib["name"]: item
        for item in root.findall("./ModelVariables/ScalarVariable")
    }
    expected_inputs = set()
    expected_outputs = set()
    expected_starts: dict[str, str] = {}
    for point in POINTS:
        prefix = f"fmuVlv{point.key}"
        expected_inputs.update({
            f"{prefix}ModeAuto", f"{prefix}ManualCmd",
            f"{prefix}FaultEnable", f"{prefix}FaultValue",
        })
        expected_outputs.update({
            f"{prefix}AutoCmd", f"{prefix}Cmd", f"{prefix}Fb",
            f"{prefix}Deviation", f"{prefix}FaultActive",
        })
        expected_starts.update({
            f"{prefix}ModeAuto": "true",
            f"{prefix}ManualCmd": str(float(point.initial)),
            f"{prefix}FaultEnable": "false",
            f"{prefix}FaultValue": "0.0",
        })
    missing_inputs = sorted(
        name for name in expected_inputs
        if name not in variables or variables[name].attrib.get("causality") != "input"
    )
    missing_outputs = sorted(
        name for name in expected_outputs
        if name not in variables or variables[name].attrib.get("causality") != "output"
    )
    if missing_inputs:
        raise ValueError(f"FMU is missing real input causality: {missing_inputs}")
    if missing_outputs:
        raise ValueError(f"FMU is missing real output causality: {missing_outputs}")
    bad_starts = []
    for name, expected in expected_starts.items():
        scalar_type = next(iter(variables[name]), None)
        actual = None if scalar_type is None else scalar_type.attrib.get("start")
        if actual != expected:
            bad_starts.append(f"{name}={actual!r}, expected {expected!r}")
    if bad_starts:
        raise ValueError(f"FMU has unsafe valve input starts: {bad_starts}")
    print(
        f"FMU ports verified: inputs={len(expected_inputs)} "
        f"core_outputs={len(expected_outputs)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", type=Path, required=True)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--fmu", type=Path, required=True)
    args = parser.parse_args()
    validate_csv(args.auto, args.smoke)
    validate_fmu(args.fmu)
    print("OPENMODELICA_NATIVE_VALVE_PHYSICS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
