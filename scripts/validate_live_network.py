#!/usr/bin/env python3
"""Fail closed unless real commands and solved values crossed the TCP boundary."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from live_protocol import COMMAND_INPUTS, LIVE_SIGNALS, PROTOCOL, contract_sha256


EXPECTED_MAIN_FMU_SHA256 = "883ca79109cc5277a01868068e916ebb1ad7df346b841820ff7b5ea66c76f387"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(row: dict[str, str], field: str) -> float:
    value = float(row[field])
    if not math.isfinite(value):
        raise ValueError(f"{field}: non-finite physical value")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-fmu-sha256", default=EXPECTED_MAIN_FMU_SHA256)
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
        if report.get("contract_sha256") != contract_sha256():
            errors.append("wire contract hash mismatch")
        if report.get("transport_mode") != "TCP_JSONL_FULL_DUPLEX":
            errors.append("transport is not full-duplex TCP")
        if report.get("connection_count") != 1:
            errors.append("exactly one TCP session is required")
    fmu_digest = gateway.get("fmu", {}).get("sha256")
    if fmu_digest != args.expected_fmu_sha256 or client.get("fmu_sha256") != fmu_digest:
        errors.append("runtime FMU SHA-256 is not the pinned main-grade artifact")

    command_mismatch = command_tx.read_bytes() != command_rx.read_bytes()
    telemetry_mismatch = telemetry_tx.read_bytes() != telemetry_rx.read_bytes()
    if command_mismatch:
        errors.append("ECMS command bytes changed across TCP")
    if telemetry_mismatch:
        errors.append("FMU telemetry bytes changed across TCP")
    if client.get("command_tx_sha256") != gateway.get("command_rx_sha256"):
        errors.append("command stream hashes differ")
    if client.get("telemetry_rx_sha256") != gateway.get("telemetry_tx_sha256"):
        errors.append("telemetry stream hashes differ")

    frames = int(client.get("telemetry_frames_received", 0))
    if frames < 100 or frames != int(gateway.get("telemetry_frames_sent", -1)):
        errors.append("telemetry frame counts differ or are too small")
    if int(gateway.get("inputs_per_frame", -1)) != len(COMMAND_INPUTS):
        errors.append("gateway did not accept all 48 inputs per frame")
    if int(gateway.get("telemetry_values_per_frame", -1)) != len(LIVE_SIGNALS):
        errors.append("gateway did not publish the complete telemetry set")

    with csv_path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != frames:
        errors.append("post-receive CSV does not contain every received frame")
    required_columns = {
        *(item.fmu_name for item in COMMAND_INPUTS),
        *(item.field for item in LIVE_SIGNALS),
    }
    if rows and any(not (row.get(field) or "").strip() for row in rows for field in required_columns):
        errors.append("post-receive CSV contains an empty command or physical value")
    times = [number(row, "time_s") for row in rows]
    if any(right <= left for left, right in zip(times, times[1:])):
        errors.append("FMU source timestamps are not strictly increasing")

    pre = [row for row in rows if 0.10 <= number(row, "time_s") <= 0.20]
    hp_post = [row for row in rows if 0.50 <= number(row, "time_s") <= 0.70]
    ip_post = [row for row in rows if number(row, "time_s") >= 1.75]
    changed_physical = 0
    summary: dict[str, float | int | str] = {}
    if not pre or not hp_post or not ip_post:
        errors.append("capture lacks required pre/post physical windows")
    else:
        pre_row, hp_row, ip_row = pre[-1], hp_post[-1], ip_post[-1]
        if number(pre_row, "fmuVlvHPSteamModeAuto") != 1:
            errors.append("HP steam valve was not AUTO before the TCP command")
        if number(hp_row, "fmuVlvHPSteamModeAuto") != 0 or not math.isclose(
            number(hp_row, "fmuVlvHPSteamManualCmd"), 0.45, abs_tol=1e-12
        ):
            errors.append("HP steam MAN command did not cross the ECMS transmit boundary")
        if not math.isclose(number(hp_row, "hpsteam_cmd"), 0.45, abs_tol=1e-6):
            errors.append("HP steam MAN command did not reach the FMI selected command")
        if not math.isclose(number(hp_row, "hpsteam_fb"), 0.45, abs_tol=1e-6):
            errors.append("HP steam command did not reach the native applied valve position")
        hp_cv_ratio = number(hp_row, "hpsteam_cv") / number(pre_row, "hpsteam_cv")
        if not math.isclose(hp_cv_ratio, 0.45 / 0.5, rel_tol=3e-3):
            errors.append("native HP steam-valve Cv did not follow the live command")

        if number(ip_row, "fmuVlvIPTurbAdmFaultEnable") != 1 or not math.isclose(
            number(ip_row, "fmuVlvIPTurbAdmFaultValue"), 0.60, abs_tol=1e-12
        ):
            errors.append("IP turbine fault command did not cross the ECMS transmit boundary")
        if not math.isclose(number(ip_row, "ipturb_adm_cmd"), 0.8, abs_tol=1e-6):
            errors.append("fault incorrectly rewrote the selected IP turbine command")
        if not math.isclose(number(ip_row, "ipturb_adm_fb"), 0.60, abs_tol=2e-2):
            errors.append("IP turbine physical actuator did not move to fault value")
        if number(ip_row, "ipturb_adm_deviation") <= 0.15:
            errors.append("IP turbine command-feedback deviation was not solved")
        if number(ip_row, "ipturb_adm_fault_active") != 1:
            errors.append("IP turbine fault state was not returned over TCP")
        ip_cv_ratio = number(ip_row, "ipturb_adm_cv") / number(pre_row, "ipturb_adm_cv")
        if ip_cv_ratio >= 0.85:
            errors.append("native IP turbine valve Cv did not follow physical feedback")

        physical_fields = [
            item.field for item in LIVE_SIGNALS
            if item.kind == "Real" and item.field not in {
                "hpsteam_auto_cmd", "hpsteam_cmd", "hpsteam_fb", "hpsteam_deviation",
                "ipturb_adm_auto_cmd", "ipturb_adm_cmd", "ipturb_adm_fb",
                "ipturb_adm_deviation",
            }
        ]
        for field in physical_fields:
            if not math.isclose(
                number(pre_row, field), number(ip_row, field), rel_tol=1e-12, abs_tol=1e-12
            ):
                changed_physical += 1
        if changed_physical < 12:
            errors.append("too few solved physical values changed after live commands")
        for field in (
            "hp_drum_level", "ip_drum_level", "lp_drum_level",
            "hp_drum_pressure", "ip_drum_pressure", "lp_drum_pressure",
            "hp_drum_temperature", "ip_drum_temperature", "lp_drum_temperature",
        ):
            number(ip_row, field)
        summary = {
            "hp_steam_cv_pre": number(pre_row, "hpsteam_cv"),
            "hp_steam_cv_post": number(hp_row, "hpsteam_cv"),
            "hp_steam_cv_ratio": hp_cv_ratio,
            "ip_turbine_fb_pre": number(pre_row, "ipturb_adm_fb"),
            "ip_turbine_fb_post": number(ip_row, "ipturb_adm_fb"),
            "ip_turbine_cv_pre": number(pre_row, "ipturb_adm_cv"),
            "ip_turbine_cv_post": number(ip_row, "ipturb_adm_cv"),
            "changed_physical_fields": changed_physical,
        }

    status = "PASS" if not errors else "FAIL"
    report = {
        "schema_version": "2.0",
        "status": status,
        "proof_type": "LIVE_CLOSED_LOOP_PHYSICAL_COMMUNICATION",
        "transport_mode": "TCP_JSONL_FULL_DUPLEX",
        "command_path": "ECMS_PROCESS_TCP_TO_RUNNING_FMU_INPUTS",
        "feedback_path": "FMU_SOLVED_PHYSICS_TCP_TO_SEPARATE_ECMS_PROCESS",
        "csv_role": "POST_RECEIVE_AUDIT_ONLY_NOT_SIMULATOR_INPUT",
        "fmu_sha256": fmu_digest,
        "frames_compared": frames,
        "inputs_per_frame": len(COMMAND_INPUTS),
        "telemetry_values_per_frame": len(LIVE_SIGNALS),
        "commands_transferred": frames * len(COMMAND_INPUTS),
        "values_received": frames * len(LIVE_SIGNALS),
        "command_stream_byte_mismatch_count": int(command_mismatch),
        "telemetry_stream_byte_mismatch_count": int(telemetry_mismatch),
        "sequence_gaps": client.get("sequence_gaps"),
        "malformed_frames": client.get("malformed_frames"),
        "latency_scope": client.get("latency_scope"),
        "round_trip_latency_ms": client.get("round_trip_latency_ms"),
        "physical_response": summary,
        "ecms_csv_sha256": sha256(csv_path),
        "errors": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit("LIVE_NETWORK_FAIL: " + "; ".join(errors[:10]))
    print(
        "LIVE_CLOSED_LOOP_PHYSICS_PASS "
        f"frames={frames} commands={report['commands_transferred']} "
        f"values={report['values_received']} changed_physical={changed_physical} "
        "command_bytes=IDENTICAL telemetry_bytes=IDENTICAL"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
