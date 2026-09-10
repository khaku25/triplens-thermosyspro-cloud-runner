#!/usr/bin/env python3
"""Promote native ThermoSysPro valve deltaP variables to FMI outputs."""

from __future__ import annotations

import argparse
import os
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from patch_fmu_valve_controls import POINTS


def promote(path: Path) -> None:
    with zipfile.ZipFile(path) as source:
        members = {
            info.filename: (info, source.read(info.filename))
            for info in source.infolist()
        }

    root = ET.fromstring(members["modelDescription.xml"][1])
    model_variables = root.find("./ModelVariables")
    model_structure = root.find("./ModelStructure")
    if model_variables is None or model_structure is None:
        raise ValueError("invalid FMI 2.0 modelDescription structure")
    outputs = model_structure.find("./Outputs")
    if outputs is None:
        outputs = ET.SubElement(model_structure, "Outputs")

    variables = list(model_variables.findall("./ScalarVariable"))
    by_name = {item.attrib["name"]: item for item in variables}
    existing_output_indices = {
        int(item.attrib["index"]) for item in outputs.findall("./Unknown")
    }

    promoted = []
    for point in POINTS:
        native_name = f"{point.object_name}.deltaP"
        target_name = f"fmuVlv{point.key}Dp"
        if target_name in by_name:
            raise ValueError(f"target FMI variable already exists: {target_name}")
        variable = by_name.get(native_name)
        if variable is None:
            raise ValueError(f"native OpenModelica variable not found: {native_name}")
        variable.attrib["name"] = target_name
        variable.attrib["causality"] = "output"
        variable.attrib["variability"] = "continuous"
        variable.attrib["initial"] = "calculated"
        scalar_type = next(iter(variable), None)
        if scalar_type is None or scalar_type.tag != "Real":
            raise ValueError(f"native deltaP is not Real: {native_name}")
        scalar_type.attrib["unit"] = "Pa"
        index = variables.index(variable) + 1
        if index not in existing_output_indices:
            ET.SubElement(outputs, "Unknown", {"index": str(index)})
            existing_output_indices.add(index)
        promoted.append((target_name, variable.attrib["valueReference"]))

    members["modelDescription.xml"] = (
        members["modelDescription.xml"][0],
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, dir=path.parent, prefix=path.name + ".", suffix=".tmp"
        ) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, (info, data) in members.items():
                target.writestr(info, data)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

    print(f"FMU native deltaP outputs promoted: {len(promoted)}")
    for name, value_reference in promoted:
        print(f"{name} valueReference={value_reference}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fmu", type=Path, required=True)
    args = parser.parse_args()
    promote(args.fmu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
