#!/usr/bin/env python3
"""Build the physically grounded TripLens FMU valve port and logic contracts."""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "config" / "fmu_valve_control_points_v1.csv"
PORTS = ROOT / "data" / "fmu_valve_ports_v1.csv"
LOGIC = ROOT / "data" / "fmu_valve_logic_v1.csv"

EXPECTED_OBJECTS = {
    "vanne_alimentationHP",
    "vanne_vapeurHP",
    "vanne_alimentationMP",
    "vanne_vapeurMP",
    "vanne_vapeurBP",
    "vanne_alimentationBP",
    "Vanne_alimentationMPHP",
    "vanne_extraction",
    "vanne_entree_TurbineHP",
    "Vanne_alimentationMPHP1",
    "Vanne_alimentationMPHP2",
    "vanne_entree_TurbineMP",
}
NATIVE_CLASS = "ThermoSysPro.WaterSteam.PressureLosses.ControlValve"

PORT_FIELDS = [
    "port_name", "direction", "data_type", "unit", "control_point_id",
    "role", "model_binding", "grounding_status", "description_ko",
]
LOGIC_FIELDS = [
    "logic_id", "control_point_id", "logic_type", "expression", "delay_s",
    "enabled_default", "implementation_status", "description_ko",
]


def read_inventory(path: Path = INVENTORY) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    ids = [row["control_point_id"] for row in rows]
    objects = [row["native_object"] for row in rows]
    if len(rows) != 12:
        raise ValueError(f"expected 12 native valves, got {len(rows)}")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate control_point_id")
    if len(objects) != len(set(objects)):
        raise ValueError("duplicate native_object")
    if set(objects) != EXPECTED_OBJECTS:
        missing = sorted(EXPECTED_OBJECTS.difference(objects))
        extra = sorted(set(objects).difference(EXPECTED_OBJECTS))
        raise ValueError(f"native valve mismatch; missing={missing}, extra={extra}")
    for row in rows:
        if row["native_class"] != NATIVE_CLASS:
            raise ValueError(f"{row['control_point_id']}: unsupported native class")
        if row["model_status"] != "NATIVE_MAPPED":
            raise ValueError(f"{row['control_point_id']}: mapping is not grounded")
        if row["command_unit"] != "pu" or row["min_cmd"] != "0" or row["max_cmd"] != "1":
            raise ValueError(f"{row['control_point_id']}: invalid opening contract")
        required = (
            "auto_driver", "native_input", "native_position_basis", "native_cv",
            "native_flow", "native_inlet_pressure", "native_outlet_pressure",
        )
        if any(not row[field].strip() for field in required):
            raise ValueError(f"{row['control_point_id']}: incomplete native mapping")
        if "A-CV-" in " ".join(row.values()):
            raise ValueError("assumed A-CV placeholders are forbidden")
    return rows


