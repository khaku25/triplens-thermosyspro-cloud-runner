#!/usr/bin/env python3
"""Regularize the pinned ThermoSysPro Stodola pressure crossover in place."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_STODOLA_PRESSURE_CROSSOVER_V1"
PARAMETER_ANCHOR = "protected\n"
PARAMETER_PATCH = f'''  // {MARKER}
  parameter Boolean regularizePressureCrossover=false
    "Enable the smooth one-way law only on a pressure-reversing turbine";
  parameter Modelica.SIunits.Pressure pressureDifferenceRegularization=100
    "Finite low-flow scale for a tiny one-way numerical leakage";

protected
  function regularizedPositivePressureSquare
    "Cancellation-safe smooth positive part for the Stodola pressure square"
    input Real pressureSquareDifference;
    input Modelica.SIunits.Pressure pressureScale;
    output Real positivePressureSquare;
  protected
    Real discriminant;
  algorithm
    discriminant := sqrt(pressureSquareDifference^2 + pressureScale^4);
    positivePressureSquare := if pressureSquareDifference >= 0 then
      0.5*(pressureSquareDifference + discriminant) else
      0.5*pressureScale^4/(discriminant - pressureSquareDifference);
  end regularizedPositivePressureSquare;

'''
NATIVE_EQUATIONS = '''  if noEvent((Pe > pcrit) or (Te > Tcrit)) then
    Q = sqrt((Pe^2 - Ps^2)/(Cst*Te));
  else
    Q = sqrt((Pe^2 - Ps^2)/(Cst*Te*proe.x));
  end if;'''
REGULARIZED_EQUATIONS = '''  if regularizePressureCrossover then
    if noEvent((Pe > pcrit) or (Te > Tcrit)) then
      Q = sqrt(noEvent(regularizedPositivePressureSquare(
        Pe^2 - Ps^2, pressureDifferenceRegularization))/(Cst*Te));
    else
      Q = sqrt(noEvent(regularizedPositivePressureSquare(
        Pe^2 - Ps^2, pressureDifferenceRegularization))
        /(Cst*Te*max(proe.x, 1e-6)));
    end if;
  elseif noEvent((Pe > pcrit) or (Te > Tcrit)) then
    Q = sqrt((Pe^2 - Ps^2)/(Cst*Te));
  else
    Q = sqrt((Pe^2 - Ps^2)/(Cst*Te*proe.x));
  end if;'''


def patch_text(source: str) -> str:
    if MARKER in source:
        if source.count(MARKER) != 1 or REGULARIZED_EQUATIONS not in source:
            raise ValueError("existing Stodola patch is incomplete")
        return source
    if source.count(PARAMETER_ANCHOR) != 1:
        raise ValueError("Stodola protected-section anchor must occur exactly once")
    if source.count(NATIVE_EQUATIONS) != 1:
        raise ValueError("native Stodola ellipse equations must occur exactly once")
    return source.replace(PARAMETER_ANCHOR, PARAMETER_PATCH, 1).replace(
        NATIVE_EQUATIONS,
        REGULARIZED_EQUATIONS,
        1,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if not args.path.is_file():
        parser.error("path must point to StodolaTurbine.mo")

    patched = patch_text(args.path.read_text(encoding="utf-8"))
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=args.path.parent,
            prefix=args.path.name + ".",
            suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            stream.write(patched)
        os.replace(temporary, args.path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(f"{MARKER} path={args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
