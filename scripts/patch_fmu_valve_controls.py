#!/usr/bin/env python3
"""Insert real FMI valve inputs into the already patched ThermoSysPro plant model."""

from __future__ import annotations

import argparse
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


MARKER = "TRIPLENS_FMU_NATIVE_VALVE_ADAPTER_V1"
REQUIRED_PREVIOUS_MARKER = "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V12"


@dataclass(frozen=True)
class Point:
    key: str
    object_name: str
    auto_expression: str
    initial: float
    original_connect: str | None
    dynamic_state: str | None = None


POINTS = (
    Point("HPFWCV", "vanne_alimentationHP",
          "regulation_Niveau_HP.SortieReelle1.signal", 0.8,
          "regulation_Niveau_HP.SortieReelle1, vanne_alimentationHP.Ouv"),
    Point("HPSteam", "vanne_vapeurHP",
          "constante_vanne_vapeurHP.y.signal", 0.5,
          "constante_vanne_vapeurHP.y, vanne_vapeurHP.Ouv"),
    Point("IPFWCV", "vanne_alimentationMP",
          "regulation_Niveau_MP.SortieReelle1.signal", 0.8,
          "regulation_Niveau_MP.SortieReelle1, vanne_alimentationMP.Ouv"),
    Point("IPSteam", "vanne_vapeurMP",
          "constante_vanne_vapeurMP.y.signal", 0.5,
          "constante_vanne_vapeurMP.y, vanne_vapeurMP.Ouv"),
    Point("LPSteam", "vanne_vapeurBP",
          "if vppSTTripLatch then vppAdmissionSeatLeak else regulation_Niveau_BP.SortieReelle1.signal",
          0.8, None, "vppLPDrumAdmissionMultiplier"),
    Point("LPFW", "vanne_alimentationBP",
          "constante_vanne_vapeurBP.y.signal", 0.5,
          "vanne_alimentationBP.Ouv, constante_vanne_vapeurBP.y"),
    Point("LPToHPIPFW", "Vanne_alimentationMPHP",
          "constante_ballonBP.y.signal", 1.0,
          "Vanne_alimentationMPHP.Ouv, constante_ballonBP.y"),
    Point("CondExtraction", "vanne_extraction",
          "regulation_Niveau_Condenseur.SortieReelle1.signal", 0.8,
          "regulation_Niveau_Condenseur.SortieReelle1, vanne_extraction.Ouv"),
    Point("HPTurbAdm", "vanne_entree_TurbineHP",
          "if vppSTTripLatch then vppAdmissionSeatLeak else ConstantVanneTurbineHP.y.signal",
          0.8, None, "vppHPAdmissionPos"),
    Point("HPFWIso", "Vanne_alimentationMPHP1",
          "arretPomesMp1.y.signal", 0.8,
          "arretPomesMp1.y, Vanne_alimentationMPHP1.Ouv"),
    Point("IPFWIso", "Vanne_alimentationMPHP2",
          "arretPomesHP1.y.signal", 0.8,
          "arretPomesHP1.y, Vanne_alimentationMPHP2.Ouv"),
    Point("IPTurbAdm", "vanne_entree_TurbineMP",
          "if vppSTTripLatch then vppAdmissionSeatLeak else ConstantVanneTurbineMP.y.signal",
          0.8, None, "vppIPAdmissionPos"),
)


def clamp(expression: str) -> str:
    return f"noEvent(min(1, max(0, {expression})))"


def declarations() -> str:
    lines = [f"  // {MARKER}"]
    for point in POINTS:
        prefix = f"fmuVlv{point.key}"
        lines.extend((
            f"  input Boolean {prefix}ModeAuto = true",
            '    "FMI input: true selects the original OpenModelica automatic driver";',
            f"  input Real {prefix}ManualCmd(min=0, max=1) = {point.initial:g}",
            '    "FMI input: manual valve position command in pu";',
            f"  input Boolean {prefix}FaultEnable = false",
            '    "FMI input: force the applied position without rewriting CMD";',
            f"  input Real {prefix}FaultValue(min=0, max=1) = 0",
            '    "FMI input: forced applied position in pu";',
            f"  output Real {prefix}AutoCmd(min=0, max=1);",
            f"  output Real {prefix}Cmd(min=0, max=1);",
            f"  output Real {prefix}Fb(min=0, max=1);",
            f"  output Real {prefix}Deviation;",
            f"  output Boolean {prefix}FaultActive;",
            f"  Real {prefix}Target(min=0, max=1);",
        ))
    return "\n".join(lines) + "\n\n"


