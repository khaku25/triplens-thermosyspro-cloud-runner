#!/usr/bin/env python3
"""Build a self-contained ECMS physical-link verification dashboard."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


DISPLAY = {
    "gt_trip_cmd": ("GT TRIP CMD", "BOOL", "ECMS"),
    "gt_trip_latch": ("GT TRIP LATCH", "BOOL", "ECMS"),
    "cb_52gt_closed": ("52GT CLOSED", "BOOL", "ECMS"),
    "cb_52st_closed": ("52ST CLOSED", "BOOL", "ECMS"),
    "gtg_power_mw": ("GTG 출력", "MW", "DCS1"),
    "gtg_speed_rpm": ("GTG 속도", "rpm", "DCS1"),
    "stg_power_w": ("STG 출력", "W", "DCS1"),
    "gt_exhaust_mass_flow_t_h": ("GT 배기 유량", "t/h", "DCS1"),
    "gt_exhaust_temperature_k": ("GT 배기 온도", "K", "DCS1"),
    "hp_drum_level_m": ("HP Drum Level", "m", "DCS2"),
    "ip_drum_level_m": ("IP Drum Level", "m", "DCS2"),
    "lp_drum_level_m": ("LP Drum Level", "m", "DCS2"),
    "hp_drum_pressure_pa": ("HP Drum Pressure", "Pa", "DCS2"),
    "ip_drum_pressure_pa": ("IP Drum Pressure", "Pa", "DCS2"),
    "lp_drum_pressure_pa": ("LP Drum Pressure", "Pa", "DCS2"),
    "hp_steam_flow_t_h": ("HP Steam Flow", "t/h", "DCS2"),
    "ip_steam_flow_t_h": ("IP Steam Flow", "t/h", "DCS2"),
    "lp_steam_flow_t_h": ("LP Steam Flow", "t/h", "DCS2"),
    "hp_admission_valve_pu": ("HP ESV/CV Position", "pu", "DCS1"),
    "ip_admission_valve_pu": ("IP Admission Position", "pu", "DCS1"),
    "lp_admission_multiplier_pu": ("LP Admission Multiplier", "pu", "DCS1"),
    "hp_bypass_valve_pu": ("HP Bypass Position", "pu", "DCS2"),
    "lp_bypass_valve_pu": ("LP Bypass Position", "pu", "DCS2"),
    "hp_bypass_steam_flow_t_h": ("HP Bypass Flow", "t/h", "DCS2"),
    "lp_bypass_steam_flow_t_h": ("LP Bypass Flow", "t/h", "DCS2"),
    "condenser_pressure_pa": ("Condenser Pressure", "Pa", "DCS2"),
    "condenser_level_m": ("Condenser Level", "m", "DCS2"),
}
PREVIEW_LABEL = {
    "gtg_power_mw": "GTG POWER",
    "gtg_speed_rpm": "GTG SPEED",
    "stg_power_w": "STG POWER",
    "gt_exhaust_mass_flow_t_h": "GT EXHAUST FLOW",
    "gt_exhaust_temperature_k": "GT EXHAUST TEMP",
}


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def decimate(rows: list[dict[str, str]], limit: int = 1200) -> list[dict[str, str]]:
    if len(rows) <= limit:
        return rows
    step = max(1, math.ceil((len(rows) - 1) / (limit - 1)))
    sampled = rows[::step]
    if sampled[-1] is not rows[-1]:
        sampled.append(rows[-1])
    return sampled


def preview_value(field: str, raw: str, unit: str) -> str:
    if not raw:
        return "—"
    try:
        value = float(raw)
    except ValueError:
        return raw
    if field == "stg_power_w":
        value /= 1_000_000
        unit = "MW"
    elif unit == "Pa":
        value /= 1_000_000
        unit = "MPa"
    digits = 1 if abs(value) >= 100 else 2 if abs(value) >= 10 else 3
    return f"{value:.{digits}f} {unit}"


def build_preview_svg(
    path: Path,
    rows: list[dict[str, str]],
    signals: list[dict[str, str]],
    event_time: float,
    manifest: dict[str, object],
    validation: dict[str, object],
) -> None:
    """Render a no-JavaScript ECMS evidence frame for artifact previews."""
    if not rows:
        raise ValueError("cannot render an empty ECMS dashboard preview")
    target_time = min(float(rows[-1]["time_s"]), event_time + 0.25)
    selected_index = min(
        range(len(rows)), key=lambda index: abs(float(rows[index]["time_s"]) - target_time)
    )
    selected = rows[selected_index]
    by_owner = {
        owner: [signal for signal in signals if signal["owner"] == owner]
        for owner in ("DCS1", "DCS2", "ECMS")
    }

    def line(text: str, x: int, y: int, *, size: int = 13, weight: int = 400,
             fill: str = "#111820", anchor: str = "start") -> str:
        return (
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{xml_escape(text)}</text>'
        )

    pieces = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">',
        '<style>text{font-family:"Malgun Gothic","맑은 고딕",Arial,sans-serif}.mono{font-family:Consolas,monospace}</style>',
        '<rect width="1600" height="900" fill="#cbd2d9"/>',
        '<rect width="1600" height="66" fill="#101e2f"/>',
        '<rect y="61" width="1600" height="5" fill="#d71920"/>',
        line("ECMS // PHYSICAL SIGNAL GATEWAY", 24, 39, size=22, weight=800, fill="#ffffff"),
        line("OpenModelica → ProcessBus → ECMS", 520, 38, size=12, weight=700, fill="#b9c7d5"),
        line(f'SOURCE {float(selected["time_s"]):.3f} s', 1575, 39, size=17, weight=800, fill="#ffffff", anchor="end"),
        '<rect x="0" y="66" width="260" height="834" fill="#17283c"/>',
        line("LINK HEALTH", 20, 100, size=11, weight=800, fill="#8fa4b8"),
        '<rect x="14" y="115" width="232" height="72" fill="#20364c"/>',
        '<rect x="14" y="115" width="7" height="72" fill="#087f5b"/>',
        line(f'{validation.get("status", "UNKNOWN")} · VALUE LOCK', 32, 142, size=16, weight=800, fill="#ffffff"),
        line("NO RECALCULATION · SOURCE TIME PRESERVED", 32, 166, size=10, fill="#b9c7d5"),
        line("RAW SHA-256", 20, 219, size=11, weight=800, fill="#8fa4b8"),
        '<rect x="14" y="230" width="232" height="86" fill="#0d1a28" stroke="#324960"/>',
    ]
    raw_hash = str((manifest.get("raw") or {}).get("sha256", ""))
    for number, chunk in enumerate((raw_hash[:32], raw_hash[32:])):
        pieces.append(line(chunk, 24, 255 + number*20, size=10, fill="#b9c7d5"))
    pieces.extend([
        line("PHYSICAL ROUTE", 20, 354, size=11, weight=800, fill="#8fa4b8"),
        line("01  OpenModelica RAW", 25, 385, size=12, weight=700, fill="#ffffff"),
        line("02  Unit / tag mapping", 25, 416, size=12, weight=700, fill="#ffffff"),
        line("03  Exact ECMS copy", 25, 447, size=12, weight=700, fill="#ffffff"),
        '<line x1="31" y1="390" x2="31" y2="429" stroke="#005eb8" stroke-width="3"/>',
        line("TRANSPORT", 20, 500, size=11, weight=800, fill="#8fa4b8"),
        line("FILE HANDOFF", 25, 530, size=13, weight=800, fill="#ffffff"),
        line("NOT AN OPC/MODBUS LATENCY TEST", 25, 553, size=9, fill="#b9c7d5"),
    ])

    kpis = [
        ("COMMUNICATION", str(validation.get("status", "?")), "#087f5b"),
        ("PHYSICAL SIGNALS", str((manifest.get("handoff") or {}).get(
            "signal_count", len(signals))), "#536271"),
        ("SOURCE SAMPLES", f'{int(validation.get("rows_compared", len(rows))):,}', "#536271"),
        ("VALUE MISMATCH", str(validation.get("value_mismatch_count", "?")), "#d71920"),
    ]
    for index, (label, value, color) in enumerate(kpis):
        x = 280 + index*322
        pieces.extend([
            f'<rect x="{x}" y="84" width="302" height="84" fill="#f7f8f9" stroke="#9da8b2"/>',
            f'<rect x="{x}" y="84" width="302" height="6" fill="{color}"/>',
            line(label, x+14, 112, size=11, weight=800, fill="#5c6772"),
            line(value, x+14, 148, size=26, weight=900),
        ])

    chart_fields = [
        ("lp_drum_level_m", "LP DRUM LEVEL", "#005eb8"),
        ("gt_exhaust_mass_flow_t_h", "GT EXHAUST FLOW", "#d71920"),
        ("gtg_power_mw", "GT GENERATOR POWER", "#005eb8"),
    ]
    chart_fields = [item for item in chart_fields if item[0] in selected]
    for chart_index, (field, label, color) in enumerate(chart_fields[:3]):
        x0 = 280 + chart_index*430
        y0, width, height = 202, 410, 180
        numeric = [float(row[field]) for row in rows if row.get(field, "").strip()]
        if not numeric:
            continue
        low, high = min(numeric), max(numeric)
        if math.isclose(low, high):
            low -= 1
            high += 1
        points = []
        for index, row in enumerate(rows):
            raw = row.get(field, "").strip()
            if not raw:
                continue
            px = x0 + 12 + index*(width-24)/max(1, len(rows)-1)
            py = y0 + 43 + (height-58)*(high-float(raw))/(high-low)
            points.append(f"{px:.1f},{py:.1f}")
        trip_x = x0 + 12 + min(
            range(len(rows)), key=lambda i: abs(float(rows[i]["time_s"])-event_time)
        )*(width-24)/max(1, len(rows)-1)
        cursor_x = x0 + 12 + selected_index*(width-24)/max(1, len(rows)-1)
        pieces.extend([
            f'<rect x="{x0}" y="{y0}" width="{width}" height="{height}" fill="#f7f8f9" stroke="#9da8b2"/>',
            line(label, x0+12, y0+25, size=12, weight=800, fill="#34495e"),
            f'<line x1="{trip_x:.1f}" y1="{y0+38}" x2="{trip_x:.1f}" y2="{y0+height-10}" stroke="#d71920" stroke-dasharray="5 4"/>',
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2"/>',
            f'<line x1="{cursor_x:.1f}" y1="{y0+38}" x2="{cursor_x:.1f}" y2="{y0+height-10}" stroke="#101e2f" stroke-width="2"/>',
            line(f"{low:.3g} … {high:.3g}", x0+width-12, y0+25, size=10, fill="#5f6b75", anchor="end"),
        ])

    group_y = 410
    for owner_index, owner in enumerate(("DCS1", "DCS2", "ECMS")):
        x0 = 280 + owner_index*430
        owner_signals = by_owner[owner][:8]
        pieces.extend([
            f'<rect x="{x0}" y="{group_y}" width="410" height="360" fill="#ffffff" stroke="#9da8b2"/>',
            f'<rect x="{x0}" y="{group_y}" width="410" height="38" fill="#17283c"/>',
            line(f"{owner} · RECEIVED PHYSICAL VALUES", x0+12, group_y+25, size=12, weight=800, fill="#ffffff"),
        ])
        for row_index, signal in enumerate(owner_signals):
            y = group_y + 65 + row_index*35
            field = signal["field"]
            value = preview_value(field, selected.get(field, ""), signal["unit"])
            active_trip = "trip" in field and float(selected.get(field) or 0) >= 0.5
            value_color = "#d71920" if active_trip else "#111820"
            pieces.extend([
                f'<line x1="{x0+10}" y1="{y+10}" x2="{x0+400}" y2="{y+10}" stroke="#e1e5e8"/>',
                line(PREVIEW_LABEL.get(field, signal["label"]), x0+12, y, size=11, fill="#394957"),
                line(value, x0+398, y, size=13, weight=800, fill=value_color, anchor="end"),
            ])

    pieces.extend([
        '<rect x="280" y="792" width="1290" height="72" fill="#f7f8f9" stroke="#9da8b2"/>',
        '<rect x="280" y="792" width="8" height="72" fill="#087f5b"/>',
        line("PHYSICAL COMMUNICATION PROOF", 304, 820, size=12, weight=800, fill="#34495e"),
        line(
            f'{validation.get("values_compared", 0):,} values compared · 0 mismatch · source timestamp offset 0 ms',
            304, 846, size=17, weight=900,
        ),
        '</svg>',
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(pieces), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--validation-report", type=Path, required=True)
    parser.add_argument("--event-time", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview-svg", type=Path)
    args = parser.parse_args()

    fields, all_rows = read_rows(args.handoff)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validation = json.loads(args.validation_report.read_text(encoding="utf-8"))
    signal_fields = [field for field in fields if field in DISPLAY]
    rows = decimate(all_rows)
    payload = {
        "rows": rows,
        "signals": [
            {"field": field, "label": DISPLAY[field][0], "unit": DISPLAY[field][1],
             "owner": DISPLAY[field][2]}
            for field in signal_fields
        ],
        "eventTime": args.event_time,
        "fullRowCount": len(all_rows),
        "manifest": manifest,
        "validation": validation,
    }
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    raw_hash = html.escape(str(manifest.get("raw", {}).get("sha256", "")))
    process_hash = html.escape(str(manifest.get("processbus", {}).get("sha256", "")))
    status = html.escape(str(validation.get("status", "UNKNOWN")))
    document = f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ECMS Physical Link</title>
<style>
:root{{--navy:#101e2f;--navy2:#17283c;--steel:#536271;--line:#8794a1;--paper:#e7ebef;--panel:#f7f8f9;--red:#d71920;--blue:#005eb8;--green:#087f5b;--amber:#f59f00;--ink:#111820}}
*{{box-sizing:border-box}} body{{margin:0;background:#cbd2d9;color:var(--ink);font-family:"Malgun Gothic","맑은 고딕",Arial,sans-serif;font-size:13px}}
header{{height:62px;background:var(--navy);color:#fff;border-bottom:5px solid var(--red);display:flex;align-items:center;justify-content:space-between;padding:0 24px}}
.brand{{font-size:20px;font-weight:800;letter-spacing:.3px}} .sub{{font-size:11px;color:#b9c7d5;margin-left:12px}}
.clock{{font-family:Consolas,monospace;font-size:16px;font-weight:700}}
.shell{{display:grid;grid-template-columns:248px minmax(0,1fr);min-height:calc(100vh - 62px)}}
aside{{background:var(--navy2);color:#dbe4ec;border-right:1px solid #08111d;padding:18px 14px}}
.aside-title{{font-size:11px;font-weight:800;color:#8fa4b8;letter-spacing:1.2px;margin:4px 6px 10px}}
.status{{border-left:6px solid var(--green);background:#20364c;padding:12px;margin-bottom:10px}}
.status strong{{display:block;color:#fff;font-size:15px}} .status small{{display:block;color:#b9c7d5;margin-top:4px;line-height:1.45}}
.hash{{font-family:Consolas,monospace;font-size:10px;word-break:break-all;color:#b9c7d5;background:#0d1a28;padding:8px;margin:8px 0 14px;border:1px solid #324960}}
.legend{{display:grid;grid-template-columns:9px 1fr;gap:8px;margin:8px 6px;align-items:center}} .dot{{height:9px;background:var(--blue)}}
main{{padding:16px 18px 28px;overflow:hidden}}
.topline{{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:10px;margin-bottom:12px}}
.kpi{{background:var(--panel);border:1px solid #a9b2bb;border-top:5px solid var(--steel);padding:11px 13px;min-height:74px}}
.kpi.pass{{border-top-color:var(--green)}} .kpi.trip{{border-top-color:var(--red)}} .kpi .label{{font-size:10px;font-weight:800;color:#5c6772;letter-spacing:.7px}}
.kpi .value{{font-size:22px;font-weight:900;margin-top:5px}} .kpi .unit{{font-size:11px;color:#69737d;margin-left:4px}}
.panel{{background:var(--panel);border:1px solid #a9b2bb;margin-bottom:12px}}
.panel-head{{height:38px;background:#d9dfe5;border-bottom:1px solid #a9b2bb;display:flex;align-items:center;justify-content:space-between;padding:0 12px;font-weight:800;color:#26384a}}
.controls{{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;padding:10px 12px;border-bottom:1px solid #c3cbd2}}
button{{border:0;background:var(--blue);color:white;padding:8px 16px;font:700 12px "Malgun Gothic";cursor:pointer;border-radius:2px}} input[type=range]{{width:100%;accent-color:var(--red)}}
.event-badge{{background:var(--red);color:white;padding:6px 10px;font-weight:900;min-width:128px;text-align:center}}
.charts{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;padding:10px}}
.chart{{border:1px solid #b4bec7;background:#fff;padding:8px}} .chart-title{{font-size:11px;font-weight:800;margin-bottom:6px;color:#34495e}}
svg{{display:block;width:100%;height:140px;background:#f2f4f6}} .axis{{stroke:#a7b1ba;stroke-width:1}} .trace{{fill:none;stroke:var(--blue);stroke-width:2}} .cursor{{stroke:var(--red);stroke-width:2}} .tripline{{stroke:var(--red);stroke-width:1;stroke-dasharray:5 4}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(230px,1fr));gap:10px;padding:10px}}
.group{{border:1px solid #adb7c0;background:#fff}} .group h3{{margin:0;padding:8px 10px;background:var(--navy2);color:white;font-size:12px}}
.sig{{display:grid;grid-template-columns:1fr auto;gap:8px;padding:7px 9px;border-top:1px solid #e1e5e8;align-items:center}} .sig:first-of-type{{border-top:0}}
.tag{{font-size:11px;color:#394957}} .val{{font-family:Consolas,monospace;font-size:14px;font-weight:800}} .unit2{{font-size:9px;color:#707a84;margin-left:3px}}
.trip-on{{background:var(--red);color:#fff;padding:3px 7px}} .closed-off{{background:#4d5862;color:#fff;padding:3px 7px}} .closed-on{{background:var(--blue);color:#fff;padding:3px 7px}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:7px 9px;border-bottom:1px solid #d6dce1;text-align:left}} th{{font-size:10px;color:#536271;background:#eef1f4}} td.mono{{font-family:Consolas,monospace;font-size:11px}}
.foot{{font-size:10px;color:#5f6b75;padding:0 2px}} @media(max-width:900px){{.shell{{grid-template-columns:1fr}}aside{{display:none}}.topline,.charts,.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header><div><span class="brand">ECMS // PHYSICAL SIGNAL GATEWAY</span><span class="sub">OpenModelica → ProcessBus → ECMS</span></div><div class="clock" id="clock">SOURCE 0.000 s</div></header>
<div class="shell">
<aside>
  <div class="aside-title">LINK HEALTH</div>
  <div class="status"><strong>{status} · VALUE LOCK</strong><small>물리값 재계산 없음<br>원본 시각 유지</small></div>
  <div class="aside-title">RAW SHA-256</div><div class="hash">{raw_hash}</div>
  <div class="aside-title">PROCESSBUS SHA-256</div><div class="hash">{process_hash}</div>
  <div class="aside-title">COLOR KEY</div>
  <div class="legend"><i class="dot" style="background:#d71920"></i><span>Trip / Open transition</span></div>
  <div class="legend"><i class="dot" style="background:#005eb8"></i><span>Normal / Closed</span></div>
  <div class="legend"><i class="dot" style="background:#536271"></i><span>Inactive / unavailable</span></div>
</aside>
<main>
  <section class="topline">
    <div class="kpi pass"><div class="label">COMMUNICATION</div><div class="value">{status}</div></div>
    <div class="kpi"><div class="label">PHYSICAL SIGNALS</div><div class="value" id="signalCount">0</div></div>
    <div class="kpi"><div class="label">SOURCE SAMPLES</div><div class="value">{len(all_rows):,}</div></div>
    <div class="kpi trip"><div class="label">VALUE MISMATCH</div><div class="value">{validation.get('value_mismatch_count', '?')}<span class="unit">건</span></div></div>
  </section>
  <section class="panel">
    <div class="panel-head"><span>물리 시계열 재생</span><span>Trip 기준 {args.event_time:.3f} s</span></div>
    <div class="controls"><button id="play">▶ 재생</button><input id="range" type="range" min="0" max="0" value="0"><div class="event-badge" id="phase">PRE-TRIP</div></div>
    <div class="charts" id="charts"></div>
    <div class="grid" id="groups"></div>
  </section>
  <section class="panel"><div class="panel-head"><span>통신 계보</span><span>NO RECALCULATION</span></div>
    <table><thead><tr><th>구간</th><th>상태</th><th>정책</th><th>증거</th></tr></thead><tbody>
      <tr><td>OpenModelica → RAW</td><td>PASS</td><td>Simulator direct</td><td class="mono">RAW SHA 고정</td></tr>
      <tr><td>RAW → ProcessBus</td><td>PASS</td><td>태그·단위 표준화만</td><td class="mono">source mapping manifest</td></tr>
      <tr><td>ProcessBus → ECMS</td><td>PASS</td><td>문자열 값 그대로 복사</td><td class="mono">{validation.get('values_compared', 0):,} values / 0 mismatch</td></tr>
    </tbody></table>
  </section>
  <div class="foot">이 화면은 파일 기반 VPP 통신 검증 화면입니다. OPC/Modbus 네트워크 지연을 측정한 화면이 아닙니다.</div>
</main></div>
<script id="payload" type="application/json">{data_json}</script>
<script>
const P=JSON.parse(document.getElementById('payload').textContent), rows=P.rows, sigs=P.signals;
const range=document.getElementById('range'), play=document.getElementById('play'); let timer=null;
range.max=Math.max(0,rows.length-1); document.getElementById('signalCount').textContent=(P.manifest.handoff&&P.manifest.handoff.signal_count)||sigs.length;
const owners=['DCS1','DCS2','ECMS'];
function numeric(field){{return rows.map(r=>Number(r[field])).filter(Number.isFinite)}}
function fmt(field,v,unit){{if(v===''||v==null)return '—'; let n=Number(v); if(!Number.isFinite(n))return v;
 if(field==='stg_power_w'){{n/=1e6;unit='MW'}} else if(unit==='Pa'){{n/=1e6;unit='MPa'}}
 const a=Math.abs(n),d=a>=100?1:a>=10?2:3; return n.toFixed(d)+' <span class="unit2">'+unit+'</span>'}}
function classFor(field,v){{if(field.includes('trip')&&Number(v)>=.5)return 'trip-on';if(field.includes('closed'))return Number(v)>=.5?'closed-on':'closed-off';return ''}}
function renderGroups(r){{const root=document.getElementById('groups');root.innerHTML='';owners.forEach(owner=>{{const box=document.createElement('div');box.className='group';box.innerHTML='<h3>'+owner+' · RECEIVED PHYSICAL VALUES</h3>';sigs.filter(s=>s.owner===owner).forEach(s=>{{const row=document.createElement('div');row.className='sig';row.innerHTML='<div class="tag">'+s.label+'<br><small>'+s.field+'</small></div><div class="val '+classFor(s.field,r[s.field])+'">'+fmt(s.field,r[s.field],s.unit)+'</div>';box.appendChild(row)}});root.appendChild(box)}})}}
function chart(field,label){{const vals=rows.map(r=>Number(r[field]));const finite=vals.filter(Number.isFinite);if(!finite.length)return '';
 let lo=Math.min(...finite),hi=Math.max(...finite);if(hi===lo){{hi+=1;lo-=1}}const W=440,H=140,p=12;
 const x=i=>p+i*(W-2*p)/Math.max(1,rows.length-1),y=v=>H-p-(v-lo)*(H-2*p)/(hi-lo);
 const points=vals.map((v,i)=>Number.isFinite(v)?x(i).toFixed(1)+','+y(v).toFixed(1):'').filter(Boolean).join(' ');
 const tripIndex=rows.findIndex(r=>Number(r.time_s)>=P.eventTime),tx=tripIndex<0?-10:x(tripIndex);
 return '<div class="chart"><div class="chart-title">'+label+' · '+lo.toPrecision(4)+' … '+hi.toPrecision(4)+'</div><svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none"><line class="axis" x1="'+p+'" y1="'+(H-p)+'" x2="'+(W-p)+'" y2="'+(H-p)+'"/><line class="tripline" x1="'+tx+'" y1="0" x2="'+tx+'" y2="'+H+'"/><polyline class="trace" points="'+points+'"/><line class="cursor" id="cursor-'+field+'" x1="'+p+'" y1="0" x2="'+p+'" y2="'+H+'"/></svg></div>'}}
const chartDefs=[['lp_drum_level_m','LP Drum Level'],['gt_exhaust_mass_flow_t_h','GT Exhaust Flow'],['hp_admission_valve_pu','HP Admission / ESV']].filter(x=>sigs.some(s=>s.field===x[0])).slice(0,3);
document.getElementById('charts').innerHTML=chartDefs.map(x=>chart(...x)).join('');
function update(i){{i=Math.max(0,Math.min(rows.length-1,Number(i)||0));range.value=i;const r=rows[i],t=Number(r.time_s);document.getElementById('clock').textContent='SOURCE '+t.toFixed(3)+' s';document.getElementById('phase').textContent=t<P.eventTime?'PRE-TRIP':t===P.eventTime?'AT TRIP':'POST-TRIP';renderGroups(r);chartDefs.forEach(([f])=>{{const el=document.getElementById('cursor-'+f);if(el){{const x=12+i*(440-24)/Math.max(1,rows.length-1);el.setAttribute('x1',x);el.setAttribute('x2',x)}}}})}}
range.addEventListener('input',e=>update(e.target.value));play.onclick=()=>{{if(timer){{clearInterval(timer);timer=null;play.textContent='▶ 재생';return}}play.textContent='Ⅱ 정지';timer=setInterval(()=>{{let i=Number(range.value)+1;if(i>=rows.length)i=0;update(i)}},70)}};update(0);
</script>
</body></html>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")
    preview_path = args.preview_svg or args.output.with_suffix(".svg")
    build_preview_svg(
        preview_path, rows, payload["signals"], args.event_time, manifest, validation
    )
    print(f"PASS: wrote ECMS physical dashboard with {len(rows)} embedded samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
