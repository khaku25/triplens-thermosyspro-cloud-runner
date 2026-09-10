#!/usr/bin/env python3
"""Run an OpenModelica Co-Simulation FMU behind a full-duplex TCP gateway."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import socket
import tempfile
import time
from pathlib import Path
from typing import Any

from live_protocol import COMMAND_INPUT, LIVE_SIGNALS, PROTOCOL, read_frame, write_frame


class PhysicalFMU:
    """Small FMPy adapter that exposes only the reviewed live wire contract."""

    def __init__(self, fmu_path: Path, stop_time: float, tolerance: float) -> None:
        try:
            from fmpy import extract, read_model_description
            from fmpy.fmi2 import FMU2Slave
        except ImportError as exc:  # pragma: no cover - exercised in Action
            raise RuntimeError("FMPy is required; install requirements-live.txt") from exc

        self._directory = Path(tempfile.mkdtemp(prefix="triplens-live-fmu-"))
        extract(str(fmu_path), unzipdir=str(self._directory))
        description = read_model_description(str(fmu_path))
        if description.fmiVersion != "2.0":
            raise ValueError(f"expected FMI 2.0, got {description.fmiVersion}")
        if description.coSimulation is None:
            raise ValueError("FMU does not expose the Co-Simulation interface")

        variables = {variable.name: variable for variable in description.modelVariables}
        required = {COMMAND_INPUT, *(item[1] for item in LIVE_SIGNALS)}
        missing = sorted(required.difference(variables))
        if missing:
            raise ValueError("FMU contract variables missing: " + ", ".join(missing))
        command = variables[COMMAND_INPUT]
        if command.causality != "input" or command.type != "Boolean":
            raise ValueError("vppExternalTripCommand is not a Boolean FMU input")
        for _field, name, expected_type, _unit, _owner in LIVE_SIGNALS:
            variable = variables[name]
            if variable.type != expected_type:
                raise ValueError(f"{name}: expected {expected_type}, got {variable.type}")

        self.guid = description.guid
        self.model_identifier = description.coSimulation.modelIdentifier
        self.generation_tool = description.generationTool or ""
        self._variables = variables
        self._slave = FMU2Slave(
            guid=description.guid,
            unzipDirectory=str(self._directory),
            modelIdentifier=self.model_identifier,
            instanceName="TripLensPhysicalPlant",
        )
        self._slave.instantiate()
        self._slave.setupExperiment(
            startTime=0.0,
            stopTime=stop_time,
            tolerance=tolerance,
        )
        self._slave.setBoolean([command.valueReference], [False])
        self._slave.enterInitializationMode()
        self._slave.exitInitializationMode()
        self._closed = False

    def set_trip(self, value: bool) -> None:
        variable = self._variables[COMMAND_INPUT]
        self._slave.setBoolean([variable.valueReference], [value])

    def do_step(self, current_time: float, step_size: float) -> None:
        self._slave.doStep(
            currentCommunicationPoint=current_time,
            communicationStepSize=step_size,
        )

    def values(self) -> dict[str, float | bool]:
        result: dict[str, float | bool] = {}
        real_specs = [item for item in LIVE_SIGNALS if item[2] == "Real"]
        bool_specs = [item for item in LIVE_SIGNALS if item[2] == "Boolean"]
        real_values = self._slave.getReal([
            self._variables[item[1]].valueReference for item in real_specs
        ])
        bool_values = self._slave.getBoolean([
            self._variables[item[1]].valueReference for item in bool_specs
        ])
        for spec, value in zip(real_specs, real_values):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"FMU returned non-finite physical value: {spec[1]}")
            result[spec[0]] = number
        for spec, value in zip(bool_specs, bool_values):
            result[spec[0]] = bool(value)
        return result

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._slave.terminate()
        finally:
            self._slave.freeInstance()
            shutil.rmtree(self._directory, ignore_errors=True)
            self._closed = True


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fmu", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--stop-time", type=float, default=10.0)
    parser.add_argument("--step-size", type=float, default=0.001)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.fmu.is_file():
        parser.error("--fmu does not exist")
    if args.stop_time <= 0 or args.step_size <= 0:
        parser.error("stop time and step size must be positive")
    steps_float = args.stop_time / args.step_size
    if not math.isclose(steps_float, round(steps_float), abs_tol=1e-9):
        parser.error("stop time must be an integer multiple of step size")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    command_log_path = args.output_dir / "gateway-command-rx.jsonl"
    telemetry_log_path = args.output_dir / "gateway-telemetry-tx.jsonl"
    report_path = args.output_dir / "gateway-report.json"
    model = PhysicalFMU(args.fmu, args.stop_time, args.tolerance)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(1)
    server.settimeout(45)
    selected_port = server.getsockname()[1]
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    args.ready_file.write_text(
        json.dumps({
            "protocol": PROTOCOL,
            "host": args.host,
            "port": selected_port,
            "pid": __import__("os").getpid(),
            "fmu_sha256": sha256(args.fmu),
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    frame_count = 0
    command_true_frames = 0
    sequence_errors = 0
    started_ns = time.time_ns()
    try:
        connection, peer = server.accept()
        with connection:
            connection.settimeout(45)
            stream = connection.makefile("rwb", buffering=0)
            hello, _raw = read_frame(stream)
            if hello.get("type") != "hello" or hello.get("role") != "ECMS":
                raise ValueError("first network frame must be the ECMS hello")
            write_frame(stream, {
                "protocol": PROTOCOL,
                "type": "hello_ack",
                "role": "PHYSICAL_FMU_GATEWAY",
                "fmu_guid": model.guid,
                "model_identifier": model.model_identifier,
                "generation_tool": model.generation_tool,
                "step_size_s": args.step_size,
                "stop_time_s": args.stop_time,
                "signal_count": len(LIVE_SIGNALS),
            })
            current_time = 0.0
            with command_log_path.open("wb") as command_log, telemetry_log_path.open("wb") as telemetry_log:
                for expected_seq in range(round(steps_float)):
                    command, raw_command = read_frame(stream)
                    if command.get("type") != "command":
                        raise ValueError("expected command frame")
                    seq = int(command.get("seq", -1))
                    if seq != expected_seq:
                        sequence_errors += 1
                        raise ValueError(f"command sequence {seq}, expected {expected_seq}")
                    command_time = float(command.get("sim_time_s", math.nan))
                    if not math.isclose(command_time, current_time, abs_tol=1e-12):
                        raise ValueError(
                            f"command time {command_time} does not match FMU time {current_time}"
                        )
                    values = command.get("values")
                    if not isinstance(values, dict) or set(values) != {COMMAND_INPUT}:
                        raise ValueError("command frame has an unreviewed input set")
                    trip = values[COMMAND_INPUT]
                    if not isinstance(trip, bool):
                        raise ValueError("vppExternalTripCommand must be Boolean")
                    command_log.write(raw_command)
                    command_true_frames += int(trip)

                    model.set_trip(trip)
                    model.do_step(current_time, args.step_size)
                    current_time = (expected_seq + 1) * args.step_size
                    payload: dict[str, Any] = {
                        "protocol": PROTOCOL,
                        "type": "telemetry",
                        "seq": expected_seq,
                        "command_seq": seq,
                        "source_time_s": current_time,
                        "source_time_ns": round(current_time * 1_000_000_000),
                        "gateway_tx_wall_ns": time.time_ns(),
                        "quality": "GOOD",
                        "source": "OPENMODELICA_FMI2_CS",
                        "values": model.values(),
                    }
                    raw_telemetry = write_frame(stream, payload)
                    telemetry_log.write(raw_telemetry)
                    frame_count += 1

                shutdown, _raw = read_frame(stream)
                if shutdown.get("type") != "shutdown":
                    raise ValueError("expected shutdown frame after final step")
                write_frame(stream, {
                    "protocol": PROTOCOL,
                    "type": "shutdown_ack",
                    "frames": frame_count,
                    "final_sim_time_s": current_time,
                })
    finally:
        server.close()
        model.close()

    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "transport_mode": "TCP_JSONL_FULL_DUPLEX",
        "protocol": PROTOCOL,
        "bind_host": args.host,
        "bind_port": selected_port,
        "peer_host": peer[0],
        "connection_count": 1,
        "command_frames_received": frame_count,
        "telemetry_frames_sent": frame_count,
        "command_true_frames": command_true_frames,
        "sequence_errors": sequence_errors,
        "step_size_s": args.step_size,
        "stop_time_s": args.stop_time,
        "fmu": {
            "file": args.fmu.name,
            "sha256": sha256(args.fmu),
            "guid": model.guid,
            "model_identifier": model.model_identifier,
            "generation_tool": model.generation_tool,
        },
        "command_rx_sha256": sha256(command_log_path),
        "telemetry_tx_sha256": sha256(telemetry_log_path),
        "wall_duration_ms": (time.time_ns() - started_ns) / 1_000_000,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "LIVE_FMU_GATEWAY_PASS "
        f"frames={frame_count} transport=TCP_JSONL_FULL_DUPLEX port={selected_port}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
