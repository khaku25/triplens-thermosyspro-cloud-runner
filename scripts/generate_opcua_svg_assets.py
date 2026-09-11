#!/usr/bin/env python3
"""Generate SVG assets for the native OpenModelica OPC UA contract.

The SVGs use OPC UA BrowseNames because OpenModelica assigns model-variable
NodeIds at runtime. Only the two namespace-0 control nodes have stable numeric
NodeIds in the supported OpenModelica runtime.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "config" / "opcua_visual_assets_v1.csv"
OUTPUT = ROOT / "topology" / "opcua"
MANIFEST = OUTPUT / "opcua_svg_manifest.json"

ENDPOINT = "opc.tcp://127.0.0.1:4841"
COMMAND_NODE = "vppExternalTripCommandNative"
TRIP_LATCH_NODE = "vppSTTripLatch"
TIME_NODE_ID = "ns=0;i=10004"
STEP_NODE_ID = "ns=0;i=10000"


@dataclass(frozen=True)
class Asset:
    asset_id: str
    equipment_id: str
    system: str
    title_ko: str
    actuator_kind: str
    position_node: str
    flow_node: str
    command_source: str
    inlet: str
    outlet: str
    svg: str
    notes: str


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def load_assets() -> list[Asset]:
    with INVENTORY.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assets = [Asset(**row) for row in rows]
    if len(assets) != 7:
        raise ValueError(f"expected seven current OPC UA actuators, found {len(assets)}")
    if len({asset.asset_id for asset in assets}) != len(assets):
        raise ValueError("duplicate OPC UA visual asset_id")
    if len({asset.svg for asset in assets}) != len(assets):
        raise ValueError("duplicate OPC UA SVG path")
    return assets


STYLE = """
  .bg{fill:#07111f}.panel{fill:#0d1b2d;stroke:#31445d;stroke-width:2}
  .title{fill:#f4f8ff;font:700 25px Arial,sans-serif}.sub{fill:#9fb2c9;font:14px Arial,sans-serif}
  .label{fill:#eef5ff;font:700 15px Arial,sans-serif}.small{fill:#b7c7da;font:12px Arial,sans-serif}
  .mono{fill:#d9e8ff;font:12px Consolas,monospace}.muted{fill:#8397ad;font:11px Arial,sans-serif}
  .equip{fill:#14283e;stroke:#5c7998;stroke-width:2}.valve{fill:#153c52;stroke:#40c4ff;stroke-width:2}
  .opc{fill:#202b46;stroke:#9c7cff;stroke-width:2}.logic{fill:#2e2446;stroke:#b899ff;stroke-width:2}
  .steam{fill:none;stroke:#ff725e;stroke-width:5}.water{fill:none;stroke:#4da3ff;stroke-width:5}
  .signal{fill:none;stroke:#b899ff;stroke-width:3;stroke-dasharray:8 6}
  .io{fill:#12283a;stroke:#4bb8d8;stroke-width:1.5}.warn{fill:#ffd166;font:12px Arial,sans-serif}
  .badge{fill:#173b2b;stroke:#4dd599;stroke-width:1.5}.badgeText{fill:#87efbd;font:700 10px Arial,sans-serif}
"""


DEFS = """
  <defs>
    <marker id="steamArrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#ff725e"/></marker>
    <marker id="waterArrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#4da3ff"/></marker>
    <marker id="signalArrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0 0L9 4.5L0 9Z" fill="#b899ff"/></marker>
  </defs>
"""


def valve_symbol(kind: str) -> str:
    if kind == "SPRAY_FLOW_SOURCE":
        return """
    <circle class="valve" cx="580" cy="260" r="45"/>
    <path d="M558 238L602 282M602 238L558 282" stroke="#d9f4ff" stroke-width="5"/>
    <path class="water" d="M580 175V215" marker-end="url(#waterArrow)"/>
"""
    return """
    <polygon class="valve" points="530,225 580,260 530,295"/>
    <polygon class="valve" points="630,225 580,260 630,295"/>
    <line x1="580" y1="205" x2="580" y2="250" stroke="#40c4ff" stroke-width="4"/>
    <circle cx="580" cy="195" r="10" fill="#40c4ff"/>
"""


def render_asset(asset: Asset) -> str:
    process_class = "water" if asset.actuator_kind == "SPRAY_FLOW_SOURCE" else "steam"
    process_arrow = "waterArrow" if process_class == "water" else "steamArrow"
    honest_note = (
        "FLOW SOURCE + INJECTOR (not a native valve body)"
        if asset.actuator_kind == "SPRAY_FLOW_SOURCE"
        else "NATIVE PHYSICAL ACTUATOR"
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1160" height="720" viewBox="0 0 1160 720"
  role="img" aria-labelledby="title desc" data-protocol="OPC UA" data-endpoint="{ENDPOINT}"
  data-equipment-id="{esc(asset.equipment_id)}">
  <title id="title">{esc(asset.title_ko)} OPC UA wiring</title>
  <desc id="desc">Native OpenModelica actuator and read-only OPC UA feedback wiring.</desc>
  <style>{STYLE}</style>
  {DEFS}
  <rect class="bg" width="1160" height="720"/>
  <rect class="panel" x="22" y="20" width="1116" height="675" rx="18"/>
  <text class="title" x="52" y="62">{esc(asset.title_ko)} · {esc(asset.equipment_id)}</text>
  <text class="sub" x="52" y="88">Native OpenModelica ⇄ OPC UA ⇄ ECMS · application binding uses BrowseName</text>
  <rect class="badge" x="790" y="44" width="303" height="28" rx="14"/>
  <text class="badgeText" x="941" y="63" text-anchor="middle">{honest_note}</text>

  <rect class="equip" x="70" y="220" width="215" height="80" rx="14"/>
  <text class="label" x="177" y="250" text-anchor="middle">{esc(asset.inlet)}</text>
  <text class="small" x="177" y="276" text-anchor="middle">process inlet</text>
  <path class="{process_class}" d="M285 260H515" marker-end="url(#{process_arrow})"/>
  {valve_symbol(asset.actuator_kind)}
  <path class="{process_class}" d="M645 260H865" marker-end="url(#{process_arrow})"/>
  <rect class="equip" x="865" y="220" width="220" height="80" rx="14"/>
  <text class="label" x="975" y="250" text-anchor="middle">{esc(asset.outlet)}</text>
  <text class="small" x="975" y="276" text-anchor="middle">process outlet</text>

  <rect class="logic" x="70" y="390" width="350" height="135" rx="14"/>
  <text class="label" x="95" y="422">INTERNAL ACTUATOR LOGIC</text>
  <text class="mono" x="95" y="452" data-opcua-browse-name="{esc(asset.command_source)}">{esc(asset.command_source)}</text>
  <text class="small" x="95" y="480">source: resolved Trip latch · OPC UA READ_ONLY</text>
  <text class="small" x="95" y="505">no independent valve write node in current contract</text>
  <path class="signal" d="M420 456H580V315" marker-end="url(#signalArrow)"/>

  <rect class="opc" x="650" y="370" width="435" height="205" rx="14"/>
  <text class="label" x="675" y="404">OPC UA FEEDBACK</text>
  <rect class="io" x="675" y="425" width="385" height="52" rx="8" data-opcua-access="READ_ONLY"
    data-opcua-browse-name="{esc(asset.position_node)}"/>
  <text class="mono" x="690" y="448">BrowseName: {esc(asset.position_node)}</text>
  <text class="small" x="690" y="469">position · pu · READ_ONLY</text>
  <rect class="io" x="675" y="492" width="385" height="52" rx="8" data-opcua-access="READ_ONLY"
    data-opcua-browse-name="{esc(asset.flow_node)}"/>
  <text class="mono" x="690" y="515">BrowseName: {esc(asset.flow_node)}</text>
  <text class="small" x="690" y="536">physical flow · t/h · READ_ONLY</text>
  <path class="signal" d="M580 315V345H650V425" marker-end="url(#signalArrow)"/>

  <text class="warn" x="70" y="625">{esc(asset.notes)}</text>
  <text class="muted" x="70" y="653">Endpoint default: {ENDPOINT} · Model-variable numeric NodeIds are discovered at runtime by BrowseName.</text>
  <text class="muted" x="70" y="674">Visual contract only · not an operating, isolation, or LOTO drawing</text>
</svg>
'''


def card(asset: Asset, x: int, y: int) -> str:
    return f'''
  <g data-equipment-id="{esc(asset.equipment_id)}">
    <rect class="equip" x="{x}" y="{y}" width="275" height="95" rx="12"/>
    <text class="label" x="{x + 16}" y="{y + 27}">{esc(asset.title_ko)}</text>
    <text class="mono" x="{x + 16}" y="{y + 52}" data-opcua-browse-name="{esc(asset.position_node)}">{esc(asset.position_node)}</text>
    <text class="small" x="{x + 16}" y="{y + 76}">{esc(asset.flow_node)} · RO</text>
  </g>'''


def render_overview(assets: list[Asset]) -> str:
    cards = "\n".join(
        card(asset, 770 + 300 * (index % 2), 160 + 120 * (index // 2))
        for index, asset in enumerate(assets)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="760" viewBox="0 0 1400 760"
  role="img" aria-labelledby="title desc" data-protocol="OPC UA" data-endpoint="{ENDPOINT}">
  <title id="title">TripLens native OpenModelica OPC UA actuator overview</title>
  <desc id="desc">Complete current native OPC UA command and actuator feedback wiring.</desc>
  <style>{STYLE}</style>
  {DEFS}
  <rect class="bg" width="1400" height="760"/><rect class="panel" x="22" y="20" width="1356" height="710" rx="18"/>
  <text class="title" x="52" y="62">TripLens Native OPC UA — Actuator &amp; Wiring Overview</text>
  <text class="sub" x="52" y="89">Current validated contract: one ECMS write → native Trip logic → seven actuator feedback groups</text>

  <rect class="equip" x="55" y="160" width="215" height="95" rx="14"/>
  <text class="label" x="162" y="194" text-anchor="middle">ECMS / MATLAB</text>
  <text class="small" x="162" y="220" text-anchor="middle">52GT OPEN → derived GT Trip</text>
  <rect class="opc" x="330" y="145" width="350" height="125" rx="14" data-opcua-access="READ_WRITE"
    data-opcua-browse-name="{COMMAND_NODE}"/>
  <text class="label" x="355" y="179">OPC UA WRITE</text>
  <text class="mono" x="355" y="207">BrowseName: {COMMAND_NODE}</text>
  <text class="small" x="355" y="233">Double 0/1 · write once on rising edge</text>
  <path class="signal" d="M270 207H330" marker-end="url(#signalArrow)"/>

  <rect class="logic" x="330" y="330" width="350" height="150" rx="14"/>
  <text class="label" x="355" y="365">NATIVE OPENMODELICA LOGIC</text>
  <text class="mono" x="355" y="395" data-opcua-browse-name="{TRIP_LATCH_NODE}">{TRIP_LATCH_NODE}</text>
  <text class="small" x="355" y="422">admission CLOSE · bypass OPEN · spray ENABLE</text>
  <text class="small" x="355" y="450">feedback values are solved physical states</text>
  <path class="signal" d="M505 270V330" marker-end="url(#signalArrow)"/>

  <rect class="opc" x="55" y="340" width="215" height="125" rx="14"/>
  <text class="label" x="80" y="374">SOLVER CONTROL</text>
  <text class="mono" x="80" y="402">STEP {STEP_NODE_ID}</text>
  <text class="mono" x="80" y="428">TIME {TIME_NODE_ID}</text>
  <text class="small" x="80" y="450">namespace 0 stable NodeIds</text>
  <path class="signal" d="M270 404H330" marker-end="url(#signalArrow)"/>

  <path class="signal" d="M680 405H735V205H770" marker-end="url(#signalArrow)"/>
  {cards}
  <text class="warn" x="55" y="650">READ_ONLY actuator feedback: no direct valve write nodes exist in the current contract.</text>
  <text class="muted" x="55" y="679">Default endpoint {ENDPOINT} · model variables are resolved by BrowseName at runtime</text>
  <text class="muted" x="55" y="705">Scope is the currently implemented native OPC UA server, not every component inside the ThermoSysPro plant model.</text>
</svg>
'''


def render_process_wiring(assets: list[Asset]) -> str:
    node = {asset.asset_id: asset for asset in assets}
    def attrs(key: str) -> str:
        asset = node[key]
        return (
            f'data-equipment-id="{esc(asset.equipment_id)}" '
            f'data-opcua-position="{esc(asset.position_node)}" '
            f'data-opcua-flow="{esc(asset.flow_node)}" '
            f'data-controlled-by="{esc(asset.command_source)}"'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="820" viewBox="0 0 1400 820"
  role="img" aria-labelledby="title desc" data-protocol="OPC UA">
  <title id="title">ThermoSysPro turbine and bypass physical wiring with OPC UA feedback</title>
  <desc id="desc">HP, IP and LP admission paths, HP and LP bypass paths, spray injection and condenser destination.</desc>
  <style>{STYLE}</style>{DEFS}
  <rect class="bg" width="1400" height="820"/><rect class="panel" x="22" y="20" width="1356" height="775" rx="18"/>
  <text class="title" x="52" y="62">ThermoSysPro Steam Path — Native OPC UA Visibility</text>
  <text class="sub" x="52" y="89">Solid: physical steam/water · dashed: internal Trip actuation · each actuator exposes position and flow by BrowseName</text>

  <rect class="equip" x="55" y="170" width="160" height="70" rx="12"/><text class="label" x="135" y="200" text-anchor="middle">HP MAIN STEAM</text>
  <text class="small" x="135" y="222" text-anchor="middle">~12.681 MPa</text>
  <g {attrs('HP_TURB_ADM_VLV')}><polygon class="valve" points="270,180 315,205 270,230"/><polygon class="valve" points="360,180 315,205 360,230"/><text class="small" x="315" y="258" text-anchor="middle">HP ADMISSION</text></g>
  <rect class="equip" x="405" y="170" width="145" height="70" rx="35"/><text class="label" x="477" y="211" text-anchor="middle">HP TURBINE</text>
  <rect class="equip" x="600" y="170" width="160" height="70" rx="12"/><text class="label" x="680" y="200" text-anchor="middle">COLD REHEAT</text><text class="small" x="680" y="222" text-anchor="middle">HPBP destination</text>
  <rect class="equip" x="810" y="170" width="160" height="70" rx="12"/><text class="label" x="890" y="200" text-anchor="middle">HOT REHEAT</text><text class="small" x="890" y="222" text-anchor="middle">LPBP source</text>
  <g {attrs('IP_TURB_ADM_VLV')}><polygon class="valve" points="1015,180 1060,205 1015,230"/><polygon class="valve" points="1105,180 1060,205 1105,230"/><text class="small" x="1060" y="258" text-anchor="middle">IP ADMISSION</text></g>
  <rect class="equip" x="1150" y="170" width="105" height="70" rx="35"/><text class="label" x="1202" y="211" text-anchor="middle">IP TURB.</text>
  <rect class="equip" x="1285" y="170" width="85" height="70" rx="35"/><text class="label" x="1327" y="211" text-anchor="middle">LP</text>
  <path class="steam" d="M215 205H270M360 205H405M550 205H600M760 205H810M970 205H1015M1105 205H1150M1255 205H1285" marker-end="url(#steamArrow)"/>

  <path class="steam" d="M135 240V380H600" marker-end="url(#steamArrow)"/>
  <g {attrs('HP_BYPASS_VLV')}><polygon class="valve" points="275,355 320,380 275,405"/><polygon class="valve" points="365,355 320,380 365,405"/><text class="small" x="320" y="430" text-anchor="middle">HP BYPASS</text></g>
  <g {attrs('HP_SPRAY_VLV')}><circle class="valve" cx="480" cy="380" r="28"/><path class="water" d="M480 305V345" marker-end="url(#waterArrow)"/><text class="small" x="480" y="430" text-anchor="middle">HP SPRAY</text></g>

  <rect class="equip" x="1160" y="610" width="190" height="75" rx="34"/><text class="label" x="1255" y="643" text-anchor="middle">CONDENSER</text><text class="small" x="1255" y="666" text-anchor="middle">LPBP destination</text>
  <path class="steam" d="M890 240V510H1255V610" marker-end="url(#steamArrow)"/>
  <g {attrs('LP_BYPASS_VLV')}><polygon class="valve" points="995,485 1040,510 995,535"/><polygon class="valve" points="1085,485 1040,510 1085,535"/><text class="small" x="1040" y="560" text-anchor="middle">LP BYPASS</text></g>
  <g {attrs('LP_SPRAY_VLV')}><circle class="valve" cx="1155" cy="510" r="28"/><path class="water" d="M1155 435V475" marker-end="url(#waterArrow)"/><text class="small" x="1155" y="560" text-anchor="middle">LP SPRAY</text></g>

  <rect class="equip" x="690" y="610" width="180" height="75" rx="15"/><text class="label" x="780" y="640" text-anchor="middle">LP DRUM STEAM</text><text class="small" x="780" y="663" text-anchor="middle">not LP bypass</text>
  <g {attrs('LP_DRUM_ADM_VLV')}><polygon class="valve" points="920,622 965,647 920,672"/><polygon class="valve" points="1010,622 965,647 1010,672"/><text class="small" x="965" y="704" text-anchor="middle">LP DRUM ADMISSION</text></g>
  <path class="steam" d="M870 647H920M1010 647H1100V290H1285" marker-end="url(#steamArrow)"/>

  <rect class="logic" x="55" y="570" width="520" height="155" rx="14"/><text class="label" x="80" y="605">TRIP ACTUATION</text>
  <text class="mono" x="80" y="634">{COMMAND_NODE} → {TRIP_LATCH_NODE}</text>
  <text class="small" x="80" y="663">CLOSE: HP/IP/LP-drum admission</text><text class="small" x="80" y="688">OPEN: HPBP/LPBP · ENABLE: HP/LP spray</text>
  <path class="signal" d="M315 570V430" marker-end="url(#signalArrow)"/><path class="signal" d="M575 647H690" marker-end="url(#signalArrow)"/>
  <text class="muted" x="55" y="770">No separate IP bypass · LP drum admission is not LPBP · application access to all seven actuator feedback nodes is READ_ONLY</text>
</svg>
'''


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def generate(check: bool = False) -> None:
    assets = load_assets()
    rendered: dict[Path, str] = {}
    for asset in assets:
        rendered[ROOT / asset.svg] = render_asset(asset)
    rendered[OUTPUT / "opcua_actuator_overview.svg"] = render_overview(assets)
    rendered[OUTPUT / "opcua_process_wiring.svg"] = render_process_wiring(assets)
    manifest = {
        "schema_version": "1.0",
        "scope": "NATIVE_OPENMODELICA_OPCUA_CURRENT_CONTRACT",
        "endpoint_default": ENDPOINT,
        "node_locator": "BrowseName",
        "write_nodes": [{"browse_name": COMMAND_NODE, "type": "Double", "semantics": "0/1 GT Trip"}],
        "solver_control_nodes": [
            {"node_id": STEP_NODE_ID, "browse_name": "OpenModelica.step", "access": "WRITE"},
            {"node_id": TIME_NODE_ID, "browse_name": "OpenModelica.time", "access": "READ"},
        ],
        "actuator_asset_count": len(assets),
        "overview_svg": "opcua_actuator_overview.svg",
        "process_wiring_svg": "opcua_process_wiring.svg",
        "assets": [asdict(asset) for asset in assets],
        "limitations": [
            "Valve feedback is application-read-only in the current contract.",
            "No independent OPC UA valve command nodes are claimed.",
            "Spray actuators are implemented as controlled flow sources and injectors.",
        ],
    }
    rendered[MANIFEST] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if check:
        stale = [str(path.relative_to(ROOT)) for path, content in rendered.items() if not path.is_file() or path.read_text(encoding="utf-8") != content]
        if stale:
            raise SystemExit("stale OPC UA visual assets: " + ", ".join(stale))
        return
    for path, content in rendered.items():
        write(path, content)
    print(f"generated {len(assets)} actuator SVGs, two wiring SVGs and {MANIFEST.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generate(check=args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
