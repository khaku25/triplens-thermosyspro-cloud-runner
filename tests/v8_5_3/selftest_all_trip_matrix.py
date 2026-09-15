#!/usr/bin/env python3
"""Static contract test for the complete executable V8 trip matrix."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


EXPECTED = {
    "direct_gt", "gt_breaker", "direct_st",
    "hp_drum_hh", "ip_drum_hh", "lp_drum_hh",
    "hp_drum_ll", "ip_drum_ll", "lp_drum_ll",
    "hp_bfp", "ip_bfp", "lp_bfp",
}


def load(path: Path):
    spec = importlib.util.spec_from_file_location("trip_matrix_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--run-controller", type=Path, required=True)
    args = parser.parse_args()
    module = load(args.runner)
    scenarios = set(module.SCENARIOS)
    if scenarios != EXPECTED:
        raise RuntimeError(f"scenario mismatch: {sorted(scenarios ^ EXPECTED)}")
    for name in ("hp", "ip", "lp"):
        hh = module.SCENARIOS[f"{name}_drum_hh"]
        ll = module.SCENARIOS[f"{name}_drum_ll"]
        if hh["expected_domain"] != "ST" or hh["expected"]["vppSTTripLatchPublished"] != 1.0:
            raise RuntimeError(f"{name} HH must trip ST only")
        if ll["expected_domain"] != "GT+ST" or ll["expected"]["vppGTTripLatch"] != 1.0 or ll["expected"]["vppSTTripLatchPublished"] != 1.0:
            raise RuntimeError(f"{name} LL must trip GT+ST")
        if not hh.get("drum") or not ll.get("drum"):
            raise RuntimeError(f"{name} drum scenarios must use coordinated valve faults")
    runner_source = args.runner.read_text(encoding="utf-8")
    for contract in (
        "def write_inputs_atomically",
        "OPENMODELICA_RUN_NODE_ID = 10001",
        "pause_runtime=bool(spec.get(\"drum\"))",
        "--no-auto-resume",
    ):
        if contract not in runner_source:
            raise RuntimeError(f"atomic drum-fault contract missing: {contract}")
    engine = args.engine.read_text(encoding="utf-8-sig")
    for marker in ("BEGIN_SCENARIO", "BEGIN_MATRIX_SCENARIO", "MATRIX_SCENARIOS"):
        if marker not in engine:
            raise RuntimeError(f"engine scenario marker missing: {marker}")
    if "AI_EXCLUDED_HISTORIAN_SUFFIXES" not in engine:
        raise RuntimeError("internal fault-injection signals are not excluded from AI RAW")
    controller = args.run_controller.read_text(encoding="utf-8")
    for contract in ("def retry_runtime_read", "OpenModelica model-time control node"):
        if contract not in controller:
            raise RuntimeError(f"embedded OPC UA readiness retry missing: {contract}")
    for name in ("hp_bfp", "ip_bfp", "lp_bfp"):
        bfp = module.SCENARIOS[name]
        if name == "lp_bfp":
            if bfp["expected_domain"] != "GT+ST":
                raise RuntimeError(f"{name} must prove Drum LL -> GT+ST")
            if not bfp.get("cause", "").endswith("DrumLL"):
                raise RuntimeError(f"{name} must require its Drum LL matrix cause")
            if bfp.get("post_fault_model_seconds") != 100.0:
                raise RuntimeError(f"{name} must retain the 100 s reference horizon")
            if len(bfp["events"]) != 10:
                raise RuntimeError(
                    f"{name} must require ten automatic events plus operator PB "
                    f"(found {len(bfp['events'])})"
                )
        else:
            if bfp["expected_domain"] != "BFP" or bfp.get("requires_drum_trip"):
                raise RuntimeError(f"{name} must be an equipment-only BFP proof")
            if bfp.get("cause") is not None:
                raise RuntimeError(f"{name} must leave Drum LL to its 100 s scenario")
            if bfp.get("post_fault_model_seconds") != 45.0:
                raise RuntimeError(f"{name} must use the 45 s short horizon")
            if len(bfp["events"]) != 6:
                raise RuntimeError(
                    f"{name} must require six BFP physical/protection events "
                    f"(found {len(bfp['events'])})"
                )
    print(json.dumps({
        "status": "PASS", "scenario_count": len(scenarios),
        "common_trip_causes": 9, "independent_bfp_trips": 3,
        "post_fault_model_seconds": 100,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
