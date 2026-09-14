#!/usr/bin/env python3
"""End-to-end proof: operator PB, split files, and combined analysis."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ALLOWED_EVENTS = {"ALARM", "OPERATOR_ACTION", "PROTECTION", "ACK", "SYSTEM"}
COMMAND_EVENT_TAGS = {
    "TRIP_CMD", "VCB_TRIP_CMD", "BREAKER_COMMAND", "OPEN_CMD", "CLOSE_CMD",
    "LP_BFP_TRIP_CMD", "LP_BFP_TRIP_LATCH", "VCB_A02_TRIP_CMD",
    "VCB_A02_OPEN_CMD", "VCB_A02_CLOSE_CMD",
}
CHAIN = (
    ("vppLPFWPTripCommandNative", "rise"),
    ("vppLPFWPTripLatchNative", "rise"),
    ("vppVCBA02TripCommandNative", "rise"),
    ("vppECMSVCBA02Closed", "fall"),
)
REQUIRED_PHYSICAL_EVENT_TAGS = {
    "LP_BFP_TRIP_PB", "BREAKER_OPEN", "MOTOR_DEENERGIZED", "RUNNING_LOST",
    "SPEED_PROVEN_LOST", "FLOW_LOW", "CHECK_VALVE_CLOSED",
}


def atomic_control(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, path)


def load_json(path: Path) -> dict[str, object] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def has_edge(rows: list[dict[str, str]], field: str, direction: str) -> bool:
    previous = None
    for row in rows:
        try:
            current = float(row[field])
        except (KeyError, TypeError, ValueError):
            continue
        if previous is not None:
            if direction == "rise" and previous < 0.5 <= current:
                return True
            if direction == "fall" and previous >= 0.5 > current:
                return True
        previous = current
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--proof-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    proof = args.proof_root.resolve()
    proof.mkdir(parents=True, exist_ok=True)
    snapshot = proof / "snapshot.json"
    control = proof / "control.json"
    stdout = proof / "engine.stdout.log"
    stderr = proof / "engine.stderr.log"
    engine = repo / "scripts" / "ecms_bfp_alarm_engine.py"
    command = [
        sys.executable, str(engine), "--repo-root", str(repo),
        "--endpoint", args.endpoint, "--snapshot-file", str(snapshot),
        "--control-file", str(control), "--output-root", str(proof / "runtime"),
        "--period", "0.25", "--raw-period", "1.0",
    ]
    with stdout.open("w", encoding="utf-8") as out_stream, stderr.open("w", encoding="utf-8") as err_stream:
        process = subprocess.Popen(command, stdout=out_stream, stderr=err_stream)
        try:
            deadline = time.monotonic() + args.timeout
            ready = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Dual Log engine exited early with code {process.returncode}")
                ready = load_json(snapshot)
                if ready and ready.get("status") == "PASS" and int(ready.get("raw_count_session", 0)) >= 2:
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("Dual Log engine did not become ready")

            atomic_control(control, {"action": "TRIP_NOW"})
            passed = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Dual Log engine exited during proof with code {process.returncode}")
                current = load_json(snapshot)
                if current and current.get("status") == "PASS":
                    analysis = current.get("analysis") or {}
                    session_tags = {
                        str(row.get("tag", ""))
                        for row in current.get("session_events", [])
                        if isinstance(row, dict)
                    }
                    if (
                        isinstance(analysis, dict)
                        and analysis.get("status") == "PASS"
                        and str(current.get("command_state", "")).endswith("_PASS")
                        and REQUIRED_PHYSICAL_EVENT_TAGS.issubset(session_tags)
                    ):
                        passed = current
                        break
                time.sleep(0.25)
            if passed is None:
                raise RuntimeError("LP BFP Dual Log proof did not reach PASS")

            event_path = Path(str(passed["event_csv"]))
            raw_path = Path(str(passed["raw_csv"]))
            analysis_path = Path(str(passed["analysis_json"]))
            if not event_path.is_file() or not raw_path.is_file() or not analysis_path.is_file():
                raise RuntimeError("EVENT.csv, RAW.csv, or DUAL_ANALYSIS.json was not created")
            event_fields, event_rows = read_csv(event_path)
            raw_fields, raw_rows = read_csv(raw_path)
            forbidden = {"scenario_id", "root_cause", "fault_injection", "fault_preset"}
            if forbidden.intersection(event_fields) or forbidden.intersection(raw_fields):
                raise RuntimeError("answer/fault metadata leaked into AI input")
            if not any(row.get("tag") == "LP_BFP_TRIP_PB" for row in event_rows):
                raise RuntimeError("operator Trip PB is missing from EVENT.csv")
            missing_physical_events = REQUIRED_PHYSICAL_EVENT_TAGS.difference(
                row.get("tag", "") for row in event_rows
            )
            if missing_physical_events:
                raise RuntimeError(
                    "physical EVENT chain is incomplete: "
                    + ",".join(sorted(missing_physical_events))
                )
            if any(row.get("event_class") not in ALLOWED_EVENTS for row in event_rows):
                raise RuntimeError("non-display record leaked into EVENT.csv")
            leaked_commands = [
                row for row in event_rows if row.get("tag") in COMMAND_EVENT_TAGS
            ]
            if leaked_commands:
                details = ",".join(
                    f"{row.get('event_class', '')}:{row.get('tag', '')}"
                    for row in leaked_commands
                )
                raise RuntimeError(
                    "general command record leaked into EVENT.csv: " + details
                )
            derived_contract = {
                "LP_BFP_TRIP_PB", "LP_BFP_TRIP_CMD", "LP_BFP_TRIP_LATCH",
                "VCB_A02_TRIP_CMD", "VCB_A02_OPEN_CMD", "VCB_A02_CLOSE_CMD",
                "VCB_A02_CLOSED", "LP_BFP_SPEED_RPM", "LP_FW_FLOW_TH",
            }
            if not derived_contract.issubset(raw_fields):
                raise RuntimeError(
                    "RAW derived Historian contract missing: "
                    + ",".join(sorted(derived_contract.difference(raw_fields)))
                )
            for field, direction in CHAIN:
                if field not in raw_fields or not has_edge(raw_rows, field, direction):
                    raise RuntimeError(f"RAW chain edge missing: {field} {direction}")
            result = load_json(analysis_path) or {}
            if not result.get("event_input_read") or not result.get("raw_input_read"):
                raise RuntimeError("TripLens did not read both EVENT and RAW")
            print(json.dumps({
                "status": "PASS", "event_csv": str(event_path), "raw_csv": str(raw_path),
                "event_rows": len(event_rows), "raw_rows": len(raw_rows),
                "historian_tags": int(passed.get("historian_tag_count", 0)),
                "operator_pb_in_event": True, "general_commands_in_event": 0,
                "physical_event_chain_verified": True,
                "raw_chain_verified": True, "dual_input_analysis": True,
            }, ensure_ascii=False, sort_keys=True))
        finally:
            if process.poll() is None:
                try:
                    atomic_control(control, {"action": "STOP"})
                    process.wait(timeout=5)
                except Exception:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
