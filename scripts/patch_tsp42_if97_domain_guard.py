#!/usr/bin/env python3
"""Guard out-of-domain IF97 trials at ThermoSysPro 4.2's Fluid.Ph entrypoint.

In-domain water/steam property calls retain the caller's exact inputs and IF97
mode. Only out-of-domain solver trials are evaluated at the closest bounded
pressure/enthalpy input, using automatic region selection.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_TSP42_IF97_DOMAIN_GUARD_V1"
PRESSURE_FLOOR_PA = 700
ALGORITHM_ANCHOR = (
    "algorithm\n"
    "  if (fluid == 1) then\n"
    "    pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(P, h, mode);"
)
PROPERTY_PATCH = '''algorithm
  if (fluid == 1) then
    pEval := min(max(P, 700), ThermoSysPro.Properties.WaterSteam.BaseIF97.data.PLIMIT1);
    hLower := ThermoSysPro.Properties.WaterSteam.BaseIF97.Regions.hlowerofp1(pEval);
    if (pEval < 10.0e6) then
      hUpper := ThermoSysPro.Properties.WaterSteam.BaseIF97.Regions.hupperofp5(pEval);
    else
      hUpper := ThermoSysPro.Properties.WaterSteam.BaseIF97.Regions.hupperofp2(pEval);
    end if;
    hEval := min(max(h, hLower), hUpper - 1);
    if (P <= 611.657) or
       (P > ThermoSysPro.Properties.WaterSteam.BaseIF97.data.PLIMIT1) or
       (h < hLower) or (h > hUpper) then
      pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(pEval, hEval, 0);
    else
      pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(P, h, mode);
    end if;'''
DECLARATIONS = '''protected
  // {marker}
  Units.SI.AbsolutePressure pEval "Bounded pressure for out-of-domain IF97 trials";
  Units.SI.SpecificEnthalpy hLower "IF97 lower enthalpy limit at pEval";
  Units.SI.SpecificEnthalpy hUpper "IF97 upper enthalpy limit at pEval";
  Units.SI.SpecificEnthalpy hEval "Bounded enthalpy for out-of-domain IF97 trials";
'''.format(marker=MARKER)


def patch_text(source: str) -> str:
    if MARKER in source:
        raise ValueError("Fluid.Ph: IF97 domain guard patch is already applied")
    if source.count("algorithm\n") != 1:
        raise ValueError("Fluid.Ph: algorithm anchor must occur exactly once")
    if source.count(ALGORITHM_ANCHOR) != 1:
        raise ValueError("Fluid.Ph: Water_Ph anchor must occur exactly once")
    if source.count("end Ph;") != 1:
        raise ValueError("Fluid.Ph: function terminator must occur exactly once")

    source = source.replace("algorithm\n", DECLARATIONS + "algorithm\n", 1)
    return source.replace(ALGORITHM_ANCHOR, PROPERTY_PATCH, 1)


def patch_file(path: Path) -> None:
    patched = patch_text(path.read_text(encoding="utf-8"))
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
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.path.name != "Ph.mo":
        parser.error("path must identify the official ThermoSysPro 4.2 Properties/Fluid/Ph.mo")
    if not args.path.is_file():
        parser.error(f"missing function file: {args.path}")
    patch_file(args.path)
    print(f"{MARKER} path={args.path} pressure_floor_pa={PRESSURE_FLOOR_PA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
