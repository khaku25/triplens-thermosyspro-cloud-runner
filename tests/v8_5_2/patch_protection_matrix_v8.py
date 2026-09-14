#!/usr/bin/env python3
"""Install the V8 common-trip matrix in the TripLens V36 Modelica model.

This patch is deliberately applied after the two V7 source patches.  It turns
the former GT/ST state-like command memories into genuine Real OPC UA inputs,
separates the GT and ST latches, qualifies all six drum trips for 0.5 model
seconds, and publishes every matrix input/output needed by the dashboard and
RAW historian.

V8.5 deliberately leaves the proven V7 ThermoSysPro hydraulic connections
unchanged.  HP/IP breaker and protection states are executable, but they are
not wired into the StaticCentrifugalPump speed boundary.  Earlier V8 builds
forced that boundary to zero (and later to an artificial floor), which could
invert turbine pressure relationships and terminate the embedded OPC UA
server.  Physical pump coupling requires a separate, validated plant-model
change; it is not part of this protection-logic release.
"""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_PROTECTION_MATRIX_V8"
LOOP_FIX_MARKER = "TRIPLENS_PROTECTION_MATRIX_V8_2_DISCRETE_LOOP_FIX"
STABLE_MARKER = "TRIPLENS_PROTECTION_LOGIC_STABLE_V8_5"
REQUIRED_MARKERS = (
    "TRIPLENS_OPCUA_RUN_DRIVEN_LIVE_V2",
    "TRIPLENS_LP_BFP_OPERATOR_CHAIN_V1",
)


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    patched, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"{label}: expected one semantic match, found {count}")
    return patched


def repair_gt_breaker_discrete_loop(source: str) -> str:
    """Remove the 52GT-cause -> GT-latch -> 52GT-cause event cycle.

    The breaker-open cause is already a discrete state, so its set event only
    needs the external CLOSED command transition.  Referring to the GT latch
    in that same event condition creates a purely discrete algebraic loop in
    OpenModelica's BackendDAE sorting pass.
    """
    if LOOP_FIX_MARKER in source:
        return source
    pattern = (
        r"  elsewhen vppECMS52GTClosedCommandNative < 0\.5 and\s*\r?\n"
        r"      not vppGTTripLatchInternal then"
    )
    replacement = (
        f"  // {LOOP_FIX_MARKER}: event condition is independent of the trip latch\n"
        "  elsewhen vppECMS52GTClosedCommandNative < 0.5 then"
    )
    return replace_once(source, pattern, replacement, "52GT discrete-loop repair")


def install_command_and_latch_declarations(source: str) -> str:
    pattern = (
        r"^(?P<indent>\s*)parameter Boolean vppExternalTripCommand\s*=\s*false[^;]*;\s*\r?\n"
        r"\s*output Real vppExternalTripCommandNative\([^;]*\)[^;]*;\s*\r?\n"
        r"\s*output Real vppExternalSTTripCommandNative\([^;]*\)[^;]*;\s*\r?\n"
        r"\s*discrete Boolean vppSTTripLatch\([^;]*\)[^;]*;"
    )
    replacement = (
        "  // TRIPLENS_PROTECTION_MATRIX_V8: genuine Real OPC UA protection inputs\n"
        "  parameter Boolean vppExternalTripCommand = false\n"
        "    \"Legacy Boolean FMU command is frozen to avoid mixed-input OPC UA indexing\";\n"
        "  input Real vppExternalTripCommandNative(start=0, min=0, max=1)\n"
        "    \"Operator/DCS direct GT Trip command; writable OPC UA input\";\n"
        "  input Real vppExternalSTTripCommandNative(start=0, min=0, max=1)\n"
        "    \"Operator/DCS direct ST Trip command; writable OPC UA input\";\n"
        "  input Real vppGTTripResetNative(start=0, min=0, max=1)\n"
        "    \"GT Trip latch reset pulse; clear initiating cause first\";\n"
        "  input Real vppSTTripResetNative(start=0, min=0, max=1)\n"
        "    \"ST Trip latch reset pulse; GT latch must be clear\";\n"
        "  discrete Boolean vppGTTripLatchInternal(start=false, fixed=true)\n"
        "    \"Independent GT Trip latch\";\n"
        "  discrete Boolean vppSTTripLatch(start=false, fixed=true)\n"
        "    \"Independent ST Trip latch\";\n"
        "  discrete Boolean vppGTBreakerOpenCauseState(start=false, fixed=true)\n"
        "    \"Latched 52GT-open-while-running initiating cause\";\n"
        "  discrete Real vppSTTripAssertTime(unit=\"s\", start=0, fixed=true);\n"
        "  discrete Real vppHPDrumHHAssertTime(unit=\"s\", start=-1, fixed=true);\n"
        "  discrete Real vppIPDrumHHAssertTime(unit=\"s\", start=-1, fixed=true);\n"
        "  discrete Real vppLPDrumHHAssertTime(unit=\"s\", start=-1, fixed=true);\n"
        "  discrete Real vppHPDrumLLAssertTime(unit=\"s\", start=-1, fixed=true);\n"
        "  discrete Real vppIPDrumLLAssertTime(unit=\"s\", start=-1, fixed=true);\n"
        "  discrete Real vppLPDrumLLAssertTime(unit=\"s\", start=-1, fixed=true);"
    )
    return replace_once(source, pattern, replacement, "GT/ST command declarations")


