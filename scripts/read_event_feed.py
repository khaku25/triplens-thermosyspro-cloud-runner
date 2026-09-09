#!/usr/bin/env python3
"""Shared EVENT.csv-only reader for Alarm Console and TripLens AI adapters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .build_vpp_event_bundle import ROOT, load_contract, read_csv, validate_events
except ImportError:  # Direct CLI execution from scripts/.
    from build_vpp_event_bundle import ROOT, load_contract, read_csv, validate_events


def read_event_feed(
    event_path: Path, contract_path: Path, consumer: str
) -> list[dict[str, str]]:
    consumer = consumer.strip().lower()
    if consumer not in {"alarm-console", "triplens-ai"}:
        raise ValueError("consumer must be alarm-console or triplens-ai")
    contract = load_contract(contract_path)
    if event_path.name != "EVENT.csv":
        raise ValueError(f"{consumer} accepts EVENT.csv only")
    fields, rows = read_csv(event_path)
    validate_events(fields, rows, contract)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument(
        "--consumer",
        choices=("alarm-console", "triplens-ai"),
        required=True,
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "config" / "event_contract_v1.json",
    )
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()
    rows = read_event_feed(args.event, args.contract, args.consumer)
    if args.emit_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({
            "consumer": args.consumer,
            "input": "EVENT.csv",
            "event_count": len(rows),
            "raw_access": False,
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
