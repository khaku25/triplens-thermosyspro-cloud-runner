#!/usr/bin/env python3
"""Render the native OPC UA capture using the TripLens operator ownership model."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from native_ecms_opcua_client import SIGNALS


@dataclass(frozen=True)
class DashboardField:
    field: str
    unit: str
    label: str


# Presentation ownership is independent of historical Signal.owner metadata.
# DCS1 owns GT/ST process observations, DCS2 owns HRSG/BOP observations, and
# ECMS owns commands, latches, breakers and protection decisions.
DCS1_FIELDS = (
    "stg_power_w",
    "gtg_power_mw",
    "gtg_speed_rpm",
    "gt_exhaust_flow_th",
    "gt_exhaust_temperature_k",
    "hp_turbine_flow_th",
    "ip_turbine_flow_th",
    "lp_turbine_flow_th",
    "hp_admission_position_pu",
    "ip_admission_position_pu",
    "lp_admission_position_pu",
)

ECMS_FIELDS = (
    "ecms_command_sent",
    "lp_fwp_trip_command_readback",
    "lp_fwp_trip_latch_readback",
    "vcb_a02_trip_command_readback",
    "vcb_a02_closed_readback",
    "lp_fwp_motor_energized",
    "lp_fwp_speed_proven",
    "lp_fwp_running",
    "common_gt_trip_request",
    "common_st_trip_request",
    "gt_trip_command",
    "gt_trip_command_readback",
    "gt_trip_latch",
    "gt_breaker_trip_command",
    "gt_breaker_closed",
    "st_trip_latch",
    "st_breaker_trip_command",
    "st_breaker_closed",
    "round_trip_ms",
)

DCS2_EXTRA_FIELDS = (
    DashboardField("lp_drum_level_l_alarm", "BOOL", "LP DRUM LEVEL L ALARM"),
    DashboardField("lp_drum_level_ll_alarm", "BOOL", "LP DRUM LEVEL LL ALARM"),
)

ECMS_EXTRA_FIELDS = (
    DashboardField("ecms_command_sent", "BOOL", "FWP-LP TRIP COMMAND SENT"),
    DashboardField(
        "lp_fwp_trip_command_readback", "BOOL", "FWP-LP TRIP COMMAND READBACK"
    ),
    DashboardField("lp_fwp_trip_latch_readback", "BOOL", "FWP-LP TRIP LATCH"),
    DashboardField("vcb_a02_trip_command_readback", "BOOL", "VCB-A02 TRIP COMMAND"),
    DashboardField("vcb_a02_closed_readback", "BOOL", "VCB-A02 CLOSED"),
    DashboardField("common_gt_trip_request", "BOOL", "COMMON GT TRIP REQUEST"),
    DashboardField("common_st_trip_request", "BOOL", "COMMON ST TRIP REQUEST"),
    DashboardField("gt_trip_command_readback", "BOOL", "GT TRIP COMMAND READBACK"),
    DashboardField("round_trip_ms", "ms", "OPC UA ROUND TRIP"),
)


def _signal_field(field: str) -> DashboardField:
    signal = next(signal for signal in SIGNALS if signal.field == field)
    return DashboardField(field, signal.unit, field.upper().replace("_", " "))


def dashboard_groups() -> dict[str, list[DashboardField]]:
    """Return the authoritative three-panel ownership contract."""
    by_field = {signal.field: signal for signal in SIGNALS}
    dcs1 = [_signal_field(field) for field in DCS1_FIELDS]
    ecms = [
        DashboardField(field, by_field[field].unit, field.upper().replace("_", " "))
        for field in ECMS_FIELDS
        if field in by_field
    ]
    ecms.extend(ECMS_EXTRA_FIELDS)
    dcs2 = [
        DashboardField(signal.field, signal.unit, signal.field.upper().replace("_", " "))
        for signal in SIGNALS
        if signal.field not in DCS1_FIELDS and signal.field not in ECMS_FIELDS
    ]
    dcs2.extend(DCS2_EXTRA_FIELDS)
    return {"DCS1": dcs1, "DCS2": dcs2, "ECMS": ecms}


def _read_events(capture: Path) -> list[dict[str, str]]:
    event_path = capture.parent / "EVENT.csv"
    if not event_path.exists():
        return []
    with event_path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


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

    groups = dashboard_groups()
    missing = sorted(
        field.field
        for fields in groups.values()
        for field in fields
        if field.field not in rows[0]
    )
    if missing:
        raise ValueError("dashboard capture fields missing: " + ", ".join(missing))

    events = _read_events(args.capture)
    payload = json.dumps(
        {
            "rows": rows,
            "groups": {
                owner: [asdict(field) for field in fields]
                for owner, fields in groups.items()
            },
            "proof": proof,
            "events": events,
        },
        separators=(",", ":"),
    ).replace("</", "<\\/")
    event_count = proof.get("event_count", len(events))
    document = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ECMS Native Physical Link</title><style>
:root{{--bg:#303a44;--navy:#101a26;--panel:#182430;--steel:#46525d;--line:#7c8892;--red:#d5001c;--blue:#006fbd;--green:#00a064;--text:#fff;--muted:#c8d0d6}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:13px "Malgun Gothic","맑은 고딕",Arial,sans-serif}}header{{background:var(--navy);border-bottom:7px solid var(--red);padding:19px 26px;font-size:22px;font-weight:900}}main{{padding:18px 26px}}.proof{{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}}.kpi{{background:var(--steel);border:1px solid var(--line);border-left:11px solid var(--green);padding:12px 15px}}.kpi small{{color:var(--muted);font-weight:800}}.kpi b{{display:block;margin-top:5px;font-size:20px}}.bar{{display:flex;gap:12px;align-items:center;background:var(--navy);padding:12px;margin-top:11px}}button{{background:var(--blue);border:0;color:white;padding:8px 18px;font-weight:900}}input{{flex:1;accent-color:var(--red)}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-top:9px}}.owner,.events{{background:var(--panel);border:1px solid var(--line)}}h2{{margin:0;background:var(--navy);padding:11px 13px;font-size:14px}}.row{{display:grid;grid-template-columns:1fr auto;border-top:1px solid #394957;padding:8px 12px;gap:8px}}.row label{{color:var(--muted);font-weight:700}}.row b{{font-family:Consolas,monospace}}.trip{{background:var(--red)}}.events{{margin-top:9px;max-height:360px;overflow:auto}}table{{width:100%;border-collapse:collapse}}th,td{{padding:7px 9px;border-top:1px solid #394957;text-align:left}}th{{position:sticky;top:0;background:var(--navy)}}.foot{{background:var(--navy);margin-top:11px;padding:13px;text-align:center;font-weight:900}}@media(max-width:1050px){{.proof,.grid{{grid-template-columns:1fr 1fr}}}}@media(max-width:700px){{.proof,.grid{{grid-template-columns:1fr}}}}
</style></head><body><header>TRIPLENS | NATIVE OPENMODELICA PHYSICAL LINK</header><main>
<section class="proof">
<div class="kpi"><small>OPC UA LINK</small><b>PASS</b></div>
<div class="kpi"><small>EVENTS</small><b>{event_count}</b></div>
<div class="kpi"><small>GT TRIP → TERMINAL</small><b>{float(proof.get('post_gt_trip_observation_s', 0)):.3f} s</b></div>
<div class="kpi"><small>TERMINATION</small><b>{proof.get('termination_reason', 'UNKNOWN')}</b></div>
</section>
<section class="proof" style="margin-top:9px">
<div class="kpi"><small>GT TRIP TIME</small><b>{proof.get('gt_trip_time_s', 'N/A')} s</b></div>
<div class="kpi"><small>TERMINAL TIME</small><b>{proof.get('terminal_time_s', 'N/A')} s</b></div>
<div class="kpi"><small>FRAMES</small><b>{proof['frames_received']}</b></div>
<div class="kpi"><small>PHYSICAL CHANGES</small><b>{proof['changed_physical_fields']}</b></div>
</section>
<div class="bar"><button id="play">▶ 재생</button><input id="range" type="range" min="0" max="{len(rows)-1}" value="0"><b id="clock"></b></div>
<section class="grid" id="grid"></section>
<section class="events"><h2>EVENT.csv | CHRONOLOGICAL EVENT SUMMARY</h2><table><thead><tr><th>SEQ</th><th>TIME</th><th>SYSTEM</th><th>TAG</th><th>STATE</th><th>QUALITY</th></tr></thead><tbody id="eventRows"></tbody></table></section>
<div class="foot">ECMS COMMAND → OPC UA → NATIVE OPENMODELICA SOLVER → OPC UA → DCS1 / DCS2 / ECMS</div>
</main><script id="data" type="application/json">{payload}</script><script>
const P=JSON.parse(document.getElementById('data').textContent),range=document.getElementById('range'),grid=document.getElementById('grid');
let timer=null;
const activeFields=new Set(['lp_fwp_trip_command_readback','lp_fwp_trip_latch_readback','vcb_a02_trip_command_readback','lp_drum_level_l_alarm','lp_drum_level_ll_alarm','common_gt_trip_request','common_st_trip_request','gt_trip_command','gt_trip_command_readback','gt_trip_latch','gt_breaker_trip_command','st_trip_latch','st_breaker_trip_command']);
function fmt(s,v){{let n=Number(v);if(s.unit==='BOOL')return n?'ON':'OFF';if(s.unit==='Pa')return(n/1e6).toFixed(4)+' MPa';return n.toFixed(Math.abs(n)>=100?2:4)+' '+s.unit}}
function draw(){{const r=P.rows[Number(range.value)];document.getElementById('clock').textContent=Number(r.time_s).toFixed(3)+' s';grid.innerHTML='';['DCS1','DCS2','ECMS'].forEach(o=>{{const box=document.createElement('div');box.className='owner';box.innerHTML='<h2>'+o+(o==='DCS1'?' | GT / ST':o==='DCS2'?' | HRSG / BOP':' | COMMAND / LATCH / BREAKER / PROTECTION')+'</h2>';P.groups[o].forEach(s=>{{const e=document.createElement('div');e.className='row '+(activeFields.has(s.field)&&Number(r[s.field])?'trip':'');e.innerHTML='<label>'+s.label+'</label><b>'+fmt(s,r[s.field])+'</b>';box.appendChild(e)}});grid.appendChild(box)}})}}
range.oninput=draw;document.getElementById('play').onclick=e=>{{if(timer){{clearInterval(timer);timer=null;e.target.textContent='▶ 재생'}}else{{e.target.textContent='Ⅱ 정지';timer=setInterval(()=>{{range.value=(Number(range.value)+1)%P.rows.length;draw()}},60)}}}};
document.getElementById('eventRows').innerHTML=P.events.map(e=>'<tr><td>'+e.event_sequence+'</td><td>'+e.time_s+' s</td><td>'+e.source_system+'</td><td>'+e.canonical_tag+'</td><td>'+e.event_state+'</td><td>'+e.quality+'</td></tr>').join('');draw();
</script></body></html>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")
    print(f"NATIVE_OPCUA_DASHBOARD_PASS rows={len(rows)} events={len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