def install_matrix_declarations(source: str) -> str:
    pattern = (
        r"(?P<head>\s*parameter Real vppGTTripCommandDelay\(unit\s*=\s*\"s\"\)\s*=\s*0\.055;\s*\r?\n)"
        r"(?P<body>\s*parameter Real vppGTBreakerOpenDelay[^;]*;\s*\r?\n"
        r"\s*parameter Real vppSTBreakerOpenDelay[^;]*;\s*\r?\n"
        r"\s*parameter Real vppGTGPowerNormalMW[^;]*;\s*\r?\n"
        r"\s*parameter Real vppGTGPowerDecayTau[^;]*;\s*\r?\n"
        r"\s*parameter Real vppGTGSpeedNormalRPM[^;]*;\s*\r?\n"
        r"\s*parameter Real vppGTGCoastdownTau[^;]*;\s*\r?\n)"
        r"\s*discrete Real vppGTTripAssertTime[^;]*;\s*\r?\n"
        r"(?P<outputs>\s*output Boolean vppGTTripCmd;)"
    )
    replacement = (
        r"\g<head>\g<body>"
        "  parameter Real vppDrumTripDelay(unit=\"s\") = 0.5\n"
        "    \"Persistence required for all drum HH/LL common-trip causes\";\n"
        "  parameter Real vppHPDrumHHSetpoint(unit=\"m\") = 1.25;\n"
        "  parameter Real vppIPDrumHHSetpoint(unit=\"m\") = 1.25;\n"
        "  parameter Real vppLPDrumHHSetpoint(unit=\"m\") = 1.95;\n"
        "  parameter Real vppHPDrumLLSetpoint(unit=\"m\") = 0.85;\n"
        "  parameter Real vppIPDrumLLSetpoint(unit=\"m\") = 0.85;\n"
        "  parameter Real vppLPDrumLLSetpoint(unit=\"m\") = 1.55;\n"
        "  discrete Real vppGTTripAssertTime(unit=\"s\", start=0, fixed=true);\n"
        "  output Boolean vppHPDrumHHRaw;\n"
        "  output Boolean vppIPDrumHHRaw;\n"
        "  output Boolean vppLPDrumHHRaw;\n"
        "  output Boolean vppHPDrumLLRaw;\n"
        "  output Boolean vppIPDrumLLRaw;\n"
        "  output Boolean vppLPDrumLLRaw;\n"
        "  output Boolean vppCauseDirectGTTrip;\n"
        "  output Boolean vppCauseGTBreakerOpenWhileRunning;\n"
        "  output Boolean vppCauseDirectSTTrip;\n"
        "  output Boolean vppCauseHPDrumHH;\n"
        "  output Boolean vppCauseIPDrumHH;\n"
        "  output Boolean vppCauseLPDrumHH;\n"
        "  output Boolean vppCauseHPDrumLL;\n"
        "  output Boolean vppCauseIPDrumLL;\n"
        "  output Boolean vppCauseLPDrumLL;\n"
        "  output Boolean vppGTTripRequest;\n"
        "  output Boolean vppSTTripRequest;\n"
        f"  // {STABLE_MARKER}: protection logic without hydraulic rewiring.\n"
        "  // Independent HP/IP BFP operator protection chains.\n"
        "  input Real vppHPFWPTripPushbuttonNative(start=0, min=0, max=1)\n"
        "    \"Operator HP BFP Trip pushbutton; writable OPC UA input\";\n"
        "  input Real vppHPFWPResetPushbuttonNative(start=0, min=0, max=1)\n"
        "    \"Operator HP BFP reset pushbutton; breaker must be commanded OPEN\";\n"
        "  input Real vppIPFWPTripPushbuttonNative(start=0, min=0, max=1)\n"
        "    \"Operator IP BFP Trip pushbutton; writable OPC UA input\";\n"
        "  input Real vppIPFWPResetPushbuttonNative(start=0, min=0, max=1)\n"
        "    \"Operator IP BFP reset pushbutton; breaker must be commanded OPEN\";\n"
        "  output Real vppHPFWPTripCommandNative;\n"
        "  output Real vppHPFWPTripLatchNative;\n"
        "  output Real vppVCBA01TripCommandNative;\n"
        "  output Real vppIPFWPTripCommandNative;\n"
        "  output Real vppIPFWPTripLatchNative;\n"
        "  output Real vppVCBB01TripCommandNative;\n"
        "  discrete Real vppHPFWPTripLatchState(start=0, fixed=true);\n"
        "  discrete Real vppIPFWPTripLatchState(start=0, fixed=true);\n"
        "  output Boolean vppHPFWPMotorEnergized;\n"
        "  output Boolean vppIPFWPMotorEnergized;\n"
        "  output Real vppHPFWPSpeedRPM(unit=\"rev/min\");\n"
        "  output Real vppIPFWPSpeedRPM(unit=\"rev/min\");\n"
        "  output Boolean vppHPFWPSpeedProven;\n"
        "  output Boolean vppIPFWPSpeedProven;\n"
        r"\g<outputs>"
    )
    return replace_once(source, pattern, replacement, "protection matrix declarations")


