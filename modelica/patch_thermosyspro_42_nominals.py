#!/usr/bin/env python3
"""Add physically scaled attributes to ThermoSysPro 4.2 SI types.

This is an OpenModelica numerical-conditioning patch only.  It changes no
equation, parameter value, or connector topology.  Absolute pressure is also
bounded just above the IF97 triple-point limit so bounded nonlinear solvers do
not evaluate the water-property functions outside their documented domain.
"""

from __future__ import annotations

import argparse
from pathlib import Path


REPLACEMENTS = {
    'type AbsolutePressure = Pressure(min = 0.0, nominal = 1e5);':
        'type AbsolutePressure = Pressure(min = 612, nominal = 1e5);',
    'type Density = Real(final quantity = "Density", final unit = "kg/m3", displayUnit = "g/cm3", min = 0.0);':
        'type Density = Real(final quantity = "Density", final unit = "kg/m3", displayUnit = "g/cm3", min = 0.0, nominal = 1000);',
    'type Power = Real(final quantity = "Power", final unit = "W");':
        'type Power = Real(final quantity = "Power", final unit = "W", nominal = 1e6);',
    'type MassFlowRate = Real(quantity = "MassFlowRate", final unit = "kg/s");':
        'type MassFlowRate = Real(quantity = "MassFlowRate", final unit = "kg/s", nominal = 100);',
    'type TemperatureDifference = Real(final quantity = "ThermodynamicTemperature", final unit = "K");':
        'type TemperatureDifference = Real(final quantity = "ThermodynamicTemperature", final unit = "K", nominal = 100);',
    'type SpecificEnergy = Real(final quantity = "SpecificEnergy", final unit = "J/kg");':
        'type SpecificEnergy = Real(final quantity = "SpecificEnergy", final unit = "J/kg", nominal = 1e6);',
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("units_mo", type=Path)
    args = parser.parse_args()

    text = args.units_mo.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS.items():
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"expected one exact match, got {count}: {old}")
        text = text.replace(old, new)
    args.units_mo.write_text(text, encoding="utf-8")
    print(f"patched {len(REPLACEMENTS)} SI type attributes in {args.units_mo}")


if __name__ == "__main__":
    main()
