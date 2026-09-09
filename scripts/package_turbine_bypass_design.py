#!/usr/bin/env python3
"""Package the patched TripTAC model and its traceable final SVG circuit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from patch_turbine_bypass_model import MARKER, patch_model


ROOT = Path(__file__).resolve().parents[1]
THERMOSYSPRO_COMMIT = "db81ae1b5a6a85f6c6c7693244cafa6087e18ff5"
REQUIRED_CONNECTION_FIELDS = {
    "connection_id",
    "domain",
    "route",
    "source_component",
    "destination_component",
    "medium",
    "modelica_evidence",
    "diagram_required",
    "status",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_modelica(text: str) -> str:
    return re.sub(r"\s+", "", text)


def load_connections(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_CONNECTION_FIELDS.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "connection register is missing: " + ", ".join(sorted(missing))
            )
        rows = list(reader)
    if not rows:
        raise ValueError("connection register is empty")
    identifiers = [row["connection_id"].strip() for row in rows]
    if any(not identifier for identifier in identifiers):
        raise ValueError("connection register has an empty connection_id")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("connection register has duplicate connection_id values")
    for row in rows:
        if row["diagram_required"].strip() not in {"0", "1"}:
            raise ValueError(
                f'{row["connection_id"]}: diagram_required must be 0 or 1'
            )
        if not row["modelica_evidence"].strip():
            raise ValueError(f'{row["connection_id"]}: modelica_evidence is required')
        if not row["status"].strip():
            raise ValueError(f'{row["connection_id"]}: status is required')
    return rows


def validate_model_and_svg(
    patched_model: str,
    svg: str,
    connections: list[dict[str, str]],
) -> None:
    compact_model = normalized_modelica(patched_model)
    missing_model = [
        row["connection_id"]
        for row in connections
        if normalized_modelica(row["modelica_evidence"]) not in compact_model
    ]
    if missing_model:
        raise ValueError(
            "connection register evidence is absent from patched Modelica: "
            + ", ".join(missing_model)
        )

    missing_svg: list[str] = []
    duplicate_svg: list[str] = []
    for row in connections:
        if row["diagram_required"] != "1":
            continue
        marker = f'data-connection-id="{row["connection_id"]}"'
        count = svg.count(marker)
        if count == 0:
            missing_svg.append(row["connection_id"])
        elif count != 1:
            duplicate_svg.append(row["connection_id"])
    if missing_svg:
        raise ValueError("SVG is missing connection IDs: " + ", ".join(missing_svg))
    if duplicate_svg:
        raise ValueError("SVG duplicates connection IDs: " + ", ".join(duplicate_svg))

    required_svg_tokens = (
        'width="1920" height="1080" viewBox="0 0 1920 1080"',
        'font-family:"Malgun Gothic","맑은 고딕"',
        "NO SEPARATE IP BYPASS",
        "NO LP-DRUM STEAM DUMP",
        "vppHPBypassValve",
        "vppLPBypassValve",
        "vppSTTripLatch",
        "OPENMODELICA NATIVE RAW",
    )
    missing_tokens = [token for token in required_svg_tokens if token not in svg]
    if missing_tokens:
        raise ValueError("SVG is missing required content: " + ", ".join(missing_tokens))
    if "vppIPBypass" in patched_model or "vppIPBypass" in svg:
        raise ValueError("a separate IP bypass must not be present")
    if re.search(r"<(?:image|script)\b|\bhref=", svg, flags=re.IGNORECASE):
        raise ValueError("SVG must be self-contained and may not link external content")


def package_readme() -> str:
    return f"""# TripTAC turbine-bypass model package

This package contains the deterministic `{MARKER}` extension of the pinned
ThermoSysPro `CombinedCycle_TripTAC` model, its TripLens wrapper, the final
1920×1080 SVG circuit, and the exact connection register used to verify them.

Load order:

1. Load ThermoSysPro commit `{THERMOSYSPRO_COMMIT}` with Modelica 3.2.3.
2. Replace or load the packaged `CombinedCycle_TripTAC.mo` at the original
   `ThermoSysPro.Examples.CombinedCyclePowerPlant` class path.
