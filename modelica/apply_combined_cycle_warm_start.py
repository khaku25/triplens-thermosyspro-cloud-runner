#!/usr/bin/env python3
"""Apply the legacy CombinedCycle Dymola iteration values to an OMC init XML.

ThermoSysPro distributed this plant with a separate post-translation
initialization script.  OpenModelica cannot execute that Dymola script against
an already generated executable, so this utility transfers matching continuous
variable values into the ``start`` attributes of the generated setup XML.
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ASSIGNMENT = re.compile(
    r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*|\[\d+\])*)\s*=\s*([^;]+);"
)


def parse_dymola_values(path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        match = ASSIGNMENT.match(line)
        if not match:
            continue
        try:
            values[match.group(1)] = float(match.group(2).strip())
        except ValueError:
            continue
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-xml", type=Path, required=True)
    parser.add_argument("--dymola-script", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    values = parse_dymola_values(args.dymola_script)
    tree = ET.parse(args.init_xml)
    matched = 0
    changed = 0
    matched_nonlinear_candidates = 0

    for scalar in tree.getroot().iter("ScalarVariable"):
        name = scalar.attrib.get("name")
        if name not in values:
            continue
        matched += 1
        # Parameter values in 4.2 are authoritative.  The legacy script is used
        # only as an iteration-variable warm start, exactly as originally
        # intended by ThermoSysPro.
        if scalar.attrib.get("variability") != "continuous":
            continue
        value_node = next(iter(scalar), None)
        if value_node is None or value_node.tag != "Real":
            continue
        old_value = value_node.attrib.get("start")
        new_value = format(values[name], ".17g")
        value_node.set("start", new_value)
        changed += old_value != new_value
        if scalar.attrib.get("classType") in {"rAlg", "rAlgConst"}:
            matched_nonlinear_candidates += 1

    if changed < 400:
        raise SystemExit(
            f"warm-start coverage unexpectedly low: matched={matched}, changed={changed}"
        )

    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    print(
        f"warm-start XML written: matched={matched}, changed={changed}, "
        f"algebraic_candidates={matched_nonlinear_candidates}"
    )


if __name__ == "__main__":
    main()
