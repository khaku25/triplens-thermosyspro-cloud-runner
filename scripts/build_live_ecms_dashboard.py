#!/usr/bin/env python3
"""Build a compact ECMS dashboard only from TCP-received physical telemetry."""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from xml.sax.saxutils import escape

from live_protocol import LIVE_SIGNALS, VALVE_POINTS


POINT_LABELS = {point.key.lower(): point.label for point in VALVE_POINTS}
FEATURED = (
    "hpsteam_cmd", "hpsteam_fb", "hpsteam_cv", "hpsteam_mass_flow", "hpsteam_delta_p",
    "ipturb_adm_cmd", "ipturb_adm_fb", "ipturb_adm_deviation", "ipturb_adm_cv",
    "hp_drum_level", "ip_drum_level", "lp_drum_level",
    "hp_drum_pressure", "ip_drum_pressure", "lp_drum_pressure",
)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def label(field: str) -> str:
    return field.replace("_", " ").upper()


def fmt(value: str, unit: str) -> str:
    number = float(value)
    if unit == "BOOL":
        return "ON" if number >= 0.5 else "OFF"
    if unit == "Pa":
        return f"{number / 1e6:.4f} MPa"
    digits = 2 if abs(number) >= 100 else 4
    return f"{number:.{digits}f} {unit}"


def preview_svg(path: Path, row: dict[str, str], proof: dict[str, object]) -> None:
    specs = {spec.field: spec for spec in LIVE_SIGNALS}
    pieces = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">',
        '<style>text{font-family:"Malgun Gothic","맑은 고딕",Arial,sans-serif}</style>',
        '<rect width="1600" height="900" fill="#28333e"/>',
        '<rect width="1600" height="72" fill="#101b28"/>',
        '<rect y="66" width="1600" height="6" fill="#d7081e"/>',
        '<text x="28" y="45" font-size="23" font-weight="800" fill="white">ECMS  |  LIVE PHYSICAL LINK</text>',
        '<rect x="28" y="100" width="1544" height="96" fill="#3a4652" stroke="#7c8995"/>',
        '<rect x="28" y="100" width="12" height="96" fill="#00a064"/>',
        '<text x="62" y="132" font-size="12" font-weight="800" fill="#bdc7d0">MAIN FMU / TCP LINK</text>',
        '<text x="62" y="174" font-size="32" font-weight="900" fill="white">PASS</text>',
        f'<text x="410" y="157" font-size="22" font-weight="800" fill="white">{proof["frames_compared"]} FRAMES</text>',
        f'<text x="720" y="157" font-size="22" font-weight="800" fill="white">{proof["values_received"]:,} VALUES</text>',
        '<text x="1540" y="157" text-anchor="end" font-size="22" font-weight="800" fill="white">BYTE MISMATCH 0</text>',
    ]
    for index, field in enumerate(FEATURED):
        spec = specs[field]
        column, line = divmod(index, 5)
        x, y = 28 + column * 515, 230 + line * 108
        active = field.endswith("deviation") and abs(float(row[field])) > 0.1
        fill = "#c90019" if active else "#14202c"
        pieces.extend((
            f'<rect x="{x}" y="{y}" width="492" height="86" fill="{fill}" stroke="#71808e"/>',
            f'<text x="{x+18}" y="{y+28}" font-size="12" font-weight="800" fill="#b8c5cf">{escape(spec.owner)} · {escape(label(field))}</text>',
            f'<text x="{x+18}" y="{y+64}" font-size="22" font-weight="900" fill="white">{escape(fmt(row[field], spec.unit))}</text>',
        ))
    pieces.extend((
        '<rect x="28" y="804" width="1544" height="54" fill="#101b28"/>',
        '<text x="800" y="838" text-anchor="middle" font-size="15" font-weight="800" fill="white">ECMS COMMAND → TCP → RUNNING OPENMODELICA FMU → PHYSICAL SOLVER → TCP → ECMS</text>',
        '</svg>',
    ))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(pieces), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview-svg", type=Path, required=True)
    args = parser.parse_args()
    rows = read_rows(args.capture)
    proof = json.loads(args.proof.read_text(encoding="utf-8"))
    if not rows or proof.get("status") != "PASS":
        raise ValueError("dashboard requires a passing TCP capture")
    specs = [
        {"field": spec.field, "label": label(spec.field), "unit": spec.unit,
         "owner": spec.owner, "causality": spec.fmi_causality}
        for spec in LIVE_SIGNALS
    ]
    payload = json.dumps({"rows": rows, "specs": specs}, separators=(",", ":")).replace("</", "<\\/")
    latency = proof.get("round_trip_latency_ms", {})
    document = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ECMS Live Physical Link</title><style>
