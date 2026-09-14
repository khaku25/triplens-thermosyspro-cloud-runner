#!/usr/bin/env python3
"""Static contract for the V8.5.1 live alarm-binding verifier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PUBLISHED_V8_5_SIGNALS = (
    "vppHPFWPMotorEnergized",
    "vppHPFWPSpeedRPM",
    "vppHPFWPSpeedProven",
    "vppIPFWPMotorEnergized",
    "vppIPFWPSpeedRPM",
    "vppIPFWPSpeedProven",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verifier", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()

    verifier = args.verifier.read_text(encoding="utf-8-sig")
    registry = args.registry.read_text(encoding="utf-8-sig")

    if "UNPUBLISHED_DERIVED_NODES" in verifier:
        raise AssertionError("obsolete static unpublished-node rejection remains")
    for token in (
        "live.walk_nodes(client.get_objects_node())",
        "alarm source binding failed: missing=",
        "duplicate=",
        "nodes[name].get_value()",
    ):
        if token not in verifier:
            raise AssertionError(f"live binding contract missing: {token}")
    for signal in PUBLISHED_V8_5_SIGNALS:
        if signal not in verifier:
            raise AssertionError(f"verifier does not require V8.5 signal: {signal}")
    for signal in (
        "vppHPFWPMotorEnergized",
        "vppHPFWPSpeedProven",
        "vppIPFWPMotorEnergized",
        "vppIPFWPSpeedProven",
    ):
        if signal not in registry:
            raise AssertionError(f"registry lost V8.5 alarm source: {signal}")

    result = {
        "status": "PASS",
        "binding_source_of_truth": "LIVE_OPC_UA_ADDRESS_SPACE",
        "published_v8_5_signals": len(PUBLISHED_V8_5_SIGNALS),
        "static_unpublished_rejection": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
