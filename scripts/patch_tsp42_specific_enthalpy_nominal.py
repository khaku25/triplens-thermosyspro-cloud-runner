#!/usr/bin/env python3
"""Give ThermoSysPro 4.2 enthalpy unknowns a representative nominal scale."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


UPSTREAM_ALIAS = "type SpecificEnthalpy = SpecificEnergy;"
ALIAS_PATCH = "type SpecificEnthalpy = SpecificEnergy(nominal = 1e6);"


def patch_text(source: str) -> str:
    if ALIAS_PATCH in source:
        if source.count(ALIAS_PATCH) == 1 and UPSTREAM_ALIAS not in source:
            raise ValueError("SpecificEnthalpy nominal patch is already applied")
        raise ValueError("SpecificEnthalpy alias must occur exactly once")
    if source.count(UPSTREAM_ALIAS) != 1:
        raise ValueError("SpecificEnthalpy alias must occur exactly once")
    return source.replace(UPSTREAM_ALIAS, ALIAS_PATCH, 1)


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
    if args.path.name != "Units.mo":
        parser.error("path must identify the official ThermoSysPro 4.2 Units.mo")
    if not args.path.is_file():
        parser.error(f"missing units file: {args.path}")
    patch_file(args.path)
    print(f"TRIPLENS_TSP42_SPECIFIC_ENTHALPY_NOMINAL_V1 path={args.path} nominal=1e6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
