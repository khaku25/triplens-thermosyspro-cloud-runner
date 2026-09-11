#!/usr/bin/env python3
"""Build the canonical native OpenModelica OPC UA contract for 12 valves.

The source inventory is physical (ThermoSysPro object bindings), while this
builder deliberately emits no FMI/FMUs or Simulink-facing names.  All command
points are writable Real state variables because OpenModelica's embedded OPC UA
server reliably exposes those variables for live writes.  Boolean semantics are
carried explicitly in ``semantic_type`` and use the 0/1 convention.
"""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "config" / "native_opcua_valve_control_points_v1.csv"
NODES = ROOT / "data" / "opcua_native_valve_nodes_v1.csv"
LOGIC = ROOT / "data" / "opcua_native_valve_logic_v1.csv"

NATIVE_CLASS = "ThermoSysPro.WaterSteam.PressureLosses.ControlValve"

# The suffix is part of the stable BrowseName and matches the adapter patch.
POINT_SUFFIXES = {
    "HP_FWCV": "HPFWCV",
    "HP_STEAM_VLV": "HPSteam",
    "IP_FWCV": "IPFWCV",
    "IP_STEAM_VLV": "IPSteam",
    "LP_STEAM_VLV": "LPSteam",
    "LP_FW_VLV": "LPFW",
    "LP_TO_HPIP_FW_VLV": "LPToHPIPFW",
    "COND_EXTRACTION_VLV": "CondExtraction",
    "HP_TURB_ADM_VLV": "HPTurbAdm",
    "HP_FW_ISO_VLV": "HPFWIso",
    "IP_FW_ISO_VLV": "IPFWIso",
    "IP_TURB_ADM_VLV": "IPTurbAdm",
}

NODE_FIELDS = [
    "canonical_tag",
    "owner",
    "layer",
    "direction",
    "opcua_browse_name",
    "data_type",
    "semantic_type",
    "unit",
    "control_point_id",
    "role",
    "model_binding",
    "writable",
    "implementation_status",
    "description_ko",
]
LOGIC_FIELDS = [
    "logic_id",
    "control_point_id",
    "logic_type",
    "expression",
    "delay_s",
    "enabled_default",
    "implementation_status",
    "description_ko",
]


def read_inventory(path: Path = INVENTORY) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    ids = [row["control_point_id"] for row in rows]
    objects = [row["native_object"] for row in rows]
    if len(rows) != 12:
        raise ValueError(f"expected 12 native valves, got {len(rows)}")
    if len(ids) != len(set(ids)) or set(ids) != set(POINT_SUFFIXES):
        raise ValueError("native valve IDs are missing or duplicated")
    if len(objects) != len(set(objects)):
        raise ValueError("duplicate native ThermoSysPro object")
    for row in rows:
        point = row["control_point_id"]
        if row["native_class"] != NATIVE_CLASS:
            raise ValueError(f"{point}: unsupported native class")
        if row["model_status"] != "NATIVE_MAPPED":
            raise ValueError(f"{point}: physical mapping is not grounded")
        if row["command_unit"] != "pu" or row["min_cmd"] != "0" or row["max_cmd"] != "1":
            raise ValueError(f"{point}: invalid 0..1 opening contract")
        required = (
            "auto_driver",
            "native_input",
            "native_position_basis",
            "native_cv",
            "native_flow",
            "native_inlet_pressure",
            "native_outlet_pressure",
        )
        if any(not row[field].strip() for field in required):
            raise ValueError(f"{point}: incomplete physical binding")
    return rows


def _node(
    *,
    tag: str,
    direction: str,
    browse_name: str,
    data_type: str,
    semantic_type: str,
    unit: str,
    point: str,
    role: str,
    binding: str,
    description: str,
) -> dict[str, object]:
    return {
        "canonical_tag": tag,
        "owner": "ECMS" if direction == "WRITE" else "OpenModelica",
        "layer": "CONTROL" if direction == "WRITE" else "PHYSICAL",
        "direction": direction,
        "opcua_browse_name": browse_name,
        "data_type": data_type,
        "semantic_type": semantic_type,
        "unit": unit,
        "control_point_id": point,
        "role": role,
        "model_binding": binding,
        "writable": 1 if direction == "WRITE" else 0,
        "implementation_status": "NATIVE_OPCUA_CONNECTED",
        "description_ko": description,
    }


