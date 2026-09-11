#!/usr/bin/env python3
"""Generate deterministic SVG views for every FMU-connected valve."""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROL_POINTS = ROOT / "config" / "fmu_valve_control_points_v1.csv"
PORTS = ROOT / "data" / "fmu_valve_ports_v1.csv"
OUTPUT_DIR = ROOT / "topology" / "valves"
OVERVIEW = ROOT / "topology" / "fmu_valves_overview.svg"
MANIFEST = ROOT / "topology" / "valve_svg_manifest.json"

SERVICE_EN = {
    "HP_FWCV": "HP drum feedwater control valve",
    "HP_STEAM_VLV": "HP drum steam valve",
    "IP_FWCV": "IP drum feedwater control valve",
    "IP_STEAM_VLV": "IP drum steam valve",
    "LP_STEAM_VLV": "LP drum steam control valve",
    "LP_FW_VLV": "LP drum feedwater valve",
    "LP_TO_HPIP_FW_VLV": "LP-to-HP/IP feedwater valve",
    "COND_EXTRACTION_VLV": "Condenser extraction control valve",
    "HP_TURB_ADM_VLV": "HP turbine admission valve",
    "HP_FW_ISO_VLV": "HP feedwater pump discharge valve",
    "IP_FW_ISO_VLV": "IP feedwater pump discharge valve",
    "IP_TURB_ADM_VLV": "IP turbine admission valve",
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def slug(value: str) -> str:
    return value.lower().replace("_", "-")


def short_port(port_name: str) -> str:
    return port_name.rsplit(".", 1)[-1]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def port_card(port: dict[str, str], x: int, y: int) -> str:
    name = port["port_name"]
    role = port["role"].replace("_", " ")
    direction = port["direction"]
    unit = port["unit"]
    role_label = role if len(role) <= 25 else role[:24] + "…"
    card_class = "input-card" if direction == "INPUT" else "output-card"
    return f"""
    <g class="port {card_class}" id="port-{esc(slug(name))}" data-bind="{esc(name)}" data-direction="{esc(direction)}" data-role="{esc(port['role'])}">
      <rect x="{x}" y="{y}" width="210" height="78" rx="10"/>
      <text class="role" x="{x + 14}" y="{y + 23}">{esc(role_label)}</text>
      <text class="port-name" x="{x + 14}" y="{y + 45}">{esc(short_port(name))}</text>
      <text class="value" x="{x + 196}" y="{y + 65}" text-anchor="end" data-value-for="{esc(name)}">-- {esc(unit)}</text>
    </g>"""


def detail_svg(point: dict[str, str], ports: list[dict[str, str]]) -> str:
    control_id = point["control_point_id"]
    equipment_id = point["equipment_id"]
    service = point["service_ko"]
    service_en = SERVICE_EN[control_id]
    native_object = point["native_object"]
    cards = []
    for index, port in enumerate(ports):
        row, column = divmod(index, 4)
        cards.append(port_card(port, 55 + 230 * column, 360 + 94 * row))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="700" viewBox="0 0 1000 700" role="img" aria-labelledby="title desc" data-control-point-id="{esc(control_id)}" data-equipment-id="{esc(equipment_id)}">
  <title id="title">{esc(equipment_id)} FMU valve detail</title>
  <desc id="desc">{esc(service)}의 AUTO/MAN 명령, 고장 주입, 적용 개도와 ThermoSysPro 물리 출력을 표시한다.</desc>
  <defs>
    <style>
      .bg{{fill:#f3f6f9}}.panel{{fill:#fff;stroke:#d5dfe7;stroke-width:2}}.title{{font:700 25px Arial,'Noto Sans KR',sans-serif;fill:#17324a}}.subtitle{{font:14px Arial,'Noto Sans KR',sans-serif;fill:#607585}}
      .pipe{{fill:none;stroke:#3481b8;stroke-width:8;stroke-linecap:round}}.valve{{fill:#fff;stroke:#7b43a1;stroke-width:4}}.equip{{font:700 17px Arial,'Noto Sans KR',sans-serif;fill:#263d50;text-anchor:middle}}.native{{font:12px monospace;fill:#627686;text-anchor:middle}}
      .signal{{fill:none;stroke:#d08b28;stroke-width:3;stroke-dasharray:7 5}}.signal-box{{fill:#fff8e7;stroke:#d08b28;stroke-width:2}}.signal-text{{font:700 13px Arial,sans-serif;fill:#664917;text-anchor:middle}}
      .port rect{{stroke-width:2}}.input-card rect{{fill:#fff8e7;stroke:#d08b28}}.output-card rect{{fill:#edf7f2;stroke:#34855c}}.role{{font:700 11px Arial,sans-serif;fill:#526574}}.port-name{{font:700 15px monospace;fill:#203b50}}.value{{font:13px monospace;fill:#246246}}.footer{{font:12px Arial,'Noto Sans KR',sans-serif;fill:#657986}}
    </style>
    <marker id="arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#3481b8"/></marker>
    <marker id="signal-arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#d08b28"/></marker>
  </defs>
  <rect class="bg" width="1000" height="700"/>
  <rect class="panel" x="24" y="22" width="952" height="650" rx="18"/>
  <text class="title" x="55" y="62">{esc(equipment_id)} · {esc(service_en)}</text>
  <text class="subtitle" x="55" y="88">{esc(point['system'])} · {esc(point['native_class'])}</text>

  <path class="pipe" d="M80 185 H385 M615 185 H920" marker-end="url(#arrow)"/>
  <path class="valve" d="M385 145 L500 185 L385 225 Z M615 145 L500 185 L615 225 Z"/>
  <text class="equip" x="500" y="129">{esc(control_id)}</text>
  <text class="native" x="500" y="251">{esc(native_object)}</text>
  <text class="subtitle" x="80" y="166">INLET · C1.P</text>
  <text class="subtitle" x="790" y="166">OUTLET · C2.P</text>

  <rect class="signal-box" x="72" y="275" width="135" height="48" rx="8"/><text class="signal-text" x="139" y="305">AUTO CMD</text>
  <rect class="signal-box" x="237" y="275" width="135" height="48" rx="8"/><text class="signal-text" x="304" y="305">MAN CMD</text>
  <rect class="signal-box" x="402" y="275" width="135" height="48" rx="8"/><text class="signal-text" x="469" y="305">AUTO / MAN</text>
  <rect class="signal-box" x="567" y="275" width="135" height="48" rx="8"/><text class="signal-text" x="634" y="305">FAULT GATE</text>
  <rect class="signal-box" x="732" y="275" width="190" height="48" rx="8"/><text class="signal-text" x="827" y="305">APPLIED POSITION</text>
  <path class="signal" d="M207 299 H402 M372 299 H402 M537 299 H567 M702 299 H732 M827 275 V235" marker-end="url(#signal-arrow)"/>

  {''.join(cards)}
  <text class="footer" x="55" y="655">FMU_CONNECTED · data-bind/data-value-for ready for OPC UA and web updates · virtual model visualization</text>
</svg>
"""


def overview_svg(points: list[dict[str, str]]) -> str:
    cards = []
    colors = {"HRSG": ("#edf5fb", "#397eaf"), "ST": ("#f3effa", "#7751a4"), "BOP": ("#edf7f2", "#39865f")}
    for index, point in enumerate(points):
        row, column = divmod(index, 4)
        x, y = 45 + 285 * column, 145 + 150 * row
        fill, stroke = colors.get(point["system"], ("#f5f5f5", "#777"))
        target = f"valves/{slug(point['control_point_id'])}.svg"
        cards.append(f"""
    <a href="{esc(target)}">
      <g class="card" data-view="{esc(target)}" data-control-point-id="{esc(point['control_point_id'])}">
        <rect x="{x}" y="{y}" width="255" height="118" rx="14" fill="{fill}" stroke="{stroke}"/>
        <text class="system" x="{x + 18}" y="{y + 27}">{esc(point['system'])}</text>
        <text class="equipment" x="{x + 127}" y="{y + 57}">{esc(point['equipment_id'])}</text>
        <text class="service" x="{x + 127}" y="{y + 83}">{esc(SERVICE_EN[point['control_point_id']])}</text>
        <text class="native" x="{x + 127}" y="{y + 105}">{esc(point['native_object'])}</text>
      </g>
    </a>""")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="650" viewBox="0 0 1200 650" role="img" aria-labelledby="title desc">
  <title id="title">TripLens FMU valve visualization index</title>
  <desc id="desc">ThermoSysPro 3.1 전체 모델에 FMU로 연결된 12개 밸브의 개별 SVG 진입 화면이다.</desc>
  <style>
    .bg{{fill:#f3f6f9}}.panel{{fill:#fff;stroke:#d5dfe7;stroke-width:2}}.title{{font:700 27px Arial,'Noto Sans KR',sans-serif;fill:#17324a}}.sub{{font:14px Arial,'Noto Sans KR',sans-serif;fill:#607585}}.card rect{{stroke-width:2}}.card{{cursor:pointer}}.system{{font:700 12px Arial,sans-serif;fill:#5f7180}}.equipment{{font:700 17px Arial,sans-serif;fill:#203b50;text-anchor:middle}}.service{{font:13px Arial,'Noto Sans KR',sans-serif;fill:#3e5668;text-anchor:middle}}.native{{font:10px monospace;fill:#6c7d89;text-anchor:middle}}
  </style>
  <rect class="bg" width="1200" height="650"/><rect class="panel" x="20" y="20" width="1160" height="610" rx="18"/>
  <text class="title" x="45" y="61">TripLens · FMU Valve SVG Index</text>
  <text class="sub" x="45" y="88">12/12 FMU_CONNECTED · AUTO/MAN, CMD, fault injection, FB, Cv, mass flow and pressure drop</text>
  {''.join(cards)}
  <text class="sub" x="45" y="615">ThermoSysPro 3.1 main · visualization asset · not for operation, maintenance or LOTO</text>
</svg>
"""


def generate(control_points: Path, ports_path: Path, output_dir: Path, overview: Path, manifest: Path) -> None:
    points = read_rows(control_points)
    ports = read_rows(ports_path)
    ports_by_point: dict[str, list[dict[str, str]]] = defaultdict(list)
    for port in ports:
        ports_by_point[port["control_point_id"]].append(port)

    output_dir.mkdir(parents=True, exist_ok=True)
    assets = []
    for point in points:
        control_id = point["control_point_id"]
        point_ports = ports_by_point[control_id]
        if not point_ports:
            raise ValueError(f"no FMU ports for {control_id}")
        target = output_dir / f"{slug(control_id)}.svg"
        target.write_text(detail_svg(point, point_ports), encoding="utf-8")
        assets.append({
            "control_point_id": control_id,
            "equipment_id": point["equipment_id"],
            "system": point["system"],
            "service_ko": point["service_ko"],
            "svg": target.relative_to(manifest.parent).as_posix(),
            "fmu_ports": [port["port_name"] for port in point_ports],
        })

    overview.parent.mkdir(parents=True, exist_ok=True)
    overview.write_text(overview_svg(points), encoding="utf-8")
    payload = {
        "schema_version": "1.0",
        "scope": "FMU_CONNECTED_VALVES",
        "control_point_source": control_points.relative_to(ROOT).as_posix() if control_points.is_relative_to(ROOT) else str(control_points),
        "port_source": ports_path.relative_to(ROOT).as_posix() if ports_path.is_relative_to(ROOT) else str(ports_path),
        "overview_svg": overview.relative_to(manifest.parent).as_posix(),
        "asset_count": len(assets),
        "assets": assets,
    }
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-points", type=Path, default=CONTROL_POINTS)
    parser.add_argument("--ports", type=Path, default=PORTS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--overview", type=Path, default=OVERVIEW)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    generate(args.control_points, args.ports, args.output_dir, args.overview, args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
