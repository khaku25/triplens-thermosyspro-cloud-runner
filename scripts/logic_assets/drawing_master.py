"""Read-only search index for existing draw.io pages and cells.

The Drawing Master is deliberately separate from the Tag Master and Logic Master:
it records where an object is drawn, but it does not create or reinterpret a rule.
"""
from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from typing import Any


MAX_XML = 25_000_000
MAX_PAGES = 400
MAX_CELLS = 15_000


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: str | None) -> float | int | None:
    if value in (None, ""):
        return None
    number = float(value)
    if not math.isfinite(number) or abs(number) > 1_000_000:
        raise ValueError("Drawing Master geometry is non-finite or excessive")
    return int(number) if number.is_integer() else number


def _keywords(values: Sequence[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for token in re.split(r"[\s,;|/]+", _text(value)):
            token = token.strip()
            if not token:
                continue
            key = token.casefold()
            if key not in seen:
                seen.add(key)
                result.append(token)
    return result


def _cell_geometry(cell: ET.Element) -> dict[str, float | int | None]:
    geometry = cell.find("mxGeometry")
    if geometry is None:
        return {"x": None, "y": None, "width": None, "height": None}
    return {
        "x": _number(geometry.get("x")),
        "y": _number(geometry.get("y")),
        "width": _number(geometry.get("width")),
        "height": _number(geometry.get("height")),
    }


def create_drawing_master(
    xml: str | bytes,
    *,
    file_path: str,
    canonical_tags: Mapping[str, str] | None = None,
    aliases: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a deterministic Drawing Master from an existing draw.io XML file.

    Only existing ``object`` cells are indexed. The input XML is never modified;
    every result carries a stable source reference and the source SHA-256.
    """
    raw = xml.encode("utf-8") if isinstance(xml, str) else bytes(xml)
    if len(raw) > MAX_XML or re.search(br"<!\s*(?:DOCTYPE|ENTITY)", raw, re.I):
        raise ValueError("Unsafe or oversized draw.io XML")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid draw.io XML: {exc}") from exc
    if root.tag != "mxfile":
        raise ValueError("Expected draw.io mxfile document")

    pages = list(root.findall("diagram"))
    if not pages or len(pages) > MAX_PAGES:
        raise ValueError("Invalid draw.io page count")
    page_ids: set[str] = set()
    entries: list[dict[str, Any]] = []
    digest = hashlib.sha256(raw).hexdigest()
    canonical_tags = canonical_tags or {}
    for page in pages:
        page_id = _text(page.get("id"))
        if not page_id or page_id in page_ids:
            raise ValueError(f"Missing or duplicate draw.io page ID: {page_id}")
        page_ids.add(page_id)
        graph_root = page.find("mxGraphModel/root")
        if graph_root is None:
            raise ValueError(f"Missing draw.io graph root: {page_id}")
        page_name = _text(page.get("name")) or page_id
        scope = _text(page.get("scope"))
        for item in graph_root.findall("object"):
            cell_id = _text(item.get("id"))
            cell = item.find("mxCell")
            if not cell_id or cell is None:
                raise ValueError(f"Invalid draw.io object cell: {page_id}")
            geometry = _cell_geometry(cell)
            tag_id = _text(item.get("tag_id"))
            logic_id = _text(item.get("rule_id"))
            kind = _text(item.get("kind")) or "object"
            display_name = _text(item.get("label")) or _text(cell.get("value")) or cell_id
            equipment_id = _text(item.get("equipment_id"))
            if not equipment_id and scope == "equipment":
                equipment_id = page_name
            if not equipment_id:
                equipment_id = _text(item.get("group_id"))
            source_ref = f"{file_path}#page={page_id}&cell={cell_id}"
            canonical_tag = _text(canonical_tags.get(tag_id)) if tag_id else ""
            keywords = _keywords(
                [
                    display_name,
                    page_name,
                    page_id,
                    kind,
                    tag_id,
                    canonical_tag,
                    logic_id,
                    equipment_id,
                    item.get("group_id"),
                    item.get("logic_type"),
                ]
            )
            entries.append(
                {
                    "drawing_id": "drawing:" + digest[:16],
                    "file_path": file_path,
                    "page_id": page_id,
                    "page_name": page_name,
                    "page_scope": scope,
                    "cell_id": cell_id,
                    "object_type": kind,
                    "display_name": display_name,
                    "equipment_id": equipment_id,
                    "canonical_tag": canonical_tag,
                    "tag_id": tag_id,
                    "logic_id": logic_id,
                    "source_ref": source_ref,
                    "evidence_ref": source_ref,
                    "keywords": keywords,
                    "x": geometry["x"],
                    "y": geometry["y"],
                    "width": geometry["width"],
                    "height": geometry["height"],
                    "verification_status": "INDEXED_FROM_DRAWIO_XML",
                }
            )
            if len(entries) > MAX_CELLS:
                raise ValueError("Too many draw.io object cells")
    entries.sort(key=lambda row: (row["file_path"], row["page_id"], row["cell_id"]))
    drawing = {
        "drawing_id": "drawing:" + digest[:16],
        "file_path": file_path,
        "aliases": sorted({_text(value) for value in aliases if _text(value)}),
        "sha256": digest,
        "page_count": len(pages),
        "source_ref": file_path,
        "verification_status": "INDEXED_FROM_DRAWIO_XML",
    }
    return {
        "schema_version": 1,
        "index_type": "DRAWING_MASTER",
        "policy": "READ_ONLY_INDEX_OF_EXISTING_DRAWIO; NO_LOGIC_REINTERPRETATION",
        "drawings": [drawing],
        "entries": entries,
        "counts": {
            "drawings": 1,
            "pages": len(pages),
            "cells": len(entries),
            "linked_tags": len({row["tag_id"] for row in entries if row["tag_id"]}),
            "linked_logic": len({row["logic_id"] for row in entries if row["logic_id"]}),
        },
        "source_sha256": digest,
    }


def search_drawing_master(index: Mapping[str, Any], query: str = "", *, limit: int = 100) -> list[dict[str, Any]]:
    """Search Drawing Master entries by tag, canonical tag, logic, page, or cell."""
    if limit < 1:
        return []
    needle = _text(query).casefold()
    rows = list(index.get("entries", []))
    if not needle:
        return rows[:limit]
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for position, row in enumerate(rows):
        fields = [
            _text(row.get("canonical_tag")),
            _text(row.get("tag_id")),
            _text(row.get("logic_id")),
            _text(row.get("page_name")),
            _text(row.get("display_name")),
            _text(row.get("equipment_id")),
            _text(row.get("source_ref")),
            " ".join(_text(token) for token in row.get("keywords", [])),
        ]
        haystack = " ".join(fields).casefold()
        if needle not in haystack:
            continue
        exact = any(needle == value.casefold() for value in fields if value)
        ranked.append((0 if exact else 1, position, row))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [row for _, _, row in ranked[:limit]]
