#!/usr/bin/env python3
"""Generate OPC UA-bound SVGs for all physical FWP discharge check valves."""

from __future__ import annotations

import argparse
import csv
import html
import json
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "config" / "opcua_fwp_check_valves_v1.csv"
OUTPUT = ROOT / "topology" / "opcua" / "check_valves"
MANIFEST = OUTPUT / "fwp_check_valve_svg_manifest.json"
ENDPOINT = "opc.tcp://127.0.0.1:4841"


@dataclass(frozen=True)
class CheckValveAsset:
    asset_id: str
    equipment_id: str
    title_ko: str
    pump_component: str
    check_valve_component: str
    open_node: str
    opening_node: str
    flow_node: str
    delta_p_node: str
    inlet_p_node: str
    outlet_p_node: str
    resistance_node: str
    inlet: str
    outlet: str
    svg: str

    @property
    def pressure_level(self) -> str:
        return self.asset_id.split("_")[1]

    @property
    def nodes(self) -> tuple[tuple[str, str, str], ...]:
        return (
            ("OPEN", self.open_node, "BOOL"),
            ("OPENING", self.opening_node, "pu"),
            ("MASS FLOW", self.flow_node, "t/h"),
            ("DIFFERENTIAL PRESSURE", self.delta_p_node, "Pa"),
            ("INLET PRESSURE", self.inlet_p_node, "Pa"),
            ("OUTLET PRESSURE", self.outlet_p_node, "Pa"),
            ("HYDRAULIC RESISTANCE", self.resistance_node, "Pa.s/kg"),
        )


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def load_assets() -> list[CheckValveAsset]:
    with INVENTORY.open(encoding="utf-8", newline="") as stream:
        assets = [CheckValveAsset(**row) for row in csv.DictReader(stream)]
    if {asset.pressure_level for asset in assets} != {"HP", "IP", "LP"}:
        raise ValueError("FWP check-valve inventory must contain HP, IP and LP exactly")
    if len(assets) != 3 or len({asset.asset_id for asset in assets}) != 3:
        raise ValueError("FWP check-valve inventory must contain three unique assets")
    all_nodes = [node for asset in assets for _, node, _ in asset.nodes]
    if len(set(all_nodes)) != 21:
        raise ValueError("each FWP check valve requires seven unique OPC UA nodes")
    return assets


STYLE = """
  .bg{fill:#07111f}.panel{fill:#0d1b2d;stroke:#31445d;stroke-width:2}
  .title{fill:#f4f8ff;font:700 24px Arial,sans-serif}.sub{fill:#9fb2c9;font:14px Arial,sans-serif}
  .label{fill:#eef5ff;font:700 14px Arial,sans-serif}.small{fill:#b7c7da;font:12px Arial,sans-serif}
  .mono{fill:#d9e8ff;font:11px Consolas,monospace}.muted{fill:#8397ad;font:11px Arial,sans-serif}
  .equip{fill:#14283e;stroke:#5c7998;stroke-width:2}.pump{fill:#153c52;stroke:#40c4ff;stroke-width:3}
  .nrv{fill:#173b2b;stroke:#4dd599;stroke-width:3}.water{fill:none;stroke:#4da3ff;stroke-width:6}
  .io{fill:#12283a;stroke:#4bb8d8;stroke-width:1.5}.passive{fill:#3a2e17;stroke:#ffd166;stroke-width:1.5}
  .badge{fill:#173b2b;stroke:#4dd599;stroke-width:1.5}.badgeText{fill:#87efbd;font:700 10px Arial,sans-serif}
"""

DEFS = """
  <defs><marker id="waterArrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
    <path d="M0 0L10 5L0 10Z" fill="#4da3ff"/></marker></defs>
"""


def feedback_rows(asset: CheckValveAsset) -> str:
    rows: list[str] = []
    for index, (label, node, unit) in enumerate(asset.nodes):
        col = index % 2
        row = index // 2
        x = 70 + 510 * col
        y = 405 + 72 * row
        rows.append(f'''
  <g data-opcua-access="READ_ONLY" data-opcua-browse-name="{esc(node)}">
    <rect class="io" x="{x}" y="{y}" width="470" height="58" rx="8"/>
    <text class="label" x="{x + 15}" y="{y + 22}">{label} · {unit}</text>
    <text class="mono" x="{x + 15}" y="{y + 44}">{esc(node)}</text>
  </g>''')
    return "".join(rows)


