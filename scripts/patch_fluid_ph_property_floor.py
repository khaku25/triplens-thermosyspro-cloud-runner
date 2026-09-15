#!/usr/bin/env python3
"""Guard the shared ThermoSysPro Fluid.Ph IF97 pressure input.

Newton trial states can temporarily evaluate a native component at zero or
negative pressure.  Every ThermoSysPro component that calls ``Fluid.Ph`` must
therefore receive a pressure at or above the IF97 triple-point pressure.  The
physical connector pressure is not changed; only the property lookup input is
bounded.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_FLUID_PH_PROPERTY_FLOOR_V1"
WATER_CALL = (
    "    pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(P, h, mode);"
)
C3_CALL = "    pro := C3H3F5.C3H3F5_Ph(P, h);"
ALGORITHM_ANCHOR = "algorithm\n"
PATCH_DECLARATION = """    protected
      Modelica.SIunits.AbsolutePressure Pthermo
        \"Pressure used only for IF97 property evaluation\";
"""
PATCH_ALGORITHM = f"""algorithm
      // {MARKER}
      Pthermo := noEvent(max(P, 611.657));
"""


def patch_text(source: str) -> str:
    if MARKER in source:
        return source
    if source.count(WATER_CALL) != 1:
        raise ValueError("Fluid.Ph: Water_Ph call must occur exactly once")
    if source.count(C3_CALL) != 1:
        raise ValueError("Fluid.Ph: C3H3F5 call must occur exactly once")
    if source.count(ALGORITHM_ANCHOR) != 1:
        raise ValueError("Fluid.Ph: algorithm anchor must occur exactly once")

    # Keep the output record public; protected declarations belong immediately
    # before the algorithm section (after the output annotation block).
    source = source.replace(ALGORITHM_ANCHOR, PATCH_DECLARATION + PATCH_ALGORITHM, 1)
    source = source.replace(
        "Water_Ph(P, h, mode)", "Water_Ph(Pthermo, h, mode)", 1
    )
    source = source.replace("C3H3F5_Ph(P, h)", "C3H3F5_Ph(Pthermo, h)", 1)
    return source


def patch_file(path: Path) -> None:
    patched = patch_text(path.read_text(encoding="utf-8"))
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=path.parent,
            prefix=path.name + ".",
            suffix=".tmp",
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
        parser.error("path must identify ThermoSysPro/Properties/Fluid/Ph.mo")
    if not args.path.is_file():
        parser.error(f"missing component file: {args.path}")
    patch_file(args.path)
    print(f"{MARKER} path={args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