def install_published_equations(source: str) -> str:
    pattern = (
        r"^\s*vppGTTripCmd\s*=\s*if vppUseExternalTripInput[^;]+;\s*\r?\n"
        r"\s*vppGTTripLatch\s*=\s*vppSTTripLatch;\s*\r?\n"
        r"\s*vppSTTripLatchPublished\s*=\s*vppSTTripLatch;\s*\r?\n"
        r"\s*vpp52GTTripCmd\s*=\s*[^;]+;\s*\r?\n"
        r"\s*vpp52GTClosed\s*=\s*[^;]+;\s*\r?\n"
        r"\s*vpp52STTripCmd\s*=\s*[^;]+;\s*\r?\n"
        r"\s*vpp52STClosed\s*=\s*[^;]+;\s*\r?\n"
        r"\s*vppGTGPowerMW\s*=\s*[^;]+;\s*\r?\n"
        r"\s*vppGTGSpeedRPM\s*=\s*[^;]+;"
    )
    replacement = (
        "  // TRIPLENS_PROTECTION_MATRIX_V8: nine explicit causes and two requests\n"
        "  vppHPDrumHHRaw = vppHPDrumLevelM >= vppHPDrumHHSetpoint;\n"
        "  vppIPDrumHHRaw = vppIPDrumLevelM >= vppIPDrumHHSetpoint;\n"
        "  vppLPDrumHHRaw = vppLPDrumLevelM >= vppLPDrumHHSetpoint;\n"
        "  vppHPDrumLLRaw = vppHPDrumLevelM <= vppHPDrumLLSetpoint;\n"
        "  vppIPDrumLLRaw = vppIPDrumLevelM <= vppIPDrumLLSetpoint;\n"
        "  vppLPDrumLLRaw = vppLPDrumLevelM <= vppLPDrumLLSetpoint;\n"
        "  vppCauseDirectGTTrip = if vppUseExternalTripInput then\n"
        "    vppExternalTripCommandNative >= 0.5 else time >= vppTripTime;\n"
        "  vppCauseGTBreakerOpenWhileRunning = vppGTBreakerOpenCauseState;\n"
        "  vppCauseDirectSTTrip = vppExternalSTTripCommandNative >= 0.5;\n"
        "  vppCauseHPDrumHH = vppHPDrumHHRaw and vppHPDrumHHAssertTime >= 0 and\n"
        "    time >= vppHPDrumHHAssertTime + vppDrumTripDelay;\n"
        "  vppCauseIPDrumHH = vppIPDrumHHRaw and vppIPDrumHHAssertTime >= 0 and\n"
        "    time >= vppIPDrumHHAssertTime + vppDrumTripDelay;\n"
        "  vppCauseLPDrumHH = vppLPDrumHHRaw and vppLPDrumHHAssertTime >= 0 and\n"
        "    time >= vppLPDrumHHAssertTime + vppDrumTripDelay;\n"
        "  vppCauseHPDrumLL = vppHPDrumLLRaw and vppHPDrumLLAssertTime >= 0 and\n"
        "    time >= vppHPDrumLLAssertTime + vppDrumTripDelay;\n"
        "  vppCauseIPDrumLL = vppIPDrumLLRaw and vppIPDrumLLAssertTime >= 0 and\n"
        "    time >= vppIPDrumLLAssertTime + vppDrumTripDelay;\n"
        "  vppCauseLPDrumLL = vppLPDrumLLRaw and vppLPDrumLLAssertTime >= 0 and\n"
        "    time >= vppLPDrumLLAssertTime + vppDrumTripDelay;\n"
        "  vppGTTripRequest = vppCauseDirectGTTrip or\n"
        "    vppCauseGTBreakerOpenWhileRunning or vppCauseHPDrumLL or\n"
        "    vppCauseIPDrumLL or vppCauseLPDrumLL;\n"
        "  vppSTTripRequest = vppGTTripRequest or vppCauseDirectSTTrip or\n"
        "    vppCauseHPDrumHH or vppCauseIPDrumHH or vppCauseLPDrumHH;\n"
        "  vppGTTripCmd = vppGTTripRequest;\n"
        "  vppGTTripLatch = vppGTTripLatchInternal;\n"
        "  vppSTTripLatchPublished = vppSTTripLatch;\n"
        "  vpp52GTTripCmd = vppGTTripLatchInternal and\n"
        "    time >= vppGTTripAssertTime + vppGTTripCommandDelay;\n"
        "  vpp52GTClosed = vppECMS52GTClosedCommandNative >= 0.5 and not\n"
        "    (vppGTTripLatchInternal and time >= vppGTTripAssertTime + vppGTBreakerOpenDelay);\n"
        "  vpp52STTripCmd = vppSTTripLatch;\n"
        "  vpp52STClosed = vppECMS52STClosedCommandNative >= 0.5 and not\n"
        "    (vppSTTripLatch and time >= vppSTTripAssertTime + vppSTBreakerOpenDelay);\n"
        "  vppGTGPowerMW = if not vppGTTripLatchInternal then vppGTGPowerNormalMW\n"
        "    else if vpp52GTClosed then vppGTGPowerNormalMW*exp(-max(0, time -\n"
        "      vppGTTripAssertTime)/vppGTGPowerDecayTau) else 0;\n"
        "  vppGTGSpeedRPM = if not vppGTTripLatchInternal or vpp52GTClosed then\n"
        "    vppGTGSpeedNormalRPM else vppGTGSpeedNormalRPM*exp(-max(0, time -\n"
        "      vppGTTripAssertTime - vppGTBreakerOpenDelay)/vppGTGCoastdownTau);"
    )
    return replace_once(source, pattern, replacement, "published trip equations")


