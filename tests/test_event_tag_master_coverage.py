import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_db(tmp: Path) -> Path:
    out = tmp / "logic.sqlite"
    manifest = tmp / "manifest.json"
    subprocess.run([
        sys.executable,
        str(ROOT / "logic_db" / "build_logic_db.py"),
        "--output", str(out),
        "--manifest", str(manifest),
    ], cwd=ROOT, check=True)
    return out


def enabled_event_rules():
    with (ROOT / "config" / "alarm_registry_v1.csv").open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if str(r.get("enabled", "")).strip() in {"1", "true", "TRUE"}]


def test_every_enabled_event_rule_has_tag_master_mapping():
    with tempfile.TemporaryDirectory() as td:
        db_path = build_db(Path(td))
        db = sqlite3.connect(db_path)
        try:
            for rule in enabled_event_rules():
                row = db.execute(
                    "SELECT tag_id FROM event_tag_link WHERE rule_id=?",
                    (rule["rule_id"],),
                ).fetchone()
                assert row, f"unmapped EVENT rule: {rule['rule_id']} ({rule['equipment']} / {rule['tag']})"
        finally:
            db.close()


def test_hp_turbine_flow_low_low_resolves_to_canonical_alarm_tag():
    with tempfile.TemporaryDirectory() as td:
        db_path = build_db(Path(td))
        db = sqlite3.connect(db_path)
        try:
            row = db.execute(
                "SELECT tag_id FROM event_tag_link WHERE rule_id='HP_STEAM_FLOW_LOW_LOW'"
            ).fetchone()
            assert row == ("HRSG.HP.STEAM.FLOW.LL",)
        finally:
            db.close()


def test_gt_trip_latch_resolves_to_gt_trip_latch_tag():
    with tempfile.TemporaryDirectory() as td:
        db_path = build_db(Path(td))
        db = sqlite3.connect(db_path)
        try:
            row = db.execute(
                "SELECT tag_id FROM event_tag_link WHERE rule_id='GT_TRIP_LATCH'"
            ).fetchone()
            assert row == ("GT.TRIP.LATCH",)
        finally:
            db.close()
