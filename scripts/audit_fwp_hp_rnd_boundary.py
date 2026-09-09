#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    contract = load_json(ROOT / "config" / "fwp_hp_rnd_boundary.json")
    signal_map = load_json(ROOT / "config" / "signal_map.json")

    assert contract["equipment_id"] == "FWP-HP"
    assert contract["source_of_truth"]["native_component"] == "PompeAlimHP"
    assert contract["source_of_truth"]["physics_input"] == "fwpHpSpeedCmd"
    assert contract["source_of_truth"]["validated_rnd_main_commit"] == (
        "817b1ef463a2bf58ca317fe3d683165875ab586f"
    )
    evidence = contract["source_of_truth"]["validation_evidence"]
    assert evidence["physical_source_run_id"] == 34366779559
    assert evidence["canonical_raw_revalidation_run_id"] == 34374439526
    assert evidence["plant_model_contract_run_id"] == 34375127982
    assert evidence["normal_100_run_id"] == 34375132429
    assert evidence["fmi_contract_run_id"] == 34375441337
    assert evidence["canonical_raw_start_s"] == 300.0
    assert evidence["canonical_raw_end_s"] == 420.0
    assert evidence["canonical_raw_rows"] == 1201
    assert evidence["canonical_physics_interval_s"] == 0.1
    assert evidence["scenario_answer_label_present"] is False
    assert contract["trip_contract"]["breaker_feedback"] == "VCB-A01.CLOSED"
    assert contract["trip_contract"]["breaker_feedback_canonical"] == (
        "fwp_hp_vcb_closed"
    )
    assert {
        "VCB-A01.CLOSED",
        "ECMS.VCB-A01.CLOSED",
        "fwp_hp_vcb_closed",
    }.issubset(set(contract["trip_contract"]["breaker_feedback_aliases"]))
    assert contract["trip_contract"]["success_value"] == 0
    assert contract["normal_stop_contract"]["breaker_value"] == 1
    assert contract["normal_stop_contract"]["breaker_feedback_canonical"] == (
        "fwp_hp_vcb_closed"
    )
    assert contract["raw_contract"]["physics_interval_s"] == 0.1
    assert contract["raw_contract"]["canonical_speed"] == "fwp_hp_speed_rpm"
    assert contract["raw_contract"]["canonical_mass_flow"] == (
        "fwp_hp_mass_flow_kg_s"
    )
    assert contract["logic_contract"]["logic_step_s"] == 0.001
    assert contract["logic_contract"]["sample_count_delay_forbidden"] is True
    assert contract["raw_contract"]["scenario_answer_labels_allowed"] is False

    signals = signal_map["signals"]
    # The feature branch predates the user's canonical FWP rename, while the
    # PR merge ref contains the current main schema. Validate both views
    # without modifying signal_map.json; the merge check must take the first
    # (current canonical) branch.
    speed_entry = signals.get("fwp_hp_speed_rpm")
    flow_entry = signals.get("fwp_hp_mass_flow_kg_s")
    current_canonical_schema = speed_entry is not None and flow_entry is not None
    if speed_entry is None:
        speed_entry = signals["bfp_hp_speed_rpm"]
    if flow_entry is None:
        flow_entry = signals["bfp_hp_mass_flow_kg_s"]
    speed = speed_entry["aliases"]
    flow = flow_entry["aliases"]
    assert "PompeAlimHP.Vr" in speed
    assert "arretPomesHP.y.signal" in speed
    assert "PompeAlimHP.Q" in flow
    assert "CapteurDebitEauHP.Measure.signal" in flow
    if current_canonical_schema:
        assert "bfp_hp_speed_rpm" in speed
        assert "bfp_hp_mass_flow_kg_s" in flow
        breaker = signals["fwp_hp_vcb_closed"]["aliases"]
        assert "VCB-A01.CLOSED" in breaker
        assert "ECMS.VCB-A01.CLOSED" in breaker

    # Synthetic components from the abandoned cold-start PR must not be part
    # of the Competition RAW contract.
    forbidden_alias_fragments = (
        "driveHP.", "driveIP.", "driveLP.",
        "checkValveHP.", "checkValveIP.", "checkValveLP.",
    )
    for entry in signals.values():
        for alias in entry.get("aliases", []):
            assert not any(x in alias for x in forbidden_alias_fragments), alias

    command_path = ROOT / "config" / "ecms_command_catalog.csv"
    with command_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    hp = [r for r in rows if r["equipment_id"] == "FWP-HP"]
    by_cmd = {r["command"]: r for r in hp}
    for cmd in ("START", "STOP", "TRIP", "RESET"):
        assert cmd in by_cmd, cmd
    assert by_cmd["TRIP"]["feedback_tag"] in {
        "VCB-A01.CLOSED",
        "ECMS.VCB-A01.CLOSED",
    }
    assert by_cmd["TRIP"]["model_input"] == "FWP_HP_TRIP"
    assert by_cmd["RESET"]["model_input"] == "FWP_HP_RESET"
    assert by_cmd["START"]["model_input"] == "FWP_HP_RUN"
    assert by_cmd["STOP"]["model_input"] == "FWP_HP_RUN"

    equipment_path = ROOT / "config" / "ecms_a_equipment.csv"
    with equipment_path.open(newline="", encoding="utf-8-sig") as f:
        eq_rows = list(csv.DictReader(f))
    ids = {r["equipment_id"] for r in eq_rows}
    assert "FWP-HP" in ids
    assert "CW-PUMP" not in ids
    assert "COND-PUMP" not in ids

    print("FWP_HP_RND_BOUNDARY_AUDIT_PASS")
    print(
        "signal_schema=",
        "current_fwp_hp" if current_canonical_schema else "legacy_bfp_hp",
    )
    print("Competition boundary uses native PompeAlimHP RAW aliases only.")
    print("No MATLAB/Simulink validation code or synthetic pump/check-valve tags required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
