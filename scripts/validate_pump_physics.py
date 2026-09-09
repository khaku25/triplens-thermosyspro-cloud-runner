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
        "speed": "driveHP.speedRpm",
        "valve": "checkValveHP.ouvert",
        "flow": "PompeAlimHP.Q",
        "process": ("BallonHP.yLevel.signal", "BallonHP.P"),
    },
    "FWP-IP": {
        "breaker": "breakerIPClosed",
        "torque": "driveIP.motorTorque",
        "speed": "driveIP.speedRpm",
        "valve": "checkValveIP.ouvert",
        "flow": "PompeAlimMP.Q",
        "process": ("BallonMP.yLevel.signal", "BallonMP.P"),
    },
    "FWP-LP": {
        "breaker": "breakerLPClosed",
        "torque": "driveLP.motorTorque",
        "speed": "driveLP.speedRpm",
        "valve": "checkValveLP.ouvert",
        "flow": "PompeAlimBP.Q",
        "process": ("Condenseur.yNiveau.signal", "BallonBP.yLevel.signal"),
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
    final_time = number(after, time_field)
    process_diagnostics = ",".join(
        f"{canonical(field)}={number(after, field):.9g}"
        for field in process_fields
    )
    print(
        f"METRICS {args.pump_id}: final_time={final_time:.9g} "
        f"breaker={after[resolved['breaker']]} "
        f"torque={number(after, resolved['torque']):.9g} "
        f"speed={number(after, resolved['speed']):.9g} "
        f"valve={after[resolved['valve']]} "
        f"flow={number(after, resolved['flow']):.9g} "
        f"process=[{process_diagnostics}]",
        flush=True,
    )

    time_tolerance = max(1e-6, abs(args.stop_time)*1e-8)
    if final_time + time_tolerance < args.stop_time:
        raise ValueError(
            f"RAW CSV stopped early at {final_time:.9g}s; "
            f"expected {args.stop_time:.9g}s"
        )

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

    if logical(after, resolved["valve"]):
        raise ValueError("pump discharge check valve did not close")

    process_changes = [
        relative_change(number(before, field), number(after, field))
        for field in process_fields
    ]
    if max(process_changes, default=0) <= 1e-7:
        raise ValueError("downstream ThermoSysPro process did not respond")

    protection_names = {
        "hp_hh": "hpDrumLevelHHPickup",
        "hp_ll": "hpDrumLevelLLPickup",
        "ip_hh": "ipDrumLevelHHPickup",
        "ip_ll": "ipDrumLevelLLPickup",
        "lp_hh": "lpDrumLevelHHPickup",
        "lp_ll": "lpDrumLevelLLPickup",
        "gt_request": "gtTripRequest",
        "st_request": "stTripRequest",
        "gt_latched": "gtTripLatched",
        "st_latched": "stTripLatched",
        "relay_received": "relay86GTTripReceived",
        "relay_operated": "relay86GTOperated",
        "gt_breaker": "gt52GClosed",
        "st_breaker": "st52GClosed",
        "gt_grid_power": "gtGridElectricalPower",
        "st_grid_power": "stGridElectricalPower",
    }
    protection = {
        key: resolve(headers, raw_name)
        for key, raw_name in protection_names.items()
    }

    first_post = post[0]
    if logical(first_post, protection["gt_latched"]) or logical(
        first_post, protection["st_latched"]
    ):
        raise ValueError(
            "plant trip latched directly with the pump breaker; "
            "common drum protection was bypassed"
        )

    gt_latched = logical(after, protection["gt_latched"])
    st_latched = logical(after, protection["st_latched"])
    if not st_latched:
        raise ValueError("no drum HH/LL common trip reached within the simulation")
    ll_pickup = any(
        logical(after, protection[key]) for key in ("hp_ll", "ip_ll", "lp_ll")
    )
    hh_pickup = any(
        logical(after, protection[key]) for key in ("hp_hh", "ip_hh", "lp_hh")
    )
    if gt_latched and not ll_pickup:
        raise ValueError("GT Trip latched without a persisted drum LL pickup")
    if not (ll_pickup or hh_pickup):
        raise ValueError("ST Trip latched without a persisted drum HH/LL pickup")

    if logical(after, protection["st_breaker"]):
        raise ValueError("52ST did not open after the resolved ST Trip")
    if abs(number(after, protection["st_grid_power"])) > 1:
        raise ValueError("ST grid power did not become zero after 52ST opened")
    if gt_latched:
        if logical(after, protection["gt_breaker"]):
            raise ValueError("52GT did not open after the resolved GT Trip")
        if abs(number(after, protection["gt_grid_power"])) > 1:
            raise ValueError("GT grid power did not become zero after 52GT opened")
        if not logical(after, protection["relay_received"]) or not logical(
            after, protection["relay_operated"]
        ):
            raise ValueError("86GT receive/operate sequence did not complete")

    first_trip = next(
        row
        for row in post
        if logical(row, protection["gt_latched"])
        or logical(row, protection["st_latched"])
    )
    trip_time = number(first_trip, time_field)
    trip_kind = "GT+ST" if logical(first_trip, protection["gt_latched"]) else "ST"
    print(
        f"TRIP {args.pump_id}: kind={trip_kind} time={trip_time:.9g} "
        f"52GT={'CLOSED' if logical(after, protection['gt_breaker']) else 'OPEN'} "
        f"52ST={'CLOSED' if logical(after, protection['st_breaker']) else 'OPEN'} "
        f"GT_grid_W={number(after, protection['gt_grid_power']):.9g} "
        f"ST_grid_W={number(after, protection['st_grid_power']):.9g}",
        flush=True,
    )

    print(
        f"PASS {args.pump_id}: breaker open -> torque zero -> "
        f"speed {initial_speed:.3f}->{final_speed:.3f} -> "
        f"flow {initial_flow:.6g}->{final_flow:.6g} -> process response -> "
        f"drum protection -> {trip_kind} breaker trip"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
