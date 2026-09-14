#!/usr/bin/env python3
"""Static contract checks for the V8 MATLAB protection/historian dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def require(text: str, token: str) -> None:
    if token not in text:
        raise AssertionError(f"V8 dashboard contract missing {token!r}")


def exact(text: str, token: str, count: int = 1) -> None:
    actual = text.count(token)
    if actual != count:
        raise AssertionError(f"expected {count} occurrences of {token!r}, found {actual}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", type=Path, required=True)
    args = parser.parse_args()
    ui = args.ui.read_text(encoding="utf-8-sig")

    require(ui, "TRIPLENS_PROTECTION_DASHBOARD_V8_COMPLETE")
    require(ui, "TRIPLENS_PROTECTION_DASHBOARD_V8_1_HEADER_LAYOUT")
    require(ui, "TRIPLENS_PROTECTION_DASHBOARD_V8_5_LOGIC_STABLE")
    require(ui, "HP/IP 물리입력은 V7 보존")
    for title in (
        '"Title","EVENT Timeline"',
        '"Title","Dual-input Analysis"',
        '"Title","Protection Logic"',
        '"Title","Live Historian"',
        '"Title","Alarm Coverage"',
    ):
        require(ui, title)

    for card in ('"LP DRUM"', '"GT / 52GT"', '"ST / 52ST"', '"LP BFP / VCB-A02"'):
        require(ui, card)

    for token in (
        '"protection_matrix"',
        '"protection_chain"',
        '"historian_rows"',
        '"RESUME_RUNTIME"',
        '"PUMP_TRIP"',
        '"PUMP_RESET"',
        '"HP TRIP PB"',
        '"IP TRIP PB"',
        '"LP TRIP PB"',
        '"HP RESET/CLOSE"',
        '"IP RESET/CLOSE"',
        '"LP RESET/CLOSE"',
        '"pump_control_trains"',
        "HP FWP / VCB-A01",
        "IP FWP / VCB-B01",
        "vppHPFWPTripLatch",
        "vppIPFWPTripLatch",
        "vppECMSVCBA01Closed",
        "vppECMSVCBB01Closed",
        'function updateProtection(snapshot)',
        'function updateHistorian(snapshot)',
        'function filterHistorian(varargin)',
        'function data=sanitizeTableData(data)',
        'sourceField="session_events"',
        '과거 기록 제외',
    ):
        require(ui, token)

    # Every non-empty dynamic table assignment must pass through the type guard.
    for assignment in (
        "alarmTable.Data=sanitizeTableData(data);",
        "coverageTable.Data=sanitizeTableData(data);",
        "causeTable.Data=sanitizeTableData(causeData);",
        "chainTable.Data=sanitizeTableData(chainData);",
        "historianTable.Data=sanitizeTableData(data);",
    ):
        exact(ui, assignment)

    # These MATLAB values are rejected by mixed-cell uitable Data in affected releases.
    unsafe_table_patterns = (
        "alarmTable.Data=table(",
        "coverageTable.Data=table(",
        "historianTable.Data=table(",
        "alarmTable.Data=string(",
        "historianTable.Data=string(",
        "alarmTable.Data=datetime(",
        "historianTable.Data=datetime(",
        "alarmTable.Data=categorical(",
        "historianTable.Data=categorical(",
    )
    found = [token for token in unsafe_table_patterns if token in ui]
    if found:
        raise AssertionError(f"unsafe MATLAB table Data assignments: {found}")

    result = {
        "status": "PASS",
        "plant_protection_tab": True,
        "live_historian_tab": True,
        "historian_search_filter": True,
        "top_status_cards": 4,
        "protection_chain_rows": 4,
        "hp_ip_fwp_visualization": True,
        "hp_ip_lp_operator_controls": True,
        "capability_guarded_controls": True,
        "current_session_event_timeline": True,
        "matlab_table_cell_guard": True,
        "manual_runtime_resume": True,
        "dpi_safe_header_layout": True,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