def make_port_rows(inventory: list[dict[str, str]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in inventory:
        point = row["control_point_id"]
        prefix = f"FMU.VLV.{point}"
        adapter = f"fmuValveAdapter.{point}"
        inputs = (
            ("MODE_AUTO", "Boolean", "BOOL", "AUTO_MAN_SELECT", f"{adapter}.modeAuto",
             "AUTO 모드 선택"),
            ("MAN_CMD", "Real", "pu", "MANUAL_COMMAND", f"{adapter}.manualCmd",
             "FMU 외부 수동 개도명령"),
            ("FAULT_ENABLE", "Boolean", "BOOL", "FAULT_ENABLE", f"{adapter}.faultEnable",
             "밸브 고장 주입 활성"),
            ("FAULT_VALUE", "Real", "pu", "FAULT_FORCED_VALUE", f"{adapter}.faultValue",
             "고장 시 실제 강제 개도"),
        )
        outputs = (
            ("AUTO_CMD", "Real", "pu", "AUTOMATIC_COMMAND", row["auto_driver"],
             "기존 자동제어기 또는 원래 신호의 명령"),
            ("CMD", "Real", "pu", "SELECTED_COMMAND", f"{adapter}.selectedCmd",
             "AUTO/MAN 선택 후 정상 명령"),
            ("FB", "Real", "pu", "APPLIED_POSITION", row["native_position_basis"],
             "고장 반영 후 모델에 실제 적용되는 밸브 개도"),
            ("DEVIATION", "Real", "pu", "COMMAND_FEEDBACK_DEVIATION", f"{adapter}.deviation",
             "CMD와 FB의 편차"),
            ("FAULT_ACTIVE", "Boolean", "BOOL", "FAULT_STATUS", f"{adapter}.faultActive",
             "명령과 분리된 고장상태"),
            ("CV", "Real", "Cv", "SOLVED_CV", row["native_cv"],
             "ThermoSysPro가 계산한 밸브 Cv"),
            ("MASS_FLOW", "Real", "t/h", "SOLVED_MASS_FLOW", f"3.6*({row['native_flow']})",
             "밸브 통과 질량유량"),
            ("DP", "Real", "Pa", "SOLVED_PRESSURE_DROP",
             f"{row['native_inlet_pressure']}-{row['native_outlet_pressure']}",
             "밸브 전후 차압"),
        )
        for suffix, data_type, unit, role, binding, description in inputs:
            result.append({
                "port_name": f"{prefix}.{suffix}", "direction": "INPUT",
                "data_type": data_type, "unit": unit, "control_point_id": point,
                "role": role, "model_binding": binding,
                "grounding_status": "ADAPTER_REQUIRED", "description_ko": description,
            })
        for suffix, data_type, unit, role, binding, description in outputs:
            status = "NATIVE_MAPPED" if role in {
                "AUTOMATIC_COMMAND", "APPLIED_POSITION", "SOLVED_CV",
                "SOLVED_MASS_FLOW", "SOLVED_PRESSURE_DROP",
            } else "ADAPTER_REQUIRED"
            result.append({
                "port_name": f"{prefix}.{suffix}", "direction": "OUTPUT",
                "data_type": data_type, "unit": unit, "control_point_id": point,
                "role": role, "model_binding": binding,
                "grounding_status": status, "description_ko": description,
            })
    return result


def make_logic_rows(inventory: list[dict[str, str]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in inventory:
        point = row["control_point_id"]
        prefix = f"FMU.VLV.{point}"
        specs = (
            ("SELECT_CMD", "CONTROL_SELECT",
             f"{prefix}.CMD = if {prefix}.MODE_AUTO then {prefix}.AUTO_CMD else {prefix}.MAN_CMD",
             0, "AUTO와 수동 명령 선택"),
            ("APPLY_FAULT", "FAULT_OVERRIDE",
             f"{prefix}.FB = if {prefix}.FAULT_ENABLE then {prefix}.FAULT_VALUE else {prefix}.CMD",
             0, "고장은 CMD를 바꾸지 않고 실제 적용값 FB만 변경"),
            ("CALC_DEVIATION", "CALCULATION",
             f"{prefix}.DEVIATION = {prefix}.CMD - {prefix}.FB",
             0, "명령과 실제 적용 개도의 편차 계산"),
            ("DEVIATION_ALARM", "ALARM",
             f"abs({prefix}.DEVIATION) >= 0.05",
             1, "5% 이상 편차가 1초 지속되면 경보"),
            ("OPEN_LS", "LIMIT_STATE", f"{prefix}.FB >= 0.98",
             0, "실제 개도 기준 전개 상태"),
            ("CLOSE_LS", "LIMIT_STATE", f"{prefix}.FB <= 0.02",
             0, "실제 개도 기준 전폐 상태"),
        )
        for suffix, logic_type, expression, delay_s, description in specs:
            result.append({
                "logic_id": f"FMU_VLV_{point}_{suffix}",
                "control_point_id": point,
                "logic_type": logic_type,
                "expression": expression,
                "delay_s": delay_s,
                "enabled_default": 1,
                "implementation_status": "DESIGN_ONLY_UNTIL_FMU_BUILD",
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
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            raise ValueError(f"{path}: generated contract is stale")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    inventory = read_inventory()
    ports = make_port_rows(inventory)
    logic = make_logic_rows(inventory)
    if len(ports) != 144:
        raise ValueError(f"expected 144 valve ports, got {len(ports)}")
    if len(logic) != 72:
        raise ValueError(f"expected 72 valve logic rows, got {len(logic)}")
    check_or_write(PORTS, encode(PORT_FIELDS, ports), args.check)
    check_or_write(LOGIC, encode(LOGIC_FIELDS, logic), args.check)
    print(f"PASS: valves={len(inventory)} ports={len(ports)} logic={len(logic)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
