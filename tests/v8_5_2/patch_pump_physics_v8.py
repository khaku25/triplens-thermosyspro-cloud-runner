#!/usr/bin/env python3
"""Install the V8.8 signed-load coastdown correction in PumpPhysics."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_PUMP_DRAG_SIGN_V8_8"


def patch_text(source: str) -> str:
    """Retain pump drag when a post-trip hydraulic flow reverses."""
    if MARKER in source:
        return source
    old_filter = (
        "    der(pumpPowerFiltered) = (max(pumpPower.signal, 0) -\n"
        "      pumpPowerFiltered)/pumpPowerFilterTime;"
    )
    new_filter = (
        f"    // {MARKER}: StaticCentrifugalPump.Wm may change\n"
        "    // sign when a tripped train reverses its hydraulic flow.  That sign does\n"
        "    // not make the shaft load assist the freely coasting rotor: the drive\n"
        "    // still sees the magnitude of the opposing pump load.  Preserve that\n"
        "    // drag magnitude so HP/IP coast down after their breaker opens.\n"
        "    der(pumpPowerFiltered) = (abs(pumpPower.signal) -\n"
        "      pumpPowerFiltered)/pumpPowerFilterTime;"
    )
    if old_filter not in source:
        raise ValueError("pump-power filter anchor is missing")
    source = source.replace(old_filter, new_filter, 1)
    old_torque = "hydraulicTorque = noEvent(max(pumpPowerFiltered, 0)*max(angularSpeed, 0)/("
    new_torque = "hydraulicTorque = noEvent(abs(pumpPowerFiltered)*max(angularSpeed, 0)/("
    if old_torque not in source:
        raise ValueError("hydraulic-torque anchor is missing")
    return source.replace(old_torque, new_torque, 1)


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
    source = args.source.read_text(encoding="utf-8-sig")
    write_atomic(args.source, patch_text(source))
    print(f"PASS: {MARKER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
