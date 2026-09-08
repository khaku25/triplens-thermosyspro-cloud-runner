import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_runtime_rules_use_only_absolute_or_boolean():
    with (ROOT / "config" / "dcs_alarm_rules.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 32
    assert {r["threshold_mode"] for r in rows} <= {"ABSOLUTE", "BOOLEAN"}
    assert all(r["unit"] for r in rows)
    assert all(float(r["hysteresis_value"]) >= 0 for r in rows)

def test_no_ratio_field_in_runtime_schema():
    header = (ROOT / "config" / "dcs_alarm_rules.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert "hysteresis_ratio" not in header
    assert "hysteresis_value" in header

