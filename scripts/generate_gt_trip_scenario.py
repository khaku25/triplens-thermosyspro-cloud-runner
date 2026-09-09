#!/usr/bin/env python3
"""Generate a label-free GT Trip RAW observation from the VPP baseline.

The RAW CSV intentionally contains only sampled commands, equipment states and
physical values.  The scenario identity and expected causal sequence are kept
in a separate oracle file so the RAW can be used for blind replay.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FORBIDDEN_RAW_TOKENS = {
    "scenario", "fault", "root_cause", "ground_truth", "answer", "expected"
}

RAW_FIELDS = [
    "time_s",
    "gt_trip_cmd",
    "gt_trip_latch",
    "gt_trip_request",
    "st_trip_request",
    "st_trip_latch",
    "cb_52gt_trip_cmd",
    "cb_52gt_closed",
    "cb_52st_trip_cmd",
    "cb_52st_closed",
    "gtg_power_mw",
    "stg_power_w",
    "gtg_speed_rpm",
    "stg_speed_rpm",
    "quality",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nested_number(document: dict[str, Any], dotted_key: str) -> float:
    value: Any = document
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"baseline is missing required numeric key: {dotted_key}")
        value = value[part]
    if isinstance(value, bool):
        raise ValueError(f"baseline key must be numeric, not boolean: {dotted_key}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"baseline key is not numeric: {dotted_key}") from exc
    if not math.isfinite(number):
        raise ValueError(f"baseline key must be finite: {dotted_key}")
    return number


def milliseconds(seconds: float, name: str) -> int:
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    value = round(seconds * 1000)
    if not math.isclose(value / 1000, seconds, abs_tol=1e-9):
        raise ValueError(f"{name} must resolve to an integer millisecond")
    return value


def positive_milliseconds(value: float, name: str) -> int:
    result = milliseconds(value / 1000.0, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def decay(initial: float, elapsed_ms: int, tau_s: float) -> float:
    if elapsed_ms <= 0:
        return initial
    return initial * math.exp(-(elapsed_ms / 1000.0) / tau_s)


def sampled_at_or_after(event_ms: int, step_ms: int) -> int:
    return ((event_ms + step_ms - 1) // step_ms) * step_ms


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate blind-replayable GT Trip RAW plus a separate oracle."
    )
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--oracle-output", type=Path)
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--pre-seconds", type=float, default=1.0)
    parser.add_argument("--post-seconds", type=float, default=4.0)
    parser.add_argument("--step-ms", type=int, default=1)
    parser.add_argument("--case-id", default="GT_TRIP_01")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.baseline.is_file():
        raise ValueError("--baseline must point to an existing VPP baseline JSON")
    if args.step_ms <= 0:
        raise ValueError("--step-ms must be positive")
    pre_ms = milliseconds(args.pre_seconds, "--pre-seconds")
    post_ms = milliseconds(args.post_seconds, "--post-seconds")
    if pre_ms <= 0 or post_ms <= 0:
        raise ValueError("--pre-seconds and --post-seconds must both be positive")
    total_ms = pre_ms + post_ms
    if total_ms % args.step_ms:
        raise ValueError("total duration must be divisible by --step-ms")

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    if not isinstance(baseline, dict):
        raise ValueError("baseline root must be a JSON object")
    required = {
        "gt_power_mw": nested_number(baseline, "ratings.gt_power_mw"),
        "st_power_mw": nested_number(baseline, "ratings.st_power_mw"),
        "gt_speed_rpm": nested_number(baseline, "ratings.gt_speed_rpm"),
        "st_speed_rpm": nested_number(baseline, "ratings.st_speed_rpm"),
        "trip_receive_delay_ms": nested_number(baseline, "timing.trip_receive_delay_ms"),
        "lockout_operate_delay_ms": nested_number(baseline, "timing.lockout_operate_delay_ms"),
        "gt_breaker_open_delay_ms": nested_number(baseline, "timing.gt_breaker_open_delay_ms"),
        "st_breaker_open_delay_ms": nested_number(baseline, "timing.st_breaker_open_delay_ms"),
        "gt_power_decay_s": nested_number(baseline, "dynamics.gt_power_decay_s"),
        "st_power_decay_s": nested_number(baseline, "dynamics.st_power_decay_s"),
        "gt_coastdown_tau_s": nested_number(baseline, "dynamics.gt_coastdown_tau_s"),
        "st_coastdown_tau_s": nested_number(baseline, "dynamics.st_coastdown_tau_s"),
    }
    for key in ("gt_power_mw", "st_power_mw", "gt_speed_rpm", "st_speed_rpm"):
        if required[key] <= 0:
            raise ValueError(f"baseline {key} must be positive")
    for key in (
        "gt_power_decay_s", "st_power_decay_s",
        "gt_coastdown_tau_s", "st_coastdown_tau_s",
    ):
        if required[key] <= 0:
            raise ValueError(f"baseline {key} must be positive")

    receive_ms = positive_milliseconds(required["trip_receive_delay_ms"], "trip_receive_delay_ms")
    lockout_delay_ms = positive_milliseconds(required["lockout_operate_delay_ms"], "lockout_operate_delay_ms")
    gt_open_delay_ms = positive_milliseconds(required["gt_breaker_open_delay_ms"], "gt_breaker_open_delay_ms")
    st_open_delay_ms = positive_milliseconds(required["st_breaker_open_delay_ms"], "st_breaker_open_delay_ms")

    trip_ms = pre_ms
    gt_lockout_ms = trip_ms + receive_ms + lockout_delay_ms
    gt_open_ms = trip_ms + gt_open_delay_ms
    st_command_ms = trip_ms
    st_open_ms = trip_ms + st_open_delay_ms
    if gt_open_ms < gt_lockout_ms:
        raise ValueError(
            "baseline violates causality: 52GT opens before its lockout Trip command"
        )
    if max(gt_open_ms, st_open_ms) > total_ms:
        raise ValueError("post-trip window ends before breaker opening completes")

    forbidden_headers = [
        field for field in RAW_FIELDS
        if any(token in field.lower() for token in FORBIDDEN_RAW_TOKENS)
    ]
    if forbidden_headers:
        raise AssertionError("RAW contract leaked answer metadata: " + ", ".join(forbidden_headers))

    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", delete=False,
            dir=args.raw_output.parent, prefix=args.raw_output.name + ".", suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=RAW_FIELDS)
            writer.writeheader()
            for time_ms in range(0, total_ms + 1, args.step_ms):
                gt_requested = time_ms >= trip_ms
                st_requested = time_ms >= trip_ms
                gt_closed = time_ms < gt_open_ms
                st_closed = time_ms < st_open_ms

                gt_internal_mw = (
                    required["gt_power_mw"] if not gt_requested else decay(
                        required["gt_power_mw"], time_ms - trip_ms,
                        required["gt_power_decay_s"],
                    )
                )
                st_internal_mw = (
                    required["st_power_mw"] if not st_requested else decay(
                        required["st_power_mw"], time_ms - trip_ms,
                        required["st_power_decay_s"],
                    )
                )
                gt_speed = (
                    required["gt_speed_rpm"] if gt_closed else decay(
                        required["gt_speed_rpm"], time_ms - gt_open_ms,
                        required["gt_coastdown_tau_s"],
                    )
                )
                st_speed = (
                    required["st_speed_rpm"] if st_closed else decay(
                        required["st_speed_rpm"], time_ms - st_open_ms,
                        required["st_coastdown_tau_s"],
                    )
                )
                writer.writerow({
                    "time_s": f"{time_ms / 1000.0:.3f}",
                    "gt_trip_cmd": int(gt_requested),
                    "gt_trip_latch": int(gt_requested),
                    "gt_trip_request": int(gt_requested),
                    "st_trip_request": int(st_requested),
                    "st_trip_latch": int(st_requested),
                    "cb_52gt_trip_cmd": int(time_ms >= gt_lockout_ms),
                    "cb_52gt_closed": int(gt_closed),
                    "cb_52st_trip_cmd": int(time_ms >= st_command_ms),
                    "cb_52st_closed": int(st_closed),
                    "gtg_power_mw": f"{gt_internal_mw if gt_closed else 0.0:.6f}",
                    "stg_power_w": f"{(st_internal_mw if st_closed else 0.0) * 1_000_000:.3f}",
                    "gtg_speed_rpm": f"{gt_speed:.6f}",
                    "stg_speed_rpm": f"{st_speed:.6f}",
                    "quality": "GOOD",
                })
        os.replace(temporary, args.raw_output)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

    oracle_output = args.oracle_output or args.raw_output.with_name(
        args.raw_output.stem + ".expected.json"
    )
    events = {
        "CMD.GTG.TRIP": trip_ms,
        "CTRL.GTG.TRIP_LATCH": trip_ms,
        "ECMS.GT.TRIP_REQUEST": trip_ms,
        "ECMS.ST.TRIP_REQUEST": trip_ms,
        "CTRL.STG.TRIP_LATCH": trip_ms,
        "ECMS.52ST.TRIP_CMD": st_command_ms,
        "ECMS.52GT.TRIP_CMD": gt_lockout_ms,
        "ECMS.52GT.CLOSED_1_TO_0": gt_open_ms,
        "ECMS.52ST.CLOSED_1_TO_0": st_open_ms,
    }
    oracle = {
        "schema_version": "1.0",
        "case_id": args.case_id,
        "classification": "GT_TRIP",
        "raw_file": args.raw_output.name,
        "raw_sha256": sha256(args.raw_output),
        "baseline_file": args.baseline.name,
        "baseline_sha256": sha256(args.baseline),
        "exact_event_times_ms": events,
        "first_observable_sample_ms": {
            tag: sampled_at_or_after(event_ms, args.step_ms)
            for tag, event_ms in events.items()
        },
        "causal_invariants": [
            "CMD.GTG.TRIP <= CTRL.GTG.TRIP_LATCH",
            "CTRL.GTG.TRIP_LATCH <= ECMS.52GT.TRIP_CMD",
            "ECMS.52GT.TRIP_CMD <= ECMS.52GT.CLOSED_1_TO_0",
            "CMD.GTG.TRIP <= ECMS.ST.TRIP_REQUEST",
            "ECMS.ST.TRIP_REQUEST <= ECMS.52ST.TRIP_CMD",
            "ECMS.52ST.TRIP_CMD <= ECMS.52ST.CLOSED_1_TO_0",
            "GT/ST power reduction is a consequence, never a Trip source",
        ],
        "raw_contains_answer_label": False,
    }
    oracle_output.parent.mkdir(parents=True, exist_ok=True)
    oracle_output.write_text(
        json.dumps(oracle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest_output = args.manifest_output or args.raw_output.with_name(
        args.raw_output.stem + ".manifest.json"
    )
    manifest = {
        "schema_version": "1.0",
        "artifact_type": "VPP_RAW_OBSERVATION",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw": {
            "file": args.raw_output.name,
            "sha256": sha256(args.raw_output),
            "row_count": total_ms // args.step_ms + 1,
            "columns": RAW_FIELDS,
            "columns_added_after_generation": False,
        },
        "sampling": {
            "period_ms": args.step_ms,
            "start_time_s": 0.0,
            "stop_time_s": total_ms / 1000.0,
            "reference_event_time_s": trip_ms / 1000.0,
        },
        "baseline": {
            "file": args.baseline.name,
            "sha256": sha256(args.baseline),
        },
        "boundary": {
            "raw_contains_scenario_label": False,
            "raw_contains_root_cause_label": False,
            "oracle_is_separate": True,
            "alarm_derivation_allowed_downstream": True,
        },
    }
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
