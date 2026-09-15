#!/usr/bin/env python3
"""Create compact human/Luna summaries and a checksum manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any


EXPECTED_SCENARIOS = [
    "direct_gt", "gt_breaker", "direct_st",
    "hp_drum_hh", "ip_drum_hh", "lp_drum_hh",
    "hp_drum_ll", "ip_drum_ll", "lp_drum_ll",
    "hp_bfp", "ip_bfp", "lp_bfp",
]


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def compact_mapping(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return ";".join(f"{key}={value[key]}" for key in sorted(value))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pre-fault-model-seconds", type=float, default=5.0)
    parser.add_argument("--post-fault-model-seconds", type=float, default=100.0)
    parser.add_argument("--require-all-pass", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for scenario in EXPECTED_SCENARIOS:
        folder = root / scenario
        result = read_json(folder / "SCENARIO_RESULT.json")
        execution = read_json(folder / "EXECUTION_RESULT.json") or {}
        if result is None:
            status = "INFRA_FAIL" if execution.get("failure_stage") else "MISSING"
            item: dict[str, Any] = {
                "scenario": scenario, "status": status, "expected_domain": "",
                "trigger_model_time_s": "", "final_model_time_s": "",
                "pre_fault_coverage_s": "", "post_fault_coverage_s": "",
                "required_post_fault_seconds": args.post_fault_model_seconds,
                "event_rows": 0, "raw_rows": 0, "raw_columns": 0,
                "cause": "", "cause_status": "NOT_EVALUATED",
                "command_leakage_count": "", "required_event_count": "",
                "missing_event_count": "",
                "problems": execution.get("message", "SCENARIO_RESULT.json missing"),
            }
        else:
            item = result
            status = str(item.get("status", "FAIL"))
            if execution.get("failure_stage"):
                status = "INFRA_FAIL"
        rows.append({
            "scenario": scenario,
            "status": status,
            "failure_stage": execution.get("failure_stage", ""),
            "expected_domain": item.get("expected_domain", ""),
            "trigger_model_time_s": item.get("trigger_model_time_s", ""),
            "final_model_time_s": item.get("final_model_time_s", ""),
            "pre_fault_coverage_s": item.get("pre_fault_coverage_s", ""),
            "post_fault_coverage_s": item.get("post_fault_coverage_s", ""),
            "required_post_fault_seconds": item.get(
                "required_post_fault_seconds", args.post_fault_model_seconds
            ),
            "event_rows": item.get("event_rows", 0),
            "raw_rows": item.get("raw_rows", 0),
            "raw_columns": item.get("raw_columns", 0),
            "cause": item.get("cause", ""),
            "cause_status": item.get("cause_status", ""),
            "asserted_matrix_causes": ";".join(item.get("asserted_matrix_causes", [])),
            "command_leakage_count": item.get("command_leakage_count", ""),
            "required_event_count": item.get("required_event_count", ""),
            "missing_event_count": item.get("missing_event_count", ""),
            "matrix_actual": compact_mapping(item.get("matrix_actual")),
            "event_file": f"{scenario}/EVENT.csv",
            "raw_file": f"{scenario}/RAW.csv",
            "result_file": f"{scenario}/SCENARIO_RESULT.json",
            "runner_log": f"{scenario}/scenario-runner.log",
            "problems": " | ".join(str(value) for value in item.get("problems", []))
            if isinstance(item.get("problems"), list) else str(item.get("problems", "")),
        })

    fields = list(rows[0])
    csv_path = root / "LUNA_SUMMARY.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    failed = [row["scenario"] for row in rows if row["status"] != "PASS"]
    payload = {
        "status": "PASS" if not failed else "FAIL",
        "artifact_contract_version": "V8_ALL_TRIP_MIXED_HORIZON_V1",
        "provenance": {
            "repository": os.environ.get("GITHUB_REPOSITORY", ""),
            "git_sha": os.environ.get("GITHUB_SHA", ""),
            "run_id": os.environ.get("GITHUB_RUN_ID", ""),
            "run_number": os.environ.get("GITHUB_RUN_NUMBER", ""),
        },
        "contract": {
            "scenario_count": len(EXPECTED_SCENARIOS),
            "pre_fault_model_seconds": args.pre_fault_model_seconds,
            "post_fault_model_seconds": args.post_fault_model_seconds,
            "scenario_post_fault_seconds": {
                row["scenario"]: row["required_post_fault_seconds"]
                for row in rows
            },
            "fresh_opcua_server_per_scenario": True,
            "continue_after_failure": True,
            "ai_inputs_per_scenario": ["EVENT.csv", "RAW.csv"],
            "test_audit_is_not_ai_input": True,
        },
        "counts": {
            "pass": sum(row["status"] == "PASS" for row in rows),
            "fail": sum(row["status"] == "FAIL" for row in rows),
            "infra_fail": sum(row["status"] == "INFRA_FAIL" for row in rows),
            "missing": sum(row["status"] == "MISSING" for row in rows),
        },
        "passed": [row["scenario"] for row in rows if row["status"] == "PASS"],
        "failed_or_missing": failed,
        "results": rows,
    }
    json_path = root / "LUNA_SUMMARY.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (root / "LUNA_README.md").write_text(
        "# Luna analysis order\n\n"
        "HP/IP BFP equipment proofs use a 45 s post-fault horizon; LP BFP and\n"
        "all drum/matrix proofs retain the 100 s horizon.\n\n"
        "1. Read `LUNA_SUMMARY.json` first.\n"
        "2. Open `SCENARIO_RESULT.json` only for a failed or selected scenario.\n"
        "3. Analyze only that scenario's `EVENT.csv` and `RAW.csv`.\n"
        "4. `TEST_AUDIT.json` and logs are orchestration evidence, not AI inputs.\n",
        encoding="utf-8",
    )

    manifest_path = root / "MANIFEST_SHA256.csv"
    candidates = [
        path for path in root.rglob("*")
        if path.is_file() and path != manifest_path and "engine/runtime" not in path.as_posix()
    ]
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["relative_path", "bytes", "sha256"])
        writer.writeheader()
        for path in sorted(candidates):
            writer.writerow({
                "relative_path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 1 if args.require_all_pass and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Create compact human/Luna summaries and a checksum manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any


EXPECTED_SCENARIOS = [
    "direct_gt", "gt_breaker", "direct_st",
    "hp_drum_hh", "ip_drum_hh", "lp_drum_hh",
    "hp_drum_ll", "ip_drum_ll", "lp_drum_ll",
    "hp_bfp", "ip_bfp", "lp_bfp",
]


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def compact_mapping(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return ";".join(f"{key}={value[key]}" for key in sorted(value))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pre-fault-model-seconds", type=float, default=5.0)
    parser.add_argument("--post-fault-model-seconds", type=float, default=100.0)
    parser.add_argument("--require-all-pass", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for scenario in EXPECTED_SCENARIOS:
        folder = root / scenario
        result = read_json(folder / "SCENARIO_RESULT.json")
        execution = read_json(folder / "EXECUTION_RESULT.json") or {}
        if result is None:
            status = "INFRA_FAIL" if execution.get("failure_stage") else "MISSING"
            item: dict[str, Any] = {
                "scenario": scenario, "status": status, "expected_domain": "",
                "trigger_model_time_s": "", "final_model_time_s": "",
                "pre_fault_coverage_s": "", "post_fault_coverage_s": "",
                "event_rows": 0, "raw_rows": 0, "raw_columns": 0,
                "cause": "", "cause_status": "NOT_EVALUATED",
                "command_leakage_count": "", "required_event_count": "",
                "missing_event_count": "",
                "problems": execution.get("message", "SCENARIO_RESULT.json missing"),
            }
        else:
            item = result
            status = str(item.get("status", "FAIL"))
            if execution.get("failure_stage"):
                status = "INFRA_FAIL"
        rows.append({
            "scenario": scenario,
            "status": status,
            "failure_stage": execution.get("failure_stage", ""),
            "expected_domain": item.get("expected_domain", ""),
            "trigger_model_time_s": item.get("trigger_model_time_s", ""),
            "final_model_time_s": item.get("final_model_time_s", ""),
            "pre_fault_coverage_s": item.get("pre_fault_coverage_s", ""),
            "post_fault_coverage_s": item.get("post_fault_coverage_s", ""),
            "event_rows": item.get("event_rows", 0),
            "raw_rows": item.get("raw_rows", 0),
            "raw_columns": item.get("raw_columns", 0),
            "cause": item.get("cause", ""),
            "cause_status": item.get("cause_status", ""),
            "asserted_matrix_causes": ";".join(item.get("asserted_matrix_causes", [])),
            "command_leakage_count": item.get("command_leakage_count", ""),
            "required_event_count": item.get("required_event_count", ""),
            "missing_event_count": item.get("missing_event_count", ""),
            "matrix_actual": compact_mapping(item.get("matrix_actual")),
            "event_file": f"{scenario}/EVENT.csv",
            "raw_file": f"{scenario}/RAW.csv",
            "result_file": f"{scenario}/SCENARIO_RESULT.json",
            "runner_log": f"{scenario}/scenario-runner.log",
            "problems": " | ".join(str(value) for value in item.get("problems", []))
            if isinstance(item.get("problems"), list) else str(item.get("problems", "")),
        })

    fields = list(rows[0])
    csv_path = root / "LUNA_SUMMARY.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    failed = [row["scenario"] for row in rows if row["status"] != "PASS"]
    payload = {
        "status": "PASS" if not failed else "FAIL",
        "artifact_contract_version": "V8_ALL_TRIP_100S_V1",
        "provenance": {
            "repository": os.environ.get("GITHUB_REPOSITORY", ""),
            "git_sha": os.environ.get("GITHUB_SHA", ""),
            "run_id": os.environ.get("GITHUB_RUN_ID", ""),
            "run_number": os.environ.get("GITHUB_RUN_NUMBER", ""),
        },
        "contract": {
            "scenario_count": len(EXPECTED_SCENARIOS),
            "pre_fault_model_seconds": args.pre_fault_model_seconds,
            "post_fault_model_seconds": args.post_fault_model_seconds,
            "fresh_opcua_server_per_scenario": True,
            "continue_after_failure": True,
            "ai_inputs_per_scenario": ["EVENT.csv", "RAW.csv"],
            "test_audit_is_not_ai_input": True,
        },
        "counts": {
            "pass": sum(row["status"] == "PASS" for row in rows),
            "fail": sum(row["status"] == "FAIL" for row in rows),
            "infra_fail": sum(row["status"] == "INFRA_FAIL" for row in rows),
            "missing": sum(row["status"] == "MISSING" for row in rows),
        },
        "passed": [row["scenario"] for row in rows if row["status"] == "PASS"],
        "failed_or_missing": failed,
        "results": rows,
    }
    json_path = root / "LUNA_SUMMARY.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (root / "LUNA_README.md").write_text(
        "# Luna analysis order\n\n"
        "1. Read `LUNA_SUMMARY.json` first.\n"
        "2. Open `SCENARIO_RESULT.json` only for a failed or selected scenario.\n"
        "3. Analyze only that scenario's `EVENT.csv` and `RAW.csv`.\n"
        "4. `TEST_AUDIT.json` and logs are orchestration evidence, not AI inputs.\n",
        encoding="utf-8",
    )

    manifest_path = root / "MANIFEST_SHA256.csv"
    candidates = [
        path for path in root.rglob("*")
        if path.is_file() and path != manifest_path and "engine/runtime" not in path.as_posix()
    ]
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["relative_path", "bytes", "sha256"])
        writer.writeheader()
        for path in sorted(candidates):
            writer.writerow({
                "relative_path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 1 if args.require_all_pass and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