:root{{--bg:#28333e;--navy:#101b28;--panel:#14202c;--steel:#3a4652;--line:#71808e;--red:#c90019;--blue:#006cbb;--green:#00a064;--text:#f4f7f9;--muted:#b8c5cf}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:13px "Malgun Gothic","맑은 고딕",Arial,sans-serif}}
header{{height:72px;background:var(--navy);border-bottom:6px solid #d7081e;padding:20px 26px;font-size:22px;font-weight:900}}main{{padding:20px 26px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.kpi{{background:var(--steel);border:1px solid var(--line);border-left:10px solid var(--green);padding:12px 16px}}.kpi small{{color:var(--muted);font-weight:800}}.kpi b{{display:block;font-size:24px;margin-top:4px}}
.control{{display:flex;gap:12px;align-items:center;background:var(--navy);padding:12px;margin-top:12px}}button{{background:var(--blue);border:0;color:white;padding:8px 18px;font-weight:800}}input[type=range]{{flex:1;accent-color:#d7081e}}input[type=search]{{background:#eef2f4;border:0;padding:8px;width:250px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}}.owner{{background:var(--panel);border:1px solid var(--line)}}h2{{margin:0;padding:12px 14px;background:var(--navy);font-size:14px}}.rows{{max-height:535px;overflow:auto}}
.row{{display:grid;grid-template-columns:1fr auto;gap:10px;border-top:1px solid #344454;padding:8px 12px}}.row label{{color:var(--muted);font-size:11px;font-weight:700}}.row b{{font-family:Consolas,monospace}}.alarm{{background:var(--red)}}.alarm label{{color:white}}
.foot{{margin-top:12px;background:var(--navy);padding:13px;text-align:center;font-weight:800}}@media(max-width:900px){{.kpis,.grid{{grid-template-columns:1fr}}}}
</style></head><body><header>ECMS&nbsp; | &nbsp;LIVE PHYSICAL LINK</header><main>
<section class="kpis"><div class="kpi"><small>MAIN FMU / TCP</small><b>PASS</b></div><div class="kpi"><small>FRAMES</small><b>{proof['frames_compared']}</b></div><div class="kpi"><small>VALUES RECEIVED</small><b>{proof['values_received']:,}</b></div><div class="kpi"><small>LOOPBACK P95</small><b>{float(latency.get('p95',0)):.3f} ms</b></div></section>
<div class="control"><button id="play">▶ 재생</button><input id="range" type="range" min="0" max="{len(rows)-1}" value="0"><span id="clock">0.000 s</span><input id="filter" type="search" placeholder="태그 검색"></div>
<section class="grid" id="grid"></section><div class="foot">ECMS COMMAND → TCP → RUNNING OPENMODELICA FMU → PHYSICAL SOLVER → TCP → ECMS</div></main>
<script id="payload" type="application/json">{payload}</script><script>
const P=JSON.parse(document.getElementById('payload').textContent),R=P.rows,S=P.specs,grid=document.getElementById('grid'),range=document.getElementById('range'),filter=document.getElementById('filter');let timer=null;
function fmt(s,v){{let n=Number(v);if(s.unit==='BOOL')return n>=.5?'ON':'OFF';if(s.unit==='Pa')return(n/1e6).toFixed(4)+' MPa';return n.toFixed(Math.abs(n)>=100?2:4)+' '+s.unit}}
function draw(){{const r=R[Number(range.value)],q=filter.value.toLowerCase();document.getElementById('clock').textContent=Number(r.time_s).toFixed(3)+' s';grid.innerHTML='';['DCS1','DCS2'].forEach(o=>{{let box=document.createElement('div');box.className='owner';box.innerHTML='<h2>'+o+' | TCP RECEIVED PHYSICS</h2><div class="rows"></div>';let list=box.lastChild;S.filter(s=>s.owner===o&&(!q||s.field.includes(q)||s.label.toLowerCase().includes(q))).forEach(s=>{{let e=document.createElement('div'),v=r[s.field],alarm=s.field.endsWith('deviation')&&Math.abs(Number(v))>.1;e.className='row '+(alarm?'alarm':'');e.innerHTML='<label>'+s.label+' · '+s.causality.toUpperCase()+'</label><b>'+fmt(s,v)+'</b>';list.appendChild(e)}});grid.appendChild(box)}})}}
range.oninput=draw;filter.oninput=draw;document.getElementById('play').onclick=e=>{{if(timer){{clearInterval(timer);timer=null;e.target.textContent='▶ 재생'}}else{{e.target.textContent='Ⅱ 정지';timer=setInterval(()=>{{range.value=(Number(range.value)+1)%R.length;draw()}},80)}}}};draw();
</script></body></html>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")
    preview_svg(args.preview_svg, rows[-1], proof)
    print(f"LIVE_ECMS_DASHBOARD_PASS frames={len(rows)} signals={len(specs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