def install_event_logic(source: str) -> str:
    pattern = (
        r"^\s*der\(vppExternalTripCommandNative\)\s*=\s*[^;]+;\s*\r?\n"
        r"\s*der\(vppExternalSTTripCommandNative\)\s*=\s*[^;]+;\s*\r?\n"
        r"\s*when vppGTTripCmd or \(vppUseExternalTripInput and "
        r"vppExternalSTTripCommandNative\s*>=\s*0\.5\) then\s*\r?\n"
        r"\s*vppSTTripLatch\s*=\s*true;\s*\r?\n"
        r"\s*vppGTTripAssertTime\s*=\s*time;\s*\r?\n"
        r"\s*end when;"
    )
    replacement = (
        "  // Drum persistence timers capture each raw-condition rising edge.\n"
        "  when vppHPDrumHHRaw then\n"
        "    vppHPDrumHHAssertTime = time;\n"
        "  end when;\n"
        "  when vppIPDrumHHRaw then\n"
        "    vppIPDrumHHAssertTime = time;\n"
        "  end when;\n"
        "  when vppLPDrumHHRaw then\n"
        "    vppLPDrumHHAssertTime = time;\n"
        "  end when;\n"
        "  when vppHPDrumLLRaw then\n"
        "    vppHPDrumLLAssertTime = time;\n"
        "  end when;\n"
        "  when vppIPDrumLLRaw then\n"
        "    vppIPDrumLLAssertTime = time;\n"
        "  end when;\n"
        "  when vppLPDrumLLRaw then\n"
        "    vppLPDrumLLAssertTime = time;\n"
        "  end when;\n"
        "  // Capture a manual/feedback-equivalent 52GT OPEN transition while the\n"
        "  // GT is in service. It remains visible until the safe reset sequence.\n"
        "  when vppGTTripResetNative >= 0.5 and\n"
        "      not vppCauseDirectGTTrip and not vppCauseHPDrumLL and\n"
        "      not vppCauseIPDrumLL and not vppCauseLPDrumLL and\n"
        "      vppECMS52GTClosedCommandNative < 0.5 then\n"
        "    vppGTBreakerOpenCauseState = false;\n"
        f"  // {LOOP_FIX_MARKER}: event condition is independent of the trip latch\n"
        "  elsewhen vppECMS52GTClosedCommandNative < 0.5 then\n"
        "    vppGTBreakerOpenCauseState = true;\n"
        "  end when;\n"
        "  when vppGTTripResetNative >= 0.5 and\n"
        "      not vppCauseDirectGTTrip and not vppCauseHPDrumLL and\n"
        "      not vppCauseIPDrumLL and not vppCauseLPDrumLL and\n"
        "      vppECMS52GTClosedCommandNative < 0.5 then\n"
        "    vppGTTripLatchInternal = false;\n"
        "    vppGTTripAssertTime = time;\n"
        "  elsewhen vppGTTripRequest and vppGTTripResetNative < 0.5 then\n"
        "    vppGTTripLatchInternal = true;\n"
        "    vppGTTripAssertTime = time;\n"
        "  end when;\n"
        "  when vppSTTripResetNative >= 0.5 and not vppCauseDirectSTTrip and\n"
        "      not vppCauseHPDrumHH and not vppCauseIPDrumHH and\n"
        "      not vppCauseLPDrumHH and not vppGTTripRequest and\n"
        "      not vppGTTripLatchInternal and\n"
        "      vppECMS52STClosedCommandNative < 0.5 then\n"
        "    vppSTTripLatch = false;\n"
        "    vppSTTripAssertTime = time;\n"
        "  elsewhen (vppSTTripRequest or vppGTTripLatchInternal) and\n"
        "      vppSTTripResetNative < 0.5 then\n"
        "    vppSTTripLatch = true;\n"
        "    vppSTTripAssertTime = time;\n"
        "  end when;"
    )
    return replace_once(source, pattern, replacement, "trip event logic")


