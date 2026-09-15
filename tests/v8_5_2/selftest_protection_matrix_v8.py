#!/usr/bin/env python3
"""Static and idempotency test for the complete V7 -> V8 Modelica patch chain."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

import patch_lp_bfp_operator_chain
import patch_opcua_write_inputs
import patch_pump_physics_v8
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

    pump_path = source_path.parent / "TripLens_PumpPhysics.mo"
    if not pump_path.is_file():
        raise FileNotFoundError(f"PumpPhysics companion is missing: {pump_path}")
    pump = pump_path.read_text(encoding="utf-8-sig")
    if patch_pump_physics_v8.MARKER not in pump:
        raise AssertionError("V8.8 pump drag-sign repair is missing")
    assert patch_pump_physics_v8.patch_text(pump) == pump
    if "abs(pumpPower.signal)" not in pump or "abs(pumpPowerFiltered)" not in pump:
        raise AssertionError("pump drag-sign equations are incomplete")
    legacy_pump = pump.replace(
        "    // TRIPLENS_PUMP_DRAG_SIGN_V8_8: StaticCentrifugalPump.Wm may change\n"
        "    // sign when a tripped train reverses its hydraulic flow.  That sign does\n"
        "    // not make the shaft load assist the freely coasting rotor: the drive\n"
        "    // still sees the magnitude of the opposing pump load.  Preserve that\n"
        "    // drag magnitude so HP/IP coast down after their breaker opens.\n",
        "",
        1,
    ).replace(
        "abs(pumpPower.signal)", "max(pumpPower.signal, 0)", 1
    ).replace(
        "abs(pumpPowerFiltered)", "max(pumpPowerFiltered, 0)", 1
    )
    if legacy_pump == pump:
        raise AssertionError("could not construct the legacy pump fixture")
    assert patch_pump_physics_v8.patch_text(legacy_pump) == pump

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

    # Existing V8 installations are upgraded in place too: HP/IP running
    # proof must remain identical to LP even when the inertial adapters are
    # already present.
    upgraded_running = v8.replace(
        "  // Keep HP/IP running proof identical to the validated LP boundary.  Flow\n"
        "  // remains an independent physical feedback/alarm, so a transient flow\n"
        "  // reversal cannot mask the motor-speed loss event.\n"
        "  vppHPFWPRunning = vppHPFWPMotorEnergized and vppHPFWPSpeedProven;\n"
        "  vppIPFWPRunning = vppIPFWPMotorEnergized and vppIPFWPSpeedProven;",
        "  vppHPFWPRunning = vppHPFWPMotorEnergized and vppHPFWPSpeedProven and\n"
        "    noEvent(abs(vppHPFWPMassFlowTH) > 0.1);\n"
        "  vppIPFWPRunning = vppIPFWPMotorEnergized and vppIPFWPSpeedProven and\n"
        "    noEvent(abs(vppIPFWPMassFlowTH) > 0.1);",
        1,
    )
    if upgraded_running == v8:
        raise AssertionError("could not construct the legacy HP/IP running fixture")
    assert patch_protection_matrix_v8.patch_text(upgraded_running) == v8

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

    # 48 valve + 8 breaker + 6 BFP PB + 4 GT/ST protection + 6 physical
    # drum-inventory source commands = 72 writable Real inputs.
    input_names = re.findall(r"^\s*input Real\s+(vpp[A-Za-z0-9_]+)", v8, re.MULTILINE)
    if len(input_names) != 72 or len(set(input_names)) != 72:
        raise AssertionError(
            f"expected 72 unique writable Real inputs, got {len(input_names)}/"
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
        "TRIPLENS_IP_BFP_COASTDOWN_V8_7",
        "vppIPFWPDrive(\n    nominalSpeedRpm = 1400, J = 100,",
        "TRIPLENS_HP_IP_V7_NORMAL_SPEED_BOUNDARY_V8_8",
        "TRIPLENS_DRUM_FAULT_STROKE_V8_8",
        "TRIPLENS_DRUM_INVENTORY_FAULT_PATH_V1",
        "vppHPDrumInventoryFaultEnableNative",
        "vppIPDrumInventoryFaultEnableNative",
        "vppLPDrumInventoryFaultEnableNative",
        "connect(vppHPDrumInventoryFaultSource.C, BallonHP.Ce2)",
        "connect(vppIPDrumInventoryFaultSource.C, BallonMP.Ce2)",
        "connect(vppLPDrumInventoryFaultSource.C, BallonBP.Ce2)",
        "parameter Real vppDrumFaultValveMinimumOpening",
        "parameter Modelica.SIunits.Time vppDrumFaultValveStrokeTime",
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
        "TRIPLENS_HP_IP_FWP_INERTIAL_DRIVES_V8_6",
        "vppHPFWPDrive.breakerClosed.signal = vppHPFWPMotorEnergized;",
        "vppIPFWPDrive.breakerClosed.signal = vppIPFWPMotorEnergized;",
        "vppHPFWPDrive.pumpPower.signal = PompeAlimHP.Wm;",
        "vppIPFWPDrive.pumpPower.signal = PompeAlimMP.Wm;",
        "arretPomesHP.y.signal else noEvent(max(vppHPFWPHydraulicSpeedFloorRPM,",
        "arretPomesMp.y.signal else noEvent(max(vppIPFWPHydraulicSpeedFloorRPM,",
        "vppHPFWPSpeedProven = vppHPFWPSpeedRPM >= 0.9*vppHPFWPDrive.nominalSpeedRpm;",
        "vppIPFWPSpeedProven = vppIPFWPSpeedRPM >= 0.9*vppIPFWPDrive.nominalSpeedRpm;",
        "vppHPFWPRunning = vppHPFWPMotorEnergized and vppHPFWPSpeedProven;",
        "vppIPFWPRunning = vppIPFWPMotorEnergized and vppIPFWPSpeedProven;",
        "connect(vppHPFWPHydraulicSpeedCommand, PompeAlimHP.rpm_or_mpower)",
        "connect(vppIPFWPHydraulicSpeedCommand, PompeAlimMP.rpm_or_mpower)",
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
        "TRIPLENS_HP_IP_BFP_INERTIAL_DRIVE_V8_4",
    )
    for contract in forbidden:
        if contract in v8:
            raise AssertionError(f"legacy contract remains: {contract}")
    # The current checked-in source is already a V8 predecessor, so verify
    # that the patched result contains the physical adapter connections and
    # no longer drives HP/IP speed directly from the legacy fixed Ramps.
    for physical_connection in (
        "connect(vppHPFWPHydraulicSpeedCommand, PompeAlimHP.rpm_or_mpower)",
        "connect(vppIPFWPHydraulicSpeedCommand, PompeAlimMP.rpm_or_mpower)",
    ):
        require_once(v8, physical_connection)
    for legacy_connection in (
        "connect(PompeAlimHP.rpm_or_mpower, arretPomesHP.y)",
        "connect(PompeAlimMP.rpm_or_mpower, arretPomesMp.y)",
    ):
        if legacy_connection in v8:
            raise AssertionError(f"legacy HP/IP Ramp connection remains: {legacy_connection}")

    # Drum fault injection may request a physically closed valve, but the
    # ThermoSysPro static ControlValve must receive a finite, time-continuous
    # opening instead of an algebraic Cv=0 step.
    for target, stroke, fault_value in (
        ("vppVlvHPFWCVTarget", "vppVlvHPFWCVFaultStroke", "vppVlvHPFWCVFaultValueNative"),
        ("vppVlvHPSteamTarget", "vppVlvHPSteamFaultStroke", "vppVlvHPSteamFaultValueNative"),
        ("vppVlvIPFWCVTarget", "vppVlvIPFWCVFaultStroke", "vppVlvIPFWCVFaultValueNative"),
        ("vppVlvIPSteamTarget", "vppVlvIPSteamFaultStroke", "vppVlvIPSteamFaultValueNative"),
        ("vppVlvLPSteamTarget", "vppVlvLPSteamFaultStroke", "vppVlvLPSteamFaultValueNative"),
        ("vppVlvLPFWTarget", "vppVlvLPFWFaultStroke", "vppVlvLPFWFaultValueNative"),
    ):
        if (
            f"Real {stroke}" not in v8
            or f"der({stroke})" not in v8
            or f"{target} = if noEvent" not in v8
            or fault_value not in v8
        ):
            raise AssertionError(f"drum fault valve stroke is missing: {target}")

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
    print("writable_real_inputs=72")
    print("matrix_causes=9")
    print("drum_trip_delay_s=0.5")
    print("gt_st_latches=independent")
    print("lp_bfp_chain=preserved")
    print("hp_ip_bfp_chains=implemented")
    print("hp_ip_hydraulic_connections=breaker_inertia_adapters")
    print("gt_breaker_discrete_loop=removed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, nargs="?")
    args = parser.parse_args()
    selftest(args.source or default_source())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
