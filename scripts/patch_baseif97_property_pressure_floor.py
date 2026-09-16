#!/usr/bin/env python3
"""Keep BaseIF97 saturation boundary evaluations above the IF97 triple point.

ThermoSysPro's low-level ``Regions.boilingcurve_p`` and ``dewcurve_p`` are
called directly by several drum and two-phase components.  During a Newton
trial their pressure input can briefly be zero or negative; the region-1/2
boundary formulas then evaluate ``R/p`` and ``R*T/(p*p)``.  Only the input to
the property calculation is bounded.  Connector pressures and model states
remain untouched.
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_BASEIF97_PROPERTY_FLOOR_V1"
PRESSURE_FLOOR = 1000.0
FUNCTIONS = ("boilingcurve_p", "dewcurve_p")


def _patch_block(source: str, name: str) -> str:
    match = re.search(rf"(?m)^    function\s+{name}\b", source)
    if match is None:
        raise ValueError(f"BaseIF97: {name} declaration not found")
    end = re.search(rf"(?m)^    end\s+{name};", source[match.end():])
    if end is None:
        raise ValueError(f"BaseIF97: {name} end marker not found")
    start = match.start()
    stop = match.end() + end.end()
    block = source[start:stop]
    if f"// {MARKER} {name}" in block:
        return source

    anchor = "      Real pv \"partial derivative of p w.r.t v\";"
    if block.count(anchor) != 1:
        raise ValueError(f"BaseIF97: {name} protected anchor not found exactly once")
    block = block.replace(
        anchor,
        anchor
        + "\n      Modelica.SIunits.AbsolutePressure pthermo"
        + ' "Pressure used only for IF97 property evaluation";',
        1,
    )
    plim = "Modelica.SIunits.Pressure plim=min(p, data.PCRIT - 1e-7)"
    if block.count(plim) != 1:
        raise ValueError(f"BaseIF97: {name} pressure-limit anchor not found exactly once")
    block = block.replace(
        plim,
        "Modelica.SIunits.Pressure plim=min(max(p, 1000.0), data.PCRIT - 1e-7)",
        1,
    )
    algorithm = "    algorithm\n"
    if block.count(algorithm) != 1:
        raise ValueError(f"BaseIF97: {name} algorithm anchor not found exactly once")
    block = block.replace(
        algorithm,
        "    algorithm\n"
        f"      // {MARKER} {name}\n"
        f"      pthermo := noEvent(max(p, {PRESSURE_FLOOR}));\n",
        1,
    )

    replacements = {
        "Basic.g1(p, bpro.T)": "Basic.g1(pthermo, bpro.T)",
        "Basic.g2(p, bpro.T)": "Basic.g2(pthermo, bpro.T)",
        "bpro.d := p/(": "bpro.d := pthermo/(",
        "if p > plim then": "if pthermo > plim then",
        "bpro.R/p*(": "bpro.R/pthermo*(",
        "bpro.R*bpro.T/(p*p)*": "bpro.R*bpro.T/(pthermo*pthermo)*",
        "bpro.pt := -p/bpro.T": "bpro.pt := -pthermo/bpro.T",
    }
    for old, new in replacements.items():
        # Each boundary function uses exactly one of the region-1/2 Gibbs
        # calls; the other spelling is intentionally absent.
        if old not in block and old.startswith("Basic.g"):
            continue
        if old not in block:
            raise ValueError(f"BaseIF97: {name} expected expression missing: {old}")
        block = block.replace(old, new, 1)
    return source[:start] + block + source[stop:]


def patch_text(source: str) -> str:
    if MARKER in source:
        if all(f"// {MARKER} {name}" in source for name in FUNCTIONS):
            return source
        raise ValueError("BaseIF97: existing pressure-floor patch is incomplete")
    for name in FUNCTIONS:
        source = _patch_block(source, name)
    return source


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
    if args.path.name != "BaseIF97.mo":
        parser.error("path must identify ThermoSysPro/Properties/WaterSteam/BaseIF97.mo")
    if not args.path.is_file():
        parser.error(f"missing component file: {args.path}")
    patch_file(args.path)
    print(f"{MARKER} path={args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
