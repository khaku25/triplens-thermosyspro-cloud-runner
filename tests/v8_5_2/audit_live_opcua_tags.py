#!/usr/bin/env python3
"""Live OPC UA census for the TripLens current tag boundary.

This script does not trust the Tag Master as an existence source. It starts from
the running OpenModelica OPC UA address space, browses exact BrowseNames, reads
current values, and exports only live-observed nodes. TripLens-local aliases are
not part of this census.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


def scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    return value


def access_text(node: Any, user: bool = False) -> str:
    try:
        values = node.get_user_access_level() if user else node.get_access_level()
        return ",".join(sorted(str(value).split(".")[-1] for value in values))
    except Exception:
        return ""


def variant_text(node: Any) -> str:
    try:
        return str(node.get_data_type_as_variant_type()).split(".")[-1]
    except Exception:
        return ""


def browse(client: Any) -> tuple[dict[str, list[Any]], int]:
    found: dict[str, list[Any]] = defaultdict(list)
    pending = deque(client.get_objects_node().get_children())
    visited: set[str] = set()
    visited_count = 0
    while pending:
        node = pending.popleft()
        identity = str(node.nodeid)
        if identity in visited:
            continue
        visited.add(identity)
        visited_count += 1
        try:
            name = str(node.get_browse_name().Name)
        except Exception:
            continue
        if name == "time" or name.startswith("vpp"):
            found[name].append(node)
        try:
            pending.extend(node.get_children())
        except Exception:
            pass
    return found, visited_count


def main() -> int:
    logging.getLogger("opcua").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--expected-min-vpp", type=int, default=680)
    args = parser.parse_args()

    from opcua import Client

    client = Client(args.endpoint, timeout=10)
    client.connect()
    try:
        found, visited_count = browse(client)
        duplicates = sorted(name for name, nodes in found.items() if len(nodes) != 1)
        rows: list[dict[str, Any]] = []
        nonnumeric: list[str] = []
        nonfinite: list[str] = []

        for name in sorted(found):
            nodes = found[name]
            if len(nodes) != 1:
                continue
            node = nodes[0]
            try:
                value = scalar(node.get_value())
            except Exception as exc:
                rows.append({
                    "browse_name": name,
                    "node_id": str(node.nodeid),
                    "variant_type": variant_text(node),
                    "access_level": access_text(node),
                    "user_access_level": access_text(node, user=True),
                    "current_value": "",
                    "numeric": "N",
                    "finite": "N",
                    "live_validated": "N",
                    "read_error": f"{type(exc).__name__}: {exc}",
                })
                nonnumeric.append(name)
                continue

            numeric = isinstance(value, (bool, int, float))
            finite = False
            if numeric:
                try:
                    finite = math.isfinite(float(value))
                except Exception:
                    finite = False
            if not numeric:
                nonnumeric.append(name)
            elif not finite:
                nonfinite.append(name)

            rows.append({
                "browse_name": name,
                "node_id": str(node.nodeid),
                "variant_type": variant_text(node),
                "access_level": access_text(node),
                "user_access_level": access_text(node, user=True),
                "current_value": value if numeric else str(value),
                "numeric": "Y" if numeric else "N",
                "finite": "Y" if finite else "N",
                "live_validated": "Y" if numeric and finite else "N",
                "read_error": "",
            })

        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", encoding="utf-8-sig", newline="") as stream:
            fields = [
                "browse_name", "node_id", "variant_type", "access_level",
                "user_access_level", "current_value", "numeric", "finite",
                "live_validated", "read_error",
            ]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        vpp_rows = [row for row in rows if row["browse_name"].startswith("vpp")]
        live_vpp = [row for row in vpp_rows if row["live_validated"] == "Y"]
        summary = {
            "status": "PASS",
            "endpoint": args.endpoint,
            "visited_nodes": visited_count,
            "time_present": "time" in found,
            "unique_vpp_browse_names": len(vpp_rows),
            "live_validated_vpp": len(live_vpp),
            "duplicates": duplicates,
            "nonnumeric": sorted(nonnumeric),
            "nonfinite": sorted(nonfinite),
            "authoritative_identity_field": "browse_name",
            "policy": (
                "Only unique, finite, numeric BrowseNames observed in the running "
                "OPC UA server are eligible for the Current Tag Master."
            ),
        }

        if duplicates:
            summary["status"] = "FAIL"
            summary["reason"] = "duplicate BrowseNames"
        elif len(live_vpp) < args.expected_min_vpp:
            summary["status"] = "FAIL"
            summary["reason"] = (
                f"live vpp count below minimum: {len(live_vpp)} < "
                f"{args.expected_min_vpp}"
            )

        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if summary["status"] == "PASS" else 1
    finally:
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