3. Load `TripLens_CombinedCycle_TripTAC.mo` and simulate that wrapper.

Locked topology: HP main steam → HPBP → cold reheat; hot reheat → LPBP →
condenser. There is no separate IP bypass and no LP-drum steam dump. All Cv,
stroke, spray-ratio, timing, and normal-point values remain engineering
provisional and are not plant-approved operating data.
"""


def build_package(
    *,
    upstream_source: Path,
    wrapper: Path,
    topology_svg: Path,
    connection_register: Path,
    output_dir: Path,
) -> dict[str, object]:
    for label, path in (
        ("upstream source", upstream_source),
        ("TripLens wrapper", wrapper),
        ("topology SVG", topology_svg),
        ("connection register", connection_register),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"{label} is missing: {path}")

    upstream_text = upstream_source.read_text(encoding="utf-8")
    patched_text = patch_model(upstream_text)
    wrapper_text = wrapper.read_text(encoding="utf-8")
    svg_text = topology_svg.read_text(encoding="utf-8")
    connections = load_connections(connection_register)
    validate_model_and_svg(patched_text, svg_text, connections)
    if (
        "extends ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC"
        not in wrapper_text
        or "vppTripTime=tripTime" not in wrapper_text
    ):
        raise ValueError("TripLens wrapper is not bound to the patched TripTAC class")

    output_dir.mkdir(parents=True, exist_ok=True)
    patched_output = output_dir / "CombinedCycle_TripTAC.mo"
    wrapper_output = output_dir / "TripLens_CombinedCycle_TripTAC.mo"
    svg_output = output_dir / "TripTAC_Turbine_Bypass_Final.svg"
    register_output = output_dir / connection_register.name
    readme_output = output_dir / "PACKAGE_README.md"
    patched_output.write_text(patched_text, encoding="utf-8")
    wrapper_output.write_text(wrapper_text, encoding="utf-8")
    shutil.copyfile(topology_svg, svg_output)
    shutil.copyfile(connection_register, register_output)
    readme_output.write_text(package_readme(), encoding="utf-8")

    packaged_files = [
        patched_output,
        wrapper_output,
        svg_output,
        register_output,
        readme_output,
    ]
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "artifact_type": "TRIPTAC_TURBINE_BYPASS_MODEL_AND_CIRCUIT",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ENGINEERING_PROVISIONAL_NOT_PLANT_APPROVED",
        "source": {
            "repository": "Dwarf-Planet-Project/ThermoSysPro",
            "commit": THERMOSYSPRO_COMMIT,
            "class": "ThermoSysPro.Examples.CombinedCyclePowerPlant.CombinedCycle_TripTAC",
            "sha256": hashlib.sha256(upstream_text.encode("utf-8")).hexdigest(),
        },
        "model": {
            "patch_marker": MARKER,
            "topology": "HPBP_TO_COLD_REHEAT_AND_HOT_REHEAT_LPBP_TO_CONDENSER",
            "separate_ip_bypass": False,
            "lp_drum_steam_dump": False,
            "connection_count": len(connections),
            "diagram_connection_count": sum(
                row["diagram_required"] == "1" for row in connections
            ),
        },
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in packaged_files
        },
    }
    manifest_output = output_dir / "design-manifest.json"
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-source", type=Path, required=True)
    parser.add_argument("--wrapper", type=Path, required=True)
    parser.add_argument(
        "--topology-svg",
        type=Path,
        default=ROOT / "topology" / "turbine_bypass_vpp.svg",
    )
    parser.add_argument(
        "--connection-register",
        type=Path,
        default=ROOT / "config" / "turbine_bypass_connections_v1.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "build" / "turbine-bypass-design",
    )
    args = parser.parse_args()
    manifest = build_package(
        upstream_source=args.upstream_source,
        wrapper=args.wrapper,
        topology_svg=args.topology_svg,
        connection_register=args.connection_register,
        output_dir=args.output_dir,
    )
    print(
        "TURBINE_BYPASS_DESIGN_PASS "
        f'connections={manifest["model"]["connection_count"]} '
        f'patch={manifest["model"]["patch_marker"]}'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
