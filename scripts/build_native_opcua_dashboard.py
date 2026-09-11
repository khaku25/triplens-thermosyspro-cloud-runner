#!/usr/bin/env python3
"""Render a compact ECMS dashboard from the post-receive native OPC UA capture."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from native_ecms_opcua_client import SIGNALS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.capture.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    proof = json.loads(args.proof.read_text(encoding="utf-8"))
    if not rows or proof.get("status") != "PASS":
        raise ValueError("dashboard requires a passing OPC UA capture")
    payload = json.dumps(
        {"rows": rows, "signals": [s.__dict__ for s in SIGNALS]},
        separators=(",", ":"),
    ).replace("</", "<\\/")
    document = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ECMS Native Physical Link</title><style>
:root{{--bg:#303a44;--navy:#101a26;--panel:#182430;--steel:#46525d;--line:#7c8892;--red:#d5001c;--blue:#006fbd;--green:#00a064;--text:#fff;--muted:#c8d0d6}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:13px "Malgun Gothic","맑은 고딕",Arial,sans-serif}}header{{height:70px;background:var(--navy);border-bottom:7px solid var(--red);padding:19px 26px;font-size:22px;font-weight:900}}main{{padding:18px 26px}}.proof{{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}}.kpi{{background:var(--steel);border:1px solid var(--line);border-left:11px solid var(--green);padding:12px 15px}}.kpi small{{color:var(--muted);font-weight:800}}.kpi b{{display:block;margin-top:5px;font-size:23px}}.bar{{display:flex;gap:12px;align-items:center;background:var(--navy);padding:12px;margin-top:11px}}button{{background:var(--blue);border:0;color:white;padding:8px 18px;font-weight:900}}input{{flex:1;accent-color:var(--red)}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:9px}}.owner{{background:var(--panel);border:1px solid var(--line)}}h2{{margin:0;background:var(--navy);padding:11px 13px;font-size:14px}}.row{{display:grid;grid-template-columns:1fr auto;border-top:1px solid #394957;padding:8px 12px}}.row label{{color:var(--muted);font-weight:700}}.row b{{font-family:Consolas,monospace}}.trip{{background:var(--red)}}.foot{{background:var(--navy);margin-top:11px;padding:13px;text-align:center;font-weight:900}}@media(max-width:850px){{.proof,.grid{{grid-template-columns:1fr}}}}
</style></head><body><header>ECMS | NATIVE OPENMODELICA PHYSICAL LINK</header><main><section class="proof"><div class="kpi"><small>OPC UA LINK</small><b>PASS</b></div><div class="kpi"><small>FRAMES</small><b>{proof['frames_received']}</b></div><div class="kpi"><small>VALUES</small><b>{proof['values_received']}</b></div><div class="kpi"><small>PHYSICAL CHANGES</small><b>{proof['changed_physical_fields']}</b></div></section><div class="bar"><button id="play">▶ 재생</button><input id="range" type="range" min="0" max="{len(rows)-1}" value="0"><b id="clock"></b></div><section class="grid" id="grid"></section><div class="foot">ECMS COMMAND → OPC UA → NATIVE OPENMODELICA SOLVER → OPC UA → ECMS</div></main><script id="data" type="application/json">{payload}</script><script>
const P=JSON.parse(document.getElementById('data').textContent),range=document.getElementById('range'),grid=document.getElementById('grid');let timer=null;function fmt(s,v){{let n=Number(v);if(s.unit==='BOOL')return n?'ON':'OFF';if(s.unit==='Pa')return(n/1e6).toFixed(4)+' MPa';return n.toFixed(Math.abs(n)>=100?2:4)+' '+s.unit}}function draw(){{const r=P.rows[Number(range.value)];document.getElementById('clock').textContent=Number(r.time_s).toFixed(3)+' s';grid.innerHTML='';['DCS1','DCS2'].forEach(o=>{{const box=document.createElement('div');box.className='owner';box.innerHTML='<h2>'+o+' | NATIVE PHYSICS</h2>';P.signals.filter(s=>s.owner===o).forEach(s=>{{const e=document.createElement('div');e.className='row '+(s.field==='gt_trip_latch'&&Number(r[s.field])?'trip':'');e.innerHTML='<label>'+s.field.toUpperCase().replaceAll('_',' ')+'</label><b>'+fmt(s,r[s.field])+'</b>';box.appendChild(e)}});grid.appendChild(box)}})}}range.oninput=draw;document.getElementById('play').onclick=e=>{{if(timer){{clearInterval(timer);timer=null;e.target.textContent='▶ 재생'}}else{{e.target.textContent='Ⅱ 정지';timer=setInterval(()=>{{range.value=(Number(range.value)+1)%P.rows.length;draw()}},60)}}}};draw();</script></body></html>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")
    print(f"NATIVE_OPCUA_DASHBOARD_PASS rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
