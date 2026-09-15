#!/usr/bin/env python3
"""Guard direct IF97 property calls during Newton trial evaluations.

Several ThermoSysPro components call ``IF97_packages`` directly rather than
going through ``Properties.Fluid.Ph``.  The IF97 implementation rejects a
pressure at or below its 611.657 Pa triple point, while a Newton trial can
temporarily propose zero pressure.  This patch bounds only the pressure used
inside the property functions; connector pressures and model equations are
unchanged.
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_IF97_PROPERTY_FLOOR_V1"
IF97_PROPERTY_PRESSURE_FLOOR = 1000.0

# Public property functions and their analytic derivative functions.  The
# token is case-sensitive because Water_sat_P uses an uppercase input P.
TARGETS = {
    "Water_Ph": "p",
    "Water_Ps": "p",
    "Water_sat_P": "P",
    "Water_PT": "p",
    "SpecificEnthalpy_PT": "p",
    "Water_Ph_der": "p",
    "Water_Ps_der": "p",
    "Water_PT_der": "p",
    "Water_sat_P_der": "P",
    "SpecificEnthalpy_PT_der": "p",
}

FUNCTION_RE = re.compile(r"(?m)^    function\s+([A-Za-z_]\w*)\b")


def _replace_token(code: str, token: str, replacement: str) -> str:
    return re.sub(
        # Do not rewrite named-argument labels (``p=...``); only rewrite the
        # value expression on the right-hand side.
        # Do not rewrite record member names such as ``g.p`` or ``pro.P``;
        # those are fields of IF97 records, not the function input.  The
        # right-hand-side guard above separately preserves named-argument
        # labels such as ``helper(p=...)``.
        rf"(?<![A-Za-z0-9_.]){re.escape(token)}(?![A-Za-z0-9_=])",
        replacement,
        code,
    )


def _patch_function(block: str, name: str, token: str) -> str:
    marker = f"// {MARKER} {name}"
    if marker in block:
        return block
    algorithm = re.search(r"(?m)^(\s*)algorithm\n", block)
    if algorithm is None:
        raise ValueError(f"{name}: algorithm section not found")
    indent = algorithm.group(1)
    code_start = algorithm.end()
    annotation = re.search(r"(?m)^\s*annotation\s*\(", block[code_start:])
    code_end = code_start + annotation.start() if annotation else len(block)
    code = block[code_start:code_end]
    code = _replace_token(code, token, f"{token}thermo")
    declaration = (
        f"{indent}protected\n"
        f"{indent}  Modelica.SIunits.AbsolutePressure {token}thermo\n"
        f'{indent}    "Pressure used only for IF97 property evaluation";\n'
    )
    prefix = (
        f"{indent}{marker}\n"
        f"{indent}{token}thermo := noEvent(max({token}, {IF97_PROPERTY_PRESSURE_FLOOR}));\n"
    )
    return block[:algorithm.start()] + declaration + block[algorithm.start():algorithm.end()] + prefix + code + block[code_end:]


def patch_text(source: str) -> str:
    if MARKER in source:
        return source
    matches = list(FUNCTION_RE.finditer(source))
    if not matches:
        raise ValueError("IF97_packages: no function declarations found")
    found = set()
    pieces: list[str] = []
    cursor = 0
    for match in matches:
        name = match.group(1)
        if name not in TARGETS:
            continue
        end_match = re.search(rf"(?m)^    end\s+{re.escape(name)};", source[match.end():])
        if end_match is None:
            raise ValueError(f"{name}: end marker not found")
        start = match.start()
        end = match.end() + end_match.end()
        pieces.append(source[cursor:start])
        pieces.append(_patch_function(source[start:end], name, TARGETS[name]))
        cursor = end
        found.add(name)
    pieces.append(source[cursor:])
    missing = set(TARGETS) - found
    if missing:
        raise ValueError("IF97_packages: missing target functions: " + ", ".join(sorted(missing)))
    return "".join(pieces)


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
    if args.path.name != "IF97_packages.mo":
        parser.error("path must identify ThermoSysPro/Properties/WaterSteam/IF97_packages.mo")
    if not args.path.is_file():
        parser.error(f"missing component file: {args.path}")
    patch_file(args.path)
    print(f"{MARKER} path={args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
