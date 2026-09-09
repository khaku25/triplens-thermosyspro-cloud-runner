#!/usr/bin/env python3
"""Fail if TripLens command/alarm catalogs misuse the word TRIP.

Canonical rule:
- TRIP request may be active-high internally.
- A TRIP-capable generator/motor/breaker must use breaker CLOSED feedback as its result.
- Analog process reduction alone must not be labeled TRIP.
- DERATE is a process reduction and must not use breaker CLOSED feedback as its defining result.
"""
from __future__ import annotations
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ROOT / 'config' / 'ecms_command_catalog.csv'
ALARMS = ROOT / 'config' / 'dcs_alarm_rules.csv'
OUT = ROOT / 'outputs' / 'trip_semantics_audit.json'


def read_csv(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    commands = read_csv(COMMANDS)
    alarms = read_csv(ALARMS)
    errors = []
    trip_rows = [r for r in commands if r['command'].strip().upper() == 'TRIP']
    derate_rows = [r for r in commands if r['command'].strip().upper() == 'DERATE']

    for r in trip_rows:
        et = r['equipment_type'].strip().upper()
        feedback = r['feedback_tag'].strip().upper()
        if et in {'GENERATOR', 'MOTOR', 'BREAKER'} and 'CLOSED' not in feedback:
            errors.append(f"{r['equipment_id']} TRIP has non-breaker feedback_tag={r['feedback_tag']}")

    for r in derate_rows:
        if 'CLOSED' in r['feedback_tag'].strip().upper():
            errors.append(f"{r['equipment_id']} DERATE incorrectly uses breaker CLOSED feedback")

    analog_trip_alarms = []
    for r in alarms:
        if r['severity'].strip().upper() != 'TRIP':
            continue
        boolean_command = r['threshold_mode'].strip().upper() == 'BOOLEAN' and 'TRIP.CMD' in r['alarm_tag'].strip().upper()
        if not boolean_command:
            analog_trip_alarms.append(r['rule_id'])
    if analog_trip_alarms:
        errors.append('Analog/non-command alarms still labeled TRIP: ' + ','.join(analog_trip_alarms))

    report = {
        'pass': not errors,
        'canonical_trip_result': 'associated breaker CLOSED feedback = 0',
        'trip_command_rows': len(trip_rows),
        'derate_command_rows': len(derate_rows),
        'analog_trip_alarm_rows': analog_trip_alarms,
        'errors': errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)
    print('TRIPLENS_TRIP_SEMANTICS_AUDIT_PASS')


if __name__ == '__main__':
    main()