def install_hp_ip_bfp_protection_chains(source: str) -> str:
    source = replace_once(
        source,
        (
            r"vppECMSVCBA01Closed\s*=\s*vppVCBA01ClosedNative\s*>=\s*0\.5\s+and\s+"
            r"vppECMSBusAAvailable\s*;"
        ),
        (
            "vppECMSVCBA01Closed = vppVCBA01TripCommandNative < 0.5 and "
            "vppVCBA01ClosedNative >= 0.5 and vppECMSBusAAvailable;"
        ),
        "VCB-A01 protection binding",
    )
    source = replace_once(
        source,
        (
            r"vppECMSVCBB01Closed\s*=\s*vppVCBB01ClosedNative\s*>=\s*0\.5\s+and\s+"
            r"vppECMSBusBAvailable\s*;"
        ),
        (
            "vppECMSVCBB01Closed = vppVCBB01TripCommandNative < 0.5 and "
            "vppVCBB01ClosedNative >= 0.5 and vppECMSBusBAvailable;"
        ),
        "VCB-B01 protection binding",
    )

    anchor = "  // TRIPLENS_PROTECTION_MATRIX_V8: nine explicit causes and two requests\n"
    if source.count(anchor) != 1:
        raise ValueError("HP/IP BFP equation anchor: expected one exact match")
    equations = (
        "  // TRIPLENS_HP_IP_BFP_OPERATOR_CHAINS_V8\n"
        "  // V8.5 keeps the proven V7 HP/IP pump speed connections intact.\n"
        "  vppHPFWPTripCommandNative =\n"
        "    if vppHPFWPTripPushbuttonNative >= 0.5 then 1 else 0;\n"
        "  vppHPFWPTripLatchNative = vppHPFWPTripLatchState;\n"
        "  vppVCBA01TripCommandNative = vppHPFWPTripLatchState;\n"
        "  vppIPFWPTripCommandNative =\n"
        "    if vppIPFWPTripPushbuttonNative >= 0.5 then 1 else 0;\n"
        "  vppIPFWPTripLatchNative = vppIPFWPTripLatchState;\n"
        "  vppVCBB01TripCommandNative = vppIPFWPTripLatchState;\n"
        "  when vppHPFWPResetPushbuttonNative >= 0.5 and\n"
        "      vppHPFWPTripPushbuttonNative < 0.5 and\n"
        "      vppVCBA01ClosedNative < 0.5 then\n"
        "    vppHPFWPTripLatchState = 0;\n"
        "  elsewhen vppHPFWPTripPushbuttonNative >= 0.5 then\n"
        "    vppHPFWPTripLatchState = 1;\n"
        "  end when;\n"
        "  when vppIPFWPResetPushbuttonNative >= 0.5 and\n"
        "      vppIPFWPTripPushbuttonNative < 0.5 and\n"
        "      vppVCBB01ClosedNative < 0.5 then\n"
        "    vppIPFWPTripLatchState = 0;\n"
        "  elsewhen vppIPFWPTripPushbuttonNative >= 0.5 then\n"
        "    vppIPFWPTripLatchState = 1;\n"
        "  end when;\n"
    )
    source = source.replace(anchor, equations + anchor, 1)
    return source