def equations() -> str:
    lines: list[str] = []
    for point in POINTS:
        prefix = f"fmuVlv{point.key}"
        lines.extend((
            f"  {prefix}AutoCmd = {clamp(point.auto_expression)};",
            f"  {prefix}Cmd = if {prefix}ModeAuto then {prefix}AutoCmd else {clamp(prefix + 'ManualCmd')};",
            f"  {prefix}Target = if {prefix}FaultEnable then {clamp(prefix + 'FaultValue')} else {prefix}Cmd;",
            f"  {prefix}FaultActive = {prefix}FaultEnable;",
        ))
        if point.dynamic_state:
            lines.append(f"  {prefix}Fb = {point.dynamic_state};")
        else:
            lines.append(f"  {prefix}Fb = {prefix}Target;")
        lines.extend((
            f"  {prefix}Deviation = {prefix}Cmd - {prefix}Fb;",
            f"  {point.object_name}.Ouv.signal = {prefix}Fb;",
            "",
        ))
    return "\n".join(lines)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def remove_connect(text: str, call: str) -> str:
    start_token = f"  connect({call})"
    start = text.find(start_token)
    if start < 0:
        raise ValueError(f"missing native automatic connection: {call}")
    end = text.find(";", start)
    if end < 0:
        raise ValueError(f"unterminated native automatic connection: {call}")
    if text.find(start_token, end + 1) >= 0:
        raise ValueError(f"duplicate native automatic connection: {call}")
    return text[:start] + f"  // {MARKER}: adapter owns {call}\n" + text[end + 1:]


def patch_model(source: str) -> str:
    if REQUIRED_PREVIOUS_MARKER not in source:
        raise ValueError("turbine bypass patch V12 must be applied first")
    if MARKER in source:
        raise ValueError("FMU valve adapter is already applied")

    source = replace_once(
        source,
        "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        declarations() + "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        "FMU declaration insertion",
    )

    for point in POINTS:
        if point.original_connect:
            source = remove_connect(source, point.original_connect)

    source = replace_once(
        source,
        "  Real vppLPDrumAdmissionMultiplier(start=1, fixed=true, min=0, max=1);",
        "  Real vppLPDrumAdmissionMultiplier(start=0.8, fixed=true, min=0, max=1);",
        "LP admission state definition",
    )
    source = replace_once(
        source,
        "    ((if vppSTTripLatch then vppAdmissionSeatLeak else 0.8)\n"
        "      - vppHPAdmissionPos)",
        "    (fmuVlvHPTurbAdmTarget - vppHPAdmissionPos)",
        "HP admission target",
    )
    source = replace_once(
        source,
        "    ((if vppSTTripLatch then vppAdmissionSeatLeak else 0.8)\n"
        "      - vppIPAdmissionPos)",
        "    (fmuVlvIPTurbAdmTarget - vppIPAdmissionPos)",
        "IP admission target",
    )
    source = replace_once(
        source,
        "    ((if vppSTTripLatch then vppAdmissionSeatLeak else 1)\n"
        "      - vppLPDrumAdmissionMultiplier)/vppAdmissionTau;",
        "    (fmuVlvLPSteamTarget - vppLPDrumAdmissionMultiplier)\n"
        "      /vppAdmissionTau;",
        "LP admission target",
    )

    source = replace_once(
        source,
        "  vanne_entree_TurbineHP.Ouv.signal = vppHPAdmissionPos;\n"
        "  vanne_entree_TurbineMP.Ouv.signal = vppIPAdmissionPos;\n"
        "  vanne_vapeurBP.Ouv.signal =\n"
        "    regulation_Niveau_BP.SortieReelle1.signal*vppLPDrumAdmissionMultiplier;\n",
        "  // Native HP/IP/LP admission valves are driven by the FMI adapter below.\n",
        "legacy direct admission equations",
    )
    source = replace_once(
        source,
        "  vppSTTripLatch = time >= vppTripTime;",
        equations() + "\n  vppSTTripLatch = time >= vppTripTime;",
        "FMU equation insertion",
    )

    for point in POINTS:
        prefix = f"fmuVlv{point.key}"
        required = (
            f"input Boolean {prefix}ModeAuto",
            f"input Real {prefix}ManualCmd",
            f"input Boolean {prefix}FaultEnable",
            f"input Real {prefix}FaultValue",
            f"{point.object_name}.Ouv.signal = {prefix}Fb",
        )
        for token in required:
            if token not in source:
                raise AssertionError(f"{point.key}: missing {token}")
        if source.count(f"{point.object_name}.Ouv.signal =") != 1:
            raise AssertionError(f"{point.key}: valve input is not singly driven")
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    original = args.source.read_text(encoding="utf-8")
    patched = patch_model(original)
    print(f"{MARKER}: valves={len(POINTS)}")
    if args.check_only:
        return 0
    destination = args.output or args.source
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False,
            dir=destination.parent, prefix=destination.name + ".", suffix=".tmp"
        ) as stream:
            temporary = Path(stream.name)
            stream.write(patched)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
