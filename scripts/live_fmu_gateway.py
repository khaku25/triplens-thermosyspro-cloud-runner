#!/usr/bin/env python3
"""Expose a running OpenModelica Co-Simulation FMU over full-duplex TCP."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import socket
import tempfile
import time
from pathlib import Path

from live_protocol import (
    COMMAND_INPUTS,
    LIVE_SIGNALS,
    PROTOCOL,
    contract_sha256,
    read_frame,
    write_frame,
)


class PhysicalFMU:
    """Strict FMPy adapter for the reviewed native-valve wire contract."""

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
            raise ValueError("FMU does not expose Co-Simulation")

        variables = {variable.name: variable for variable in description.modelVariables}
        required = {item.fmu_name for item in (*COMMAND_INPUTS, *LIVE_SIGNALS)}
        missing = sorted(required.difference(variables))
        if missing:
            raise ValueError("FMU contract variables missing: " + ", ".join(missing))
        for spec in COMMAND_INPUTS:
            variable = variables[spec.fmu_name]
            if variable.causality != "input" or variable.type != spec.kind:
                raise ValueError(f"{spec.fmu_name}: not the required {spec.kind} FMI input")
        for spec in LIVE_SIGNALS:
            variable = variables[spec.fmu_name]
            if variable.type != spec.kind:
                raise ValueError(f"{spec.fmu_name}: expected {spec.kind}, got {variable.type}")
            if spec.fmi_causality == "output" and variable.causality != "output":
                raise ValueError(f"{spec.fmu_name}: missing FMI output causality")
            if spec.fmi_causality == "local" and variable.causality not in (None, "local"):
                raise ValueError(f"{spec.fmu_name}: expected a readable local FMU state")

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
        self._slave.instantiate(loggingOn=True)
        self._slave.setupExperiment(startTime=0.0, stopTime=stop_time, tolerance=tolerance)
        self._slave.enterInitializationMode()
        self._slave.exitInitializationMode()
        self._closed = False

    def set_inputs(self, values: dict[str, object]) -> None:
        expected = {item.fmu_name for item in COMMAND_INPUTS}
        if set(values) != expected:
            raise ValueError("command frame must contain all 48 reviewed FMI inputs")
        real_refs: list[int] = []
        real_values: list[float] = []
        bool_refs: list[int] = []
        bool_values: list[bool] = []
        for spec in COMMAND_INPUTS:
            value = values[spec.fmu_name]
            reference = self._variables[spec.fmu_name].valueReference
            if spec.kind == "Boolean":
                if not isinstance(value, bool):
                    raise ValueError(f"{spec.fmu_name}: expected Boolean")
                bool_refs.append(reference)
                bool_values.append(value)
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{spec.fmu_name}: expected Real")
                number = float(value)
                if not math.isfinite(number) or not 0.0 <= number <= 1.0:
                    raise ValueError(f"{spec.fmu_name}: command outside 0..1 pu")
                real_refs.append(reference)
                real_values.append(number)
        self._slave.setReal(real_refs, real_values)
        self._slave.setBoolean(bool_refs, bool_values)

    def do_step(self, current_time: float, step_size: float) -> None:
        status = self._slave.doStep(
            currentCommunicationPoint=current_time,
            communicationStepSize=step_size,
        )
        if status not in (None, 0, 1):
            raise RuntimeError(f"FMU doStep failed with FMI status {status}")

    def values(self) -> dict[str, float | bool]:
        result: dict[str, float | bool] = {}
        real_specs = [item for item in LIVE_SIGNALS if item.kind == "Real"]
        bool_specs = [item for item in LIVE_SIGNALS if item.kind == "Boolean"]
        real_values = self._slave.getReal([
            self._variables[item.fmu_name].valueReference for item in real_specs
        ])
        bool_values = self._slave.getBoolean([
            self._variables[item.fmu_name].valueReference for item in bool_specs
        ])
        for spec, value in zip(real_specs, real_values):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"FMU returned non-finite value: {spec.fmu_name}")
            result[spec.field] = number
        for spec, value in zip(bool_specs, bool_values):
            result[spec.field] = bool(value)
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
    parser.add_argument("--stop-time", type=float, default=2.0)
    parser.add_argument("--step-size", type=float, default=0.01)
    parser.add_argument("--tolerance", type=float, default=1e-3)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.fmu.is_file():
        parser.error("--fmu does not exist")
    steps_float = args.stop_time / args.step_size
    if args.stop_time <= 0 or args.step_size <= 0 or not math.isclose(
        steps_float, round(steps_float), abs_tol=1e-9
    ):
        parser.error("stop time must be a positive integer multiple of step size")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    command_log_path = args.output_dir / "gateway-command-rx.jsonl"
    telemetry_log_path = args.output_dir / "gateway-telemetry-tx.jsonl"
    report_path = args.output_dir / "gateway-report.json"
    fmu_digest = sha256(args.fmu)
    model = PhysicalFMU(args.fmu, args.stop_time, args.tolerance)
    metadata = {
        "guid": model.guid,
        "model_identifier": model.model_identifier,
        "generation_tool": model.generation_tool,
    }
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(1)
    server.settimeout(90)
    selected_port = server.getsockname()[1]
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    args.ready_file.write_text(json.dumps({
        "protocol": PROTOCOL,
        "host": args.host,
        "port": selected_port,
        "pid": os.getpid(),
        "fmu_sha256": fmu_digest,
        "contract_sha256": contract_sha256(),
    }, indent=2) + "\n", encoding="utf-8")

    frame_count = 0
    sequence_errors = 0
    peer = ("", 0)
    try:
        connection, peer = server.accept()
        with connection:
            connection.settimeout(90)
            stream = connection.makefile("rwb", buffering=0)
            hello, _raw = read_frame(stream)
            if hello.get("type") != "hello" or hello.get("role") != "ECMS":
                raise ValueError("first frame must be the ECMS hello")
            if hello.get("contract_sha256") != contract_sha256():
                raise ValueError("ECMS/gateway contract hash differs")
            write_frame(stream, {
                "protocol": PROTOCOL,
                "type": "hello_ack",
                "role": "PHYSICAL_FMU_GATEWAY",
                **metadata,
                "fmu_sha256": fmu_digest,
                "contract_sha256": contract_sha256(),
                "step_size_s": args.step_size,
                "stop_time_s": args.stop_time,
                "input_count": len(COMMAND_INPUTS),
                "telemetry_count": len(LIVE_SIGNALS),
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
                        raise ValueError("command timestamp differs from FMU time")
                    values = command.get("values")
                    if not isinstance(values, dict):
                        raise ValueError("command values must be an object")
                    command_log.write(raw_command)
                    model.set_inputs(values)
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
                        "source": "OPENMODELICA_FMI2_CO_SIMULATION",
                        "values": model.values(),
                    }
                    telemetry_log.write(write_frame(stream, payload))
                    frame_count += 1
                shutdown, _raw = read_frame(stream)
                if shutdown.get("type") != "shutdown":
                    raise ValueError("expected shutdown after final step")
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
        "schema_version": "2.0",
        "status": "PASS",
        "transport_mode": "TCP_JSONL_FULL_DUPLEX",
        "protocol": PROTOCOL,
        "contract_sha256": contract_sha256(),
        "bind_host": args.host,
        "bind_port": selected_port,
        "peer_host": peer[0],
        "connection_count": 1,
        "command_frames_received": frame_count,
        "telemetry_frames_sent": frame_count,
        "inputs_per_frame": len(COMMAND_INPUTS),
        "telemetry_values_per_frame": len(LIVE_SIGNALS),
        "sequence_errors": sequence_errors,
        "step_size_s": args.step_size,
        "stop_time_s": args.stop_time,
        "fmu": {"file": args.fmu.name, "sha256": fmu_digest, **metadata},
        "initialization_mode": "STANDARD_SYMBOLIC_DECLARED_STARTS",
        "command_rx_sha256": sha256(command_log_path),
        "telemetry_tx_sha256": sha256(telemetry_log_path),
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "LIVE_FMU_GATEWAY_PASS "
        f"frames={frame_count} inputs={len(COMMAND_INPUTS)} telemetry={len(LIVE_SIGNALS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
