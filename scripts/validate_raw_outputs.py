#!/usr/bin/env python3
"""Fail closed unless an Action result contains only RAW physics and its manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


ALLOWED_FILES = {"thermosyspro-raw.csv", "raw-manifest.json"}
FORBIDDEN_ARTIFACT_TOKENS = {
    "processbus",
    "dcs1",
    "dcs2",
    "ecms",
    "incident",
    "important-changes",
    "ground-truth",
    "root-cause",
}
FORBIDDEN_METADATA_COLUMNS = {
    "scenario",
    "scenario_id",
    "scenario_name",
    "scenario_type",
    "fault",
    "fault_id",
    "fault_name",
    "fault_type",
    "root_cause",
    "ground_truth",
    "answer",
    "answer_label",
    "expected_cause",
    "expected_result",
}

PHYSICAL_BYPASS_VARIANTS = {
    "HPBP_LPBP_DYNAMIC_V11",
    "HPBP_LPBP_PHYSICAL_V11",
    "HPBP_LPBP_PHYSICAL_V12",
    "HPBP_LPBP_PHYSICAL_V12_TPH_EXPORT_V1",
    "HPBP_LPBP_PHYSICAL_V13_GT_TRIP_HANDOFF",
}
DYNAMIC_BYPASS_COLUMNS = {
    "vppSTTripLatch",
    "vppHPAdmissionPos",
    "vppIPAdmissionPos",
    "vppLPDrumAdmissionMultiplier",
    "vppHPBypassCmd",
    "vppLPBypassCmd",
    "vppHPBypassPos",
    "vppLPBypassPos",
    "vppHPSprayPos",
    "vppLPSprayPos",
    "vppHPBypassOpenLS",
    "vppHPBypassCloseLS",
    "vppLPBypassOpenLS",
    "vppLPBypassCloseLS",
    "vppHPBypassMassFlowTH",
    "vppLPBypassMassFlowTH",
    "vppHPSprayMassFlowTH",
    "vppLPSprayMassFlowTH",
    "vppHPBypassInletPressure",
    "vppLPBypassInletPressure",
    "vppHPBypassOutletPressure",
    "vppLPBypassOutletPressure",
    "vppHPBypassInletTemperature",
    "vppLPBypassInletTemperature",
    "vppHPBypassOutletTemperature",
    "vppLPBypassOutletTemperature",
    "vppCondenserPressure",
    "vppCondenserLevel",
}
NORMAL_RELIABILITY_COLUMNS = DYNAMIC_BYPASS_COLUMNS | {
    "Alternateur.Welec",
    "BallonHP.yLevel.signal",
    "BallonMP.yLevel.signal",
    "BallonBP.yLevel.signal",
    "BallonHP.P",
    "BallonMP.P",
    "BallonBP.P",
    "vppHPTurbineSteamFlowTH",
    "vppIPTurbineSteamFlowTH",
    "vppLPTurbineSteamFlowTH",
}
DERATE_BOUNDARY_COLUMNS = {
    "vppSTTripLatch",
    "vppHPBypassCmd",
    "vppLPBypassCmd",
    "vppHPBypassPos",
    "vppLPBypassPos",
    "vppHPSprayPos",
    "vppLPSprayPos",
    "vppHPBypassOpenLS",
    "vppHPBypassCloseLS",
    "vppLPBypassOpenLS",
    "vppLPBypassCloseLS",
    "vppHPBypassMassFlowTH",
    "vppLPBypassMassFlowTH",
    "vppHPSprayMassFlowTH",
    "vppLPSprayMassFlowTH",
    "vppGTExhaustMassFlowTH",
    "Temperature.y.signal",
}
GT_TRIP_HANDOFF_COLUMNS = {
    "vppGTTripCmd",
    "vppGTTripLatch",
    "vpp52GTTripCmd",
    "vpp52GTClosed",
    "vpp52STTripCmd",
    "vpp52STClosed",
    "vppGTGPowerMW",
    "vppGTGSpeedRPM",
    "vppGTExhaustMassFlowTH",
    "Alternateur.Welec",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def parse_boolean(value: str, *, column: str, row_number: int) -> bool:
    key = value.strip().lower()
    if key in {"true", "1", "1.0"}:
        return True
    if key in {"false", "0", "0.0"}:
        return False
    raise ValueError(f"RAW CSV row {row_number} {column} is not Boolean")


def validate_dynamic_bypass(path: Path, nominal_period_ms: float) -> dict[str, float]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        missing = sorted(DYNAMIC_BYPASS_COLUMNS.difference(columns))
        if missing:
            raise ValueError(
                "dynamic bypass RAW is missing columns: " + ", ".join(missing)
            )
        rows = list(reader)

    numeric_columns = DYNAMIC_BYPASS_COLUMNS.difference(
        {
            "vppSTTripLatch",
            "vppHPBypassOpenLS",
            "vppHPBypassCloseLS",
            "vppLPBypassOpenLS",
            "vppLPBypassCloseLS",
        }
    )
    numeric: dict[str, list[float]] = {column: [] for column in numeric_columns}
    times: list[float] = []
    latch: list[bool] = []
    booleans: dict[str, list[bool]] = {
        column: []
        for column in DYNAMIC_BYPASS_COLUMNS
        if column not in numeric_columns
    }
    for row_number, row in enumerate(rows, start=2):
        try:
            current_time = float(row["time"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"RAW CSV row {row_number} has invalid time") from exc
        times.append(current_time)
        for column in numeric_columns:
            try:
                value = float(row[column])
            except ValueError as exc:
                raise ValueError(
                    f"RAW CSV row {row_number} {column} is not numeric"
                ) from exc
            if not math.isfinite(value):
                raise ValueError(
                    f"RAW CSV row {row_number} {column} is not finite"
                )
            numeric[column].append(value)
        for column in booleans:
            booleans[column].append(
                parse_boolean(row[column], column=column, row_number=row_number)
            )
        latch.append(booleans["vppSTTripLatch"][-1])

    try:
        trip_index = latch.index(True)
    except ValueError as exc:
        raise ValueError("dynamic bypass RAW never asserts vppSTTripLatch") from exc
    if trip_index == 0 or any(latch[:trip_index]) or not all(latch[trip_index:]):
        raise ValueError("vppSTTripLatch must make one false-to-true transition")

    final_limits = {
        "vppHPBypassOpenLS": True,
        "vppHPBypassCloseLS": False,
        "vppLPBypassOpenLS": True,
        "vppLPBypassCloseLS": False,
    }
    for column, expected in final_limits.items():
        if booleans[column][-1] is not expected:
            raise ValueError(f"dynamic bypass final state is wrong for {column}")
    for column in ("vppHPBypassPos", "vppLPBypassPos"):
        if numeric[column][-1] < 0.95:
            raise ValueError(f"dynamic bypass did not reach open limit: {column}")
    for column in (
        "vppHPAdmissionPos",
        "vppIPAdmissionPos",
        "vppLPDrumAdmissionMultiplier",
    ):
        if numeric[column][-1] > 0.01:
            raise ValueError(f"Trip isolation did not reach closed state: {column}")
    for column in ("vppHPBypassMassFlowTH", "vppLPBypassMassFlowTH"):
        if max(numeric[column][trip_index:]) <= 0:
            raise ValueError(f"no positive physical bypass flow was produced: {column}")
    for column in (
        "vppHPBypassInletPressure",
        "vppLPBypassInletPressure",
        "vppHPBypassOutletPressure",
        "vppLPBypassOutletPressure",
        "vppCondenserPressure",
    ):
        if min(numeric[column]) <= 0:
            raise ValueError(f"non-positive pressure in dynamic bypass RAW: {column}")

    crossings: dict[str, float] = {}
    if nominal_period_ms <= 20.0:
        trip_time = times[trip_index]
        targets = {
            "vppHPAdmissionPos": (lambda value: value <= 0.04, 0.150),
            "vppIPAdmissionPos": (lambda value: value <= 0.04, 0.150),
            "vppLPDrumAdmissionMultiplier": (lambda value: value <= 0.05, 0.150),
            "vppHPBypassPos": (lambda value: value >= 0.95, 0.300),
            "vppLPBypassPos": (lambda value: value >= 0.95, 0.400),
            "vppHPSprayPos": (lambda value: value >= 0.95, 0.050),
            "vppLPSprayPos": (lambda value: value >= 0.95, 0.050),
        }
        tolerance_s = max(0.005, 2*nominal_period_ms/1000)
        for column, (crossed, expected_s) in targets.items():
            crossing_time = next(
                (times[index] for index in range(trip_index, len(times))
                 if crossed(numeric[column][index])),
                None,
            )
            if crossing_time is None:
                raise ValueError(f"dynamic response never crosses target: {column}")
            elapsed = crossing_time - trip_time
            if abs(elapsed - expected_s) > tolerance_s:
                raise ValueError(
                    f"dynamic response timing mismatch for {column}: "
                    f"{elapsed:.6g}s, expected {expected_s:.6g}s"
                )
            crossings[column] = elapsed
    return crossings


def validate_normal_operation(path: Path) -> dict[str, float]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        missing = sorted(NORMAL_RELIABILITY_COLUMNS.difference(columns))
        if missing:
            raise ValueError(
                "normal-operation RAW is missing columns: " + ", ".join(missing)
            )
        rows = list(reader)

    boolean_columns = {
        "vppSTTripLatch",
        "vppHPBypassOpenLS",
        "vppHPBypassCloseLS",
        "vppLPBypassOpenLS",
        "vppLPBypassCloseLS",
    }
    numeric_columns = NORMAL_RELIABILITY_COLUMNS.difference(boolean_columns)
    numeric: dict[str, list[float]] = {column: [] for column in numeric_columns}
    boolean: dict[str, list[bool]] = {column: [] for column in boolean_columns}
    for row_number, row in enumerate(rows, start=2):
        for column in numeric_columns:
            try:
                value = float(row[column])
            except ValueError as exc:
                raise ValueError(
                    f"RAW CSV row {row_number} {column} is not numeric"
                ) from exc
            if not math.isfinite(value):
                raise ValueError(
                    f"RAW CSV row {row_number} {column} is not finite"
                )
            numeric[column].append(value)
        for column in boolean_columns:
            boolean[column].append(
                parse_boolean(row[column], column=column, row_number=row_number)
            )

    if any(boolean["vppSTTripLatch"]):
        raise ValueError("normal-operation RAW asserts vppSTTripLatch")
    expected_limits = {
        "vppHPBypassOpenLS": False,
        "vppHPBypassCloseLS": True,
        "vppLPBypassOpenLS": False,
        "vppLPBypassCloseLS": True,
    }
    for column, expected in expected_limits.items():
        if any(value is not expected for value in boolean[column]):
            raise ValueError(f"normal-operation limit switch changed: {column}")

    for column in (
        "vppHPBypassCmd",
        "vppLPBypassCmd",
        "vppHPBypassPos",
        "vppLPBypassPos",
        "vppHPSprayPos",
        "vppLPSprayPos",
    ):
        if max(abs(value) for value in numeric[column]) > 1e-8:
            raise ValueError(f"normal-operation command/position changed: {column}")
    for column in ("vppHPBypassMassFlowTH", "vppLPBypassMassFlowTH"):
        if max(abs(value) for value in numeric[column]) > 1e-6:
            raise ValueError(f"normal-operation bypass produced steam flow: {column}")
    for column in ("vppHPSprayMassFlowTH", "vppLPSprayMassFlowTH"):
        if min(numeric[column]) < 0 or max(numeric[column]) > 1e-3:
            raise ValueError(f"normal-operation spray seat leakage is invalid: {column}")

    admission_setpoints = {
        "vppHPAdmissionPos": 0.8,
        "vppIPAdmissionPos": 0.8,
        "vppLPDrumAdmissionMultiplier": 1.0,
    }
    for column, setpoint in admission_setpoints.items():
        maximum_error = max(abs(value - setpoint) for value in numeric[column])
        if maximum_error > 1e-5:
            raise ValueError(
                f"normal-operation admission drift for {column}: {maximum_error:.6g}"
            )

    positive_columns = {
        "Alternateur.Welec",
        "BallonHP.P",
        "BallonMP.P",
        "BallonBP.P",
        "vppHPTurbineSteamFlowTH",
        "vppIPTurbineSteamFlowTH",
        "vppLPTurbineSteamFlowTH",
        "vppHPBypassInletPressure",
        "vppLPBypassInletPressure",
        "vppHPBypassOutletPressure",
        "vppLPBypassOutletPressure",
        "vppCondenserPressure",
        "vppHPBypassInletTemperature",
        "vppLPBypassInletTemperature",
        "vppHPBypassOutletTemperature",
        "vppLPBypassOutletTemperature",
    }
    for column in positive_columns:
        if min(numeric[column]) <= 0:
            raise ValueError(f"normal-operation value is non-positive: {column}")

    level_columns = (
        "BallonHP.yLevel.signal",
        "BallonMP.yLevel.signal",
        "BallonBP.yLevel.signal",
        "vppCondenserLevel",
    )
    for column in level_columns:
        if min(numeric[column]) <= 0 or max(numeric[column]) >= 3:
            raise ValueError(f"normal-operation level leaves physical bounds: {column}")
        drift = abs(numeric[column][-1] - numeric[column][0])
        if drift > 0.25:
            raise ValueError(f"normal-operation level drift for {column}: {drift:.6g} m")

    relative_drift_columns = (
        "Alternateur.Welec",
        "BallonHP.P",
        "BallonMP.P",
        "BallonBP.P",
        "vppHPTurbineSteamFlowTH",
        "vppIPTurbineSteamFlowTH",
        "vppLPTurbineSteamFlowTH",
        "vppCondenserPressure",
    )
    relative_drift: dict[str, float] = {}
    for column in relative_drift_columns:
        initial = numeric[column][0]
        drift = abs(numeric[column][-1] - initial) / abs(initial)
        relative_drift[column] = drift
        limit = 0.15 if column == "Alternateur.Welec" else 0.20
        if drift > limit:
            raise ValueError(
                f"normal-operation relative drift for {column}: {drift:.3%}"
            )
    return {
        "generator_relative_drift": relative_drift["Alternateur.Welec"],
        "maximum_level_drift_m": max(
            abs(numeric[column][-1] - numeric[column][0])
            for column in level_columns
        ),
        "maximum_pressure_or_flow_relative_drift": max(
            drift
            for column, drift in relative_drift.items()
            if column != "Alternateur.Welec"
        ),
        "maximum_bypass_steam_flow_t_h": max(
            max(abs(value) for value in numeric[column])
            for column in ("vppHPBypassMassFlowTH", "vppLPBypassMassFlowTH")
        ),
    }


def validate_derate_operation(path: Path) -> dict[str, float]:
    """Verify that the exhaust DERATE profile does not assert turbine Trip."""
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        missing = sorted(DERATE_BOUNDARY_COLUMNS.difference(columns))
        if missing:
            raise ValueError(
                "GT DERATE RAW is missing columns: " + ", ".join(missing)
            )
        rows = list(reader)

    boolean_columns = {
        "vppSTTripLatch",
        "vppHPBypassOpenLS",
        "vppHPBypassCloseLS",
        "vppLPBypassOpenLS",
        "vppLPBypassCloseLS",
    }
    numeric_columns = DERATE_BOUNDARY_COLUMNS.difference(boolean_columns)
    numeric: dict[str, list[float]] = {column: [] for column in numeric_columns}
    boolean: dict[str, list[bool]] = {column: [] for column in boolean_columns}
    for row_number, row in enumerate(rows, start=2):
        for column in numeric_columns:
            try:
                value = float(row[column])
            except ValueError as exc:
                raise ValueError(
                    f"RAW CSV row {row_number} {column} is not numeric"
                ) from exc
            if not math.isfinite(value):
                raise ValueError(
                    f"RAW CSV row {row_number} {column} is not finite"
                )
            numeric[column].append(value)
        for column in boolean_columns:
            boolean[column].append(
                parse_boolean(row[column], column=column, row_number=row_number)
            )

    if any(boolean["vppSTTripLatch"]):
        raise ValueError("GT DERATE profile asserted the embedded ST Trip latch")
    expected_limits = {
        "vppHPBypassOpenLS": False,
        "vppHPBypassCloseLS": True,
        "vppLPBypassOpenLS": False,
        "vppLPBypassCloseLS": True,
    }
    for column, expected in expected_limits.items():
        if any(value is not expected for value in boolean[column]):
            raise ValueError(f"GT DERATE changed bypass limit switch: {column}")
    for column in (
        "vppHPBypassCmd",
        "vppLPBypassCmd",
        "vppHPBypassPos",
        "vppLPBypassPos",
        "vppHPSprayPos",
        "vppLPSprayPos",
    ):
        if max(abs(value) for value in numeric[column]) > 1e-8:
            raise ValueError(f"GT DERATE actuated the Trip-only bypass path: {column}")
    for column in (
        "vppHPBypassMassFlowTH",
        "vppLPBypassMassFlowTH",
        "vppHPSprayMassFlowTH",
        "vppLPSprayMassFlowTH",
    ):
        if max(abs(value) for value in numeric[column]) > 1e-6:
            raise ValueError(f"GT DERATE produced Trip-only bypass flow: {column}")

    flow = numeric["vppGTExhaustMassFlowTH"]
    temperature = numeric["Temperature.y.signal"]
    expected = {
        "flow_initial_t_h": (flow[0], 2184.984),
        "flow_final_t_h": (flow[-1], 540.0),
        "temperature_initial_k": (temperature[0], 893.75),
        "temperature_final_k": (temperature[-1], 550.0),
    }
    for label, (actual, target) in expected.items():
        if not math.isclose(actual, target, rel_tol=1e-8, abs_tol=1e-6):
            raise ValueError(
                f"GT DERATE {label} is {actual:.12g}, expected {target:.12g}"
            )
    return {label: actual for label, (actual, _) in expected.items()}


def validate_gt_trip_handoff(
    path: Path, nominal_period_ms: float
) -> dict[str, float]:
    """Fail closed unless GT/ST electrical states originate in Modelica RAW."""
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        missing = sorted(GT_TRIP_HANDOFF_COLUMNS.difference(columns))
        if missing:
            raise ValueError(
                "GT Trip physical RAW is missing columns: " + ", ".join(missing)
            )
        rows = list(reader)

    times = [float(row["time"]) for row in rows]
    bool_columns = (
        "vppGTTripCmd", "vppGTTripLatch", "vpp52GTTripCmd",
        "vpp52GTClosed", "vpp52STTripCmd", "vpp52STClosed",
    )
    digital = {
        column: [
            parse_boolean(row[column], column=column, row_number=index)
            for index, row in enumerate(rows, start=2)
        ]
        for column in bool_columns
    }
    analog: dict[str, list[float]] = {}
    for column in (
        "vppGTGPowerMW", "vppGTGSpeedRPM", "vppGTExhaustMassFlowTH",
        "Alternateur.Welec",
    ):
        values = [float(row[column]) for row in rows]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"GT Trip physical RAW contains non-finite {column}")
        analog[column] = values

    def edge(column: str, old: bool, new: bool) -> float:
        values = digital[column]
        matches = [
            times[index]
            for index in range(1, len(values))
            if values[index - 1] is old and values[index] is new
        ]
        if len(matches) != 1:
            raise ValueError(
                f"{column} must make exactly one {old}->{new} transition"
            )
        return matches[0]

    gt_cmd_s = edge("vppGTTripCmd", False, True)
    gt_latch_s = edge("vppGTTripLatch", False, True)
    gt_52_cmd_s = edge("vpp52GTTripCmd", False, True)
    gt_52_open_s = edge("vpp52GTClosed", True, False)
    st_52_cmd_s = edge("vpp52STTripCmd", False, True)
    st_52_open_s = edge("vpp52STClosed", True, False)
    tolerance_s = max(0.002, 2 * nominal_period_ms / 1000)
    expectations = {
        "GT latch": (gt_latch_s - gt_cmd_s, 0.0),
        "52GT Trip command": (gt_52_cmd_s - gt_cmd_s, 0.055),
        "52GT opening": (gt_52_open_s - gt_cmd_s, 0.080),
        "52ST Trip command": (st_52_cmd_s - gt_cmd_s, 0.0),
        "52ST opening": (st_52_open_s - gt_cmd_s, 0.100),
    }
    for label, (actual, expected) in expectations.items():
        if abs(actual - expected) > tolerance_s:
            raise ValueError(
                f"{label} timing is {actual:.6f}s, expected {expected:.6f}s"
            )

    power = analog["vppGTGPowerMW"]
    speed = analog["vppGTGSpeedRPM"]
    exhaust = analog["vppGTExhaustMassFlowTH"]
    open_index = next(index for index, time_s in enumerate(times) if time_s >= gt_52_open_s)
    if power[0] <= 0 or max(abs(value) for value in power[open_index:]) > 1e-6:
        raise ValueError("GT generator output did not become zero after 52GT opened")
    if speed[0] <= 0 or speed[-1] >= 0.05 * speed[0]:
        raise ValueError("GT shaft speed did not physically coast down")
    if exhaust[0] <= 0 or exhaust[-1] > 0.10 * exhaust[0]:
        raise ValueError("GT exhaust mass flow did not reach the purge/coastdown boundary")
    if max(abs(value) for value in analog["Alternateur.Welec"]) <= 0:
        raise ValueError("ST generator physical power is missing or identically zero")

    return {
        "gt_trip_command_time_s": gt_cmd_s,
        "cb_52gt_trip_command_time_s": gt_52_cmd_s,
        "cb_52gt_open_time_s": gt_52_open_s,
        "cb_52st_open_time_s": st_52_open_s,
        "gtg_initial_power_mw": power[0],
        "gtg_final_power_mw": power[-1],
        "gtg_initial_speed_rpm": speed[0],
        "gtg_final_speed_rpm": speed[-1],
        "gt_exhaust_final_t_h": exhaust[-1],
    }


def validate_raw_csv(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            columns = next(reader)
        except StopIteration as exc:
            raise ValueError("thermosyspro-raw.csv is empty") from exc
        column_keys = [normalized(column) for column in columns]
        forbidden = sorted(set(column_keys).intersection(FORBIDDEN_METADATA_COLUMNS))
        if forbidden:
            raise ValueError(
                "RAW CSV contains answer/scenario metadata: " + ", ".join(forbidden)
            )
        if "time" not in column_keys:
            raise ValueError("RAW CSV is missing the native time column")
        time_index = column_keys.index("time")
        previous: float | None = None
        row_count = 0
        duplicate_count = 0
        first_time: float | None = None
        last_time: float | None = None
        for row_number, row in enumerate(reader, start=2):
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) != len(columns):
                raise ValueError(
                    f"RAW CSV row {row_number} width does not match the header"
                )
            try:
                current = float(row[time_index])
            except ValueError as exc:
                raise ValueError(
                    f"RAW CSV row {row_number} time is not numeric"
                ) from exc
            if not math.isfinite(current):
                raise ValueError(f"RAW CSV row {row_number} time is not finite")
            if previous is not None and current < previous:
                raise ValueError("RAW CSV native time reverses")
            if previous is not None and current == previous:
                duplicate_count += 1
            if first_time is None:
                first_time = current
            last_time = current
            previous = current
            row_count += 1
    if row_count < 2:
        raise ValueError("RAW CSV needs at least two data rows")
    return {
        "columns": columns,
        "row_count": row_count,
        "duplicate_count": duplicate_count,
        "first_time_s": first_time,
        "last_time_s": last_time,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if not args.output_dir.is_dir():
        parser.error("--output-dir must exist")
    files = {
        path.relative_to(args.output_dir).as_posix(): path
        for path in args.output_dir.rglob("*")
        if path.is_file()
    }
    unexpected = sorted(set(files).difference(ALLOWED_FILES))
    missing = sorted(ALLOWED_FILES.difference(files))
    forbidden_named = sorted(
        relative
        for relative in files
        if any(token in relative.lower() for token in FORBIDDEN_ARTIFACT_TOKENS)
    )
    if missing:
        raise ValueError("RAW-only bundle is missing: " + ", ".join(missing))
    if unexpected:
        raise ValueError(
            "RAW-only bundle contains unexpected files: " + ", ".join(unexpected)
        )
    if forbidden_named:
        raise ValueError(
            "RAW-only bundle contains derived/answer artifacts: "
            + ", ".join(forbidden_named)
        )

    raw_path = files["thermosyspro-raw.csv"]
    manifest_path = files["raw-manifest.json"]
    raw_summary = validate_raw_csv(raw_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("artifact_type") != "THERMOSYSPRO_RAW_ONLY":
        raise ValueError("raw-manifest.json has the wrong artifact_type")
    raw = manifest.get("raw")
    if not isinstance(raw, dict):
        raise ValueError("raw-manifest.json is missing raw metadata")
    expected = {
        "file": raw_path.name,
        "bytes": raw_path.stat().st_size,
        "sha256": sha256(raw_path),
        "row_count": raw_summary["row_count"],
        "columns": raw_summary["columns"],
        "first_time_s": raw_summary["first_time_s"],
        "last_time_s": raw_summary["last_time_s"],
        "duplicate_native_time_rows": raw_summary["duplicate_count"],
        "copy_policy": "BYTE_FOR_BYTE_FROM_OPENMODELICA_RESULT",
        "rows_modified": False,
        "columns_added": False,
        "columns_removed": False,
    }
    for key, value in expected.items():
        if raw.get(key) != value:
            raise ValueError(f"raw-manifest.json mismatch for {key}")
    boundary = manifest.get("boundary")
    if not isinstance(boundary, dict):
        raise ValueError("raw-manifest.json is missing the ownership boundary")
    if boundary.get("action_output") != ["MODELICA_RAW_PHYSICS"]:
        raise ValueError("Action output boundary is not RAW-only")
    if boundary.get("scenario_label_included") is not False:
        raise ValueError("scenario labels must not be included")
    if boundary.get("root_cause_label_included") is not False:
        raise ValueError("root-cause labels must not be included")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("raw-manifest.json is missing runtime metadata")
    sampling = manifest.get("sampling")
    if not isinstance(sampling, dict):
        raise ValueError("raw-manifest.json is missing sampling metadata")
    try:
        requested_start_s = float(sampling["requested_start_time_s"])
        requested_stop_s = float(sampling["requested_stop_time_s"])
        nominal_period_ms = float(sampling["nominal_csv_period_ms"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("raw-manifest.json has invalid simulation boundaries") from exc
    if not all(
        math.isfinite(value)
        for value in (requested_start_s, requested_stop_s, nominal_period_ms)
    ) or requested_stop_s <= requested_start_s or nominal_period_ms <= 0:
        raise ValueError("raw-manifest.json has invalid simulation boundaries")
    completion_tolerance_s = max(1e-9, nominal_period_ms / 2000.0)
    if abs(float(raw_summary["first_time_s"]) - requested_start_s) > completion_tolerance_s:
        raise ValueError("RAW simulation does not reach the requested start boundary")
    if abs(float(raw_summary["last_time_s"]) - requested_stop_s) > completion_tolerance_s:
        raise ValueError(
            "RAW simulation ended early: "
            f"last_time={raw_summary['last_time_s']} s, "
            f"requested_stop_time={requested_stop_s} s"
        )
    if runtime.get("model_variant") in PHYSICAL_BYPASS_VARIANTS:
        transform = runtime.get("source_transform")
        if not isinstance(transform, dict):
            raise ValueError("dynamic bypass manifest is missing source-transform proof")
        variant = str(runtime.get("model_variant", ""))
        if variant.startswith("HPBP_LPBP_PHYSICAL_V13"):
            expected_marker = "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V13"
        elif variant.startswith("HPBP_LPBP_PHYSICAL_V12"):
            expected_marker = "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V12"
        else:
            expected_marker = "TRIPLENS_VPP_TURBINE_BYPASS_PATCH_V11"
        if transform.get("marker") != expected_marker:
            raise ValueError("dynamic bypass manifest has the wrong patch marker")
        digest = transform.get("patched_model_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("dynamic bypass manifest has an invalid patched-model hash")
        if sampling.get("profile") == "normal_3min":
            reliability = validate_normal_operation(raw_path)
            print(
                "NORMAL_OPERATION_RELIABILITY_PASS "
                + json.dumps(reliability, sort_keys=True)
            )
        elif sampling.get("profile") == "gt_derate_3min_10ms":
            derate = validate_derate_operation(raw_path)
            print(
                "GT_DERATE_BOUNDARY_VALIDATION_PASS "
                + json.dumps(derate, sort_keys=True)
            )
        else:
            crossings = validate_dynamic_bypass(raw_path, nominal_period_ms)
            print(
                "DYNAMIC_BYPASS_VALIDATION_PASS "
                + json.dumps(crossings, sort_keys=True)
            )
            if str(sampling.get("profile", "")).startswith("gt_trip_"):
                gt_trip = validate_gt_trip_handoff(raw_path, nominal_period_ms)
                print(
                    "GT_TRIP_PHYSICAL_HANDOFF_PASS "
                    + json.dumps(gt_trip, sort_keys=True)
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
