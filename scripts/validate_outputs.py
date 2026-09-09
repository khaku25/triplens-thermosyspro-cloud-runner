#!/usr/bin/env python3
"""Fail the workflow if generated result contracts are incomplete or inconsistent."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


REQUIRED_ARTIFACTS = {
    "thermosyspro-raw.csv",
    "processbus.csv",
    "signal-mapping-review.json",
    "ecms-trend.csv",
    "ecms-events.csv",
    "ecms-feeders.csv",
    "config/ecms_a_settings.csv",
    "config/ecms_a_equipment.csv",
    "config/ecms_command_catalog.csv",
    "config/fault_presets.json",
    "config/vpp_baseline_v1.json",
    "config/signal_map.json",
    "config/common_trip_matrix.csv",
    "config/tag_alias_contract.csv",
    "examples/bfp_trip_commands.csv",
    "data/ecms_m_links.csv",
    "data/ecms_tag_catalog.csv",
    "data/thermo_vpp_m_locked_tags.csv",
    "data/m_layer_manifest.json",
    "topology/triplens_ecms_vpp.svg",
    "topology/triplens_ecms_6p9kv.svg",
    "matlab/triplens_ecms_editor.m",
    "matlab/triplens_ecms_vpp_editor.m",
    "matlab/triplens_ecms_vpp_simulate.m",
    "matlab/run_cloud_result.m",
    "ECMSVPP.m",
    "ECMS_START.m",
    "ECMS_RUN.m",
    "ECMS_RESULT.m",
    "ECMS_DIAGNOSE.m",
    "ECMS_SELF_TEST.m",
}

CAUSAL_ARTIFACTS = {
    "GT_TRIP_RAW_DATA.csv",
    "incident-raw.csv",
    "incident-window.json",
    "important-changes.csv",
    "DCS1.csv",
    "DCS2.csv",
    "ECMS.csv",
    "config/dcs_alarm_rules.csv",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def require_columns(path: Path, required: set[str]) -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = read_csv(path)
    missing = required.difference(fields)
    if missing:
        raise ValueError(f"{path.name}: missing columns: {', '.join(sorted(missing))}")
    if len(rows) < 2:
        raise ValueError(f"{path.name}: expected at least two rows")
    return fields, rows


def finite_float(value: str, field: str, path: Path) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{path.name}: {field} is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{path.name}: {field} is not finite")
    return number


def strictly_increasing(rows: list[dict[str, str]], field: str, path: Path) -> None:
    values = [finite_float(row[field], field, path) for row in rows]
    if any(right <= left for left, right in zip(values, values[1:])):
        raise ValueError(f"{path.name}: {field} is not strictly increasing")


def nondecreasing(rows: list[dict[str, str]], field: str, path: Path) -> None:
    values = [finite_float(row[field], field, path) for row in rows]
    if any(right < left for left, right in zip(values, values[1:])):
        raise ValueError(f"{path.name}: {field} is not nondecreasing")


def derive_config_status(rows: list[dict[str, str]], label: str) -> str:
    statuses = {row["status"].strip().upper() for row in rows if row["status"].strip()}
    if not statuses:
        raise ValueError(f"{label}: no configuration status")
    if "PROVISIONAL" in statuses:
        return "PROVISIONAL"
    if len(statuses) == 1:
        return next(iter(statuses))
    return "MIXED"


def combine_config_status(settings_status: str, equipment_status: str) -> str:
    if "PROVISIONAL" in {settings_status, equipment_status}:
        return "PROVISIONAL"
    if settings_status == equipment_status:
        return settings_status
    return "MIXED"


def read_settings(path: Path) -> tuple[dict[str, str], str]:
    _, rows = require_columns(path, {"setting_id", "value", "unit", "status"})
    settings = {row["setting_id"].strip(): row["value"].strip() for row in rows}
    return settings, derive_config_status(rows, "ecms_a_settings.csv")


def verify_manifest(
    output_dir: Path,
    manifest: dict[str, object],
    additional_required: set[str] | None = None,
) -> None:
    metadata = manifest.get("files")
    if not isinstance(metadata, dict):
        raise ValueError("manifest.json: files object is missing")
    actual = {
        path.relative_to(output_dir).as_posix(): path
        for path in output_dir.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    required = REQUIRED_ARTIFACTS | (additional_required or set())
    missing_required = required.difference(actual)
    if missing_required:
        raise ValueError("output bundle is missing: " + ", ".join(sorted(missing_required)))
    if set(metadata) != set(actual):
        missing = sorted(set(actual).difference(metadata))
        stale = sorted(set(metadata).difference(actual))
        raise ValueError(
            "manifest file set mismatch"
            + (f"; unlisted: {', '.join(missing)}" if missing else "")
            + (f"; absent: {', '.join(stale)}" if stale else "")
        )
    for relative, path in actual.items():
        entry = metadata[relative]
        if not isinstance(entry, dict):
            raise ValueError(f"manifest.json: invalid metadata for {relative}")
        if entry.get("bytes") != path.stat().st_size:
            raise ValueError(f"manifest.json: byte count mismatch for {relative}")
        if entry.get("sha256") != sha256(path):
            raise ValueError(f"manifest.json: SHA-256 mismatch for {relative}")


def expected_uv_times(
    trend_rows: list[dict[str, str]],
    voltage_field: str,
    pickup_pu: float,
    delay_ms: int,
) -> list[int]:
    expected: list[int] = []
    low_start: int | None = None
    operated = False
    trend_path = Path("ecms-trend.csv")
    for row in trend_rows:
        time_ms = int(finite_float(row["source_time_ms"], "source_time_ms", trend_path))
        low = finite_float(row[voltage_field], voltage_field, trend_path) < pickup_pu
        if low:
            if low_start is None:
                low_start = time_ms
                operated = False
            if not operated and time_ms >= low_start + delay_ms:
                expected.append(low_start + delay_ms)
                operated = True
        else:
            low_start = None
            operated = False
    return expected


def validate_feeders(
    feeder_path: Path,
    feeder_rows: list[dict[str, str]],
    trend_rows: list[dict[str, str]],
    equipment_rows: list[dict[str, str]],
    m_link_rows: list[dict[str, str]],
    expected_status: str,
    power_factor: float,
) -> None:
    equipment = {row["equipment_id"].strip().upper(): row for row in equipment_rows}
    if len(equipment) != len(equipment_rows):
        raise ValueError("ecms_a_equipment.csv: duplicate equipment_id")
    expected_feeders = {row["feeder_id"].strip() for row in equipment_rows}
    if len(expected_feeders) != len(equipment_rows):
        raise ValueError("ecms_a_equipment.csv: duplicate feeder_id")
    trend_by_time = {row["source_time_ms"]: row for row in trend_rows}
    m_link_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    link_ids: list[str] = []
    for row in m_link_rows:
        if row["locked"].strip().lower() not in {"1", "true", "yes", "on"}:
            raise ValueError("ecms_m_links.csv: every M link must remain locked")
        link_ids.append(row["link_id"].strip())
        m_link_groups[row["ecms_equipment_id"].strip().upper()].append(
            (row["link_id"].strip(), row["source_m_tag_id"].strip())
        )
    if len(link_ids) != len(set(link_ids)):
        raise ValueError("ecms_m_links.csv: duplicate link_id")
    m_links: dict[str, tuple[str, str]] = {}
    for equipment_id in equipment:
        links = m_link_groups.get(equipment_id, [])
        if len(links) != 1:
            raise ValueError(f"ecms_m_links.csv: {equipment_id} must have exactly one locked M link")
        m_links[equipment_id] = links[0]
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in feeder_rows:
        grouped[row["source_time_ms"]].append(row)
        if row["source_time_ms"] not in trend_by_time:
            raise ValueError("ecms-feeders.csv: source time is absent from trend")
        equipment_id = row["equipment_id"].strip().upper()
        if equipment_id not in equipment:
            raise ValueError(f"ecms-feeders.csv: unknown equipment_id {row['equipment_id']}")
        configured = equipment[equipment_id]
        if row["feeder_id"] != configured["feeder_id"].strip():
            raise ValueError(f"ecms-feeders.csv: feeder mismatch for {row['equipment_id']}")
        if row["bus"] != configured["bus"].strip().upper():
            raise ValueError(f"ecms-feeders.csv: bus mismatch for {row['equipment_id']}")
        if row["equipment_status"] != configured["status"].strip():
            raise ValueError(f"ecms-feeders.csv: status mismatch for {row['equipment_id']}")
        if not math.isclose(
            finite_float(row["configured_voltage_kv"], "configured_voltage_kv", feeder_path),
            finite_float(configured["voltage_kv"], "voltage_kv", feeder_path),
            abs_tol=1e-9,
        ):
            raise ValueError(f"ecms-feeders.csv: configured voltage mismatch for {row['equipment_id']}")
        trend = trend_by_time[row["source_time_ms"]]
        if row["quality"] != trend["quality"] or row["a_config_status"] != expected_status:
            raise ValueError("ecms-feeders.csv: trend quality/config status was not propagated")
        suffix = "a" if row["bus"] == "BUS-A" else "b"
        expected_voltage = finite_float(trend[f"bus_{suffix}_voltage_kv"], "bus voltage", feeder_path)
        actual_voltage = finite_float(row["bus_voltage_kv"], "bus_voltage_kv", feeder_path)
        if not math.isclose(actual_voltage, expected_voltage, abs_tol=1e-9):
            raise ValueError(f"ecms-feeders.csv: bus voltage mismatch for {row['equipment_id']}")
        expected_closed = int(configured["normal_breaker_state"].strip().upper() == "CLOSED")
        if int(row["breaker_closed"]) != expected_closed:
            raise ValueError(f"ecms-feeders.csv: breaker state mismatch for {row['equipment_id']}")
        if int(row["energized"]) != int(expected_closed and expected_voltage > 0):
            raise ValueError(f"ecms-feeders.csv: energized state mismatch for {row['equipment_id']}")
        if configured["rated_kw"].strip():
            expected_current = (
                float(configured["rated_kw"]) / (math.sqrt(3.0) * expected_voltage * power_factor)
                if expected_closed and expected_voltage > 0 else 0.0
            )
            actual_current = finite_float(row["current_a"], "current_a", feeder_path)
            if not math.isclose(actual_current, expected_current, abs_tol=1e-5):
                raise ValueError(f"ecms-feeders.csv: current mismatch for {row['equipment_id']}")
        elif row["current_a"]:
            raise ValueError(f"ecms-feeders.csv: current must be blank without a rating for {row['equipment_id']}")
        expected_link = m_links.get(equipment_id, ("", ""))
        if (row["m_link_id"], row["source_m_tag_id"]) != expected_link:
            raise ValueError(f"ecms-feeders.csv: M-link mismatch for {row['equipment_id']}")
        if row["provenance"] != "A_CONFIGURED_E_DERIVED":
            raise ValueError(f"ecms-feeders.csv: invalid provenance for {row['equipment_id']}")
    if set(grouped) != set(trend_by_time):
        raise ValueError("ecms-feeders.csv: not every trend sample has feeder rows")
    for time_ms, rows in grouped.items():
        ids = {row["equipment_id"] for row in rows}
        feeders = {row["feeder_id"] for row in rows}
        if ids != set(equipment) or feeders != expected_feeders or len(rows) != len(equipment):
            raise ValueError(f"ecms-feeders.csv: incomplete or duplicate feeder snapshot at {time_ms} ms")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--trip-time", type=float, required=True)
    parser.add_argument(
        "--sampling-profile",
        choices=("standard", "causal_100ms", "incident_1ms"),
        default="standard",
    )
    args = parser.parse_args()
    process_path = args.output_dir / "processbus.csv"
    raw_path = args.output_dir / "thermosyspro-raw.csv"
    trend_path = args.output_dir / "ecms-trend.csv"
    event_path = args.output_dir / "ecms-events.csv"
    feeder_path = args.output_dir / "ecms-feeders.csv"
    manifest_path = args.output_dir / "manifest.json"
    settings_path = args.output_dir / "config/ecms_a_settings.csv"
    equipment_path = args.output_dir / "config/ecms_a_equipment.csv"
    m_links_path = args.output_dir / "data/ecms_m_links.csv"
    m_tags_path = args.output_dir / "data/thermo_vpp_m_locked_tags.csv"

    process_fields, process_rows = require_columns(process_path, {
        "scenario_id", "time_s", "gt_trip_cmd", "stg_power_w",
        "gt_exhaust_mass_flow_kg_s", "gt_exhaust_temperature_k",
    })
    trend_fields, trend_rows = require_columns(trend_path, {
        "ecms_time_ms", "source_time_ms", "quality", "a_config_status",
        "cb_52gt_closed", "stg_power_mw", "bus_a_voltage_pu", "bus_b_voltage_pu",
        "gt_main_transformer_direction", "st_main_transformer_direction",
        "grid_voltage_pu", "grid_voltage_kv", "source_parallel_allowed",
        "source_parallel_active",
    })
    event_fields, event_rows = require_columns(event_path, {
        "event_time_ms", "source_time_ms", "tag", "new_value", "event_class",
        "quality", "provenance",
    })
    feeder_fields, feeder_rows = require_columns(feeder_path, {
        "ecms_time_ms", "source_time_ms", "quality", "a_config_status",
        "equipment_id", "bus", "feeder_id", "configured_voltage_kv", "rated_kw",
        "breaker_closed", "energized", "bus_voltage_kv", "priority",
        "current_a", "equipment_status", "m_link_id", "source_m_tag_id", "provenance",
    })
    _, equipment_rows = require_columns(equipment_path, {
        "equipment_id", "bus", "feeder_id", "voltage_kv", "normal_breaker_state", "status",
    })
    _, m_link_rows = require_columns(m_links_path, {
        "link_id", "ecms_equipment_id", "source_m_tag_id", "locked",
    })
    _, m_tag_rows = require_columns(m_tags_path, {"tag_id", "tag_class", "value_basis"})
    settings, settings_status = read_settings(settings_path)
    equipment_status = derive_config_status(equipment_rows, "ecms_a_equipment.csv")
    expected_status = combine_config_status(settings_status, equipment_status)
    m_tag_ids = [row["tag_id"].strip() for row in m_tag_rows]
    if len(m_tag_ids) != len(set(m_tag_ids)):
        raise ValueError("thermo_vpp_m_locked_tags.csv: duplicate tag_id")
    if any(
        row["tag_class"].strip().upper() != "M" or row["value_basis"].strip().upper() != "M"
        for row in m_tag_rows
    ):
        raise ValueError("thermo_vpp_m_locked_tags.csv: non-M row")
    unknown_m_tags = {
        row["source_m_tag_id"].strip() for row in m_link_rows
    }.difference(m_tag_ids)
    if unknown_m_tags:
        raise ValueError("ecms_m_links.csv: unknown M-tag reference(s): " + ", ".join(sorted(unknown_m_tags)))

    if any("SST" in field.upper() for field in process_fields + trend_fields + event_fields + feeder_fields):
        raise ValueError("obsolete SST field found in generated contracts")
    if any("SST" in row["tag"].upper() for row in event_rows):
        raise ValueError("ecms-events.csv: obsolete SST event found")
    strictly_increasing(process_rows, "time_s", process_path)
    strictly_increasing(trend_rows, "source_time_ms", trend_path)
    nondecreasing(event_rows, "source_time_ms", event_path)

    for row in process_rows:
        time_s = finite_float(row["time_s"], "time_s", process_path)
        expected_trip = "1" if time_s >= args.trip_time else "0"
        if row["gt_trip_cmd"] != expected_trip:
            raise ValueError("processbus.csv: gt_trip_cmd does not match requested trip time")
    trip_events = [row for row in event_rows if row["tag"] == "GT.TRIP.CMD"]
    if len(trip_events) != 1 or trip_events[0]["new_value"] != "1":
        raise ValueError("ecms-events.csv: expected exactly one asserted GT.TRIP.CMD event")
    if int(finite_float(trip_events[0]["source_time_ms"], "source_time_ms", event_path)) != round(args.trip_time * 1000):
        raise ValueError("ecms-events.csv: GT.TRIP.CMD time does not match workflow input")

    valid_quality = {"GOOD", "BAD"}
    for path, rows in ((trend_path, trend_rows), (event_path, event_rows), (feeder_path, feeder_rows)):
        invalid = {row["quality"] for row in rows}.difference(valid_quality)
        if invalid:
            raise ValueError(f"{path.name}: invalid quality value(s): {', '.join(sorted(invalid))}")
    if any(row["a_config_status"] != expected_status for row in trend_rows):
        raise ValueError("ecms-trend.csv: a_config_status does not match A settings")

    grid_kv = finite_float(settings["GRID_VOLTAGE_KV"], "GRID_VOLTAGE_KV", settings_path)
    allow_parallel = settings["ALLOW_SOURCE_PARALLEL"].strip().lower() in {"1", "true", "yes", "on"}
    if allow_parallel:
        raise ValueError("ALLOW_SOURCE_PARALLEL=true is unsupported by the VPP synchronism model")
    for row in trend_rows:
        grid_pu = finite_float(row["grid_voltage_pu"], "grid_voltage_pu", trend_path)
        actual_grid_kv = finite_float(row["grid_voltage_kv"], "grid_voltage_kv", trend_path)
        if not math.isclose(actual_grid_kv, grid_kv * grid_pu, abs_tol=1e-6):
            raise ValueError("ecms-trend.csv: grid_voltage_kv does not follow GRID_VOLTAGE_KV")
        if row["source_parallel_allowed"] != "0" or row["source_parallel_active"] != "0":
            raise ValueError("ecms-trend.csv: source parallel must remain disabled")

    pickup_pu = finite_float(settings["UNDERVOLTAGE_PICKUP_PU"], "UNDERVOLTAGE_PICKUP_PU", settings_path)
    delay_ms = int(finite_float(settings["UNDERVOLTAGE_DELAY_MS"], "UNDERVOLTAGE_DELAY_MS", settings_path))
    for bus, voltage_field in (("BUS-A", "bus_a_voltage_pu"), ("BUS-B", "bus_b_voltage_pu")):
        expected = expected_uv_times(trend_rows, voltage_field, pickup_pu, delay_ms)
        actual = [int(row["source_time_ms"]) for row in event_rows if row["tag"] == f"{bus}.27UV.OPERATE"]
        if actual != expected:
            raise ValueError(f"ecms-events.csv: {bus} undervoltage delay contract mismatch")

    power_factor = finite_float(settings["POWER_FACTOR"], "POWER_FACTOR", settings_path)
    validate_feeders(
        feeder_path, feeder_rows, trend_rows, equipment_rows, m_link_rows,
        expected_status, power_factor,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenario = manifest.get("scenario", {})
    if float(scenario["trip_time_s"]) != args.trip_time:
        raise ValueError("manifest trip time does not match workflow input")
    sampling = manifest.get("sampling")
    if sampling is None and args.sampling_profile == "standard":
        # Preserve read compatibility with result bundles created before
        # sampling provenance was added. New bundles always include this field.
        sampling = {"profile": "standard"}
    if not isinstance(sampling, dict) or sampling.get("profile") != args.sampling_profile:
        raise ValueError("manifest sampling profile does not match workflow input")
    if args.sampling_profile == "incident_1ms":
        physics = sampling.get("physics")
        ecms_sampling = sampling.get("ecms")
        if not isinstance(physics, dict) or not isinstance(ecms_sampling, dict):
            raise ValueError("manifest incident sampling metadata is incomplete")
        physics_period_ms = finite_float(
            str(physics.get("nominal_output_period_ms")),
            "nominal_output_period_ms",
            manifest_path,
        )
        if not math.isclose(physics_period_ms, 1.0, abs_tol=1e-9):
            raise ValueError("incident_1ms must use true 1 ms ThermoSysPro CSV output intervals")
        process_times_ms = [
            round(finite_float(row["time_s"], "time_s", process_path) * 1000)
            for row in process_rows
        ]
        _, raw_rows = require_columns(raw_path, {"time"})
        raw_times_ms = [
            round(finite_float(row["time"], "time", raw_path) * 1000)
            for row in raw_rows
        ]
        if any(
            later - earlier != 1
            for earlier, later in zip(process_times_ms, process_times_ms[1:])
        ):
            raise ValueError("processbus.csv does not contain a complete 1 ms physical output grid")
        if raw_times_ms != process_times_ms:
            raise ValueError("thermosyspro-raw.csv and processbus.csv 1 ms grids do not match")
        expected_start_ms = 0
        expected_stop_ms = round(float(scenario["stop_time_s"]) * 1000)
        if process_times_ms[0] != expected_start_ms or process_times_ms[-1] != expected_stop_ms:
            raise ValueError("1 ms physical output grid does not cover the complete simulation horizon")
        window_start = int(ecms_sampling.get("incident_window_start_ms"))
        window_end = int(ecms_sampling.get("incident_window_end_ms"))
        incident_period_ms = int(ecms_sampling.get("incident_period_ms"))
        normal_period_ms = int(ecms_sampling.get("normal_period_ms"))
        if incident_period_ms != 1:
            raise ValueError("manifest incident ECMS period is not 1 ms")
        if normal_period_ms <= 0:
            raise ValueError("manifest normal ECMS period must be positive")
        trend_times = [int(row["source_time_ms"]) for row in trend_rows]
        expected_trend_times = sorted(
            set(range(expected_start_ms, expected_stop_ms + 1, normal_period_ms))
            | set(range(window_start, window_end + 1, incident_period_ms))
            | {expected_start_ms, expected_stop_ms, round(args.trip_time * 1000)}
        )
        if trend_times != expected_trend_times:
            raise ValueError("ecms-trend.csv does not match the declared multirate sampling grid")
        if "sampling_resolution" not in trend_fields:
            raise ValueError("ecms-trend.csv is missing sampling_resolution provenance")
        for row in trend_rows:
            time_ms = int(row["source_time_ms"])
            expected_label = (
                "INCIDENT_1MS" if window_start <= time_ms <= window_end
                else f"NORMAL_{normal_period_ms}MS"
            )
            if row["sampling_resolution"] != expected_label:
                raise ValueError("ecms-trend.csv sampling_resolution does not match its time grid")
    if args.sampling_profile == "causal_100ms":
        physical_times_ms = [
            round(finite_float(row["time_s"], "time_s", process_path) * 1000)
            for row in process_rows
        ]
        if any(
            later - earlier != 100
            for earlier, later in zip(physical_times_ms, physical_times_ms[1:])
        ):
            raise ValueError("causal_100ms requires a complete 100 ms ProcessBus grid")
        raw_alias = args.output_dir / "GT_TRIP_RAW_DATA.csv"
        if raw_alias.read_bytes() != process_path.read_bytes():
            raise ValueError("GT_TRIP_RAW_DATA.csv must be a lossless ProcessBus copy")

        incident_path = args.output_dir / "incident-raw.csv"
        incident_fields, incident_rows = require_columns(
            incident_path,
            {"scenario_id", "time_s", "relative_time_s", "gt_trip_cmd"},
        )
        strictly_increasing(incident_rows, "time_s", incident_path)
        incident_start = finite_float(incident_rows[0]["time_s"], "time_s", incident_path)
        incident_end = finite_float(incident_rows[-1]["time_s"], "time_s", incident_path)
        if not incident_start < args.trip_time < incident_end:
            raise ValueError("incident-raw.csv must contain both pre-trip and post-trip samples")
        if any(
            not math.isclose(
                finite_float(row["relative_time_s"], "relative_time_s", incident_path),
                finite_float(row["time_s"], "time_s", incident_path) - args.trip_time,
                abs_tol=1e-9,
            )
            for row in incident_rows
        ):
            raise ValueError("incident-raw.csv relative_time_s is inconsistent")
        source_by_time = {row["time_s"]: row for row in process_rows}
        for row in incident_rows:
            source = source_by_time.get(row["time_s"])
            if source is None:
                raise ValueError("incident-raw.csv contains a non-ProcessBus sample")
            for field in process_fields:
                if row.get(field) != source.get(field):
                    raise ValueError("incident-raw.csv altered a ProcessBus value")

        incident_metadata_path = args.output_dir / "incident-window.json"
        incident_metadata = json.loads(incident_metadata_path.read_text(encoding="utf-8"))
        if not math.isclose(
            float(incident_metadata["trip_command_time_s"]), args.trip_time, abs_tol=1e-9
        ):
            raise ValueError("incident-window.json trip command time mismatch")
        if incident_metadata.get("detection", {}).get("root_cause_inferred") is not False:
            raise ValueError("incident-window.json must not claim an inferred root cause")
        alarm_summary = incident_metadata.get("alarm_summary", {})
        if alarm_summary.get("pretrip_alarm_fabricated") is not False:
            raise ValueError("incident-window.json permits fabricated pre-trip alarms")

        changes_path = args.output_dir / "important-changes.csv"
        _, change_rows = read_csv(changes_path)
        if not change_rows:
            raise ValueError("important-changes.csv must include at least the GT trip command")
        nondecreasing(change_rows, "change_time_s", changes_path)
        command_changes = [
            row for row in change_rows
            if row.get("change_kind") == "COMMAND" and row.get("signal") == "gt_trip_cmd"
        ]
        if len(command_changes) != 1 or not math.isclose(
            float(command_changes[0]["change_time_s"]), args.trip_time, abs_tol=1e-9
        ):
            raise ValueError("important-changes.csv GT trip command is missing or mistimed")

        rules_path = args.output_dir / "config/dcs_alarm_rules.csv"
        _, rule_rows = require_columns(rules_path, {
            "rule_id", "system", "source_signal", "alarm_tag", "direction",
            "threshold_mode", "threshold_value", "status",
        })
        rules_by_tag = {row["alarm_tag"]: row for row in rule_rows}
        if len(rules_by_tag) != len(rule_rows):
            raise ValueError("dcs_alarm_rules.csv contains duplicate alarm_tag")
        dcs_required = {
            "event_sequence", "source_time_ms", "time_s", "phase", "system", "tag",
            "alarm_state", "source_signal", "value", "threshold", "quality",
            "provenance", "rule_status",
        }
        all_dcs_rows: list[dict[str, str]] = []
        for system in ("DCS1", "DCS2"):
            dcs_path = args.output_dir / f"{system}.csv"
            dcs_fields, dcs_rows = read_csv(dcs_path)
            missing = dcs_required.difference(dcs_fields)
            if missing:
                raise ValueError(f"{dcs_path.name}: missing columns: {', '.join(sorted(missing))}")
            nondecreasing(dcs_rows, "source_time_ms", dcs_path)
            for row in dcs_rows:
                if row["system"] != system:
                    raise ValueError(f"{dcs_path.name}: wrong system value")
                time_s = finite_float(row["time_s"], "time_s", dcs_path)
                if not incident_start <= time_s <= incident_end:
                    raise ValueError(f"{dcs_path.name}: event is outside incident RAW")
                rule = rules_by_tag.get(row["tag"])
                if rule is None or row["source_signal"] != rule["source_signal"]:
                    raise ValueError(f"{dcs_path.name}: event has no matching configured rule")
                if row["rule_status"] != rule["status"]:
                    raise ValueError(f"{dcs_path.name}: rule status was not propagated")
                if row["alarm_state"] == "ACTIVE":
                    value = finite_float(row["value"], "value", dcs_path)
                    threshold = finite_float(row["threshold"], "threshold", dcs_path)
                    direction = rule["direction"].strip().upper()
                    if direction == "LOW" and value > threshold + 1e-9:
                        raise ValueError(f"{dcs_path.name}: LOW alarm precedes its threshold crossing")
                    if direction == "HIGH" and value < threshold - 1e-9:
                        raise ValueError(f"{dcs_path.name}: HIGH alarm precedes its threshold crossing")
            all_dcs_rows.extend(dcs_rows)
        trip_dcs = [
            row for row in all_dcs_rows
            if row["tag"] == "GT.TRIP.CMD" and row["alarm_state"] == "ACTIVE"
        ]
        if len(trip_dcs) != 1 or int(trip_dcs[0]["source_time_ms"]) != round(args.trip_time * 1000):
            raise ValueError("DCS1.csv must contain one correctly timed GT.TRIP.CMD alarm")
        if (args.output_dir / "ECMS.csv").read_bytes() != event_path.read_bytes():
            raise ValueError("ECMS.csv must be a lossless ecms-events.csv copy")
    trend_start_ms = int(float(trend_rows[0]["source_time_ms"]))
    trend_stop_ms = int(float(trend_rows[-1]["source_time_ms"]))
    if any(
        not trend_start_ms <= int(float(row["source_time_ms"])) <= trend_stop_ms
        for row in event_rows
    ):
        raise ValueError("ecms-events.csv: event lies outside the generated trend horizon")
    command_scenario = scenario.get("command_scenario", "none")
    if command_scenario not in {"none", "bfp_trip"}:
        raise ValueError(f"manifest.json: unknown command scenario {command_scenario!r}")
    if command_scenario == "bfp_trip":
        command_path = args.output_dir / "examples/bfp_trip_commands.csv"
        command_fields, command_rows = read_csv(command_path)
        missing_command_fields = {
            "time_s", "equipment_id", "command", "command_value", "execution_layer",
        }.difference(command_fields)
        if missing_command_fields or not command_rows:
            raise ValueError(
                "bfp_trip_commands.csv: missing command fields or command rows: "
                + ", ".join(sorted(missing_command_fields))
            )
        for command in command_rows:
            command_ms = round(finite_float(command["time_s"], "time_s", command_path) * 1000)
            equipment_id = command["equipment_id"].strip().upper()
            action = command["command"].strip().upper()
            tag = f"COMMAND.{equipment_id}.{action}"
            matches = [
                row for row in event_rows
                if row["tag"] == tag and int(row["source_time_ms"]) == command_ms
                and row["provenance"] == "USER_COMMAND"
            ]
            if len(matches) != 1:
                raise ValueError(f"ecms-events.csv: executed command event is missing for {tag}")
            if equipment_id in {row["equipment_id"] for row in feeder_rows}:
                after = [
                    row for row in feeder_rows
                    if row["equipment_id"] == equipment_id
                    and int(row["source_time_ms"]) >= command_ms
                ]
                if not after:
                    raise ValueError(f"ecms-feeders.csv: no post-command rows for {equipment_id}")
                if action in {"STOP", "TRIP", "OPEN", "OUT_OF_SERVICE", "LOSS"} and any(
                    row["breaker_closed"] != "0" for row in after
                ):
                    raise ValueError(f"ecms-feeders.csv: {equipment_id} did not follow {action}")
    if scenario.get("fault_preset") == "ecms_comms_loss":
        trip_ms = round(args.trip_time * 1000)
        if not any(row["tag"] == "ECMS.COMMS.QUALITY" and row["quality"] == "BAD" for row in event_rows):
            raise ValueError("ecms-events.csv: communications-loss event did not preserve BAD quality")
        if any(row["quality"] != "BAD" for row in trend_rows if int(row["source_time_ms"]) >= trip_ms):
            raise ValueError("ecms-trend.csv: communications-loss quality is not BAD after trip")
        if any(row["quality"] != "BAD" for row in feeder_rows if int(row["source_time_ms"]) >= trip_ms):
            raise ValueError("ecms-feeders.csv: communications-loss quality is not BAD after trip")
    verify_manifest(
        args.output_dir,
        manifest,
        CAUSAL_ARTIFACTS if args.sampling_profile == "causal_100ms" else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
