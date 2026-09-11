#!/usr/bin/env python3
"""Add 12 live native OPC UA valve boundaries to the pinned TSP 3.1 plant.

This is the native replacement for the legacy FMI valve adapter.  It contains
no FMU or Simulink runtime dependency: ECMS writes directly to OpenModelica's
embedded OPC UA server, and physical feedback is published by the same model.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


MARKER = "TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_V1"
REQUIRED_PREVIOUS_MARKER = "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V13"
FORBIDDEN_LEGACY_MARKER = "TRIPLENS_FMU_NATIVE_VALVE_ADAPTER_V1"


@dataclass(frozen=True)
class Point:
    control_point_id: str
    suffix: str
    object_name: str
    auto_expression: str
    initial: float
    original_connect: str | None
    dynamic_state: str | None = None


POINTS = (
    Point("HP_FWCV", "HPFWCV", "vanne_alimentationHP",
          "regulation_Niveau_HP.SortieReelle1.signal", 0.8,
          "regulation_Niveau_HP.SortieReelle1, vanne_alimentationHP.Ouv"),
    Point("HP_STEAM_VLV", "HPSteam", "vanne_vapeurHP",
          "constante_vanne_vapeurHP.y.signal", 0.5,
          "constante_vanne_vapeurHP.y, vanne_vapeurHP.Ouv"),
    Point("IP_FWCV", "IPFWCV", "vanne_alimentationMP",
          "regulation_Niveau_MP.SortieReelle1.signal", 0.8,
          "regulation_Niveau_MP.SortieReelle1, vanne_alimentationMP.Ouv"),
    Point("IP_STEAM_VLV", "IPSteam", "vanne_vapeurMP",
          "constante_vanne_vapeurMP.y.signal", 0.5,
          "constante_vanne_vapeurMP.y, vanne_vapeurMP.Ouv"),
    Point("LP_STEAM_VLV", "LPSteam", "vanne_vapeurBP",
          "if vppSTTripLatch then vppAdmissionSeatLeak else regulation_Niveau_BP.SortieReelle1.signal",
          0.8, None, "vppLPDrumAdmissionMultiplier"),
    Point("LP_FW_VLV", "LPFW", "vanne_alimentationBP",
          "constante_vanne_vapeurBP.y.signal", 0.5,
          "vanne_alimentationBP.Ouv, constante_vanne_vapeurBP.y"),
    Point("LP_TO_HPIP_FW_VLV", "LPToHPIPFW", "Vanne_alimentationMPHP",
          "constante_ballonBP.y.signal", 1.0,
          "Vanne_alimentationMPHP.Ouv, constante_ballonBP.y"),
    Point("COND_EXTRACTION_VLV", "CondExtraction", "vanne_extraction",
          "regulation_Niveau_Condenseur.SortieReelle1.signal", 0.8,
          "regulation_Niveau_Condenseur.SortieReelle1, vanne_extraction.Ouv"),
    Point("HP_TURB_ADM_VLV", "HPTurbAdm", "vanne_entree_TurbineHP",
          "if vppSTTripLatch then vppAdmissionSeatLeak else ConstantVanneTurbineHP.y.signal",
          0.8, None, "vppHPAdmissionPos"),
    Point("HP_FW_ISO_VLV", "HPFWIso", "Vanne_alimentationMPHP1",
          "arretPomesMp1.y.signal", 0.8,
          "arretPomesMp1.y, Vanne_alimentationMPHP1.Ouv"),
    Point("IP_FW_ISO_VLV", "IPFWIso", "Vanne_alimentationMPHP2",
          "arretPomesHP1.y.signal", 0.8,
          "arretPomesHP1.y, Vanne_alimentationMPHP2.Ouv"),
    Point("IP_TURB_ADM_VLV", "IPTurbAdm", "vanne_entree_TurbineMP",
          "if vppSTTripLatch then vppAdmissionSeatLeak else ConstantVanneTurbineMP.y.signal",
          0.8, None, "vppIPAdmissionPos"),
)


def clamp(expression: str) -> str:
    return f"noEvent(min(1, max(0, {expression})))"


def declarations() -> str:
    lines = [f"  // {MARKER}"]
    for point in POINTS:
        stem = f"vppVlv{point.suffix}"
        lines.extend((
            f"  output Real {stem}ModeAutoNative(start=1, fixed=true, stateSelect=StateSelect.always)",
            '    "Writable native OPC UA AUTO/MAN selector; 1=AUTO, 0=MAN";',
            f"  output Real {stem}ManualCmdNative(min=0, max=1, start={point.initial:g}, fixed=true, stateSelect=StateSelect.always)",
            '    "Writable native OPC UA manual position command in pu";',
            f"  output Real {stem}FaultEnableNative(start=0, fixed=true, stateSelect=StateSelect.always)",
            '    "Writable native OPC UA fault selector; 1=forced position";',
            f"  output Real {stem}FaultValueNative(min=0, max=1, start=0, fixed=true, stateSelect=StateSelect.always)",
            '    "Writable native OPC UA forced applied position in pu";',
            f"  output Real {stem}AutoCmd(min=0, max=1);",
            f"  output Real {stem}Cmd(min=0, max=1);",
            f"  output Real {stem}Fb(min=0, max=1);",
            f"  output Real {stem}Deviation;",
            f"  output Boolean {stem}FaultActive;",
            f"  output Real {stem}Cv;",
            f"  output Real {stem}MassFlowTH(unit=\"t/h\");",
            f"  output Real {stem}DPPa(unit=\"Pa\");",
            f"  Real {stem}Target(min=0, max=1);",
        ))
    return "\n".join(lines) + "\n\n"


def equations() -> str:
    lines: list[str] = []
    for point in POINTS:
        stem = f"vppVlv{point.suffix}"
        lines.extend((
            f"  der({stem}ModeAutoNative) = Modelica.Constants.eps*sin(time);",
            f"  der({stem}ManualCmdNative) = Modelica.Constants.eps*sin(time);",
            f"  der({stem}FaultEnableNative) = Modelica.Constants.eps*sin(time);",
            f"  der({stem}FaultValueNative) = Modelica.Constants.eps*sin(time);",
            f"  {stem}AutoCmd = {clamp(point.auto_expression)};",
            f"  {stem}Cmd = if {stem}ModeAutoNative >= 0.5 then {stem}AutoCmd else {clamp(stem + 'ManualCmdNative')};",
            f"  {stem}Target = if {stem}FaultEnableNative >= 0.5 then {clamp(stem + 'FaultValueNative')} else {stem}Cmd;",
            f"  {stem}FaultActive = {stem}FaultEnableNative >= 0.5;",
        ))
        if point.dynamic_state:
            lines.append(f"  {stem}Fb = {point.dynamic_state};")
        else:
            lines.append(f"  {stem}Fb = {stem}Target;")
        lines.extend((
            f"  {stem}Deviation = {stem}Cmd - {stem}Fb;",
            f"  {point.object_name}.Ouv.signal = {stem}Fb;",
            f"  {stem}Cv = {point.object_name}.Cv;",
            f"  {stem}MassFlowTH = 3.6*{point.object_name}.Q;",
            f"  {stem}DPPa = {point.object_name}.C1.P - {point.object_name}.C2.P;",
            "",
        ))
    return "\n".join(lines)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def remove_connect(text: str, call: str) -> str:
    token = f"  connect({call})"
    start = text.find(token)
    if start < 0:
        raise ValueError(f"missing native automatic connection: {call}")
    end = text.find(";", start)
    if end < 0 or text.find(token, end + 1) >= 0:
        raise ValueError(f"invalid native automatic connection: {call}")
    return text[:start] + f"  // {MARKER}: adapter owns {call}\n" + text[end + 1:]


def patch_model(source: str) -> str:
    if REQUIRED_PREVIOUS_MARKER not in source:
        raise ValueError("turbine bypass patch V13 must be applied first")
    if FORBIDDEN_LEGACY_MARKER in source:
        raise ValueError("legacy FMU valve adapter conflicts with native OPC UA adapter")
    if MARKER in source:
        raise ValueError("native OPC UA valve adapter is already applied")

    source = replace_once(
        source,
        "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        declarations() + "  parameter Real CstHP(fixed=false,start=7618660.65374636)",
        "native OPC UA declaration insertion",
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
        "    (vppVlvHPTurbAdmTarget - vppHPAdmissionPos)",
        "HP admission target",
    )
    source = replace_once(
        source,
        "    ((if vppSTTripLatch then vppAdmissionSeatLeak else 0.8)\n"
        "      - vppIPAdmissionPos)",
        "    (vppVlvIPTurbAdmTarget - vppIPAdmissionPos)",
        "IP admission target",
    )
    source = replace_once(
        source,
        "    ((if vppSTTripLatch then vppAdmissionSeatLeak else 1)\n"
        "      - vppLPDrumAdmissionMultiplier)/vppAdmissionTau;",
        "    (vppVlvLPSteamTarget - vppLPDrumAdmissionMultiplier)\n"
        "      /vppAdmissionTau;",
        "LP admission target",
    )
    source = replace_once(
        source,
        "  vanne_entree_TurbineHP.Ouv.signal = vppHPAdmissionPos;\n"
        "  vanne_entree_TurbineMP.Ouv.signal = vppIPAdmissionPos;\n"
        "  vanne_vapeurBP.Ouv.signal =\n"
        "    regulation_Niveau_BP.SortieReelle1.signal*vppLPDrumAdmissionMultiplier;\n",
        "  // Native HP/IP/LP admission valves are driven by the OPC UA adapter below.\n",
        "legacy direct admission equations",
    )
    source = replace_once(
        source,
        "  // The native OPC UA server permits writes to continuous states.",
        equations() + "\n  // The native OPC UA server permits writes to continuous states.",
        "native OPC UA equation insertion",
    )

    for point in POINTS:
        stem = f"vppVlv{point.suffix}"
        required = (
            f"output Real {stem}ModeAutoNative",
            f"output Real {stem}ManualCmdNative",
            f"output Real {stem}FaultEnableNative",
            f"output Real {stem}FaultValueNative",
            f"{point.object_name}.Ouv.signal = {stem}Fb",
            f"{stem}Cv = {point.object_name}.Cv",
            f"{stem}MassFlowTH = 3.6*{point.object_name}.Q",
            f"{stem}DPPa = {point.object_name}.C1.P - {point.object_name}.C2.P",
        )
        for token in required:
            if token not in source:
                raise AssertionError(f"{point.control_point_id}: missing {token}")
        if source.count(f"{point.object_name}.Ouv.signal =") != 1:
            raise AssertionError(
                f"{point.control_point_id}: physical valve input is not singly driven"
            )
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    patched = patch_model(args.source.read_text(encoding="utf-8"))
    print(f"{MARKER}: valves={len(POINTS)} nodes={len(POINTS) * 12}")
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
