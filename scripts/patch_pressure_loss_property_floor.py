#!/usr/bin/env python3
"""Guard IF97 property calls in pressure-loss components during Newton trials.

The hydraulic pressure equations retain their original ``Pm`` values. Only
the pressure passed to ``Fluid.Ph`` is bounded at the IF97 triple point.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_PRESSURE_LOSS_PROPERTY_FLOOR_V1"
PROPERTY_CALL = "  pro = ThermoSysPro.Properties.Fluid.Ph(Pm, h, mode, fluid);"
PROPERTY_PATCH = f'''  // {MARKER}
  Pthermo = noEvent(max(propertyPressureFloor, Pm));
  pro = ThermoSysPro.Properties.Fluid.Ph(Pthermo, h, mode, fluid);'''
PARAMETER_ANCHOR = '''  parameter Modelica.SIunits.MassFlowRate Qeps=1.e-3
    "Small mass flow for continuous flow reversal";'''
PARAMETER_PATCH = PARAMETER_ANCHOR + '''
  parameter Modelica.SIunits.AbsolutePressure propertyPressureFloor=611.657
    "IF97 triple-point floor used only during property evaluation";'''
VARIABLE_ANCHOR = '  Modelica.SIunits.AbsolutePressure Pm(start=1.e5)'


def patch_text(source: str, component_name: str) -> str:
    if MARKER in source:
        raise ValueError(f"{component_name}: property-floor patch is already applied")
    if source.count(PARAMETER_ANCHOR) != 1:
        raise ValueError(f"{component_name}: Qeps anchor must occur exactly once")
    if source.count(VARIABLE_ANCHOR) != 1:
        raise ValueError(f"{component_name}: Pm anchor must occur exactly once")
    if source.count(PROPERTY_CALL) != 1:
        raise ValueError(f"{component_name}: Fluid.Ph call must occur exactly once")

    source = source.replace(PARAMETER_ANCHOR, PARAMETER_PATCH, 1)
    start = source.index(VARIABLE_ANCHOR)
    end = source.index(";", start) + 1
    source = (
        source[:end]
        + '\n  Modelica.SIunits.AbsolutePressure Pthermo'
        + ' "Pressure used only for IF97 property evaluation";'
        + source[end:]
    )
    source = source.replace(PROPERTY_CALL, PROPERTY_PATCH, 1)
    return source


def patch_file(path: Path) -> None:
    patched = patch_text(path.read_text(encoding="utf-8"), path.stem)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False,
            dir=path.parent, prefix=path.name + ".", suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            stream.write(patched)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    if len(args.paths) != 2:
        parser.error("exactly ControlValve.mo and PipePressureLoss.mo are required")
    expected = {"ControlValve.mo", "PipePressureLoss.mo"}
    if {path.name for path in args.paths} != expected:
        parser.error("paths must identify ControlValve.mo and PipePressureLoss.mo")
    for path in args.paths:
        if not path.is_file():
            parser.error(f"missing component file: {path}")
    for path in args.paths:
        patch_file(path)
        print(f"{MARKER} path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
