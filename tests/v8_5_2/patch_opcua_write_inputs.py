#!/usr/bin/env python3
"""Turn the ECMS command memories into genuine OpenModelica input variables.

The previous adapter exposed command points as writable continuous states.  A
Write service call was accepted, but the active integrator restored the state
from its own history immediately afterwards.  OpenModelica's embedded OPC UA
interface is intended to write top-level input/state variables; command points
are therefore inputs, while the actual ThermoSysPro valve physics is unchanged.

OpenModelica issue #8705 documents an input-index defect when Real and Boolean
top-level inputs coexist.  This native-OPC-UA runtime does not use the legacy
FMU Boolean input, so it is frozen as a parameter to keep the writable boundary
Real-only.
"""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_OPCUA_RUN_DRIVEN_LIVE_V2"
VALVE_MARKER = "TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2"

VALVE_RE = re.compile(
    r"^(?P<indent>\s*)output Real (?P<name>vppVlv[A-Za-z0-9]+(?:ModeAuto|ManualCmd|FaultEnable|FaultValue)Native)"
    r"\((?P<attrs>[^\n;]*)\);$",
    re.MULTILINE,
)

BREAKER_NAMES = (
    "vppECMS52GTClosedCommandNative",
    "vppECMS52STClosedCommandNative",
    "vppECMSCBInAClosedCommandNative",
    "vppECMSCBInBClosedCommandNative",
    "vppECMSCBTieClosedCommandNative",
    "vppVCBA01ClosedNative",
    "vppVCBA02ClosedNative",
    "vppVCBB01ClosedNative",
)


def clean_attrs(attrs: str) -> str:
    start_match = re.search(r"(?:^|,)\s*start\s*=\s*([^,]+)", attrs)
    if start_match is None:
        raise ValueError(f"command declaration has no start value: {attrs}")
    parts = [part.strip() for part in attrs.split(",")]
    kept = [
        part for part in parts
        if part and not part.startswith("fixed") and not part.startswith("stateSelect")
    ]
    return ", ".join(kept)


def replace_valves(text: str) -> str:
    seen: list[str] = []

    def repl(match: re.Match[str]) -> str:
        attrs = clean_attrs(match.group("attrs"))
        seen.append(match.group("name"))
        # A top-level input binding such as "= 1" is an equation and pins the
        # value on every step.  The start attribute supplies initialization;
        # leaving the input unbound lets the embedded OPC UA server own it.
        return f'{match.group("indent")}input Real {match.group("name")}({attrs});'

    patched = VALVE_RE.sub(repl, text)
    if len(seen) != 48 or len(set(seen)) != 48:
        raise ValueError(f"expected 48 valve command declarations, found {len(seen)}")
    return patched


def replace_breakers(text: str) -> str:
    patched = text
    for name in BREAKER_NAMES:
        pattern = re.compile(
            rf"^(?P<indent>\s*)output Real {re.escape(name)}\((?P<attrs>[^\n;]*)\);$",
            re.MULTILINE,
        )
        match = pattern.search(patched)
        if match is None:
            raise ValueError(f"breaker command declaration not found: {name}")
        attrs = clean_attrs(match.group("attrs"))
        replacement = f'{match.group("indent")}input Real {name}({attrs});'
        patched, count = pattern.subn(replacement, patched, count=1)
        if count != 1:
            raise ValueError(f"breaker command declaration count invalid: {name}")
    return patched


def remove_state_derivatives(text: str, names: tuple[str, ...]) -> str:
    patched = text
    for name in names:
        pattern = re.compile(
            rf"^\s*der\({re.escape(name)}\)\s*=\s*[^;]+;\s*\r?\n",
            re.MULTILINE,
        )
        patched, count = pattern.subn("", patched, count=1)
        if count != 1:
            raise ValueError(f"state derivative not found exactly once: {name}")
    return patched


def patch_text(text: str) -> str:
    if MARKER in text:
        return text
    if VALVE_MARKER not in text:
        raise ValueError("initialization-safe 12-valve marker is missing")

    patched = replace_valves(text)
    patched = replace_breakers(patched)

    valve_names = tuple(match.group("name") for match in re.finditer(
        r"^\s*input Real (?P<name>vppVlv[A-Za-z0-9]+(?:ModeAuto|ManualCmd|FaultEnable|FaultValue)Native)\(",
        patched,
        re.MULTILINE,
    ))
    if len(valve_names) != 48:
        raise ValueError(f"expected 48 converted valve inputs, got {len(valve_names)}")
    patched = remove_state_derivatives(patched, valve_names + BREAKER_NAMES)

    boolean_pattern = re.compile(
        r"^(?P<indent>\s*)input Boolean vppExternalTripCommand\(start\s*=\s*false\)\s*=\s*false"
        r"(?P<tail>\s+\"[^\n]*\";)$",
        re.MULTILINE,
    )
    patched, count = boolean_pattern.subn(
        r"\g<indent>parameter Boolean vppExternalTripCommand = false\g<tail>",
        patched,
        count=1,
    )
    if count != 1:
        raise ValueError("legacy Boolean top-level input was not found exactly once")

    anchor = "  // TRIPLENS_NATIVE_OPCUA_VALVE_ADAPTER_SAFE_V2\n"
    if anchor not in patched:
        raise ValueError("valve declaration anchor is missing")
    patched = patched.replace(
        anchor,
        f"  // {MARKER}: 56 unbound real command inputs; no Boolean input-index collision\n" + anchor,
        1,
    )

    if re.search(r"^\s*input Boolean\s+", patched, re.MULTILINE):
        raise ValueError("a top-level Boolean input remains after patching")
    if re.search(r"der\(vppVlv[A-Za-z0-9]+(?:ModeAuto|ManualCmd|FaultEnable|FaultValue)Native\)", patched):
        raise ValueError("a valve command derivative remains after patching")
    return patched


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
    print("Command inputs: 56 (48 valve + 8 breaker)")
    print("Legacy top-level Boolean input: frozen parameter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
