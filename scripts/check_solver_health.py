#!/usr/bin/env python3
"""Fail closed when OpenModelica build or runtime logs show numerical debt.

The checker deliberately treats warnings as findings too.  A warning is accepted
only when it matches a reviewed, stage-specific rule whose occurrence budget has
not been exhausted.  Fatal errors, solver failures, assertion failures,
division-by-zero diagnostics, and non-finite values are never allowlistable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = ROOT / "config" / "solver_health_allowlist_v1.json"
DEFAULT_OUTPUT = ROOT / "outputs" / "native-opcua" / "solver-health.json"
SCHEMA_VERSION = "TRIPLENS-SOLVER-HEALTH/1"

REQUIRED_MARKERS = {
    "runtime": (
        "The initialization finished successfully",
        "The embedded server is initialized",
    ),
}

# Ordered from most specific/severe to least specific.  A line is counted once.
FINDING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "division_by_zero",
        re.compile(r"division[- ]by[- ]zero|divide[- ]by[- ]zero|zero divisor", re.I),
    ),
    (
        "assertion_failure",
        re.compile(
            r"assertion (?:has been violated|failed)|assert(?:ion)? failed|"
            r"variable violating (?:min|max) constraint",
            re.I,
        ),
    ),
    (
        "solver_failure",
        re.compile(
            r"error solving (?:non[- ]?linear|linear) system|"
            r"(?:solving|solve).*?(?:non[- ]?linear|linear).*?"
            r"(?:fails?|failed|failure|error)|"
            r"(?:non[- ]?linear|linear) solver (?:fails?|failed)",
            re.I,
        ),
    ),
    (
        "fatal_error",
        re.compile(
            r"failed to build model|compilation process failed|fatal error|"
            r"segmentation fault|core dumped|traceback \(most recent call last\)|"
            r"(?:^|\s)error:\s",
            re.I,
        ),
    ),
    (
        "non_finite_value",
        re.compile(r"(?<![A-Za-z])(?:nan|[+-]?inf(?:inity)?)(?![A-Za-z])", re.I),
    ),
    ("warning", re.compile(r"\bwarning\b", re.I)),
)

NON_ALLOWLISTABLE = {
    "division_by_zero",
    "assertion_failure",
    "solver_failure",
    "fatal_error",
    "non_finite_value",
    "missing_input",
    "missing_success_marker",
}
MAX_EVIDENCE_PER_DISPOSITION = 100


@dataclass(frozen=True)
class AllowRule:
    rule_id: str
    stage: str
    category: str
    pattern_text: str
    pattern: re.Pattern[str]
    max_occurrences: int
    justification: str


@dataclass(frozen=True)
class Finding:
    stage: str
    path: str
    line_number: int
    category: str
    text: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_line(line: str) -> str | None:
    for category, pattern in FINDING_PATTERNS:
        if pattern.search(line):
            return category
    return None


def load_allowlist(path: Path) -> tuple[list[AllowRule], dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError("solver-health allowlist schema_version must be 1")
    rules: list[AllowRule] = []
    seen: set[str] = set()
    for row in raw.get("rules", []):
        rule_id = str(row.get("id", "")).strip()
        stage = str(row.get("stage", "")).strip()
        category = str(row.get("category", "")).strip()
        pattern_text = str(row.get("pattern", ""))
        justification = str(row.get("justification", "")).strip()
        max_occurrences = row.get("max_occurrences")
        if not rule_id or rule_id in seen:
            raise ValueError(f"missing or duplicate allowlist rule id: {rule_id!r}")
        if stage not in {"build", "runtime"}:
            raise ValueError(f"{rule_id}: stage must be build or runtime")
        if category in NON_ALLOWLISTABLE:
            raise ValueError(f"{rule_id}: category {category} cannot be allowlisted")
        if category != "warning":
            raise ValueError(f"{rule_id}: only non-critical warnings may be allowlisted")
        if not isinstance(max_occurrences, int) or not (1 <= max_occurrences <= 500):
            raise ValueError(f"{rule_id}: max_occurrences must be between 1 and 500")
        if len(justification) < 30:
            raise ValueError(f"{rule_id}: justification is too short")
        try:
            compiled = re.compile(pattern_text)
        except re.error as exc:
            raise ValueError(f"{rule_id}: invalid regular expression: {exc}") from exc
        rules.append(
            AllowRule(
                rule_id=rule_id,
                stage=stage,
                category=category,
                pattern_text=pattern_text,
                pattern=compiled,
                max_occurrences=max_occurrences,
                justification=justification,
            )
        )
        seen.add(rule_id)
    return rules, raw


def scan_log(stage: str, path: Path) -> tuple[dict[str, Any], list[Finding]]:
    display_path = str(path)
    if not path.is_file():
        metadata = {
            "stage": stage,
            "path": display_path,
            "exists": False,
            "sha256": None,
            "line_count": 0,
            "required_markers": list(REQUIRED_MARKERS.get(stage, ())),
            "observed_markers": [],
        }
        return metadata, [Finding(stage, display_path, 0, "missing_input", "log file is missing")]

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    findings: list[Finding] = []
    for line_number, line in enumerate(lines, start=1):
        category = classify_line(line)
        if category is not None:
            findings.append(
                Finding(stage, display_path, line_number, category, line.strip())
            )

    required = REQUIRED_MARKERS.get(stage, ())
    observed = [marker for marker in required if marker in text]
    for marker in required:
        if marker not in text:
            findings.append(
                Finding(
                    stage,
                    display_path,
                    0,
                    "missing_success_marker",
                    f"required marker not found: {marker}",
                )
            )

    metadata = {
        "stage": stage,
        "path": display_path,
        "exists": True,
        "sha256": _sha256(path),
        "line_count": len(lines),
        "required_markers": list(required),
        "observed_markers": observed,
    }
    return metadata, findings


def _finding_dict(finding: Finding, **extra: Any) -> dict[str, Any]:
    result = {
        "stage": finding.stage,
        "path": finding.path,
        "line_number": finding.line_number,
        "category": finding.category,
        "text": finding.text,
    }
    result.update(extra)
    return result


def evaluate(
    build_logs: Iterable[Path],
    runtime_logs: Iterable[Path],
    allowlist_path: Path,
) -> dict[str, Any]:
    rules, allowlist_raw = load_allowlist(allowlist_path)
    inputs: list[dict[str, Any]] = []
    findings: list[Finding] = []
    for stage, paths in (("build", build_logs), ("runtime", runtime_logs)):
        for path in paths:
            metadata, found = scan_log(stage, path)
            inputs.append(metadata)
            findings.extend(found)

    rule_counts: Counter[str] = Counter()
    allowed: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    for finding in findings:
        if finding.category in NON_ALLOWLISTABLE:
            unexpected.append(_finding_dict(finding, reason="critical_category"))
            continue

        matching = [
            rule
            for rule in rules
            if rule.stage == finding.stage
            and rule.category == finding.category
            and rule.pattern.search(finding.text)
        ]
        if len(matching) > 1:
            unexpected.append(
                _finding_dict(finding, reason="ambiguous_allowlist_match")
            )
            continue
        if not matching:
            unexpected.append(_finding_dict(finding, reason="not_allowlisted"))
            continue
        rule = matching[0]
        rule_counts[rule.rule_id] += 1
        if rule_counts[rule.rule_id] > rule.max_occurrences:
            unexpected.append(
                _finding_dict(
                    finding,
                    reason="allowlist_budget_exceeded",
                    allowlist_rule_id=rule.rule_id,
                )
            )
            continue
        allowed.append(_finding_dict(finding, allowlist_rule_id=rule.rule_id))

    finding_counts = Counter(finding.category for finding in findings)
    unexpected_counts = Counter(row["category"] for row in unexpected)
    rule_report = []
    for rule in rules:
        count = rule_counts[rule.rule_id]
        rule_report.append(
            {
                "id": rule.rule_id,
                "stage": rule.stage,
                "category": rule.category,
                "max_occurrences": rule.max_occurrences,
                "observed_occurrences": count,
                "budget_exceeded": count > rule.max_occurrences,
                "justification": rule.justification,
            }
        )

    return {
        "schema": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not unexpected else "FAIL",
        "policy": {
            "fail_closed": True,
            "critical_categories_never_allowlistable": sorted(NON_ALLOWLISTABLE),
            "allowlist_path": str(allowlist_path),
            "allowlist_sha256": _sha256(allowlist_path),
            "allowlist_description": allowlist_raw.get("description", ""),
        },
        "inputs": inputs,
        "summary": {
            "finding_count": len(findings),
            "allowlisted_count": len(allowed),
            "unexpected_count": len(unexpected),
            "finding_counts_by_category": dict(sorted(finding_counts.items())),
            "unexpected_counts_by_category": dict(sorted(unexpected_counts.items())),
        },
        "allowlist_rules": rule_report,
        "allowlisted_evidence": allowed[:MAX_EVIDENCE_PER_DISPOSITION],
        "unexpected_evidence": unexpected[:MAX_EVIDENCE_PER_DISPOSITION],
        "evidence_truncated": {
            "allowlisted": max(0, len(allowed) - MAX_EVIDENCE_PER_DISPOSITION),
            "unexpected": max(0, len(unexpected) - MAX_EVIDENCE_PER_DISPOSITION),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-log", action="append", type=Path, required=True)
    parser.add_argument("--runtime-log", action="append", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = evaluate(args.build_log, args.runtime_log, args.allowlist)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"SOLVER_HEALTH_CONFIGURATION_ERROR: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = report["summary"]
    print(
        f"SOLVER_HEALTH_{report['status']} "
        f"findings={summary['finding_count']} "
        f"allowlisted={summary['allowlisted_count']} "
        f"unexpected={summary['unexpected_count']} "
        f"report={args.output}"
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
