#!/usr/bin/env python3
"""Make ECMS writes wait for OpenModelica's next solver-boundary commit."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path


MARKER = "TRIPLENS_OPCUA_RUN_DELAYED_ECHO_V2"

HELPER = '''\n\ndef wait_write_echo(node, expected: float, timeout_s: float = 30.0) -> float:\n    """Wait for OpenModelica to commit an OPC UA input at a solver boundary."""\n    deadline = time.monotonic() + timeout_s\n    last = float("nan")\n    while time.monotonic() < deadline:\n        last = scalar(node.get_value())\n        if math.isclose(last, expected, rel_tol=0.0, abs_tol=2e-6):\n            return last\n        time.sleep(0.02)\n    raise LocalControlError(\n        f"delayed write commit timeout after {timeout_s:.0f}s: "\n        f"expected={expected}, actual={last}"\n    )\n'''


def patch_text(text: str) -> str:
    if MARKER in text:
        return text
    anchor = "\ndef write_valve(\n"
    if text.count(anchor) != 1:
        raise ValueError(f"write_valve anchor count={text.count(anchor)}")
    text = text.replace(anchor, HELPER + f"\n\n# {MARKER}\n" + anchor, 1)

    if text.count("ua.Variant(float(value), ua.VariantType.Double)") != 2:
        raise ValueError("expected exactly two Double command writes")
    text = text.replace(
        "ua.Variant(float(value), ua.VariantType.Double)",
        "ua.Variant(float(value), ua.VariantType.Float)",
    )

    valve_old = '''        echo = scalar(nodes[browse_name].get_value())\n        if not math.isclose(echo, value, rel_tol=0.0, abs_tol=1e-12):\n            raise LocalControlError(f"write echo mismatch for {browse_name}: {echo}")'''
    valve_new = '''        echo = wait_write_echo(nodes[browse_name], value)'''
    if text.count(valve_old) != 1:
        raise ValueError(f"valve echo block count={text.count(valve_old)}")
    text = text.replace(valve_old, valve_new, 1)

    breaker_old = '''        echo = scalar(command_node.get_value())\n        if not math.isclose(echo, value, abs_tol=1e-12):\n            raise LocalControlError(f"write echo mismatch for {binding.write_browse_name}: {echo}")'''
    breaker_new = '''        echo = wait_write_echo(command_node, value)'''
    if text.count(breaker_old) != 1:
        raise ValueError(f"breaker echo block count={text.count(breaker_old)}")
    return text.replace(breaker_old, breaker_new, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    original = args.source.read_text(encoding="utf-8-sig")
    patched = patch_text(original)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=args.source.parent
    ) as stream:
        stream.write(patched)
        temporary = Path(stream.name)
    temporary.replace(args.source)
    print(f"PASS: {MARKER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