def render_asset(asset: CheckValveAsset) -> str:
    label = f"{asset.pressure_level} FWP DISCHARGE CHECK VALVE"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1160" height="760" viewBox="0 0 1160 760"
  role="img" aria-labelledby="title desc" data-protocol="OPC UA" data-endpoint="{ENDPOINT}"
  data-equipment-id="{esc(asset.equipment_id)}">
  <title id="title">{label} OPC UA physical feedback</title>
  <desc id="desc">Passive physical non-return valve after {esc(asset.pump_component)} with seven read-only solved values.</desc>
  <style>{STYLE}</style>{DEFS}
  <rect class="bg" width="1160" height="760"/><rect class="panel" x="22" y="20" width="1116" height="715" rx="18"/>
  <text class="title" x="52" y="62">{label}</text>
  <text class="sub" x="52" y="88">ThermoSysPro/OpenModelica → OPC UA → ECMS/SVG · BrowseName runtime binding</text>
  <rect class="badge" x="835" y="43" width="255" height="28" rx="14"/><text class="badgeText" x="962" y="62" text-anchor="middle">PASSIVE · PHYSICAL · READ ONLY</text>

  <rect class="equip" x="70" y="205" width="180" height="90" rx="14"/>
  <text class="label" x="160" y="240" text-anchor="middle">{esc(asset.inlet)}</text><text class="small" x="160" y="266" text-anchor="middle">{esc(asset.pump_component)}</text>
  <path class="water" d="M250 250H350" marker-end="url(#waterArrow)"/>
  <circle class="pump" cx="395" cy="250" r="44"/><path d="M373 275Q430 250 373 225Z" fill="#d9f4ff"/>
  <text class="small" x="395" y="320" text-anchor="middle">CENTRIFUGAL PUMP</text>
  <path class="water" d="M439 250H560" marker-end="url(#waterArrow)"/>
  <g data-component="{esc(asset.check_valve_component)}" data-symbol-type="SPRING_CHECK_VALVE"
    data-symbol-convention="ISO-10628-style" aria-label="Spring-loaded non-return valve">
    <polygon class="nrv" points="575,215 635,250 575,285"/>
    <line x1="635" y1="210" x2="635" y2="290" stroke="#87efbd" stroke-width="6"/>
    <polyline points="635,210 625,200 645,188 625,176 635,164" fill="none"
      stroke="#87efbd" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    <text class="small" x="610" y="320" text-anchor="middle">SPRING CHECK VALVE · NRV</text>
  </g>
  <path class="water" d="M650 250H805" marker-end="url(#waterArrow)"/>
  <rect class="equip" x="805" y="205" width="285" height="90" rx="14"/>
  <text class="label" x="947" y="240" text-anchor="middle">{esc(asset.outlet)}</text><text class="small" x="947" y="266" text-anchor="middle">protected discharge header</text>

  <rect class="passive" x="70" y="345" width="1020" height="38" rx="10"/>
  <text class="small" x="580" y="369" text-anchor="middle">No WRITE command: flap position is solved from flow, pressure and spring-equivalent dynamics</text>
  {feedback_rows(asset)}
  <text class="muted" x="70" y="703">ISO 10628-style process symbol · OpenModelica physical component · not an operating or isolation drawing</text>
  <text class="muted" x="70" y="720">Endpoint {ENDPOINT} · Value/StatusCode/SourceTimestamp/ServerTimestamp handled by the OPC UA client</text>
