"""Self-contained bridge for the TripLens Vercel Agent API."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from triplens.agent_tools import EvidenceStore
from triplens.dual_log_analyzer import analyze_dual_logs

SERVICE_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = SERVICE_ROOT / "triplens"
CURRENT_V8_ROOT = PACKAGE_ROOT / "current_v8"
LIVE_LOGIC = CURRENT_V8_ROOT / "live_logic_runtime.csv"
LIVE_TAG_ALLOWLIST = CURRENT_V8_ROOT / "live_tag_allowlist.csv"
LIVE_MANIFEST = CURRENT_V8_ROOT / "live_validation_manifest.json"

PROTECTION_LOGIC_TYPES = {
    "PROTECTION_CAUSE",
    "TRIP_REQUEST",
    "LATCH",
    "BREAKER_SEQUENCE",
}


def sha256_files(*paths: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def current_v8_manifest() -> dict[str, Any]:
    if not LIVE_MANIFEST.exists():
        raise RuntimeError(f"Current V8 manifest missing: {LIVE_MANIFEST}")
    return json.loads(LIVE_MANIFEST.read_text(encoding="utf-8-sig"))


def live_tag_allowlist() -> set[str]:
    if not LIVE_TAG_ALLOWLIST.exists():
        raise RuntimeError(f"Current V8 tag allowlist missing: {LIVE_TAG_ALLOWLIST}")
    with LIVE_TAG_ALLOWLIST.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    tags = {str(row.get("raw_tag_id", "")).strip() for row in rows}
    tags.discard("")
    if len(tags) != 603:
        raise RuntimeError(f"Current V8 live tag count mismatch: {len(tags)} != 603")
    return tags


def runtime_logic_rows() -> list[dict[str, Any]]:
    """Load only the live-validated 53-rule Current V8 Logic Master.

    Vercel must not fall back to older catalogues or infer logic for tags that are
    not registered in this exact live baseline.
    """
    if not LIVE_LOGIC.exists():
        raise RuntimeError(f"Current V8 live logic missing: {LIVE_LOGIC}")

    allowed = live_tag_allowlist()
    rows: list[dict[str, Any]] = []
    with LIVE_LOGIC.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if str(row.get("status", "")).strip().upper() != "ACTIVE":
                continue
            linked = [
                part.strip()
                for part in str(row.get("linked_tag_ids", "")).replace(",", ";").split(";")
                if part.strip()
            ]
            source_nodes = [tag for tag in linked if tag.startswith("vpp")]
            missing_live = sorted(tag for tag in source_nodes if tag not in allowed)
            if missing_live:
                raise RuntimeError(
                    f"Current V8 logic references non-live OPC UA tags: "
                    f"{row.get('logic_id', '')}: {missing_live}"
                )

            logic_type = str(row.get("logic_type", "")).strip().upper()
            if logic_type == "ALARM":
                event_class = "ALARM"
            elif logic_type in PROTECTION_LOGIC_TYPES:
                event_class = "PROTECTION"
            elif logic_type == "COMMAND_INTERFACE":
                event_class = "OPERATOR_ACTION"
            else:
                event_class = "SYSTEM"

            item = dict(row)
            item["event_class"] = event_class
            item["canonical_tag"] = row.get("event_tag", "")
            item["verification_status"] = "LIVE_OPCUA_VALIDATED"
            rows.append(item)

    if len(rows) != 53:
        raise RuntimeError(f"Current V8 logic rule count mismatch: {len(rows)} != 53")
    return rows


def logic_summary() -> dict[str, Any]:
    rows = runtime_logic_rows()
    alarm = sum(str(r.get("logic_type", "")).upper() == "ALARM" for r in rows)
    protection = sum(str(r.get("logic_type", "")).upper() in PROTECTION_LOGIC_TYPES for r in rows)
    commands = sum(str(r.get("logic_type", "")).upper() == "COMMAND_INTERFACE" for r in rows)
    response = sum(str(r.get("logic_type", "")).upper() == "PHYSICAL_RESPONSE" for r in rows)
    return {
        "live_rules": len(rows),
        "alarm": alarm,
        "protection": protection,
        "commands": commands,
        "physical_response": response,
        "active_logic_core": len(rows),
        "source": "Current V8 Live OPC UA Verified SOT",
    }


def build_store(event_path: Path, raw_path: Path) -> EvidenceStore:
    return EvidenceStore(Path(event_path), Path(raw_path), logic_rows=runtime_logic_rows())


def evidence_readiness(event_path: Path, raw_path: Path) -> dict[str, Any]:
    return analyze_dual_logs(Path(event_path), Path(raw_path))


def public_contract() -> dict[str, Any]:
    manifest = current_v8_manifest()
    return {
        "version": "CURRENT_V8_LIVE_SOT_V1",
        "runtime_baseline": manifest.get("baseline", "Current V8 Live OPC UA Verified"),
        "validation_run": manifest.get("validation_run", {}),
        "current_v8_counts": manifest.get("counts", {}),
        "source_identity_policy": manifest.get("policy", {}).get(
            "source_identity", "exact live OPC UA BrowseName"
        ),
        "input": ["EVENT.csv", "RAW.csv"],
        "read_only": True,
        "python_role": "EVIDENCE_PROVIDER_AND_VERIFIER",
        "decision_authority": "GEMINI_AGENT",
        "status_scope": "EVIDENCE_READINESS_ONLY",
        "reserved_agent_decisions": [
            "critical_events",
            "primary_cause",
            "direct_trigger",
            "propagation",
            "causal_chain",
        ],
        "logic_summary": logic_summary(),
        "live_tag_allowlist_count": len(live_tag_allowlist()),
        "direct_upload_soft_limit_bytes": 4_000_000,
    }
