#!/usr/bin/env python3
"""Prove that ECMS physical-input values are exact ProcessBus copies."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


META_FIELDS = {
    "source_time_ms", "time_s", "quality", "transport_status", "value_policy"
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--processbus", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    p_fields, process_rows = read(args.processbus)
    h_fields, handoff_rows = read(args.handoff)
    signals = [field for field in h_fields if field not in META_FIELDS]
    errors: list[str] = []

    expected_hashes = (
        (args.raw, manifest.get("raw", {}).get("sha256"), "RAW"),
        (args.processbus, manifest.get("processbus", {}).get("sha256"), "ProcessBus"),
        (args.handoff, manifest.get("handoff", {}).get("sha256"), "handoff"),
    )
    for path, expected, label in expected_hashes:
        actual = sha256(path)
        if actual != expected:
            errors.append(f"{label} hash mismatch: {actual} != {expected}")
    if len(process_rows) != len(handoff_rows):
        errors.append(
            f"row count mismatch: ProcessBus={len(process_rows)} handoff={len(handoff_rows)}"
        )

    compared = 0
    mismatch_count = 0
    max_source_time_offset_ms = 0
    for index, (source, received) in enumerate(
        zip(process_rows, handoff_rows), start=2
    ):
        if received.get("time_s") != source.get("time_s"):
            errors.append(f"row {index}: time_s changed")
        expected_ms = round(float(source["time_s"]) * 1000)
        actual_ms = int(received["source_time_ms"])
        max_source_time_offset_ms = max(
            max_source_time_offset_ms, abs(actual_ms - expected_ms)
        )
        if received.get("transport_status") != "RECEIVED":
            errors.append(f"row {index}: transport_status is not RECEIVED")
        if received.get("value_policy") != "EXACT_PROCESSBUS_COPY":
            errors.append(f"row {index}: non-passthrough value policy")
        for signal in signals:
            compared += 1
            if received.get(signal, "") != source.get(signal, ""):
                mismatch_count += 1
                if mismatch_count <= 20:
                    errors.append(f"row {index}: {signal} value changed")

    if mismatch_count:
        errors.append(f"physical value mismatch count: {mismatch_count}")
    status = "PASS" if not errors else "FAIL"
    report = {
        "schema_version": "1.0",
        "status": status,
        "transport_mode": "FILE_HANDOFF",
        "rows_compared": min(len(process_rows), len(handoff_rows)),
        "signals_compared": len(signals),
        "values_compared": compared,
        "value_mismatch_count": mismatch_count,
        "max_source_time_offset_ms": max_source_time_offset_ms,
        "raw_sha256": sha256(args.raw),
        "processbus_sha256": sha256(args.processbus),
        "handoff_sha256": sha256(args.handoff),
        "errors": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if errors:
        raise SystemExit("FAIL: " + "; ".join(errors[:5]))
    print(
        f"PASS: {compared} values are byte-equal at preserved source timestamps; "
        f"RAW sha256={report['raw_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
