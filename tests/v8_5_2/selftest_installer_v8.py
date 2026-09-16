#!/usr/bin/env python3
"""Static safety/ordering contract for the V8 PowerShell installer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def require(text: str, token: str) -> None:
    if token not in text:
        raise AssertionError(f"missing installer contract: {token!r}")


def ordered(text: str, tokens: tuple[str, ...]) -> None:
    cursor = -1
    for token in tokens:
        position = text.find(token, cursor + 1)
        if position < 0:
            raise AssertionError(f"missing ordered installer contract: {token!r}")
        if position <= cursor:
            raise AssertionError(f"installer order invalid at: {token!r}")
        cursor = position


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--start", type=Path, required=True)
    parser.add_argument("--reset", type=Path, required=True)
    args = parser.parse_args()

    installer = args.installer.read_text(encoding="utf-8-sig")
    start = args.start.read_text(encoding="utf-8-sig")
    reset = args.reset.read_text(encoding="utf-8-sig")

    ordered(
        installer,
        (
            "Invoke-PythonChecked $python @($sourcePatch, $targetSource)",
            "Invoke-PythonChecked $python @($bfpPatch, $targetSource)",
            "Invoke-PythonChecked $python @($matrixPatch, $targetSource)",
            "Write-Host 'SMOKE: default DASSL solver; stopTime=0.1'",
            "Stop-VerifiedTripLensServer $repo $OpcUaPort",
        ),
    )
    for token in (
        "before-protection-dashboard-v8-",
        "V8 source/client/payload rollback completed.",
        "Restart-PreviousServer",
        "TRIPLENS_PROTECTION_MATRIX_V8",
        "TRIPLENS_PROTECTION_MATRIX_V8_2_DISCRETE_LOOP_FIX",
        "TRIPLENS_PROTECTION_LOGIC_STABLE_V8_5",
        "Obsolete V8 52GT/GT-latch discrete-loop condition is still present.",
        "SOURCE LOOP FIX: 52GT OPEN event is independent of GT Trip Latch",
        "Internal command contract is not 66 nodes",
        "LIVE VERIFY 1/4",
        "discard that proof trajectory",
        "LIVE VERIFY 2/4",
        "foreach ($caseName in @('hp','ip','st','gt_breaker','gt'))",
        "--case', $caseName",
        "LIVE VERIFY 3/4",
        "V8.5.1 alarm binding verifier contract",
        "LIVE VERIFY 4/4",
        "PASS: TRIPLENS_PROTECTION_DASHBOARD_V8_5_2_DUAL_LOG_EVENT_HOTFIX",
        "CLEAN RUNTIME",
        "TCP $Port is owned by a non-TripLens process",
    ):
        require(installer, token)

    for text, tokens in (
        (
            start,
            (
                "runtime\\protection_dashboard_v8_5_stable",
                "TripLens_v36_ProtectionDashboardV8_5_Stable",
                "Refusing unverified server path",
                "opcua_run_controller.py",
            ),
        ),
        (
            reset,
            (
                "START_TRIPLENS_PROTECTION_V8_5_STABLE.ps1",
                "runtime\\protection_dashboard_v8_5_stable\\server.exe.path.txt",
                "Get-NetTCPConnection",
            ),
        ),
    ):
        for token in tokens:
            require(text, token)
    if "EVENT.csv" in reset or "RAW.csv" in reset:
        raise AssertionError("reset script must preserve EVENT.csv and RAW.csv")

    result = {
        "status": "PASS",
        "patch_order": ["V7_INPUTS", "V7_LP_BFP", "V8_MATRIX"],
        "smoke_before_server_stop": True,
        "payload_rollback": True,
        "previous_server_restart": True,
        "legacy_write_proof_isolated": True,
        "single_server_owner_guard": True,
        "runtime_path": "protection_dashboard_v8_5_stable",
        "event_raw_preserved": True,
        "gt_breaker_discrete_loop_guard": True,
        "isolated_live_cases": True,
        "hp_ip_hydraulic_boundary": "V8_5_3_BREAKER_INERTIA_ADAPTER",
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
