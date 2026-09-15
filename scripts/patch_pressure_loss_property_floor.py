#!/usr/bin/env python3
"""Guard pressure-loss properties during zero-flow Newton trials.

The hydraulic pressure equations retain their original ``Pm`` values. Only
the pressure passed to ``Fluid.Ph`` is bounded at the IF97 triple point.  The
pipe component additionally keeps the density denominator finite while a pump
coasts down through a physically closed check valve.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_PRESSURE_LOSS_PROPERTY_FLOOR_V1"
DENSITY_MARKER = "TRIPLENS_PRESSURE_LOSS_DENSITY_FLOOR_V1"
# IF97 rejects the triple-point boundary itself (p <= 611.657 Pa), therefore
# the evaluation floor is deliberately above it.
IF97_PROPERTY_PRESSURE_FLOOR = 1000.0
PROPERTY_CALL = "  pro = ThermoSysPro.Properties.Fluid.Ph(Pm, h, mode, fluid);"
PROPERTY_PATCH = f'''  // {MARKER}
  Pthermo = noEvent(max(propertyPressureFloor, Pm));
  pro = ThermoSysPro.Properties.Fluid.Ph(Pthermo, h, mode, fluid);'''
PARAMETER_ANCHOR = '''  parameter Modelica.SIunits.MassFlowRate Qeps=1.e-3
    "Small mass flow for continuous flow reversal";'''
PARAMETER_PATCH = PARAMETER_ANCHOR + '''
  parameter Modelica.SIunits.AbsolutePressure propertyPressureFloor=1000.0
    "IF97 triple-point floor used only during property evaluation";'''
VARIABLE_ANCHOR = '  Modelica.SIunits.AbsolutePressure Pm(start=1.e5)'
DENSITY_PARAMETER = '''  parameter Modelica.SIunits.Density densityFloor=0.1
    "Numerical floor used only if an IF97 Newton iterate has zero density";'''
DENSITY_ASSIGNMENT = "    rho = pro.d;"
DENSITY_PATCH = f'''    // {DENSITY_MARKER}
    rho = noEvent(max(densityFloor, pro.d));'''


def install_property_floor(source: str, component_name: str) -> str:
    """Install the IF97 pressure guard once and accept an existing install."""
    if MARKER in source:
        return source
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
    return source.replace(PROPERTY_CALL, PROPERTY_PATCH, 1)


def install_pipe_density_floor(source: str, component_name: str) -> str:
    """Prevent the PipePressureLoss ``.../rho`` denominator reaching zero."""
    if component_name != "PipePressureLoss" or DENSITY_MARKER in source:
        return source
    if source.count(PARAMETER_PATCH) != 1:
        raise ValueError(f"{component_name}: property-floor parameter anchor missing")
    if source.count(DENSITY_ASSIGNMENT) != 1:
        raise ValueError(f"{component_name}: density assignment must occur exactly once")
    source = source.replace(PARAMETER_PATCH, PARAMETER_PATCH + '\n' + DENSITY_PARAMETER, 1)
    return source.replace(DENSITY_ASSIGNMENT, DENSITY_PATCH, 1)


def patch_text(source: str, component_name: str) -> str:
    source = install_property_floor(source, component_name)
    return install_pipe_density_floor(source, component_name)


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
