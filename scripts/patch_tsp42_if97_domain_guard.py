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
HELPER_MARKER = "TRIPLENS_TSP42_IF97_DOMAIN_GUARD_HELPER_V1"
PRESSURE_FLOOR_PA = 700
DIRECT_WATER_PH_CALL = (
    "ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(P, h, mode)"
)
SAFE_WATER_PH_CALL = "ThermoSysPro.Properties.Fluid.Ph(P, h, mode, 1)"
DIRECT_WATER_PH_DER_CALL = (
    "ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph_der("
    "p = P, h = h, mode = mode, p_der = der_P, h_der = der_h)"
)
SAFE_WATER_PH_DER_CALL = (
    "ThermoSysPro.Properties.Fluid.Ph_der(P, h, mode, der_P, der_h)"
)
WITHIN_ANCHOR = "within ThermoSysPro.Properties.Fluid;"
ALGORITHM_ANCHOR = (
    "algorithm\n"
    "  if (fluid == 1) then\n"
    "    pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(P, h, mode);"
)
PROPERTY_PATCH = '''algorithm
  if (fluid == 1) then
    pEval := min(max(P, 700), ThermoSysPro.Properties.WaterSteam.BaseIF97.data.PLIMIT1);
    hLower := ThermoSysPro.Properties.WaterSteam.BaseIF97.Regions.hlowerofp1(pEval);
    if (pEval < ThermoSysPro.Properties.WaterSteam.BaseIF97.data.PLIMIT5) then
      hUpper := ThermoSysPro.Properties.WaterSteam.BaseIF97.Regions.hupperofp5(pEval);
    elseif (pEval < ThermoSysPro.Properties.WaterSteam.BaseIF97.data.PLIMIT4A) then
      hUpper := ThermoSysPro.Properties.WaterSteam.BaseIF97.Regions.hlowerofp5(pEval);
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
PH_DER_SOURCE = '''within ThermoSysPro.Properties.Fluid;

function Ph_der "Guarded directional derivative for water/steam properties"
  input Units.SI.AbsolutePressure P;
  input Units.SI.SpecificEnthalpy h;
  input Integer mode = 0;
  input Real der_P;
  input Real der_h;
  output ThermoSysPro.Properties.WaterSteam.Common.ThermoProperties_ph der_pro;
protected
  Units.SI.AbsolutePressure pEval;
  Units.SI.SpecificEnthalpy hLower;
  Units.SI.SpecificEnthalpy hUpper;
  Units.SI.SpecificEnthalpy hEval;
algorithm
  pEval := min(max(P, 700), ThermoSysPro.Properties.WaterSteam.BaseIF97.data.PLIMIT1);
  hLower := ThermoSysPro.Properties.WaterSteam.BaseIF97.Regions.hlowerofp1(pEval);
  if (pEval < ThermoSysPro.Properties.WaterSteam.BaseIF97.data.PLIMIT5) then
    hUpper := ThermoSysPro.Properties.WaterSteam.BaseIF97.Regions.hupperofp5(pEval);
  elseif (pEval < ThermoSysPro.Properties.WaterSteam.BaseIF97.data.PLIMIT4A) then
    hUpper := ThermoSysPro.Properties.WaterSteam.BaseIF97.Regions.hlowerofp5(pEval);
  else
    hUpper := ThermoSysPro.Properties.WaterSteam.BaseIF97.Regions.hupperofp2(pEval);
  end if;
  hEval := min(max(h, hLower), hUpper - 1);
  if (P <= 611.657) or
     (P > ThermoSysPro.Properties.WaterSteam.BaseIF97.data.PLIMIT1) or
     (h < hLower) or (h > hUpper) then
    der_pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph_der(
      p = pEval, h = hEval, mode = 0, p_der = 0, h_der = 0);
  else
    der_pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph_der(
      p = P, h = h, mode = mode, p_der = der_P, h_der = der_h);
  end if;
end Ph_der;
'''


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


def patch_helper_text(source: str) -> tuple[str, int]:
    """Route Fluid property helpers through the guarded Ph function."""
    if HELPER_MARKER in source:
        raise ValueError("Fluid helper: IF97 domain guard patch is already applied")
    calls = 0
    patched_lines: list[str] = []
    for line in source.splitlines(keepends=True):
        code, comment_separator, line_comment = line.partition("//")
        for direct, safe in (
            (DIRECT_WATER_PH_CALL, SAFE_WATER_PH_CALL),
            (DIRECT_WATER_PH_DER_CALL, SAFE_WATER_PH_DER_CALL),
        ):
            calls += code.count(direct)
            code = code.replace(direct, safe)
        patched_lines.append(
            code + comment_separator + line_comment
        )
    if calls == 0:
        return source, 0
    if source.count(WITHIN_ANCHOR) != 1:
        raise ValueError("Fluid helper: package anchor must occur exactly once")

    source = "".join(patched_lines)
    source = source.replace(
        WITHIN_ANCHOR,
        WITHIN_ANCHOR + "\n// " + HELPER_MARKER,
        1,
    )
    return source, calls


def _atomic_write(path: Path, content: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False,
            dir=path.parent, prefix=path.name + ".", suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def patch_file(path: Path) -> None:
    _atomic_write(path, patch_text(path.read_text(encoding="utf-8")))


def patch_fluid_directory(directory: Path) -> list[tuple[str, int]]:
    if directory.name != "Fluid" or directory.parent.name != "Properties":
        raise ValueError("path must identify ThermoSysPro 4.2 Properties/Fluid")
    if not directory.is_dir():
        raise ValueError(f"missing Fluid properties directory: {directory}")

    ph_file = directory / "Ph.mo"
    ph_der_file = directory / "Ph_der.mo"
    patched_ph = patch_text(ph_file.read_text(encoding="utf-8"))
    if ph_der_file.exists():
        raise ValueError("Fluid helper: refusing to overwrite an existing Ph_der.mo")
    helper_updates: list[tuple[Path, str, int]] = []
    for candidate in sorted(directory.glob("*.mo")):
        if candidate.name == "Ph.mo":
            continue
        source = candidate.read_text(encoding="utf-8")
        patched, calls = patch_helper_text(source)
        if calls:
            helper_updates.append((candidate, patched, calls))
    if not helper_updates:
        raise ValueError("Fluid helper: no direct IF97 Water_Ph calls were found")
    if sum(calls for _candidate, _patched, calls in helper_updates) < 1:
        raise ValueError("Fluid helper: no direct IF97 property calls were found")

    _atomic_write(ph_file, patched_ph)
    _atomic_write(ph_der_file, PH_DER_SOURCE)
    for candidate, patched, _calls in helper_updates:
        _atomic_write(candidate, patched)
    return [(candidate.name, calls) for candidate, _patched, calls in helper_updates]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        patches = patch_fluid_directory(args.path)
    except ValueError as exc:
        parser.error(str(exc))
    for filename, calls in patches:
        print(f"{HELPER_MARKER} file={filename} calls={calls}")
    print(
        f"{MARKER} path={args.path / 'Ph.mo'} pressure_floor_pa={PRESSURE_FLOOR_PA} "
        f"helper_files={len(patches)} helper_calls={sum(c for _, c in patches)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
