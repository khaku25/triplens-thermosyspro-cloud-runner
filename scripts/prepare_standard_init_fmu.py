#!/usr/bin/env python3
"""Prepare an OpenModelica FMU source tree for full-runtime initialization.

OpenModelica's FMI wrapper calls ``initialization(..., "fmi", ...)``.  That
special path skips the generated model's declared parameter and variable start
values.  Generated FMUs also compile with ``OMC_MINIMAL_RUNTIME``, which omits
KINSOL even though this model's native initialization selects it.  This tool
restores the normal symbolic path and links the generated model/FMI interface
against the matching full OpenModelica runtime.  It does not alter any Modelica
equation or physical value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


RUNTIME_SOURCE = Path("sources/fmi-export/fmu2_model_interface.c")
CMAKE_SOURCE = Path("sources/CMakeLists.txt")
FMI_INIT_CALL = 'initialization(comp->fmuData, comp->threadData, "fmi", "", 0.0)'
STANDARD_INIT_CALL = 'initialization(comp->fmuData, comp->threadData, "", "", 0.0)'
EXPECTED_REPLACEMENTS = 2
MINIMAL_LIBRARY_TARGET = """add_library(${FMU_NAME_HASH}
            ${FMU_RUNTIME_SOURCES}
            ${FMU_GENERATED_MODEL_SOURCES})"""
FULL_LIBRARY_TARGET = """set(FMU_INTERFACE_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/fmi-export/fmu2_model_interface.c
    ${CMAKE_CURRENT_SOURCE_DIR}/fmi-export/fmu_read_flags.c)

add_library(${FMU_NAME_HASH}
            ${FMU_GENERATED_MODEL_SOURCES}
            ${FMU_INTERFACE_SOURCES})

set(OPENMODELICA_SIMULATION_RUNTIME
    "${OPENMODELICA_RUNTIME_DIRECTORY}/libSimulationRuntimeC.so")
if(NOT EXISTS "${OPENMODELICA_SIMULATION_RUNTIME}")
  message(FATAL_ERROR "Full OpenModelica SimulationRuntimeC was not found")
endif()
target_link_options(${FMU_NAME_HASH} PRIVATE
                    "LINKER:--no-as-needed"
                    "${OPENMODELICA_SIMULATION_RUNTIME}")"""
MINIMAL_DEFINITIONS = (
    "target_compile_definitions(${FMU_NAME_HASH} PRIVATE "
    "OMC_MINIMAL_RUNTIME=1;OMC_FMI_RUNTIME=1;CMINPACK_NO_DLL${WITH_SUNDIALS})"
)
FULL_DEFINITIONS = (
    "target_compile_definitions(${FMU_NAME_HASH} PRIVATE OMC_FMI_RUNTIME=1;CMINPACK_NO_DLL)"
)


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

    cmake_source = work_dir / CMAKE_SOURCE
    if not cmake_source.is_file():
        raise ValueError(f"FMU source archive lacks {CMAKE_SOURCE}")
    cmake_original = cmake_source.read_text(encoding="utf-8")
    if cmake_original.count(MINIMAL_LIBRARY_TARGET) != 1:
        raise ValueError("FMU CMake library target does not match the pinned source")
    if cmake_original.count(MINIMAL_DEFINITIONS) != 1:
        raise ValueError("FMU CMake minimal-runtime definition does not match the pinned source")
    cmake_patched = cmake_original.replace(MINIMAL_LIBRARY_TARGET, FULL_LIBRARY_TARGET)
    cmake_patched = cmake_patched.replace(MINIMAL_DEFINITIONS, FULL_DEFINITIONS)
    cmake_source.write_text(cmake_patched, encoding="utf-8")

    result: dict[str, object] = {
        "schema_version": "1.0",
        "status": "PREPARED",
        "source_fmu_sha256": sha256(source_fmu),
        "physical_equations_changed": False,
        "runtime_source": RUNTIME_SOURCE.as_posix(),
        "runtime_change": "STANDARD_SYMBOLIC_INIT_WITH_FULL_OPENMODELICA_RUNTIME_ABI",
        "replacement_count": replacements,
        "patched_runtime_source_sha256": sha256(runtime_source),
        "patched_cmake_source_sha256": sha256(cmake_source),
        "embedded_minimal_runtime": False,
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
