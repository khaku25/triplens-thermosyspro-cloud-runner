#!/usr/bin/env python3
"""Static contract test for the V8 runtime reset and timeline UI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def exact(text: str, token: str, count: int = 1) -> None:
    actual = text.count(token)
    if actual != count:
        raise AssertionError(f"expected {count} occurrences of {token!r}, found {actual}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--reset-script", type=Path, required=True)
    args = parser.parse_args()
    ui = args.ui.read_text(encoding="utf-8-sig")
    engine = args.engine.read_text(encoding="utf-8-sig")
    reset = args.reset_script.read_text(encoding="utf-8-sig")

    exact(ui, "function resetRuntime(~,~)")
    exact(ui, "function launchRuntimeReset(files)")
    exact(ui, "function pollRuntimeReset(~,~)")
    exact(ui, "function stopResetTimer()")
    for token in (
        '"Text","시간 0 재시작"',
        'eventSummary=uilabel',
        '현재 세션 EVENT 0건',
        'PLANT-WIDE',
        'model_time_stalled_s',
        'stopWorker(true);',
        'TRIPLENS_PROTECTION_DASHBOARD_V8_1_HEADER_LAYOUT',
        "root.RowHeight={112,210,72,76,'1x',42}",
        'header.RowHeight={38,48}',
        "header.ColumnWidth={150,'1x',150,135,110,110}",
        'header.Padding=[2 2 2 2]',
        '"Tooltip","검증된 서버를 종료하고 모델시간 0초부터 새로 시작"',
    ):
        if token not in ui:
            raise AssertionError(f"UI contract missing {token!r}")
    for token in (
        '"model_time_advancing"',
        '"model_time_stalled_s"',
        "self.observe_model_time(self.last_model_time)",
    ):
        if token not in engine:
            raise AssertionError(f"engine liveness contract missing {token!r}")
    for token in (
        "server.exe.path.txt",
        "Get-NetTCPConnection",
        "Stop-Process -Id $owner.Id -Force",
        "START_TRIPLENS_PROTECTION_V8_5_STABLE.ps1",
    ):
        if token not in reset:
            raise AssertionError(f"reset safety contract missing {token!r}")
    if "EVENT.csv" in reset or "RAW.csv" in reset:
        raise AssertionError("runtime reset script must not touch EVENT.csv or RAW.csv")

    result = {
        "status": "PASS",
        "time_zero_button": True,
        "verified_owner_guard": True,
        "event_raw_preserved": True,
        "model_time_stall_detection": True,
        "session_timeline_status": True,
        "dpi_safe_header_layout": True,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
