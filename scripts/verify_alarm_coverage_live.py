#!/usr/bin/env python3
"""Read-only OPC UA binding proof for the complete TripLens alarm registry."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path


logging.getLogger("opcua").setLevel(logging.ERROR)

RUNTIME_SIGNALS = {
    "vppLPFWPTripPushbuttonNative", "vppLPFWPResetPushbuttonNative",
    "vppLPFWPTripCommandNative", "vppLPFWPTripLatchNative",
    "vppVCBA02TripCommandNative", "vppVCBA02ClosedNative",
    "vppECMSVCBA02Closed", "vppLPFWPMotorEnergized",
    "vppLPFWPSpeedProven", "vppLPFWPRunning", "vppLPFWPSpeedRPM",
    "vppLPFWPCheckValveOpen", "vppLPFWPCheckValveOpening",
    "vppLPFWPMassFlowTH", "vppLPFWPDeltaPPa", "vppLPDrumLevelM",
    "vppLPDrumPressurePa", "time",
    "vppHPFWPMotorEnergized", "vppHPFWPSpeedRPM",
    "vppHPFWPSpeedProven", "vppIPFWPMotorEnergized",
    "vppIPFWPSpeedRPM", "vppIPFWPSpeedProven",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    sys.path.insert(0, str(root / "scripts"))
    import local_ecms_opcua as live  # pylint: disable=import-error,import-outside-toplevel

    with args.registry.open("r", encoding="utf-8-sig", newline="") as stream:
        rules = [row for row in csv.DictReader(stream) if str(row.get("enabled", "")).strip() == "1"]
    alarm_names = {str(row["source_node"]) for row in rules}
    # V8.5 publishes the HP/IP motor and speed-proven outputs.  Do not reject
    # nodes from an old, static "unpublished" list: the running candidate's
    # OPC UA address space below is the source of truth.
    names = sorted(alarm_names.union(RUNTIME_SIGNALS))
    client = live.connect(args.endpoint, 5.0)
    try:
        matches = {name: [] for name in names}
        for node in live.walk_nodes(client.get_objects_node()):
            try:
                name = str(node.get_browse_name().Name)
            except Exception:
                continue
            if name in matches:
                matches[name].append(node)
        missing = sorted(name for name, found in matches.items() if not found)
        duplicate = sorted(name for name, found in matches.items() if len(found) > 1)
        if missing or duplicate:
            raise RuntimeError(
                "alarm source binding failed: missing=" + ",".join(missing) +
                "; duplicate=" + ",".join(duplicate)
            )
        nodes = {name: found[0] for name, found in matches.items()}
        values = {}
        for name in names:
            if nodes[name] is None:
                raise RuntimeError(f"alarm source binding returned null: {name}")
            values[name] = live.scalar(nodes[name].get_value())
    finally:
        try:
            client.disconnect()
        except (ConnectionError, OSError):
            # A server-side close must not hide the binding result with a
            # second SecureClose/WinError 10054 traceback.
            pass
    details = []
    for rule in rules:
        source = str(rule["source_node"])
        value = values[source]
        if not isinstance(value, (int, float, bool)):
            raise TypeError(f"nonnumeric OPC UA alarm source: {source}={value!r}")
        details.append({"rule_id": rule["rule_id"], "source_node": source, "value": value, "status": "BOUND"})
    result = {
        "status": "PASS",
        "endpoint": args.endpoint,
        "rule_count": len(rules),
        "unique_source_nodes": len(alarm_names),
        "required_runtime_nodes": len(names),
        "bound_rules": len(details),
        "details": details,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "status", "rule_count", "unique_source_nodes", "required_runtime_nodes", "bound_rules",
    )}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
