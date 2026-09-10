#!/usr/bin/env python3
"""Extract and lock M rows from the supplied Thermo VPP tag catalog."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=PROJECT_ROOT / "data/thermo_vpp_full_tag_list.csv")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/thermo_vpp_m_locked_tags.csv")
    parser.add_argument("--links", type=Path, default=PROJECT_ROOT / "data/ecms_m_links.csv")
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "data/m_layer_manifest.json")
    args = parser.parse_args()

    with args.source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    if not fields or "tag_id" not in fields or "tag_class" not in fields:
        raise ValueError("source tag catalog does not have tag_id/tag_class")
    if len({row["tag_id"] for row in rows}) != len(rows):
        raise ValueError("source tag catalog contains duplicate tag_id")

    m_rows = [row for row in rows if row["tag_class"] == "M" and row["value_basis"] == "M"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(m_rows)

    m_ids = {row["tag_id"] for row in m_rows}
    with args.links.open("r", encoding="utf-8-sig", newline="") as stream:
        links = list(csv.DictReader(stream))
    invalid = sorted({row["source_m_tag_id"] for row in links}.difference(m_ids))
    if invalid:
        raise ValueError("ECMS M links reference non-M or missing tags: " + ", ".join(invalid))

    manifest = {
        "schema_version": "1.0",
        "source_file": args.source.name,
        "source_sha256": digest(args.source),
        "source_row_count": len(rows),
        "m_file": args.output.name,
        "m_sha256": digest(args.output),
        "m_row_count": len(m_rows),
        "ecms_m_link_count": len(links),
        "lock_policy": "M tag_id, unit, tag_class, value_basis and model_mapping are read-only",
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