def make_node_rows(inventory: list[dict[str, str]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in inventory:
        point = row["control_point_id"]
        stem = f"vppVlv{POINT_SUFFIXES[point]}"
        tag = f"VLV.{point}"
        writes = (
            ("MODE_AUTO", f"{stem}ModeAutoNative", "Real", "Boolean", "BOOL",
             "AUTO_MAN_SELECT", f"{stem}ModeAutoNative >= 0.5", "AUTO 모드 선택(0/1)"),
            ("MANUAL_POSITION", f"{stem}ManualCmdNative", "Real", "Real", "pu",
             "MANUAL_COMMAND", f"{stem}ManualCmdNative", "수동 밸브 개도명령"),
            ("FAULT_ENABLE", f"{stem}FaultEnableNative", "Real", "Boolean", "BOOL",
             "FAULT_ENABLE", f"{stem}FaultEnableNative >= 0.5", "밸브 고장 주입 활성(0/1)"),
            ("FAULT_POSITION", f"{stem}FaultValueNative", "Real", "Real", "pu",
             "FAULT_FORCED_VALUE", f"{stem}FaultValueNative", "고장 시 실제 강제 개도"),
        )
        reads = (
            ("AUTO_CMD", f"{stem}AutoCmd", "Real", "Real", "pu",
             "AUTOMATIC_COMMAND", row["auto_driver"], "기존 자동제어기의 명령"),
            ("CMD", f"{stem}Cmd", "Real", "Real", "pu",
             "SELECTED_COMMAND", f"{stem}Cmd", "AUTO/MAN 선택 후 정상 명령"),
            ("POSITION", f"{stem}Fb", "Real", "Real", "pu",
             "APPLIED_POSITION", row["native_position_basis"], "물리 모델에 실제 적용된 개도"),
            ("DEVIATION", f"{stem}Deviation", "Real", "Real", "pu",
             "COMMAND_FEEDBACK_DEVIATION", f"{stem}Cmd-{stem}Fb", "명령과 적용 개도의 편차"),
            ("FAULT_ACTIVE", f"{stem}FaultActive", "Boolean", "Boolean", "BOOL",
             "FAULT_STATUS", f"{stem}FaultEnableNative >= 0.5", "명령과 분리된 고장상태"),
            ("CV", f"{stem}Cv", "Real", "Real", "Cv",
             "SOLVED_CV", row["native_cv"], "ThermoSysPro 계산 밸브 Cv"),
            ("MASS_FLOW", f"{stem}MassFlowTH", "Real", "Real", "t/h",
             "SOLVED_MASS_FLOW", f"3.6*({row['native_flow']})", "밸브 통과 질량유량"),
            ("DP", f"{stem}DPPa", "Real", "Real", "Pa",
             "SOLVED_PRESSURE_DROP", f"{row['native_inlet_pressure']}-{row['native_outlet_pressure']}",
             "밸브 전후 차압"),
        )
        for suffix, browse, dtype, semantic, unit, role, binding, description in writes:
            result.append(_node(
                tag=f"CMD.{tag}.{suffix}", direction="WRITE", browse_name=browse,
                data_type=dtype, semantic_type=semantic, unit=unit, point=point,
                role=role, binding=binding, description=description,
            ))
        for suffix, browse, dtype, semantic, unit, role, binding, description in reads:
            prefix = "TSP" if suffix in {"CV", "MASS_FLOW", "DP"} else "DCS"
            result.append(_node(
                tag=f"{prefix}.{tag}.{suffix}", direction="READ", browse_name=browse,
                data_type=dtype, semantic_type=semantic, unit=unit, point=point,
                role=role, binding=binding, description=description,
            ))
    if len(result) != 144 or len({row["canonical_tag"] for row in result}) != 144:
        raise AssertionError("native valve node contract must contain 144 unique points")
    if len({row["opcua_browse_name"] for row in result}) != 144:
        raise AssertionError("native valve BrowseNames must be unique")
    return result


def make_logic_rows(inventory: list[dict[str, str]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in inventory:
        point = row["control_point_id"]
        base = f"VLV.{point}"
        specs = (
            ("SELECT_CMD", "CONTROL_SELECT",
             f"DCS.{base}.CMD = if CMD.{base}.MODE_AUTO then DCS.{base}.AUTO_CMD else CMD.{base}.MANUAL_POSITION",
             0, "AUTO와 수동 명령 선택"),
            ("APPLY_FAULT", "FAULT_OVERRIDE",
             f"DCS.{base}.POSITION = if CMD.{base}.FAULT_ENABLE then CMD.{base}.FAULT_POSITION else DCS.{base}.CMD",
             0, "고장은 CMD를 바꾸지 않고 실제 적용값만 변경"),
            ("CALC_DEVIATION", "CALCULATION",
             f"DCS.{base}.DEVIATION = DCS.{base}.CMD - DCS.{base}.POSITION",
             0, "명령과 실제 개도의 편차 계산"),
            ("DEVIATION_ALARM", "ALARM", f"abs(DCS.{base}.DEVIATION) >= 0.05",
             1, "5% 이상 편차가 1초 지속되면 경보"),
            ("OPEN_LS", "LIMIT_STATE", f"DCS.{base}.POSITION >= 0.98",
             0, "실제 개도 기준 전개 상태"),
            ("CLOSE_LS", "LIMIT_STATE", f"DCS.{base}.POSITION <= 0.02",
             0, "실제 개도 기준 전폐 상태"),
        )
        for suffix, logic_type, expression, delay_s, description in specs:
            result.append({
                "logic_id": f"NATIVE_OPCUA_VLV_{point}_{suffix}",
                "control_point_id": point,
                "logic_type": logic_type,
                "expression": expression,
                "delay_s": delay_s,
                "enabled_default": 1,
                "implementation_status": "NATIVE_OPCUA_CONNECTED",
                "description_ko": description,
            })
    return result


def encode(fields: list[str], rows: list[dict[str, object]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def check_or_write(path: Path, expected: str, check: bool) -> None:
    if check:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.read_text(encoding="utf-8") != expected:
            raise ValueError(f"{path}: generated contract is stale")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(expected, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    inventory = read_inventory()
    nodes = make_node_rows(inventory)
    logic = make_logic_rows(inventory)
    if len(logic) != 72:
        raise AssertionError(f"expected 72 logic rows, got {len(logic)}")
    check_or_write(NODES, encode(NODE_FIELDS, nodes), args.check)
    check_or_write(LOGIC, encode(LOGIC_FIELDS, logic), args.check)
    print(f"PASS: native_valves={len(inventory)} nodes={len(nodes)} logic={len(logic)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
