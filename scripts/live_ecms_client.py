#!/usr/bin/env python3
"""Drive the physical FMU over TCP and archive only what ECMS receives."""

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

from live_protocol import COMMAND_INPUT, LIVE_SIGNALS, PROTOCOL, read_frame, write_frame


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--stop-time", type=float, default=10.0)
    parser.add_argument("--step-size", type=float, default=0.001)
    parser.add_argument("--trip-at", type=float, default=2.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.step_size <= 0 or args.stop_time <= 0:
        parser.error("stop time and step size must be positive")
    steps_float = args.stop_time / args.step_size
    if not math.isclose(steps_float, round(steps_float), abs_tol=1e-9):
        parser.error("stop time must be an integer multiple of step size")
    if not 0 < args.trip_at < args.stop_time:
        parser.error("trip time must be inside the simulated window")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    command_log_path = args.output_dir / "ecms-command-tx.jsonl"
    telemetry_log_path = args.output_dir / "ecms-telemetry-rx.jsonl"
    csv_path = args.output_dir / "ECMS-live-physical.csv"
    report_path = args.output_dir / "ecms-client-report.json"
    fields = [item[0] for item in LIVE_SIGNALS]
    latencies_ms: list[float] = []
    observed_trip_frames = 0
    previous_source_time = -math.inf
    connected_ns = time.time_ns()

    with socket.create_connection((args.host, args.port), timeout=45) as connection:
        connection.settimeout(45)
        stream = connection.makefile("rwb", buffering=0)
        write_frame(stream, {
            "protocol": PROTOCOL,
            "type": "hello",
            "role": "ECMS",
            "requested_signals": fields,
        })
        hello, _raw = read_frame(stream)
        if hello.get("type") != "hello_ack":
            raise ValueError("physical gateway did not acknowledge ECMS")
        if int(hello.get("signal_count", -1)) != len(fields):
            raise ValueError("physical gateway signal contract differs from ECMS")
        if not math.isclose(float(hello["step_size_s"]), args.step_size, abs_tol=1e-12):
            raise ValueError("physical gateway step size differs from ECMS")

        with command_log_path.open("wb") as command_log, telemetry_log_path.open("wb") as telemetry_log, csv_path.open(
            "w", encoding="utf-8", newline=""
        ) as csv_stream:
            writer = csv.DictWriter(
                csv_stream,
                fieldnames=[
                    "source_time_ns", "time_s", "quality", "transport_status",
                    "transport_mode", "round_trip_latency_ms", COMMAND_INPUT,
                    *fields,
                ],
                lineterminator="\n",
            )
            writer.writeheader()
            for seq in range(round(steps_float)):
                current_time = seq * args.step_size
                trip = current_time >= args.trip_at
                sent_ns = time.time_ns()
                raw_command = write_frame(stream, {
                    "protocol": PROTOCOL,
                    "type": "command",
                    "seq": seq,
                    "sim_time_s": current_time,
                    "ecms_tx_wall_ns": sent_ns,
                    "values": {COMMAND_INPUT: trip},
                })
                command_log.write(raw_command)
                telemetry, raw_telemetry = read_frame(stream)
                received_ns = time.time_ns()
                telemetry_log.write(raw_telemetry)
                if telemetry.get("type") != "telemetry":
                    raise ValueError("expected a telemetry frame")
                if int(telemetry.get("seq", -1)) != seq:
                    raise ValueError("telemetry sequence mismatch")
                if int(telemetry.get("command_seq", -1)) != seq:
                    raise ValueError("telemetry does not acknowledge the current command")
                source_time = float(telemetry["source_time_s"])
                if source_time <= previous_source_time:
                    raise ValueError("FMU source time is not strictly increasing")
                previous_source_time = source_time
                expected_time = (seq + 1) * args.step_size
                if not math.isclose(source_time, expected_time, abs_tol=1e-12):
                    raise ValueError("FMU source time does not match the communication step")
                values = telemetry.get("values")
                if not isinstance(values, dict) or set(values) != set(fields):
                    raise ValueError("telemetry frame has an unreviewed signal set")
                latency_ms = (received_ns - sent_ns) / 1_000_000
                latencies_ms.append(latency_ms)
                observed_trip_frames += int(bool(values["gt_trip_latch"]))
                writer.writerow({
                    "source_time_ns": int(telemetry["source_time_ns"]),
                    "time_s": repr(source_time),
                    "quality": telemetry.get("quality"),
                    "transport_status": "RECEIVED_OVER_TCP",
                    "transport_mode": "TCP_JSONL_FULL_DUPLEX",
                    "round_trip_latency_ms": repr(latency_ms),
                    COMMAND_INPUT: int(trip),
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
        "schema_version": "1.0",
        "status": "PASS",
        "transport_mode": "TCP_JSONL_FULL_DUPLEX",
        "protocol": PROTOCOL,
        "remote_endpoint": f"{args.host}:{args.port}",
        "connection_count": 1,
        "command_frames_sent": len(latencies_ms),
        "telemetry_frames_received": len(latencies_ms),
        "sequence_gaps": 0,
        "malformed_frames": 0,
        "trip_command_time_s": args.trip_at,
        "observed_trip_frames": observed_trip_frames,
        "step_size_s": args.step_size,
        "stop_time_s": args.stop_time,
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
        "signal_count": len(fields),
        "wall_duration_ms": (time.time_ns() - connected_ns) / 1_000_000,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "LIVE_ECMS_CLIENT_PASS "
        f"frames={len(latencies_ms)} signals={len(fields)} "
        f"p95_loopback_ms={report['round_trip_latency_ms']['p95']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
