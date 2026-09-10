#!/usr/bin/env python3
"""Prepare an OpenModelica FMU source tree for normal symbolic initialization.

OpenModelica's FMI wrapper calls ``initialization(..., "fmi", ...)``.  That
special path skips the generated model's declared parameter and variable start
values.  The same model initializes successfully in the native simulator,
which calls the normal symbolic path.  This tool applies only that runtime
bridge change; it does not alter any Modelica equation or physical value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


RUNTIME_SOURCE = Path("sources/fmi-export/fmu2_model_interface.c")
FMI_INIT_CALL = 'initialization(comp->fmuData, comp->threadData, "fmi", "", 0.0)'
STANDARD_INIT_CALL = 'initialization(comp->fmuData, comp->threadData, "", "", 0.0)'
EXPECTED_REPLACEMENTS = 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"unsafe FMU archive member: {member.filename}")
    archive.extractall(destination)


def prepare(source_fmu: Path, work_dir: Path, manifest: Path) -> dict[str, object]:
    if not source_fmu.is_file():
        raise ValueError(f"source FMU does not exist: {source_fmu}")
    if work_dir.exists():
        raise ValueError(f"work directory must not already exist: {work_dir}")
    work_dir.mkdir(parents=True)
    with zipfile.ZipFile(source_fmu) as archive:
        safe_extract(archive, work_dir)

    runtime_source = work_dir / RUNTIME_SOURCE
    if not runtime_source.is_file():
        raise ValueError(f"FMU source archive lacks {RUNTIME_SOURCE}")
    original = runtime_source.read_text(encoding="utf-8")
    replacements = original.count(FMI_INIT_CALL)
    if replacements != EXPECTED_REPLACEMENTS:
        raise ValueError(
            f"expected {EXPECTED_REPLACEMENTS} FMI initialization calls, found {replacements}"
        )
    patched = original.replace(FMI_INIT_CALL, STANDARD_INIT_CALL)
    runtime_source.write_text(patched, encoding="utf-8")

    result: dict[str, object] = {
        "schema_version": "1.0",
        "status": "PREPARED",
        "source_fmu_sha256": sha256(source_fmu),
        "physical_equations_changed": False,
        "runtime_source": RUNTIME_SOURCE.as_posix(),
        "runtime_change": "FMI_SPECIAL_INIT_TO_STANDARD_SYMBOLIC_INIT",
        "replacement_count": replacements,
        "patched_runtime_source_sha256": sha256(runtime_source),
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-fmu", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.source_fmu, args.work_dir, args.manifest)
    print(
        "STANDARD_INIT_FMU_PREPARED "
        f"source_sha256={result['source_fmu_sha256']} "
        f"replacements={result['replacement_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
