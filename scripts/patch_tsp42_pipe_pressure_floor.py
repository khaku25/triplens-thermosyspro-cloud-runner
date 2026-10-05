#!/usr/bin/env python3
"""Keep IF97 property trials in-domain in ThermoSysPro 4.2 pipe losses.

The component's hydraulic pressure equations remain unchanged. Only the
pressure passed to the fluid-property function is bounded during solver
iterations, above the IF97 triple-point pressure.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_TSP42_PIPE_PROPERTY_FLOOR_V1"
PROPERTY_FLOOR_PA = 700
PROTECTED_ANCHOR = "protected\n"
PROPERTY_CALL = "  pro = ThermoSysPro.Properties.Fluid.Ph(Pm, h, mode, fluid);"
PROPERTY_PATCH = (
    "  pro = ThermoSysPro.Properties.Fluid.Ph("
    "noEvent(max(propertyPressureFloor, Pm)), h, mode, fluid);"
)


def patch_text(source: str) -> str:
    if MARKER in source:
        raise ValueError("PipePressureLoss: property-floor patch is already applied")
    if source.count(PROTECTED_ANCHOR) != 1:
        raise ValueError("PipePressureLoss: protected declaration anchor must occur exactly once")
    if source.count(PROPERTY_CALL) != 1:
        raise ValueError("PipePressureLoss: Fluid.Ph anchor must occur exactly once")

    declarations = '''protected
  // {marker}
  constant Units.SI.AbsolutePressure propertyPressureFloor = {floor}
    "Pressure floor for IF97 property evaluation only";
'''.format(marker=MARKER, floor=PROPERTY_FLOOR_PA)
    source = source.replace(PROTECTED_ANCHOR, declarations, 1)
    return source.replace(PROPERTY_CALL, PROPERTY_PATCH, 1)


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
    if args.path.name != "PipePressureLoss.mo":
        parser.error("path must identify the official ThermoSysPro 4.2 PipePressureLoss.mo")
    if not args.path.is_file():
        parser.error(f"missing component file: {args.path}")
    patch_file(args.path)
    print(f"{MARKER} path={args.path} floor_pa={PROPERTY_FLOOR_PA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
