#!/usr/bin/env python3
"""Send live ECMS commands and archive only telemetry received over TCP."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import socket
import statistics
import time
from pathlib import Path

from live_protocol import (
    COMMAND_INPUTS,
    LIVE_SIGNALS,
    PROTOCOL,
    contract_sha256,
    read_frame,
    scenario_commands,
    write_frame,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--stop-time", type=float, default=2.0)
    parser.add_argument("--step-size", type=float, default=0.01)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    steps_float = args.stop_time / args.step_size
    if args.step_size <= 0 or args.stop_time <= 0 or not math.isclose(
        steps_float, round(steps_float), abs_tol=1e-9
    ):
        parser.error("stop time must be a positive integer multiple of step size")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    command_log_path = args.output_dir / "ecms-command-tx.jsonl"
    telemetry_log_path = args.output_dir / "ecms-telemetry-rx.jsonl"
    csv_path = args.output_dir / "ECMS-live-physical.csv"
    report_path = args.output_dir / "ecms-client-report.json"
    input_names = [item.fmu_name for item in COMMAND_INPUTS]
    signal_fields = [item.field for item in LIVE_SIGNALS]
    latencies_ms: list[float] = []
    previous_source_time = -math.inf
    connected_ns = time.time_ns()
    fmu_digest = ""

    with socket.create_connection((args.host, args.port), timeout=90) as connection:
        connection.settimeout(90)
        stream = connection.makefile("rwb", buffering=0)
        write_frame(stream, {
            "protocol": PROTOCOL,
            "type": "hello",
            "role": "ECMS",
            "contract_sha256": contract_sha256(),
            "requested_inputs": input_names,
            "requested_signals": signal_fields,
        })
        hello, _raw = read_frame(stream)
        if hello.get("type") != "hello_ack":
            raise ValueError("physical gateway did not acknowledge ECMS")
        if hello.get("contract_sha256") != contract_sha256():
            raise ValueError("physical gateway contract differs from ECMS")
        if int(hello.get("input_count", -1)) != len(input_names):
            raise ValueError("physical gateway input count differs from ECMS")
        if int(hello.get("telemetry_count", -1)) != len(signal_fields):
            raise ValueError("physical gateway telemetry count differs from ECMS")
        if not math.isclose(float(hello["step_size_s"]), args.step_size, abs_tol=1e-12):
            raise ValueError("physical gateway step size differs from ECMS")
        fmu_digest = str(hello["fmu_sha256"])

        with command_log_path.open("wb") as command_log, telemetry_log_path.open("wb") as telemetry_log, csv_path.open(
            "w", encoding="utf-8", newline=""
        ) as csv_stream:
            writer = csv.DictWriter(
                csv_stream,
                fieldnames=[
                    "source_time_ns", "time_s", "quality", "transport_status",
                    "transport_mode", "round_trip_latency_ms",
                    *input_names, *signal_fields,
                ],
                lineterminator="\n",
            )
            writer.writeheader()
            for seq in range(round(steps_float)):
                current_time = seq * args.step_size
                commands = scenario_commands(current_time)
                sent_ns = time.time_ns()
                command_log.write(write_frame(stream, {
                    "protocol": PROTOCOL,
                    "type": "command",
                    "seq": seq,
                    "sim_time_s": current_time,
                    "ecms_tx_wall_ns": sent_ns,
                    "values": commands,
                }))
                telemetry, raw_telemetry = read_frame(stream)
                received_ns = time.time_ns()
                telemetry_log.write(raw_telemetry)
                if telemetry.get("type") != "telemetry":
                    raise ValueError("expected telemetry frame")
                if int(telemetry.get("seq", -1)) != seq or int(
                    telemetry.get("command_seq", -1)
                ) != seq:
                    raise ValueError("telemetry sequence/ack mismatch")
                source_time = float(telemetry["source_time_s"])
                expected_time = (seq + 1) * args.step_size
                if source_time <= previous_source_time or not math.isclose(
                    source_time, expected_time, abs_tol=1e-12
                ):
                    raise ValueError("FMU source time is invalid")
                previous_source_time = source_time
                values = telemetry.get("values")
                if not isinstance(values, dict) or set(values) != set(signal_fields):
                    raise ValueError("telemetry frame has an unreviewed signal set")
                latency_ms = (received_ns - sent_ns) / 1_000_000
                latencies_ms.append(latency_ms)
                writer.writerow({
                    "source_time_ns": int(telemetry["source_time_ns"]),
                    "time_s": repr(source_time),
                    "quality": telemetry.get("quality"),
                    "transport_status": "RECEIVED_OVER_TCP",
                    "transport_mode": "TCP_JSONL_FULL_DUPLEX",
                    "round_trip_latency_ms": repr(latency_ms),
                    **{
                        name: int(value) if isinstance(value, bool) else repr(float(value))
                        for name, value in commands.items()
                    },
                    **{
                        field: int(value) if isinstance(value, bool) else repr(float(value))
                        for field, value in values.items()
                    },
                })

        write_frame(stream, {
            "protocol": PROTOCOL,
            "type": "shutdown",
            "reason": "ECMS_CAPTURE_COMPLETE",
        })
        shutdown, _raw = read_frame(stream)
        if shutdown.get("type") != "shutdown_ack":
            raise ValueError("physical gateway did not close cleanly")

    sorted_latency = sorted(latencies_ms)
    p95_index = max(0, math.ceil(0.95 * len(sorted_latency)) - 1)
    report = {
        "schema_version": "2.0",
        "status": "PASS",
        "transport_mode": "TCP_JSONL_FULL_DUPLEX",
        "protocol": PROTOCOL,
        "contract_sha256": contract_sha256(),
        "remote_endpoint": f"{args.host}:{args.port}",
        "connection_count": 1,
        "command_frames_sent": len(latencies_ms),
        "telemetry_frames_received": len(latencies_ms),
        "inputs_per_frame": len(COMMAND_INPUTS),
        "telemetry_values_per_frame": len(LIVE_SIGNALS),
        "sequence_gaps": 0,
        "malformed_frames": 0,
        "step_size_s": args.step_size,
        "stop_time_s": args.stop_time,
        "scenario": {
            "hp_steam_manual_at_s": 0.25,
            "hp_steam_manual_cmd_pu": 0.45,
            "ip_turbine_fault_at_s": 0.75,
            "ip_turbine_fault_value_pu": 0.60,
        },
        "fmu_sha256": fmu_digest,
        "latency_scope": "GITHUB_ACTION_LOOPBACK_NOT_PLANT_NETWORK",
        "round_trip_latency_ms": {
            "minimum": min(latencies_ms),
            "mean": statistics.fmean(latencies_ms),
            "p95": sorted_latency[p95_index],
            "maximum": max(latencies_ms),
        },
        "command_tx_sha256": sha256(command_log_path),
        "telemetry_rx_sha256": sha256(telemetry_log_path),
        "ecms_csv": {"file": csv_path.name, "sha256": sha256(csv_path)},
        "wall_duration_ms": (time.time_ns() - connected_ns) / 1_000_000,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "LIVE_ECMS_CLIENT_PASS "
        f"frames={len(latencies_ms)} inputs={len(COMMAND_INPUTS)} "
        f"telemetry={len(LIVE_SIGNALS)} p95_loopback_ms={report['round_trip_latency_ms']['p95']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