def install_hp_ip_pump_proof_aliases(source: str) -> str:
    pattern = (
        r"(?P<head>\s*vppHPFWPSpeedCommandRPM\s*=\s*PompeAlimHP\.rpm_or_mpower\.signal;\s*\r?\n"
        r"\s*vppIPFWPSpeedCommandRPM\s*=\s*PompeAlimMP\.rpm_or_mpower\.signal;\s*\r?\n)"
        r"\s*vppHPFWPRunning\s*=\s*noEvent\([^;]+;\s*\r?\n"
        r"\s*vppIPFWPRunning\s*=\s*noEvent\([^;]+;"
    )
    replacement = (
        r"\g<head>"
        "  // V8.5 publishes the unchanged V7 hydraulic speed as process evidence.\n"
        "  // Motor/running are protection indications, not a claim that the legacy\n"
        "  // StaticCentrifugalPump has a validated electrical coastdown model.\n"
        "  vppHPFWPMotorEnergized = vppECMSVCBA01Closed;\n"
        "  vppIPFWPMotorEnergized = vppECMSVCBB01Closed;\n"
        "  vppHPFWPSpeedRPM = vppHPFWPSpeedCommandRPM;\n"
        "  vppIPFWPSpeedRPM = vppIPFWPSpeedCommandRPM;\n"
        "  vppHPFWPSpeedProven = noEvent(vppHPFWPSpeedRPM > 1);\n"
        "  vppIPFWPSpeedProven = noEvent(vppIPFWPSpeedRPM > 1);\n"
        "  vppHPFWPRunning = vppHPFWPMotorEnergized and vppHPFWPSpeedProven and\n"
        "    noEvent(abs(vppHPFWPMassFlowTH) > 0.1);\n"
        "  vppIPFWPRunning = vppIPFWPMotorEnergized and vppIPFWPSpeedProven and\n"
        "    noEvent(abs(vppIPFWPMassFlowTH) > 0.1);"
    )
    return replace_once(source, pattern, replacement, "HP/IP pump proof aliases")


def bind_gt_physics_to_gt_latch(source: str) -> str:
    source = replace_once(
        source,
        r"der\(vppGTExhaustMassFlowState\)\s*=\s*\(\(if vppSTTripLatch then",
        "der(vppGTExhaustMassFlowState) = ((if vppGTTripLatchInternal then",
        "GT exhaust mass-flow latch binding",
    )
    source = replace_once(
        source,
        r"der\(vppGTExhaustTemperatureState\)\s*=\s*\(\(if vppSTTripLatch then",
        "der(vppGTExhaustTemperatureState) = ((if vppGTTripLatchInternal then",
        "GT exhaust temperature latch binding",
    )
    return source


