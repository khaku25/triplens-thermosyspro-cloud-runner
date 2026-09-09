#!/usr/bin/env python3
"""Generate the Modelica VPP alarm runtime from versioned CSV logic.

The generated Modelica model owns threshold, hysteresis, pickup-delay and
common Trip decisions.  Downstream CSV export is intentionally limited to
serializing the resulting Boolean state transitions.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_RULE_FIELDS = {
    "logic_version",
    "rule_id",
    "enabled",
    "system",
    "logic_kind",
    "source_signal",
    "logic_signal",
    "active_when",
    "alarm_tag",
    "direction",
    "threshold_mode",
    "threshold_value",
    "hysteresis_value",
    "delay_s",
    "status",
}


@dataclass(frozen=True)
class Rule:
    order: int
    logic_version: str
    rule_id: str
    identifier: str
    system: str
    kind: str
    source_signal: str
    logic_signal: str
    active_when: bool
    direction: str
    threshold: float
    threshold_text: str
    hysteresis: float
    hysteresis_text: str
    delay: float
    delay_text: str
    status: str


@dataclass(frozen=True)
class Binding:
    source_signal: str
    input_type: str
    expression: str
    unit: str


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def identifier(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not result or result[0].isdigit():
        result = "r_" + result
    return result


def finite_number(value: str, *, label: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def parse_enabled(value: str, *, label: str) -> bool:
    normalized = value.strip().upper()
    if normalized in {"1", "TRUE", "YES"}:
        return True
    if normalized in {"0", "FALSE", "NO"}:
        return False
    raise ValueError(f"{label} must be 0/1 or false/true")


def load_rules(path: Path) -> list[Rule]:
    fields, rows = read_csv(path)
    missing = REQUIRED_RULE_FIELDS.difference(fields)
    if missing:
        raise ValueError("VPP logic CSV is missing: " + ", ".join(sorted(missing)))

    rules: list[Rule] = []
    seen_ids: set[str] = set()
    seen_identifiers: set[str] = set()
    versions: set[str] = set()
    for order, row in enumerate(rows):
        row_number = order + 2
        if not parse_enabled(row["enabled"], label=f"row {row_number} enabled"):
            continue
        rule_id = row["rule_id"].strip()
        safe = identifier(rule_id)
        if not rule_id or rule_id in seen_ids:
            raise ValueError(f"row {row_number} has an empty or duplicate rule_id")
        if safe in seen_identifiers:
            raise ValueError(f"{rule_id}: Modelica identifier collision")
        seen_ids.add(rule_id)
        seen_identifiers.add(safe)

        version = row["logic_version"].strip()
        if not version:
            raise ValueError(f"{rule_id}: logic_version is required")
        versions.add(version)
        system = row["system"].strip().upper()
        kind = row["logic_kind"].strip().upper()
        direction = row["direction"].strip().upper()
        mode = row["threshold_mode"].strip().upper()
        status = row["status"].strip()
        if system not in {"DCS1", "DCS2"}:
            raise ValueError(f"{rule_id}: system must be DCS1 or DCS2")
        if kind not in {"ANALOG", "BOOLEAN", "STATE"}:
            raise ValueError(f"{rule_id}: unsupported logic_kind {kind}")
        if direction not in {"HIGH", "LOW"}:
            raise ValueError(f"{rule_id}: direction must be HIGH or LOW")
        if kind == "ANALOG" and mode != "ABSOLUTE":
            raise ValueError(f"{rule_id}: ANALOG rules require ABSOLUTE mode")
        if kind == "BOOLEAN" and mode != "BOOLEAN":
            raise ValueError(f"{rule_id}: BOOLEAN rules require BOOLEAN mode")
        if kind == "STATE" and mode != "STATE":
            raise ValueError(f"{rule_id}: STATE rules require STATE mode")
        if not status:
            raise ValueError(f"{rule_id}: status is required")

        threshold_text = row["threshold_value"].strip()
        hysteresis_text = row["hysteresis_value"].strip()
        delay_text = row["delay_s"].strip()
        threshold = finite_number(threshold_text, label=f"{rule_id} threshold")
        hysteresis = finite_number(hysteresis_text, label=f"{rule_id} hysteresis")
        delay = finite_number(delay_text, label=f"{rule_id} delay")
        if hysteresis < 0 or delay < 0:
            raise ValueError(f"{rule_id}: hysteresis and delay must be non-negative")
        active_when = parse_enabled(
            row["active_when"], label=f"{rule_id} active_when"
        )
        source_signal = row["source_signal"].strip()
        if not source_signal:
            raise ValueError(f"{rule_id}: source_signal is required")
        rules.append(
            Rule(
                order=order,
                logic_version=version,
                rule_id=rule_id,
                identifier=safe,
                system=system,
                kind=kind,
                source_signal=source_signal,
                logic_signal=row["logic_signal"].strip(),
                active_when=active_when,
                direction=direction,
                threshold=threshold,
                threshold_text=threshold_text,
                hysteresis=hysteresis,
                hysteresis_text=hysteresis_text,
                delay=delay,
                delay_text=delay_text,
                status=status,
            )
        )
    if not rules:
        raise ValueError("VPP logic CSV has no enabled rules")
    if len(versions) != 1:
        raise ValueError("all enabled VPP rules must use one logic_version")
    return rules


def load_bindings(path: Path) -> list[Binding]:
    fields, rows = read_csv(path)
    required = {"source_signal", "input_type", "pump_model_expression", "unit"}
    missing = required.difference(fields)
    if missing:
        raise ValueError("VPP binding CSV is missing: " + ", ".join(sorted(missing)))
    result: list[Binding] = []
    seen: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        source = row["source_signal"].strip()
        input_type = row["input_type"].strip().upper()
        expression = row["pump_model_expression"].strip()
        if not source or source in seen:
            raise ValueError(f"binding row {row_number} has an empty or duplicate source")
        if identifier(source) != source:
            raise ValueError(f"{source}: source_signal must be a Modelica identifier")
        if input_type not in {"REAL", "BOOLEAN"}:
            raise ValueError(f"{source}: input_type must be REAL or BOOLEAN")
        if not expression:
            raise ValueError(f"{source}: pump_model_expression is required")
        seen.add(source)
        result.append(
            Binding(
                source_signal=source,
                input_type=input_type,
                expression=expression,
                unit=row["unit"].strip(),
            )
        )
    return result


def load_timing(path: Path) -> dict[str, str]:
    fields, rows = read_csv(path)
    required = {"parameter", "value_s", "status"}
    missing = required.difference(fields)
    if missing:
        raise ValueError("VPP timing CSV is missing: " + ", ".join(sorted(missing)))
    values: dict[str, str] = {}
    for row in rows:
        name = row["parameter"].strip()
        value = row["value_s"].strip()
        number = finite_number(value, label=f"{name} timing")
        if number < 0:
            raise ValueError(f"{name}: timing must be non-negative")
        if not row["status"].strip():
            raise ValueError(f"{name}: status is required")
        if name in values:
            raise ValueError(f"duplicate timing parameter: {name}")
        values[name] = value
    expected = {
        "gt_receive_delay",
        "gt_lockout_delay",
        "gt_breaker_delay",
        "st_breaker_delay",
    }
    if set(values) != expected:
        raise ValueError(
            "VPP timing parameters must be exactly: " + ", ".join(sorted(expected))
        )
    return values


def load_trip_matrix(path: Path) -> list[dict[str, str]]:
    fields, rows = read_csv(path)
    required = {"cause_id", "source_signal", "gt_trip_request", "st_trip_request"}
    missing = required.difference(fields)
    if missing:
        raise ValueError("Trip matrix CSV is missing: " + ", ".join(sorted(missing)))
    if not rows:
        raise ValueError("Trip matrix CSV is empty")
    for row_number, row in enumerate(rows, start=2):
        for column in ("gt_trip_request", "st_trip_request"):
            if row[column].strip() not in {"0", "1"}:
                raise ValueError(f"trip matrix row {row_number} {column} must be 0 or 1")
    return rows


def modelica_number(text: str) -> str:
    number = finite_number(text, label="Modelica numeric literal")
    if number == 0:
        return "0"
    return f"{number:.15g}"


def render_modelica(
    rules: list[Rule],
    bindings: list[Binding],
    trip_matrix: list[dict[str, str]],
    timing: dict[str, str],
) -> str:
    binding_by_source = {binding.source_signal: binding for binding in bindings}
    generated_rules = [rule for rule in rules if rule.kind != "STATE"]
    for rule in generated_rules:
        binding = binding_by_source.get(rule.source_signal)
        if binding is None:
            raise ValueError(f"{rule.rule_id}: no Modelica signal binding for {rule.source_signal}")
        expected_type = "REAL" if rule.kind == "ANALOG" else "BOOLEAN"
        if binding.input_type != expected_type:
            raise ValueError(
                f"{rule.rule_id}: {rule.source_signal} must be {expected_type}"
            )

    logic_signal_map: dict[str, Rule] = {}
    for rule in generated_rules:
        if not rule.logic_signal:
            continue
        if rule.logic_signal in logic_signal_map:
            raise ValueError(f"duplicate logic_signal: {rule.logic_signal}")
        logic_signal_map[rule.logic_signal] = rule

    def matrix_expression(column: str) -> str:
        expressions: list[str] = []
        for row in trip_matrix:
            if row[column].strip() != "1":
                continue
            source = row["source_signal"].strip()
            if source in logic_signal_map:
                expression = "alarm_" + logic_signal_map[source].identifier
            elif source in binding_by_source:
                expression = source
            else:
                raise ValueError(
                    f"trip matrix source {source} has no alarm logic or direct binding"
                )
            if expression not in expressions:
                expressions.append(expression)
        return " or ".join(expressions) if expressions else "false"

    used_sources = {rule.source_signal for rule in generated_rules}
    for row in trip_matrix:
        source = row["source_signal"].strip()
        if source in binding_by_source:
            used_sources.add(source)
    ordered_bindings = [
        binding for binding in bindings if binding.source_signal in used_sources
    ]
    logic_version = generated_rules[0].logic_version

    lines = [
        "within ;",
        "package TripLens_VPPAlarmRuntime",
        '  "Generated from the versioned VPP logic CSV; do not hand-edit"',
        "",
        "  model VPPAlarmRuntime",
        f'    parameter String logicVersion = "{logic_version}";',
    ]
    for binding in ordered_bindings:
        if binding.input_type == "BOOLEAN":
            lines.append(f"    input Boolean {binding.source_signal};")
        elif binding.unit:
            lines.append(
                f'    input Real {binding.source_signal}(unit="{binding.unit}");'
            )
        else:
            lines.append(f"    input Real {binding.source_signal};")

    lines.append("")
    for rule in generated_rules:
        lines.append(f"    output Boolean alarm_{rule.identifier};")
    lines.extend(
        [
            "    output Boolean gtTripRequest;",
            "    output Boolean stTripRequest;",
            "    output Boolean gtTripLatched;",
            "    output Boolean stTripLatched;",
            "    output Boolean relay86GTTripReceived;",
            "    output Boolean relay86GTOperated;",
            "    output Boolean breaker52GTClosed;",
            "    output Boolean breaker52STClosed;",
            "    output Real gtTripElapsed(unit=\"s\");",
            "    output Real stTripElapsed(unit=\"s\");",
            "",
        ]
    )

    for rule in generated_rules:
        if rule.kind == "ANALOG":
            direction = "1" if rule.direction == "HIGH" else "-1"
            lines.extend(
                [
                    f"    TripLens_VPPLogicBlocks.AnalogAlarm analog_{rule.identifier}(",
                    f"      direction={direction},",
                    f"      setpoint={modelica_number(rule.threshold_text)},",
                    f"      hysteresis={modelica_number(rule.hysteresis_text)},",
                    f"      pickupDelay={modelica_number(rule.delay_text)});",
                ]
            )
        else:
            active_when = "true" if rule.active_when else "false"
            lines.extend(
                [
                    f"    TripLens_VPPLogicBlocks.BooleanAlarm boolean_{rule.identifier}(",
                    f"      activeWhen={active_when},",
                    f"      pickupDelay={modelica_number(rule.delay_text)});",
                ]
            )

    lines.extend(
        [
            "    TripLens_VPPLogicBlocks.GTTripSequence gtSequence(",
            f"      receiveDelay={modelica_number(timing['gt_receive_delay'])},",
            f"      lockoutDelay={modelica_number(timing['gt_lockout_delay'])},",
            f"      breakerDelay={modelica_number(timing['gt_breaker_delay'])});",
            "    TripLens_VPPLogicBlocks.STTripSequence stSequence(",
            f"      breakerDelay={modelica_number(timing['st_breaker_delay'])});",
            "",
            "  equation",
        ]
    )

    for rule in generated_rules:
        block = "analog" if rule.kind == "ANALOG" else "boolean"
        lines.append(
            f"    {block}_{rule.identifier}.u = {rule.source_signal};"
        )
        lines.append(
            f"    alarm_{rule.identifier} = {block}_{rule.identifier}.active;"
        )

    lines.extend(
        [
            "",
            "    // Layer 2 is generated directly from common_trip_matrix.csv.",
            f"    gtTripRequest = {matrix_expression('gt_trip_request')};",
            f"    stTripRequest = {matrix_expression('st_trip_request')};",
            "",
            "    gtSequence.request = gtTripRequest;",
            "    stSequence.request = stTripRequest;",
            "    gtTripLatched = gtSequence.latched;",
            "    stTripLatched = stSequence.latched;",
            "    relay86GTTripReceived = gtSequence.relayTripReceived;",
            "    relay86GTOperated = gtSequence.relay86Operated;",
            "    breaker52GTClosed = gtSequence.breakerClosed;",
            "    breaker52STClosed = stSequence.breakerClosed;",
            "    gtTripElapsed = gtSequence.elapsed;",
            "    stTripElapsed = stSequence.elapsed;",
            "  end VPPAlarmRuntime;",
            "",
            "end TripLens_VPPAlarmRuntime;",
            "",
        ]
    )
    return "\n".join(lines)


def generate(
    *,
    rules_path: Path,
    bindings_path: Path,
    trip_matrix_path: Path,
    timing_path: Path,
    output_path: Path,
) -> list[Rule]:
    rules = load_rules(rules_path)
    model = render_modelica(
        rules,
        load_bindings(bindings_path),
        load_trip_matrix(trip_matrix_path),
        load_timing(timing_path),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(model, encoding="utf-8")
    return rules


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rules",
        type=Path,
        default=ROOT / "config" / "vpp_event_logic_provisional.csv",
    )
    parser.add_argument(
        "--bindings",
        type=Path,
        default=ROOT / "config" / "vpp_modelica_signal_bindings.csv",
    )
    parser.add_argument(
        "--trip-matrix",
        type=Path,
        default=ROOT / "config" / "common_trip_matrix.csv",
    )
    parser.add_argument(
        "--timing",
        type=Path,
        default=ROOT / "config" / "vpp_trip_timing_provisional.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "TripLens_VPPAlarmRuntime.mo",
    )
    args = parser.parse_args()
    rules = generate(
        rules_path=args.rules,
        bindings_path=args.bindings,
        trip_matrix_path=args.trip_matrix,
        timing_path=args.timing,
        output_path=args.output,
    )
    generated = sum(rule.kind != "STATE" for rule in rules)
    print(f"VPP_LOGIC_MODEL_GENERATED={args.output}")
    print(f"ENABLED_EVENT_RULES={len(rules)}")
    print(f"MODELICA_ALARM_RULES={generated}")
    print(f"LOGIC_VERSION={rules[0].logic_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
