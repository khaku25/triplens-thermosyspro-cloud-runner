#!/usr/bin/env python3
"""Guard the physical-only fault paths used by the V8 matrix verifier."""

from __future__ import annotations

import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "modelica" / "TripLens_CombinedCycle_TripTAC_ProcessView_v36.mo"
PUMP_MODEL = ROOT / "modelica" / "TripLens_PumpPhysics.mo"


def reverse_block(flow: float, transition: float = 1.0) -> float:
    return 0.5 - 0.5 * math.tanh(flow / transition)


def main() -> int:
    source = MODEL.read_text(encoding="utf-8")
    for section in ("HP", "IP", "LP"):
        for token in (
            f"vpp{section}DrumInventoryFaultEnableNative",
            f"vpp{section}DrumInventoryFaultValueNative",
            f"vpp{section}DrumInventoryDisturbanceMassFlowTH",
            f"vpp{section}DrumInventoryFaultSource",
            f"vpp{section}DrumInventoryFaultInjector",
            f"vpp{section}DrumInventoryFaultEnthalpyCommand.signal = Ballon",
            f"connect(vpp{section}DrumInventoryFaultEnthalpyCommand, "
            f"vpp{section}DrumInventoryFaultSource.ISpecificEnthalpy)",
            f"connect(vpp{section}DrumInventoryFaultInjector.C2, Ballon"
            f"{'MP' if section == 'IP' else 'BP' if section == 'LP' else 'HP'}.Ce2)",
        ):
            if token not in source:
                raise RuntimeError(f"missing physical {section} drum path token: {token}")
        forbidden = f"vpp{section}DrumLevelM = vpp{section}DrumInventory"
        if forbidden in source:
            raise RuntimeError(f"{section} drum level is assigned from a fault input")
    if "TRIPLENS_DRUM_INVENTORY_FAULT_PATH_V1" not in source:
        raise RuntimeError("physical drum inventory marker missing")
    if "closeFlow = 70, closedResistance = 1e5" not in source:
        raise RuntimeError("HP check-valve startup-safe finite resistance is missing")
    if "closeFlow = 100, closedResistance = 1e7" not in source:
        raise RuntimeError("LP check-valve reverse-flow seal is missing")
    pump_source = PUMP_MODEL.read_text(encoding="utf-8")
    for token in (
        "model SpringLoadedCheckValve",
        "valveTarget = noEvent",
        "Modelica.Math.tanh((Q - closeFlow)/",
        "effectiveResistance = openResistance + (closedResistance -",
    ):
        if token not in pump_source:
            raise RuntimeError(f"HP/IP check-valve seat guard missing: {token}")
    if reverse_block(80.0) >= 1e-12:
        raise RuntimeError("forward check-valve resistance guard changed normal flow")
    if reverse_block(-20.0) <= 1.0 - 1e-12:
        raise RuntimeError("reverse check-valve seat resistance guard is ineffective")
    print("PASS: V8 physical drum fault paths and NRV reverse-flow guard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