def patch_text(source: str) -> str:
    if MARKER in source:
        if STABLE_MARKER not in source:
            raise ValueError(
                "an older V8 source is installed; restore the V7 source backup "
                "before applying V8.5 Logic Stable"
            )
        return repair_gt_breaker_discrete_loop(source)
    for marker in REQUIRED_MARKERS:
        if marker not in source:
            raise ValueError(f"required predecessor marker is missing: {marker}")

    source = install_command_and_latch_declarations(source)
    source = install_matrix_declarations(source)
    source = install_published_equations(source)
    source = install_hp_ip_bfp_protection_chains(source)
    source = install_event_logic(source)
    source = bind_gt_physics_to_gt_latch(source)
    source = install_hp_ip_pump_proof_aliases(source)
    source = repair_gt_breaker_discrete_loop(source)

    required = (
        "input Real vppExternalTripCommandNative",
        "input Real vppExternalSTTripCommandNative",
        "input Real vppGTTripResetNative",
        "input Real vppSTTripResetNative",
        "input Real vppHPFWPTripPushbuttonNative",
        "input Real vppHPFWPResetPushbuttonNative",
        "input Real vppIPFWPTripPushbuttonNative",
        "input Real vppIPFWPResetPushbuttonNative",
        "vppGTTripLatch = vppGTTripLatchInternal",
        "vppSTTripRequest = vppGTTripRequest",
        "vppCauseGTBreakerOpenWhileRunning",
        "vppCauseHPDrumHH",
        "vppCauseIPDrumHH",
        "vppCauseLPDrumHH",
        "vppCauseHPDrumLL",
        "vppCauseIPDrumLL",
        "vppCauseLPDrumLL",
        "if vppGTTripLatchInternal then vppGTExhaustMassFlowTrip",
        "if vppSTTripLatch then vppAdmissionSeatLeak",
        "vppHPFWPMotorEnergized = vppECMSVCBA01Closed",
        "vppIPFWPSpeedProven = noEvent(vppIPFWPSpeedRPM > 1)",
        "vppHPFWPTripLatchNative = vppHPFWPTripLatchState",
        "vppVCBA01TripCommandNative = vppHPFWPTripLatchState",
        "vppIPFWPTripLatchNative = vppIPFWPTripLatchState",
        "vppVCBB01TripCommandNative = vppIPFWPTripLatchState",
        "vppECMSVCBA01Closed = vppVCBA01TripCommandNative < 0.5",
        "vppECMSVCBB01Closed = vppVCBB01TripCommandNative < 0.5",
        "connect(PompeAlimHP.rpm_or_mpower, arretPomesHP.y)",
        "connect(PompeAlimMP.rpm_or_mpower, arretPomesMp.y)",
        STABLE_MARKER,
        LOOP_FIX_MARKER,
    )
    for contract in required:
        if contract not in source:
            raise ValueError(f"post-patch contract missing: {contract}")
    forbidden = (
        "vppGTTripLatch = vppSTTripLatch",
        "der(vppExternalTripCommandNative)",
        "der(vppExternalSTTripCommandNative)",
        "output Real vppExternalTripCommandNative",
        "output Real vppExternalSTTripCommandNative",
        "elsewhen vppECMS52GTClosedCommandNative < 0.5 and\n"
        "      not vppGTTripLatchInternal then",
        "vppHPFWPHydraulicSpeedCommand",
        "vppIPFWPHydraulicSpeedCommand",
        "TRIPLENS_HP_IP_BFP_INERTIAL_DRIVE_V8_4",
    )
    for contract in forbidden:
        if contract in source:
            raise ValueError(f"legacy protection contract remains: {contract}")
    return source


def write_atomic(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=path.parent
    ) as stream:
        stream.write(text)
        temporary = Path(stream.name)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    original = args.source.read_text(encoding="utf-8-sig")
    patched = patch_text(original)
    write_atomic(args.source, patched)
    print(f"PASS: {MARKER}")
    print("Protection inputs: direct GT/ST Trip/reset + HP/IP/LP BFP operator PBs")
    print("Matrix: 9 causes; GT and ST latches are independent")
    print("Drum HH/LL persistence: 0.5 model seconds")
    print("HP/IP physical pump connections: V7 preserved (logic-only protection boundary)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
