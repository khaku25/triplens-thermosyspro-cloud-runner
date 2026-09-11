#!/usr/bin/env python3
"""Fail closed unless commands and physical values crossed the TCP boundary."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from live_protocol import LIVE_SIGNALS, PROTOCOL


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir
    gateway = json.loads((root / "gateway-report.json").read_text(encoding="utf-8"))
    client = json.loads((root / "ecms-client-report.json").read_text(encoding="utf-8"))
    command_tx = root / "ecms-command-tx.jsonl"
    command_rx = root / "gateway-command-rx.jsonl"
    telemetry_tx = root / "gateway-telemetry-tx.jsonl"
    telemetry_rx = root / "ecms-telemetry-rx.jsonl"
    csv_path = root / "ECMS-live-physical.csv"
    errors: list[str] = []

    if gateway.get("status") != "PASS" or client.get("status") != "PASS":
        errors.append("gateway or ECMS client did not report PASS")
    for report in (gateway, client):
        if report.get("protocol") != PROTOCOL:
            errors.append("wire protocol mismatch")
        if report.get("transport_mode") != "TCP_JSONL_FULL_DUPLEX":
            errors.append("transport is not full-duplex TCP")
        if report.get("connection_count") != 1:
            errors.append("exactly one TCP session is required")
    if command_tx.read_bytes() != command_rx.read_bytes():
        errors.append("ECMS command bytes changed across TCP")
    if telemetry_tx.read_bytes() != telemetry_rx.read_bytes():
        errors.append("FMU telemetry bytes changed across TCP")
    if client.get("command_tx_sha256") != gateway.get("command_rx_sha256"):
        errors.append("command stream hashes differ")
    if client.get("telemetry_rx_sha256") != gateway.get("telemetry_tx_sha256"):
        errors.append("telemetry stream hashes differ")
    frames = int(client.get("telemetry_frames_received", 0))
    if frames < 2 or frames != int(gateway.get("telemetry_frames_sent", -1)):
        errors.append("telemetry frame counts differ")

    with csv_path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != frames:
        errors.append("ECMS CSV does not contain every received frame")
    signal_fields = [item[0] for item in LIVE_SIGNALS]
    if rows and any(not (row.get(field) or "").strip() for row in rows for field in signal_fields):
        errors.append("ECMS CSV contains an empty physical signal")
    times = [float(row["time_s"]) for row in rows]
    if any(right <= left for left, right in zip(times, times[1:])):
        errors.append("ECMS source timestamps are not strictly increasing")

    trip_at = float(client.get("trip_command_time_s", math.nan))
    pre = [
        row for row in rows
        if float(row["time_s"]) <= trip_at - 10 * float(client["step_size_s"])
    ]
    post = [row for row in rows if float(row["time_s"]) >= trip_at + 0.5]
    if not pre or not post:
        errors.append("capture lacks pre-Trip or post-Trip physical windows")
    else:
        if any(float(row["gt_trip_latch"]) != 0 for row in pre):
            errors.append("physical Trip latch asserted before ECMS command")
        if not any(float(row["gt_trip_latch"]) == 1 for row in post):
            errors.append("physical Trip latch did not follow ECMS command")
        if min(float(row["hp_admission_valve_pu"]) for row in post) >= 0.1:
            errors.append("HP admission valve did not physically close")
        if max(float(row["hp_bypass_valve_pu"]) for row in post) <= 0.9:
            errors.append("HP bypass valve did not physically open")
        if max(float(row["hp_bypass_steam_flow_t_h"]) for row in post) <= 0:
            errors.append("FMU did not solve positive HP bypass steam flow")
        pre_exhaust = float(pre[-1]["gt_exhaust_mass_flow_t_h"])
        post_exhaust = float(post[-1]["gt_exhaust_mass_flow_t_h"])
        if not post_exhaust < pre_exhaust * 0.5:
            errors.append("command-driven GT exhaust mass flow did not fall")
        changed_physical = 0
        for field in signal_fields:
            try:
                first = float(pre[-1][field])
                last = float(post[-1][field])
            except (TypeError, ValueError):
                continue
            if not math.isclose(first, last, rel_tol=1e-9, abs_tol=1e-12):
                changed_physical += 1
        if changed_physical < 10:
            errors.append("too few FMU outputs responded to the live command")

    status = "PASS" if not errors else "FAIL"
    report = {
        "schema_version": "1.0",
        "status": status,
        "proof_type": "LIVE_CLOSED_LOOP_PHYSICAL_COMMUNICATION",
        "transport_mode": "TCP_JSONL_FULL_DUPLEX",
        "command_path": "ECMS_TCP_COMMAND_TO_FMI_INPUT",
        "feedback_path": "FMI_SOLVED_OUTPUT_TO_ECMS_TCP_TELEMETRY",
        "csv_role": "POST_RECEIVE_AUDIT_ONLY_NOT_SIMULATOR_INPUT",
        "fmu_sha256": gateway.get("fmu", {}).get("sha256"),
        "trip_command_time_s": trip_at,
        "frames_compared": frames,
        "signals_per_frame": len(LIVE_SIGNALS),
        "values_received": frames * len(LIVE_SIGNALS),
        "command_stream_byte_mismatch_count": int(command_tx.read_bytes() != command_rx.read_bytes()),
        "telemetry_stream_byte_mismatch_count": int(telemetry_tx.read_bytes() != telemetry_rx.read_bytes()),
        "sequence_gaps": client.get("sequence_gaps"),
        "malformed_frames": client.get("malformed_frames"),
        "latency_scope": client.get("latency_scope"),
        "round_trip_latency_ms": client.get("round_trip_latency_ms"),
        "ecms_csv_sha256": sha256(csv_path),
        "errors": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if errors:
        raise SystemExit("LIVE_NETWORK_FAIL: " + "; ".join(errors[:8]))
    print(
        "LIVE_CLOSED_LOOP_PASS "
        f"frames={frames} values={report['values_received']} "
        "command_bytes=IDENTICAL telemetry_bytes=IDENTICAL"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
