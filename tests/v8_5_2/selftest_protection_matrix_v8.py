#!/usr/bin/env python3
"""Static and idempotency test for the complete V7 -> V8 Modelica patch chain."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

import patch_lp_bfp_operator_chain
import patch_opcua_write_inputs
import patch_protection_matrix_v8


def default_source() -> Path:
    scratch = Path(__file__).resolve().parents[3]
    candidates = (
        scratch / "work" / "TripLens_CombinedCycle_TripTAC_ProcessView_v36.mo",
        scratch / "triplens-thermosyspro-cloud-runner" / "modelica"
        / "TripLens_CombinedCycle_TripTAC_ProcessView_v36.mo",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("no V36 Modelica source candidate exists")


def require_once(text: str, literal: str) -> None:
    count = text.count(literal)
    if count != 1:
        raise AssertionError(f"expected one {literal!r}, found {count}")


def selftest(source_path: Path) -> None:
    original = source_path.read_text(encoding="utf-8-sig")
    v7_inputs = patch_opcua_write_inputs.patch_text(original)
    v7_complete = patch_lp_bfp_operator_chain.patch_text(v7_inputs)
    v8 = patch_protection_matrix_v8.patch_text(v7_complete)

    # Every patch must be idempotent when an installer is safely re-run.
    assert patch_opcua_write_inputs.patch_text(v8) == v8
    assert patch_lp_bfp_operator_chain.patch_text(v8) == v8
    assert patch_protection_matrix_v8.patch_text(v8) == v8

    # A source left by the first V8 package must be repairable in place too.
    fixed_event = (
        "  // TRIPLENS_PROTECTION_MATRIX_V8_2_DISCRETE_LOOP_FIX: event condition "
        "is independent of the trip latch\n"
        "  elsewhen vppECMS52GTClosedCommandNative < 0.5 then"
    )
    looping_event = (
        "  elsewhen vppECMS52GTClosedCommandNative < 0.5 and\n"
        "      not vppGTTripLatchInternal then"
    )
    legacy_v8 = v8.replace(fixed_event, looping_event)
    if legacy_v8 == v8:
        raise AssertionError("could not construct the legacy V8 loop fixture")
    assert patch_protection_matrix_v8.patch_text(legacy_v8) == v8

    for name in (
        "vppExternalTripCommandNative",
        "vppExternalSTTripCommandNative",
        "vppGTTripResetNative",
        "vppSTTripResetNative",
        "vppHPFWPTripPushbuttonNative",
        "vppHPFWPResetPushbuttonNative",
        "vppIPFWPTripPushbuttonNative",
        "vppIPFWPResetPushbuttonNative",
    ):
        require_once(v8, f"input Real {name}")
        if re.search(rf"der\({re.escape(name)}\)", v8):
            raise AssertionError(f"writable input has a derivative: {name}")

    # 48 valve + 8 breaker + 6 BFP PB + 4 GT/ST protection = 66 Real inputs.
    input_names = re.findall(r"^\s*input Real\s+(vpp[A-Za-z0-9_]+)", v8, re.MULTILINE)
    if len(input_names) != 66 or len(set(input_names)) != 66:
        raise AssertionError(
            f"expected 66 unique writable Real inputs, got {len(input_names)}/"
            f"{len(set(input_names))}"
        )

    expected_causes = (
        "vppCauseDirectGTTrip",
        "vppCauseGTBreakerOpenWhileRunning",
        "vppCauseDirectSTTrip",
        "vppCauseHPDrumHH",
        "vppCauseIPDrumHH",
        "vppCauseLPDrumHH",
        "vppCauseHPDrumLL",
        "vppCauseIPDrumLL",
        "vppCauseLPDrumLL",
    )
    for name in expected_causes:
        require_once(v8, f"output Boolean {name}")

    gt_request = re.search(
        r"vppGTTripRequest\s*=\s*(.*?);", v8, re.DOTALL
    )
    st_request = re.search(
        r"vppSTTripRequest\s*=\s*(.*?);", v8, re.DOTALL
    )
    if gt_request is None or st_request is None:
        raise AssertionError("aggregate trip request equations are missing")
    gt_body = gt_request.group(1)
    st_body = st_request.group(1)
    for cause in ("DirectGTTrip", "GTBreakerOpenWhileRunning", "HPDrumLL", "IPDrumLL", "LPDrumLL"):
        if f"vppCause{cause}" not in gt_body:
            raise AssertionError(f"GT request omits cause: {cause}")
    for forbidden_cause in ("DirectSTTrip", "HPDrumHH", "IPDrumHH", "LPDrumHH"):
        if f"vppCause{forbidden_cause}" in gt_body:
            raise AssertionError(f"GT request incorrectly includes ST-only cause: {forbidden_cause}")
    for cause in ("vppGTTripRequest", "vppCauseDirectSTTrip", "vppCauseHPDrumHH", "vppCauseIPDrumHH", "vppCauseLPDrumHH"):
        if cause not in st_body:
            raise AssertionError(f"ST request omits cause/intertrip: {cause}")

    contracts = (
        "vppGTTripRequest = vppCauseDirectGTTrip or",
        "vppSTTripRequest = vppGTTripRequest or vppCauseDirectSTTrip or",
        "vppGTTripLatch = vppGTTripLatchInternal;",
        "vppCauseGTBreakerOpenWhileRunning = vppGTBreakerOpenCauseState;",
        "vppSTTripLatchPublished = vppSTTripLatch;",
        "vpp52GTTripCmd = vppGTTripLatchInternal and",
        "vpp52STTripCmd = vppSTTripLatch;",
        "time >= vppHPDrumHHAssertTime + vppDrumTripDelay",
        "time >= vppLPDrumLLAssertTime + vppDrumTripDelay",
        "vppHPDrumHHAssertTime >= 0",
        "vppLPDrumLLAssertTime >= 0",
        "if vppGTTripLatchInternal then vppGTExhaustMassFlowTrip",
        "if vppGTTripLatchInternal then vppGTExhaustTemperatureTrip",
        "if vppSTTripLatch then vppAdmissionSeatLeak",
        "vppVCBA02TripCommandNative = vppLPFWPTripLatchState;",
        "vppHPFWPMotorEnergized = vppECMSVCBA01Closed;",
        "vppIPFWPMotorEnergized = vppECMSVCBB01Closed;",
        "vppHPFWPTripCommandNative =",
        "vppHPFWPTripLatchNative = vppHPFWPTripLatchState;",
        "vppVCBA01TripCommandNative = vppHPFWPTripLatchState;",
        "vppIPFWPTripCommandNative =",
        "vppIPFWPTripLatchNative = vppIPFWPTripLatchState;",
        "vppVCBB01TripCommandNative = vppIPFWPTripLatchState;",
        "vppECMSVCBA01Closed = vppVCBA01TripCommandNative < 0.5",
        "vppECMSVCBB01Closed = vppVCBB01TripCommandNative < 0.5",
        "vppVCBA01ClosedNative < 0.5 then",
        "vppVCBB01ClosedNative < 0.5 then",
        "connect(PompeAlimHP.rpm_or_mpower, arretPomesHP.y)",
        "connect(PompeAlimMP.rpm_or_mpower, arretPomesMp.y)",
        "TRIPLENS_PROTECTION_LOGIC_STABLE_V8_5",
        "vppGTBreakerOpenCauseState = true;",
        "vppGTBreakerOpenCauseState = false;",
        "TRIPLENS_PROTECTION_MATRIX_V8_2_DISCRETE_LOOP_FIX",
        "elsewhen vppECMS52GTClosedCommandNative < 0.5 then",
    )
    for contract in contracts:
        if contract not in v8:
            raise AssertionError(f"missing semantic contract: {contract}")

    forbidden = (
        "vppGTTripLatch = vppSTTripLatch;",
        "der(vppExternalTripCommandNative)",
        "der(vppExternalSTTripCommandNative)",
        "elsewhen vppECMS52GTClosedCommandNative < 0.5 and\n"
        "      not vppGTTripLatchInternal then",
        "vppHPFWPHydraulicSpeedCommand",
        "vppIPFWPHydraulicSpeedCommand",
        "TRIPLENS_HP_IP_BFP_INERTIAL_DRIVE_V8_4",
    )
    for contract in forbidden:
        if contract in v8:
            raise AssertionError(f"legacy contract remains: {contract}")
    # The exact V7 hydraulic input connections must survive the protection
    # patch.  V8/V8.4 failed because these were rewired to zero/floored speed.
    for stable_connection in (
        "connect(PompeAlimHP.rpm_or_mpower, arretPomesHP.y)",
        "connect(PompeAlimMP.rpm_or_mpower, arretPomesMp.y)",
    ):
        require_once(v7_complete, stable_connection)
        require_once(v8, stable_connection)

    # Exercise the filesystem CLI contract without mutating the real source.
    with tempfile.TemporaryDirectory() as directory:
        candidate = Path(directory) / source_path.name
        candidate.write_text(v7_complete, encoding="utf-8", newline="")
        patched = patch_protection_matrix_v8.patch_text(
            candidate.read_text(encoding="utf-8")
        )
        candidate.write_text(patched, encoding="utf-8", newline="")
        assert candidate.read_text(encoding="utf-8") == v8

    print("PASS: TRIPLENS_PROTECTION_MATRIX_V8_STATIC_SELFTEST")
    print(f"source={source_path}")
    print("writable_real_inputs=66")
    print("matrix_causes=9")
    print("drum_trip_delay_s=0.5")
    print("gt_st_latches=independent")
    print("lp_bfp_chain=preserved")
    print("hp_ip_bfp_chains=implemented")
    print("hp_ip_hydraulic_connections=v7_preserved")
    print("gt_breaker_discrete_loop=removed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="?")
    args = parser.parse_args()
    selftest(args.source or default_source())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
