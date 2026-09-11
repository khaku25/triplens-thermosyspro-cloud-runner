#!/usr/bin/env python3
"""Build the ECMS view from TCP-received FMU telemetry, never from simulator files."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from live_protocol import LIVE_SIGNALS


LABELS = {
    "gt_trip_cmd": "GT TRIP CMD",
    "gt_trip_latch": "GT TRIP LATCH",
    "st_trip_latch": "ST TRIP LATCH",
    "cb_52gt_trip_cmd": "52GT TRIP CMD",
    "cb_52gt_closed": "52GT CLOSED",
    "cb_52st_trip_cmd": "52ST TRIP CMD",
    "cb_52st_closed": "52ST CLOSED",
    "gtg_power_mw": "GT GENERATOR POWER",
    "gtg_speed_rpm": "GT SPEED",
    "gt_exhaust_mass_flow_t_h": "GT EXHAUST FLOW",
    "gt_exhaust_temperature_k": "GT EXHAUST TEMP",
    "hp_drum_level_m": "HP DRUM LEVEL",
    "ip_drum_level_m": "IP DRUM LEVEL",
    "lp_drum_level_m": "LP DRUM LEVEL",
    "hp_drum_pressure_pa": "HP DRUM PRESSURE",
    "ip_drum_pressure_pa": "IP DRUM PRESSURE",
    "lp_drum_pressure_pa": "LP DRUM PRESSURE",
    "hp_steam_flow_t_h": "HP STEAM FLOW",
    "ip_steam_flow_t_h": "IP STEAM FLOW",
    "lp_steam_flow_t_h": "LP STEAM FLOW",
    "hp_admission_valve_pu": "HP ESV / ADMISSION",
    "ip_admission_valve_pu": "IP ADMISSION",
    "lp_admission_multiplier_pu": "LP ADMISSION",
    "hp_bypass_valve_pu": "HP BYPASS POSITION",
    "lp_bypass_valve_pu": "LP BYPASS POSITION",
    "hp_bypass_steam_flow_t_h": "HP BYPASS FLOW",
    "lp_bypass_steam_flow_t_h": "LP BYPASS FLOW",
    "hp_bypass_spray_flow_t_h": "HP SPRAY FLOW",
    "lp_bypass_spray_flow_t_h": "LP SPRAY FLOW",
    "condenser_pressure_pa": "CONDENSER PRESSURE",
    "condenser_level_m": "CONDENSER LEVEL",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sample_rows(rows: list[dict[str, str]], limit: int = 1400) -> list[dict[str, str]]:
    if len(rows) <= limit:
        return rows
    stride = math.ceil((len(rows) - 1) / (limit - 1))
    result = rows[::stride]
    if result[-1] is not rows[-1]:
        result.append(rows[-1])
    return result


def format_value(field: str, raw: str, unit: str) -> str:
    value = float(raw)
    if unit == "BOOL":
        return "ON" if value >= 0.5 else "OFF"
    if unit == "Pa":
        return f"{value / 1e6:.3f} MPa"
    digits = 1 if abs(value) >= 100 else 2 if abs(value) >= 10 else 3
    return f"{value:.{digits}f} {unit}"


def build_preview(path: Path, rows: list[dict[str, str]], proof: dict[str, object]) -> None:
    trip_at = float(proof["trip_command_time_s"])
    selected = min(rows, key=lambda row: abs(float(row["time_s"]) - trip_at - 0.5))
    by_owner = {
        owner: [item for item in LIVE_SIGNALS if item[4] == owner]
        for owner in ("DCS1", "DCS2", "ECMS")
    }

    def text(value: str, x: int, y: int, size: int = 13, weight: int = 400,
             color: str = "#e9eef3", anchor: str = "start") -> str:
        return (
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{color}" text-anchor="{anchor}">{xml_escape(value)}</text>'
        )

    latency = proof.get("round_trip_latency_ms", {})
    pieces = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">',
        '<style>text{font-family:"Malgun Gothic","맑은 고딕",Arial,sans-serif}.mono{font-family:Consolas,monospace}</style>',
        '<rect width="1600" height="900" fill="#222c37"/>',
        '<rect width="1600" height="70" fill="#0b1522"/>',
        '<rect y="64" width="1600" height="6" fill="#e30613"/>',
        text("ECMS  |  LIVE PHYSICAL BUS", 24, 43, 23, 800, "#ffffff"),
        text("FMI 2.0 CS · FULL-DUPLEX TCP", 1548, 42, 13, 700, "#aebdca", "end"),
        '<rect x="24" y="94" width="1552" height="92" fill="#303d4a" stroke="#667687"/>',
        '<rect x="24" y="94" width="10" height="92" fill="#008f5d"/>',
        text("PHYSICAL LINK", 52, 122, 11, 800, "#9eb0c0"),
        text("PASS", 52, 162, 30, 900, "#ffffff"),
        text(f'{proof.get("frames_compared", 0):,} TCP FRAMES', 350, 124, 11, 800, "#9eb0c0"),
        text(f'{proof.get("values_received", 0):,} RECEIVED VALUES', 350, 160, 22, 900),
        text("BYTE MISMATCH", 750, 124, 11, 800, "#9eb0c0"),
        text("0", 750, 160, 28, 900, "#ffffff"),
        text("LOOPBACK P95", 1080, 124, 11, 800, "#9eb0c0"),
        text(f'{float(latency.get("p95", 0)):.3f} ms', 1080, 160, 22, 900),
        text(f'SOURCE {float(selected["time_s"]):.3f} s', 1548, 160, 20, 900, "#ffffff", "end"),
    ]
    x_positions = {"DCS1": 24, "DCS2": 548, "ECMS": 1072}
    limits = {"DCS1": 12, "DCS2": 12, "ECMS": 7}
    for owner in ("DCS1", "DCS2", "ECMS"):
        x = x_positions[owner]
        width = 504
        pieces.extend([
            f'<rect x="{x}" y="212" width="{width}" height="614" fill="#18232f" stroke="#667687"/>',
            f'<rect x="{x}" y="212" width="{width}" height="44" fill="#0b1522"/>',
            text(f"{owner}  |  LIVE RECEIVED", x + 16, 241, 13, 800, "#ffffff"),
        ])
        for index, (field, _fmu, _kind, unit, _owner) in enumerate(by_owner[owner][:limits[owner]]):
            y = 290 + index * 42
            value = format_value(field, selected[field], unit)
            is_alarm = ("trip" in field and float(selected[field]) >= 0.5) or (
                "closed" in field and float(selected[field]) < 0.5
            )
            if is_alarm:
                pieces.append(f'<rect x="{x+8}" y="{y-25}" width="{width-16}" height="34" fill="#c90012"/>')
            else:
                pieces.append(f'<line x1="{x+10}" y1="{y+12}" x2="{x+width-10}" y2="{y+12}" stroke="#354657"/>')
            pieces.append(text(LABELS[field], x + 16, y, 11, 700, "#ffffff" if is_alarm else "#b8c4cf"))
            pieces.append(text(value, x + width - 16, y, 13, 800, "#ffffff", "end"))
    pieces.extend([
        '<rect x="24" y="846" width="1552" height="34" fill="#0b1522"/>',
        text("ECMS COMMAND → TCP → RUNNING OPENMODELICA FMU → SOLVED PHYSICS → TCP → ECMS", 800, 869, 13, 800, "#ffffff", "middle"),
        "</svg>",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(pieces), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview-svg", type=Path, required=True)
    args = parser.parse_args()
    all_rows = read_rows(args.capture)
    if not all_rows:
        raise ValueError("ECMS live capture is empty")
    proof = json.loads(args.proof.read_text(encoding="utf-8"))
    if proof.get("status") != "PASS":
        raise ValueError("refusing to build a PASS dashboard from failed proof")
    rows = sample_rows(all_rows)
    signals = [
        {"field": field, "label": LABELS[field], "unit": unit, "owner": owner}
        for field, _fmu, _kind, unit, owner in LIVE_SIGNALS
    ]
    payload = json.dumps(
        {"rows": rows, "signals": signals, "proof": proof}, ensure_ascii=False
    ).replace("</", "<\\/")
    status = html.escape(str(proof["status"]))
    latency = proof.get("round_trip_latency_ms", {})
    document = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ECMS Live Physical Bus</title><style>
:root{{--bg:#222c37;--navy:#0b1522;--panel:#18232f;--steel:#303d4a;--line:#667687;--text:#edf2f6;--muted:#9eb0c0;--red:#c90012;--blue:#0067b9;--green:#008f5d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:13px "Malgun Gothic","맑은 고딕",Arial,sans-serif}}
header{{height:70px;background:var(--navy);border-bottom:6px solid #e30613;display:flex;align-items:center;justify-content:space-between;padding:0 24px}}
.brand{{font-size:22px;font-weight:900}}.meta{{font:700 12px Consolas,monospace;color:#aebdca}}main{{padding:18px 24px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.kpi{{background:var(--steel);border:1px solid var(--line);border-top:6px solid var(--green);padding:12px 15px}}
.kpi b{{display:block;font-size:25px;margin-top:5px}}.kpi small{{font-weight:800;color:var(--muted)}}.bar{{margin-top:14px;background:var(--navy);border:1px solid var(--line);padding:10px;display:grid;grid-template-columns:auto 1fr auto;gap:14px;align-items:center}}
button{{background:var(--blue);color:white;border:0;padding:8px 18px;font:800 12px "Malgun Gothic"}}input{{width:100%;accent-color:#e30613}}#clock{{font:800 15px Consolas,monospace}}
.owners{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:10px}}.owner{{background:var(--panel);border:1px solid var(--line)}}h2{{font-size:13px;margin:0;background:var(--navy);padding:11px 13px}}
.row{{display:grid;grid-template-columns:1fr auto;padding:8px 11px;border-top:1px solid #354657;align-items:center}}.row label{{font-size:11px;color:#b8c4cf;font-weight:700}}.value{{font:800 13px Consolas,monospace}}
.alarm{{background:var(--red);border-top-color:#ff4352}}.alarm label{{color:white}}.foot{{margin-top:12px;padding:11px 14px;background:var(--navy);font-weight:800;text-align:center}}
@media(max-width:900px){{.kpis,.owners{{grid-template-columns:1fr}}}}</style></head><body>
<header><div class="brand">ECMS&nbsp; | &nbsp;LIVE PHYSICAL BUS</div><div class="meta">FMI 2.0 CS · FULL-DUPLEX TCP</div></header><main>
<section class="kpis"><div class="kpi"><small>PHYSICAL LINK</small><b>{status}</b></div><div class="kpi"><small>TCP FRAMES</small><b>{proof['frames_compared']:,}</b></div><div class="kpi"><small>RECEIVED VALUES</small><b>{proof['values_received']:,}</b></div><div class="kpi"><small>LOOPBACK P95</small><b>{float(latency.get('p95',0)):.3f} ms</b></div></section>
<div class="bar"><button id="play">▶ 재생</button><input id="range" type="range" min="0" max="{len(rows)-1}" value="0"><span id="clock">0.000 s</span></div>
<section class="owners" id="owners"></section><div class="foot">ECMS COMMAND → TCP → RUNNING OPENMODELICA FMU → SOLVED PHYSICS → TCP → ECMS</div>
</main><script id="payload" type="application/json">{payload}</script><script>
const P=JSON.parse(document.getElementById('payload').textContent),R=P.rows,S=P.signals,root=document.getElementById('owners'),range=document.getElementById('range');let timer=null;
function fmt(s,v){{let n=Number(v);if(s.unit==='BOOL')return n>=.5?'ON':'OFF';if(s.unit==='Pa')return (n/1e6).toFixed(3)+' MPa';let d=Math.abs(n)>=100?1:Math.abs(n)>=10?2:3;return n.toFixed(d)+' '+s.unit}}
function alarm(f,v){{return(f.includes('trip')&&Number(v)>=.5)||(f.includes('closed')&&Number(v)<.5)}}
function draw(i){{const r=R[i];document.getElementById('clock').textContent=Number(r.time_s).toFixed(3)+' s';root.innerHTML='';['DCS1','DCS2','ECMS'].forEach(o=>{{let box=document.createElement('div');box.className='owner';box.innerHTML='<h2>'+o+' | LIVE RECEIVED</h2>';S.filter(s=>s.owner===o).forEach(s=>{{let e=document.createElement('div');e.className='row '+(alarm(s.field,r[s.field])?'alarm':'');e.innerHTML='<label>'+s.label+'</label><span class="value">'+fmt(s,r[s.field])+'</span>';box.appendChild(e)}});root.appendChild(box)}})}}
range.oninput=e=>draw(Number(e.target.value));document.getElementById('play').onclick=e=>{{if(timer){{clearInterval(timer);timer=null;e.target.textContent='▶ 재생'}}else{{e.target.textContent='Ⅱ 정지';timer=setInterval(()=>{{range.value=(Number(range.value)+1)%R.length;draw(Number(range.value))}},50)}}}};draw(0);
</script></body></html>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")
    build_preview(args.preview_svg, all_rows, proof)
    print(f"PASS: built live ECMS dashboard from {len(all_rows)} TCP-received frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