</svg>
'''


def render_wiring(assets: list[CheckValveAsset]) -> str:
    groups: list[str] = []
    for index, asset in enumerate(assets):
        y = 190 + 175 * index
        groups.append(f'''
  <g data-equipment-id="{esc(asset.equipment_id)}" data-opcua-open="{esc(asset.open_node)}"
    data-opcua-opening="{esc(asset.opening_node)}" data-opcua-flow="{esc(asset.flow_node)}"
    data-opcua-delta-p="{esc(asset.delta_p_node)}" data-opcua-inlet-p="{esc(asset.inlet_p_node)}"
    data-opcua-outlet-p="{esc(asset.outlet_p_node)}" data-opcua-resistance="{esc(asset.resistance_node)}">
    <rect class="equip" x="60" y="{y - 40}" width="220" height="80" rx="14"/><text class="label" x="170" y="{y - 7}" text-anchor="middle">{asset.pressure_level} FEEDWATER SOURCE</text><text class="small" x="170" y="{y + 18}" text-anchor="middle">pump suction</text>
    <path class="water" d="M280 {y}H380" marker-end="url(#waterArrow)"/>
    <circle class="pump" cx="425" cy="{y}" r="40"/><path d="M405 {y + 23}Q455 {y} 405 {y - 23}Z" fill="#d9f4ff"/>
    <text class="small" x="425" y="{y + 63}" text-anchor="middle">{esc(asset.pump_component)}</text>
    <path class="water" d="M465 {y}H590" marker-end="url(#waterArrow)"/>
    <polygon class="nrv" points="605,{y - 32} 660,{y} 605,{y + 32}"/><line x1="670" y1="{y - 38}" x2="670" y2="{y + 38}" stroke="#87efbd" stroke-width="6"/>
    <text class="small" x="637" y="{y + 62}" text-anchor="middle">DISCHARGE NRV</text>
    <path class="water" d="M675 {y}H825" marker-end="url(#waterArrow)"/>
    <rect class="equip" x="825" y="{y - 40}" width="245" height="80" rx="14"/><text class="label" x="947" y="{y - 7}" text-anchor="middle">{esc(asset.outlet)}</text><text class="small" x="947" y="{y + 18}" text-anchor="middle">forward-flow destination</text>
    <rect class="io" x="1100" y="{y - 58}" width="250" height="116" rx="10"/>
    <text class="mono" x="1115" y="{y - 30}">{esc(asset.open_node)}</text><text class="mono" x="1115" y="{y - 8}">{esc(asset.opening_node)}</text><text class="mono" x="1115" y="{y + 14}">{esc(asset.flow_node)}</text><text class="mono" x="1115" y="{y + 36}">+ pressure / dP / resistance</text>
  </g>''')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="760" viewBox="0 0 1400 760" role="img" aria-labelledby="title desc" data-protocol="OPC UA">
  <title id="title">TripLens HP IP LP feedwater-pump discharge check-valve wiring</title><desc id="desc">All physical feedwater pumps with discharge non-return valves and native OPC UA feedback.</desc>
  <style>{STYLE}</style>{DEFS}<rect class="bg" width="1400" height="760"/><rect class="panel" x="22" y="20" width="1356" height="715" rx="18"/>
  <text class="title" x="52" y="62">ALL PHYSICAL FWP DISCHARGES — CHECK VALVE WIRING</text><text class="sub" x="52" y="89">HP / IP / LP · passive physical protection · seven solved OPC UA values per valve</text>
  {''.join(groups)}
  <text class="muted" x="60" y="710">Blue: physical water path · green: spring-loaded non-return valve · all 21 application nodes are READ_ONLY</text>
</svg>
'''


def generate(check: bool = False) -> None:
    assets = load_assets()
    rendered = {ROOT / asset.svg: render_asset(asset) for asset in assets}
    rendered[OUTPUT / "fwp_discharge_check_valve_wiring.svg"] = render_wiring(assets)
    manifest = {
        "schema_version": "1.0",
        "scope": "NATIVE_OPENMODELICA_OPCUA_ALL_PHYSICAL_FWP_CHECK_VALVES",
        "endpoint_default": ENDPOINT,
        "node_locator": "BrowseName",
        "access": "READ_ONLY",
        "physical_pump_count": 3,
        "check_valve_count": 3,
        "feedback_nodes_per_valve": 7,
        "feedback_node_count": 21,
        "assets": [asdict(asset) for asset in assets],
        "wiring_svg": "fwp_discharge_check_valve_wiring.svg",
    }
    rendered[MANIFEST] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if check:
        stale = [str(path.relative_to(ROOT)) for path, content in rendered.items() if not path.is_file() or path.read_text(encoding="utf-8") != content]
        if stale:
            raise SystemExit("stale FWP check-valve SVG assets: " + ", ".join(stale))
        return
    for path, content in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print("generated 3 FWP check-valve SVGs, one wiring SVG and 21-node manifest")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generate(check=args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
