#!/usr/bin/env python3
"""Validate the breaker-to-process causal chain in a native OMC RAW CSV."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


FIELD_SETS = {
    "FWP-HP": {
        "breaker": "breakerHPClosed",
        "torque": "driveHP.motorTorque",
        "speed": "PompeAlimHP.VRot",
        "valve": "checkValveHP.ouvert",
        "flow": "PompeAlimHP.Q",
        "process": ("BallonHP.yLevel.signal", "BallonHP.P"),
    },
    "FWP-IP": {
        "breaker": "breakerIPClosed",
        "torque": "driveIP.motorTorque",
        "speed": "PompeAlimMP.VRot",
        "valve": "checkValveIP.ouvert",
        "flow": "PompeAlimMP.Q",
        "process": ("BallonMP.yLevel.signal", "BallonMP.P"),
    },
    "FWP-LP": {
        "breaker": "breakerLPClosed",
        "torque": "driveLP.motorTorque",
        "speed": "PompeAlimBP.VRot",
        "valve": "checkValveLP.ouvert",
        "flow": "PompeAlimBP.Q",
        "process": ("Condenseur.yNiveau.signal", "BallonBP.yLevel.signal"),
    },
    "COND-PUMP": {
        "breaker": "breakerLPClosed",
        "torque": "driveLP.motorTorque",
        "speed": "PompeAlimBP.VRot",
        "valve": "checkValveLP.ouvert",
        "flow": "PompeAlimBP.Q",
        "process": ("Condenseur.yNiveau.signal", "BallonBP.yLevel.signal"),
    },
    "CW-PUMP": {
        "breaker": "breakerCWClosed",
        "torque": "cwPumpDrive.motorTorque",
        "speed": "cwPumpDrive.speedRpm",
        "valve": "cwPumpDrive.checkValvePosition",
        "flow": "cwPumpDrive.massFlow.signal",
        "process": ("Condenseur.P",),
    },
}


def canonical(value: str) -> str:
    return value.lstrip("\ufeff").strip().strip('"')


def resolve(headers: list[str], expected: str) -> str:
    by_name = {canonical(item): item for item in headers}
    if expected in by_name:
        return by_name[expected]
    suffix = [raw for name, raw in by_name.items() if name.endswith("." + expected)]
    if len(suffix) == 1:
        return suffix[0]
    raise ValueError(f"missing or ambiguous RAW signal: {expected}")


def number(row: dict[str, str], field: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric RAW value for {canonical(field)}") from exc
    if not math.isfinite(value):
        raise ValueError(f"non-finite RAW value for {canonical(field)}")
    return value


def logical(row: dict[str, str], field: str) -> bool:
    value = row[field].strip().lower()
    if value in {"true", "1", "1.0"}:
        return True
    if value in {"false", "0", "0.0"}:
        return False
    raise ValueError(f"invalid logical RAW value for {canonical(field)}: {value!r}")


def relative_change(initial: float, final: float) -> float:
    return abs(final - initial) / max(abs(initial), 1e-9)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--pump-id", choices=sorted(FIELD_SETS), required=True)
    parser.add_argument("--trip-time", type=float, required=True)
    parser.add_argument("--stop-time", type=float, required=True)
    args = parser.parse_args()

    if not math.isfinite(args.stop_time) or args.stop_time <= args.trip_time:
        parser.error("--stop-time must be finite and later than --trip-time")

    with args.input.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("RAW CSV has no header")
        rows = list(reader)
        headers = list(reader.fieldnames)
    if len(rows) < 3:
        raise ValueError("RAW CSV requires at least three samples")

    fields = FIELD_SETS[args.pump_id]
    time_field = resolve(headers, "time")
    final_time = number(rows[-1], time_field)
    time_tolerance = max(1e-6, abs(args.stop_time)*1e-8)
    if final_time + time_tolerance < args.stop_time:
        raise ValueError(
            f"RAW CSV stopped early at {final_time:.9g}s; "
            f"expected {args.stop_time:.9g}s"
        )
    resolved = {
        key: resolve(headers, value)
        for key, value in fields.items()
        if key != "process"
    }
    process_fields = [resolve(headers, item) for item in fields["process"]]

    pre = [row for row in rows if number(row, time_field) < args.trip_time]
    post = [row for row in rows if number(row, time_field) >= args.trip_time]
    if not pre or len(post) < 2:
        raise ValueError("RAW CSV does not span both sides of the trip")

    before = pre[-1]
    after = post[-1]
    if not logical(before, resolved["breaker"]):
        raise ValueError("selected pump breaker was not closed before trip")
    if logical(after, resolved["breaker"]):
        raise ValueError("selected pump breaker did not open")

    initial_torque = number(before, resolved["torque"])
    final_torque = number(after, resolved["torque"])
    if initial_torque <= 0:
        raise ValueError("motor torque was not positive before trip")
    if abs(final_torque) > max(1e-3, abs(initial_torque)*1e-6):
        raise ValueError("motor torque did not collapse to zero after breaker opening")

    initial_speed = number(before, resolved["speed"])
    final_speed = number(after, resolved["speed"])
    if initial_speed <= 0 or final_speed >= initial_speed*0.9:
        raise ValueError("rotating inertia did not produce a material pump coastdown")

    initial_flow = number(before, resolved["flow"])
    final_flow = number(after, resolved["flow"])
    if abs(final_flow) >= abs(initial_flow)*0.8:
        raise ValueError("pump trip did not materially reduce process flow")

    if args.pump_id == "CW-PUMP":
        if number(after, resolved["valve"]) > 0.1:
            raise ValueError("CW boundary check valve did not close")
    elif logical(after, resolved["valve"]):
        raise ValueError("pump discharge check valve did not close")

    process_changes = [
        relative_change(number(before, field), number(after, field))
        for field in process_fields
    ]
    if max(process_changes, default=0) <= 1e-7:
        raise ValueError("downstream ThermoSysPro process did not respond")

    print(
        f"PASS {args.pump_id}: breaker open -> torque zero -> "
        f"speed {initial_speed:.3f}->{final_speed:.3f} -> "
        f"flow {initial_flow:.6g}->{final_flow:.6g} -> process response"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
