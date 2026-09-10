#!/usr/bin/env python3
"""Validate the exact FMI names, types and causality before starting the gateway."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from live_protocol import COMMAND_INPUTS, LIVE_SIGNALS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fmu", type=Path, required=True)
    args = parser.parse_args()
    with zipfile.ZipFile(args.fmu) as archive:
        root = ET.fromstring(archive.read("modelDescription.xml"))
    if root.attrib.get("fmiVersion") != "2.0" or root.find("CoSimulation") is None:
        raise ValueError("runtime artifact is not an FMI 2.0 Co-Simulation FMU")
    variables = {
        item.attrib["name"]: item
        for item in root.findall("./ModelVariables/ScalarVariable")
    }
    for spec in (*COMMAND_INPUTS, *LIVE_SIGNALS):
        variable = variables.get(spec.fmu_name)
        if variable is None:
            raise ValueError(f"missing FMU variable: {spec.fmu_name}")
        scalar = next(iter(variable), None)
        if scalar is None or scalar.tag != spec.kind:
            raise ValueError(f"{spec.fmu_name}: FMI scalar type differs")
        actual_causality = variable.attrib.get("causality", "local")
        if actual_causality != spec.fmi_causality:
            raise ValueError(
                f"{spec.fmu_name}: causality={actual_causality}, expected={spec.fmi_causality}"
            )
    print(
        "LIVE_FMU_CONTRACT_PASS "
        f"inputs={len(COMMAND_INPUTS)} telemetry={len(LIVE_SIGNALS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
