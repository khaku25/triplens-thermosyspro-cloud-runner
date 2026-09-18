"""Bridge the existing TripLens Python evidence core into the Vercel API service."""

from __future__ import annotations

import csv
import hashlib
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from triplens_agent_tools import EvidenceStore, load_logic_rows  # type: ignore  # noqa: E402
from triplens_dual_log_analyzer import analyze_dual_logs  # type: ignore  # noqa: E402

RUNTIME_REGISTRY = ROOT / "config" / "alarm_registry_v1.csv"
DEFAULT_ACTIVE_LOGIC_CORE = 440


def sha256_files(*paths: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def runtime_logic_rows() -> list[dict[str, Any]]:
    configured = os.getenv("TRIPLENS_LOGIC_DB_PATH", "").strip()
    if configured and Path(configured).exists():
        return load_logic_rows(Path(configured))

    rows: list[dict[str, Any]] = []
    if not RUNTIME_REGISTRY.exists():
        return rows
    with RUNTIME_REGISTRY.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if str(row.get("enabled", "")).strip().lower() not in {"1", "true", "yes"}:
                continue
            rows.append(
                {
                    "logic_id": row.get("rule_id", ""),
                    "tag_id": row.get("tag", ""),
                    "event_tag": row.get("tag", ""),
                    "source_node": row.get("source_node", ""),
                    "equipment": row.get("equipment", ""),
                    "event_class": row.get("event_class", ""),
                    "condition": row.get("active_when", ""),
                    "threshold": row.get("active_threshold", ""),
                    "unit": row.get("unit", ""),
                    "status": "ACTIVE",
                    "verification_status": "RUNTIME_REGISTRY_EXACT",
                }
            )
    return rows


def logic_summary() -> dict[str, Any]:
    rows = runtime_logic_rows()
    alarm = sum(str(r.get("event_class", "")).upper() == "ALARM" for r in rows)
    protection = sum(str(r.get("event_class", "")).upper() == "PROTECTION" for r in rows)
    return {
        "live_rules": len(rows),
        "alarm": alarm,
        "protection": protection,
        "active_logic_core": DEFAULT_ACTIVE_LOGIC_CORE,
        "source": "GitHub main Current V8 runtime registry",
    }


def build_store(event_path: Path, raw_path: Path) -> EvidenceStore:
    return EvidenceStore(Path(event_path), Path(raw_path), logic_rows=runtime_logic_rows())


def evidence_readiness(event_path: Path, raw_path: Path) -> dict[str, Any]:
    return analyze_dual_logs(Path(event_path), Path(raw_path))


def public_contract() -> dict[str, Any]:
    return {
        "version": "VERCEL_MIGRATION_P0",
        "runtime_baseline": "Windows Local V8",
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
        "direct_upload_soft_limit_bytes": 4_000_000,
    }
