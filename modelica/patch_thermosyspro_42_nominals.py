#!/usr/bin/env python3
"""Apply OpenModelica compatibility fixes to ThermoSysPro 4.2.

This is an OpenModelica initialization compatibility patch. It changes no
connector topology. Absolute pressure is bounded just above the IF97
triple-point limit so bounded nonlinear solvers do not evaluate water-property
functions outside their documented domain.
The optional integrator patch prevents permanent-mode controller states found
by the steady initialization problem from being overwritten by the initial
``when not reset`` event immediately after the solve.
"""

from __future__ import annotations

import argparse
from pathlib import Path


REPLACEMENTS = {
    'type AbsolutePressure = Pressure(min = 0.0, nominal = 1e5);':
        'type AbsolutePressure = Pressure(min = 0.0, nominal = 1e5);',
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
    parser.add_argument("--if97-packages", type=Path)
    parser.add_argument("--integrator", type=Path)
    parser.add_argument("--dynamic-drum", type=Path)
    parser.add_argument("--stodola-turbine", type=Path)
    parser.add_argument("--fluid-ph", type=Path)
    parser.add_argument("--two-phase-pipe", type=Path)
    args = parser.parse_args()

    text = args.units_mo.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS.items():
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"expected one exact match, got {count}: {old}")
        text = text.replace(old, new)
    args.units_mo.write_text(text, encoding="utf-8")
    print(f"patched {len(REPLACEMENTS)} SI type attributes in {args.units_mo}")

    if args.if97_packages is not None:
        if97_text = args.if97_packages.read_text(encoding="utf-8")
        old = 'assert(false, "Water_Ph: Incorrect region number (" + String(region) + ")");'
        new = (
            'assert(false, "Water_Ph: Incorrect region number (" + '
            'String(region) + ") for p=" + String(p) + " Pa, h=" + '
            'String(h) + " J/kg");'
        )
        count = if97_text.count(old)
        if count != 1:
            raise SystemExit(f"expected one Water_Ph diagnostic match, got {count}")
        args.if97_packages.write_text(
            if97_text.replace(old, new), encoding="utf-8"
        )
        print(f"expanded Water_Ph diagnostics in {args.if97_packages}")

    if args.integrator is not None:
        integrator_text = args.integrator.read_text(encoding="utf-8")
        old = """  when not (reset.signal) then
    x0 = ureset.signal/k;
    reinit(x, x0);
  end when;"""
        new = """  when not (reset.signal) then
    // Preserve the original event/reinit equation structure. In permanent
    // mode, x was already determined by the steady initialization equations,
    // so reinitialize it to itself instead of overwriting it with ureset/k.
    x0 = if permanent then x else ureset.signal/k;
    reinit(x, x0);
  end when;"""
        count = integrator_text.count(old)
        if count != 1:
            raise SystemExit(
                f"expected one permanent-integrator event match, got {count}"
            )
        args.integrator.write_text(
            integrator_text.replace(old, new), encoding="utf-8"
        )
        print(f"preserved permanent controller initialization in {args.integrator}")

    if args.dynamic_drum is not None:
        drum_text = args.dynamic_drum.read_text(encoding="utf-8")
        parameter_anchor = (
            '  parameter Units.SI.AbsolutePressure P0 = 50.e5 '
            '"Fluid initial pressure (active if steady_state=false)";'
        )
        parameter_replacement = parameter_anchor + """
  parameter Boolean use_start_enthalpies = false
    "Use hl0/hv0 rather than saturation values when steady_state=false";
  parameter Units.SI.SpecificEnthalpy hl0 = 1.e5
    "Initial liquid enthalpy when use_start_enthalpies=true";
  parameter Units.SI.SpecificEnthalpy hv0 = 2.5e6
    "Initial vapor enthalpy when use_start_enthalpies=true";"""
        initial_anchor = """    hl = lsat.h;
    hv = vsat.h;"""
        initial_replacement = """    hl = if use_start_enthalpies then hl0 else lsat.h;
    hv = if use_start_enthalpies then hv0 else vsat.h;"""
        if drum_text.count(parameter_anchor) != 1:
            raise SystemExit("expected one DynamicDrum P0 parameter anchor")
        if drum_text.count(initial_anchor) != 1:
            raise SystemExit("expected one DynamicDrum enthalpy initialization anchor")
        drum_text = drum_text.replace(parameter_anchor, parameter_replacement)
        drum_text = drum_text.replace(initial_anchor, initial_replacement)
        args.dynamic_drum.write_text(drum_text, encoding="utf-8")
        print(f"enabled explicit DynamicDrum enthalpy starts in {args.dynamic_drum}")

    if args.stodola_turbine is not None:
        turbine_text = args.stodola_turbine.read_text(encoding="utf-8")
        anchor = '  parameter Integer mode_ps = 0 "IF97 region after isentropic expansion. 1:liquid - 2:steam - 4:saturation line - 0:automatic";'
        replacement = anchor + """
  parameter Units.SI.SpecificEnthalpy h_property_min = 1.e5
    "Lower evaluation guard used only during nonlinear iterations";"""
        pros1_old = "  pros1 = ThermoSysPro.Properties.Fluid.Ph(Ps, Hrs, mode_s, fluid);"
        pros1_new = "  pros1 = ThermoSysPro.Properties.Fluid.Ph(Ps, max(Hrs, h_property_min), mode_s, fluid);"
        pros_old = "  pros = ThermoSysPro.Properties.Fluid.Ph(Ps, Cs.h, mode_s, fluid);"
        pros_new = "  pros = ThermoSysPro.Properties.Fluid.Ph(Ps, max(Cs.h, h_property_min), mode_s, fluid);"
        for old in (anchor, pros1_old, pros_old):
            if turbine_text.count(old) != 1:
                raise SystemExit(f"expected one StodolaTurbine anchor, got {turbine_text.count(old)}: {old}")
        turbine_text = turbine_text.replace(anchor, replacement)
        turbine_text = turbine_text.replace(pros1_old, pros1_new)
        turbine_text = turbine_text.replace(pros_old, pros_new)
        args.stodola_turbine.write_text(turbine_text, encoding="utf-8")
        print(f"guarded StodolaTurbine property iterations in {args.stodola_turbine}")

    if args.fluid_ph is not None:
        fluid_ph_text = args.fluid_ph.read_text(encoding="utf-8")
        old = "    pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(P, h, mode);"
        new = """    // Keep trial points from an unconstrained Newton/homotopy iteration
    // inside IF97's domain. Physical converged solutions above these guards
    // evaluate the exact original property function.
    pro := ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(
      max(P, 612), max(h, 1.e5), mode);"""
        if fluid_ph_text.count(old) != 1:
            raise SystemExit(
                f"expected one generic Fluid.Ph water call, got {fluid_ph_text.count(old)}"
            )
        args.fluid_ph.write_text(
            fluid_ph_text.replace(old, new), encoding="utf-8"
        )
        print(f"guarded generic water property iterations in {args.fluid_ph}")

    if args.two_phase_pipe is not None:
        pipe_text = args.two_phase_pipe.read_text(encoding="utf-8")
        inlet_old = "  proc[1] = ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(P[1], h[1]);"
        inlet_new = """  proc[1] = ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(
    max(P[1], 612), if h[1] > 1.e5 then h[1] else h[2]);"""
        outlet_old = "  proc[2] = ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(P[N + 1], h[N + 1]);"
        outlet_new = """  proc[2] = ThermoSysPro.Properties.WaterSteam.IF97.Water_Ph(
    max(P[N + 1], 612),
    if h[N + 1] > 1.e5 then h[N + 1] else h[N]);"""
        boiling_old = "    heb[i] = noEvent(if (Pb[i] > 1) then 55*(abs(Pb[i])/pcrit)^0.12*(-Modelica.Math.log10(abs(Pb[i])/pcrit))^(-0.55)*Mmol^(-0.5)*(abs(dW1[i])/dSi)^0.67 else 100);"
        boiling_new = "    heb[i] = noEvent(if (Pb[i] > 1) then 55*(abs(Pb[i])/pcrit)^0.12*(-Modelica.Math.log10(abs(Pb[i])/pcrit))^(-0.55)*Mmol^(-0.5)*(max(abs(dW1[i]), 1)/dSi)^0.67 else 100);"
        sat_thermal_old = "    (lsat1[i], vsat1[i]) = ThermoSysPro.Properties.WaterSteam.IF97.Water_sat_P(P[i + 1]);"
        sat_thermal_new = "    (lsat1[i], vsat1[i]) = ThermoSysPro.Properties.WaterSteam.IF97.Water_sat_P(max(min(P[i + 1], pcrit - 1), ptriple));"
        sat_hydraulic_old = "    (lsat2[i], vsat2[i]) = ThermoSysPro.Properties.WaterSteam.IF97.Water_sat_P((P[i] + P[i + 1])/2);"
        sat_hydraulic_new = "    (lsat2[i], vsat2[i]) = ThermoSysPro.Properties.WaterSteam.IF97.Water_sat_P(max(min((P[i] + P[i + 1])/2, pcrit - 1), ptriple));"
        for old in (inlet_old, outlet_old, boiling_old,
                    sat_thermal_old, sat_hydraulic_old):
            if pipe_text.count(old) != 1:
                raise SystemExit(
                    f"expected one DynamicTwoPhaseFlowPipe boundary call, got {pipe_text.count(old)}"
                )
        pipe_text = pipe_text.replace(inlet_old, inlet_new)
        pipe_text = pipe_text.replace(outlet_old, outlet_new)
        pipe_text = pipe_text.replace(boiling_old, boiling_new)
        pipe_text = pipe_text.replace(sat_thermal_old, sat_thermal_new)
        pipe_text = pipe_text.replace(sat_hydraulic_old, sat_hydraulic_new)
        args.two_phase_pipe.write_text(pipe_text, encoding="utf-8")
        print(f"guarded two-phase pipe boundary properties in {args.two_phase_pipe}")


if __name__ == "__main__":
    main()
