#!/usr/bin/env python3
"""Validate the V8.5.2 writable OPC UA input contract in OpenModelica XML."""

from __future__ import annotations

import argparse
import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path


EXTRA_INPUTS = (
    "vppECMS52GTClosedCommandNative",
    "vppECMS52STClosedCommandNative",
    "vppECMSCBInAClosedCommandNative",
    "vppECMSCBInBClosedCommandNative",
    "vppECMSCBTieClosedCommandNative",
    "vppVCBA01ClosedNative",
    "vppVCBA02ClosedNative",
    "vppVCBB01ClosedNative",
    "vppLPFWPTripPushbuttonNative",
    "vppLPFWPResetPushbuttonNative",
    "vppHPFWPTripPushbuttonNative",
    "vppHPFWPResetPushbuttonNative",
    "vppIPFWPTripPushbuttonNative",
    "vppIPFWPResetPushbuttonNative",
    "vppExternalTripCommandNative",
    "vppExternalSTTripCommandNative",
    "vppGTTripResetNative",
    "vppSTTripResetNative",
    "vppHPDrumInventoryFaultEnableNative",
    "vppHPDrumInventoryFaultValueNative",
    "vppIPDrumInventoryFaultEnableNative",
    "vppIPDrumInventoryFaultValueNative",
    "vppLPDrumInventoryFaultEnableNative",
    "vppLPDrumInventoryFaultValueNative",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-xml", type=Path, required=True)
    parser.add_argument("--valve-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with args.valve_map.open("r", encoding="utf-8-sig", newline="") as stream:
        valve_inputs = [
            row["opcua_browse_name"].strip()
            for row in csv.DictReader(stream)
            if row.get("direction", "").strip() == "WRITE"
        ]
    required = valve_inputs + list(EXTRA_INPUTS)
    if len(required) != 72 or len(set(required)) != 72:
        raise SystemExit(
            f"expected 72 unique command inputs, got total={len(required)} unique={len(set(required))}"
        )

    root = ET.parse(args.init_xml).getroot()
    variables = {
        item.attrib.get("name", ""): item
        for item in root.iter()
        if item.tag.endswith("ScalarVariable")
    }
    missing = [name for name in required if name not in variables]
    invalid = []
    for name in required:
        item = variables.get(name)
        if item is None:
            continue
        if item.attrib.get("causality") != "input" or item.attrib.get("isValueChangeable") != "true":
            invalid.append(
                {
                    "name": name,
                    "causality": item.attrib.get("causality"),
                    "isValueChangeable": item.attrib.get("isValueChangeable"),
                }
            )
    result = {
        "status": "PASS" if not missing and not invalid else "FAIL",
        "required_count": len(required),
        "missing": missing,
        "invalid": invalid,
        "inputs": required,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
