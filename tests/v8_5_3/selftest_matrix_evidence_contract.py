#!/usr/bin/env python3
"""Validate the evidence boundary of the V8 common GT/ST matrix."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


EXPECTED_CAUSES = {
    "DIRECT_GT_TRIP", "GT_BREAKER_OPEN_WHILE_RUNNING", "DIRECT_ST_TRIP",
    "HP_DRUM_HH", "IP_DRUM_HH", "LP_DRUM_HH",
    "HP_DRUM_LL", "IP_DRUM_LL", "LP_DRUM_LL",
}
GENERIC_FUTURE = {"VIBRATION", "LUBE_OIL", "AXIAL", "FLAME_LOSS", "EXHAUST_SPREAD"}
VERIFIABLE = {"VERIFIABLE_RAW_EVENT"}
INCONCLUSIVE = {"INCONCLUSIVE"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()

    matrix = read_csv(args.matrix)
    catalog = read_csv(args.catalog)
    errors: list[str] = []
    required_matrix = {
        "cause_id", "source_event_tag", "active_tag_master_tag", "evidence_status",
        "implementation_status", "gt_trip_request", "st_trip_request",
    }
    missing = required_matrix.difference(matrix[0] if matrix else set())
    if missing:
        errors.append("matrix missing evidence fields: " + ",".join(sorted(missing)))
    by_cause = {row.get("cause_id", "").strip().upper(): row for row in matrix}
    if set(by_cause) != EXPECTED_CAUSES:
        errors.append("matrix cause set differs: " + ",".join(sorted(set(by_cause) ^ EXPECTED_CAUSES)))
    for cause, row in by_cause.items():
        if not row.get("source_event_tag", "").strip():
            errors.append(f"{cause}: missing RAW/EVENT source tag")
        evidence = row.get("evidence_status", "").strip().upper()
        active_tag = row.get("active_tag_master_tag", "").strip().upper()
        if evidence == "VERIFIABLE_RAW_EVENT" and not active_tag:
            errors.append(f"{cause}: verifiable row has no Active Tag Master tag")
        if evidence == "INCONCLUSIVE" and active_tag != "UNKNOWN":
            errors.append(f"{cause}: inconclusive row must use UNKNOWN active tag")
    for cause in ("HP_DRUM_HH", "IP_DRUM_HH", "LP_DRUM_HH", "HP_DRUM_LL", "IP_DRUM_LL", "LP_DRUM_LL"):
        row = by_cause.get(cause, {})
        if row.get("evidence_status") not in VERIFIABLE:
            errors.append(f"{cause}: drum cause must be RAW/EVENT verifiable")
        if not row.get("active_tag_master_tag", "").startswith("HRSG."):
            errors.append(f"{cause}: drum cause must use HRSG Active Tag Master tag")

    catalog_tags = {row.get("tag", "").strip().upper() for row in catalog}
    for tag in ("GT.TRIP.CMD", "FWP_HP.TRIPPED", "FWP_HP.TRIP_LATCH", "FWP_HP.SPEED_RPM",
                "FWP_HP.SPEED_PROVEN", "FWP-HP.SPEED_PROVEN.LOST", "VCB_A01_TRIP_CMD",
                "HRSG.HP.DRUM.LEVEL.HH", "HRSG.HP.DRUM.LEVEL.LL",
                "HRSG.IP.DRUM.LEVEL.HH", "HRSG.IP.DRUM.LEVEL.LL",
                "HRSG.LP.DRUM.LEVEL.HH", "HRSG.LP.DRUM.LEVEL.LL",
                "GT.EXHAUST.TEMP.L", "GT.EXHAUST.TEMP.LL",
                "GT.EXHAUST.FLOW.L", "GT.EXHAUST.FLOW.LL"):
        if tag not in catalog_tags:
            errors.append(f"catalog missing supplied Active Tag Master tag: {tag}")
    catalog_future = {
        row.get("tag", "").strip().upper()
        for row in catalog
        if row.get("matrix_status", "").strip().upper() == "FUTURE_EXTENSION"
    }
    if not GENERIC_FUTURE.issubset(catalog_future):
        errors.append("generic ungrounded causes are not all FUTURE_EXTENSION")
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print("PASS: TRIPLENS_V8_COMMON_TRIP_EVIDENCE_CONTRACT")
    print(f"matrix_causes={len(matrix)} catalog_rows={len(catalog)} future_extensions={len(catalog_future)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
