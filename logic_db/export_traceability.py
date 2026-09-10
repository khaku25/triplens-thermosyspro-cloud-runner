#!/usr/bin/env python3
"""Export a self-contained, read-only Logic -> Tag -> ECMS/DCS traceability viewer."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


def records(db: sqlite3.Connection, sql: str, params=()):
    return [dict(row) for row in db.execute(sql, params)]


def build_payload(db: sqlite3.Connection):
    rules = records(
        db,
        """
        SELECT l.*,
               CASE
                 WHEN EXISTS (SELECT 1 FROM logic_tag_link x WHERE x.logic_id=l.logic_id)
                   THEN 'MODEL_TAG_LINKED'
                 WHEN l.implementation_readiness='SCENARIO_SOURCE_REQUIRED'
                   THEN 'SOURCE_REQUIRED'
                 ELSE 'NO_SOURCE_DECLARED'
               END AS trace_status
        FROM v_active_logic l
        ORDER BY l.platform,l.system,l.priority_rank,l.logic_id
        """,
    )
    links = records(
        db,
        """
        SELECT x.logic_id,x.source_kind,x.source_ordinal,s.source_name,
               x.tag_id,x.mapping_method,x.source_unit,x.target_unit,
               x.unit_transform,x.verification_status,
               t.record_type,t.platform AS tag_platform,t.system AS tag_system,
               t.equipment_id,t.signal_name,t.description_ko AS tag_description_ko,
               t.unit,t.model_mapping,t.canonical_signal,t.status AS tag_status
        FROM logic_tag_link x
        JOIN logic_source s
          ON s.logic_id=x.logic_id
         AND s.source_kind=x.source_kind
         AND s.ordinal=x.source_ordinal
        JOIN tag_master t ON t.tag_id=x.tag_id
        ORDER BY x.logic_id,x.source_ordinal,x.source_kind
        """,
    )
    runtime = records(
        db,
        """
        SELECT r.*,
               max(CASE WHEN x.link_role='SOURCE_SIGNAL' THEN x.tag_id END) AS source_tag_id,
               max(CASE WHEN x.link_role='ALARM_OUTPUT' THEN x.tag_id END) AS alarm_output_tag_id
        FROM runtime_alarm_rule r
        LEFT JOIN runtime_tag_link x ON x.rule_id=r.rule_id
        GROUP BY r.rule_id
        ORDER BY r.system,r.rule_id
        """,
    )
    ports = records(db, "SELECT * FROM v_ecms_ports ORDER BY direction,signal_name")
    drawings = records(
        db,
        """
        SELECT m.tag_id,m.drawing_id,m.drawing_tag_id,m.equipment_reference,
               m.mapping_confidence,m.verification_status,d.drawing_type,d.title,
               d.revision,d.source_file
        FROM tag_drawing_map m
        JOIN drawing_reference d ON d.drawing_id=m.drawing_id
        ORDER BY m.drawing_id,m.drawing_tag_id,m.tag_id
        """,
    )
    validation = records(db, "SELECT * FROM validation_result ORDER BY check_id")
    by_logic = {}
    for link in links:
        by_logic.setdefault(link["logic_id"], []).append(link)
    for rule in rules:
        rule["source_links"] = by_logic.get(rule["logic_id"], [])
        rule["execution_layer"] = "SIMULINK_ECMS_CANDIDATE" if rule["platform"] == "ECMS" else "PROGRAM_A_DCS"

    summary = {
        "active_logic": len(rules),
        "source_linked_logic": sum(r["trace_status"] == "MODEL_TAG_LINKED" for r in rules),
        "source_required_logic": sum(r["trace_status"] != "MODEL_TAG_LINKED" for r in rules),
        "runtime_rules": len(runtime),
        "ecms_ports": len(ports),
        "ecms_bound_ports": sum(bool(str(p.get("bound_tag") or "").strip()) for p in ports),
        "drawing_links": len(drawings),
        "validation_passed": sum(bool(v["passed"]) for v in validation),
        "validation_total": len(validation),
    }
    return {
        "summary": summary,
        "rules": rules,
        "runtime": runtime,
        "ports": ports,
        "drawings": drawings,
        "validation": validation,
        "scope_note": "활성 로직만 표시합니다. Simulink 내부 포트 연결과 외부 물리 태그 배선은 구분합니다.",
    }


HTML = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TripLens 로직·태그 추적기</title>
<style>
:root{--navy:#101d33;--navy2:#172a48;--line:#c9d1dc;--bg:#eef1f5;--card:#fff;--red:#c91f2c;--orange:#e56b13;--yellow:#e6a400;--blue:#1261a0;--green:#147a4d;--gray:#667085;--ink:#172033}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Malgun Gothic","맑은 고딕",Arial,sans-serif;font-size:14px}
header{background:var(--navy);color:#fff;padding:18px 22px;border-bottom:5px solid #263f67}h1{font-size:22px;margin:0 0 5px}.sub{color:#c7d2e3;font-size:12px}
.cards{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:10px;padding:14px 18px}.card{background:#fff;border:1px solid var(--line);border-left:5px solid var(--blue);padding:12px}.card b{font-size:22px;display:block}.card span{font-size:11px;color:var(--gray)}
.tabs{display:flex;gap:4px;padding:0 18px}.tab{border:1px solid #aeb8c7;background:#dce2ea;color:#2a3a52;padding:9px 13px;font-weight:700;cursor:pointer}.tab.on{background:var(--navy2);color:#fff;border-color:var(--navy2)}
.toolbar{display:grid;grid-template-columns:minmax(220px,2fr) repeat(4,minmax(120px,1fr));gap:8px;padding:12px 18px;background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}input,select{width:100%;border:1px solid #aeb8c7;background:#fff;padding:9px;color:var(--ink)}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 420px;min-height:580px}.gridwrap{overflow:auto;padding:12px 18px}.detail{background:#fff;border-left:1px solid var(--line);padding:16px;overflow:auto}.detail h2{font-size:17px;margin:0 0 12px}.detail .muted{color:var(--gray)}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line)}th{position:sticky;top:0;background:#dce2ea;text-align:left;padding:9px;border-bottom:2px solid #98a4b5;font-size:12px}td{padding:8px;border-bottom:1px solid #e2e6ec;vertical-align:top}tbody tr{cursor:pointer}tbody tr:hover{background:#edf5ff}.id{font-family:Consolas,monospace;font-weight:700}.badge{display:inline-block;padding:3px 6px;color:#fff;font-size:10px;font-weight:700}.b-red{background:var(--red)}.b-orange{background:var(--orange)}.b-yellow{background:var(--yellow);color:#281f00}.b-blue{background:var(--blue)}.b-green{background:var(--green)}.b-gray{background:var(--gray)}
.chain{display:grid;gap:8px}.node{border:1px solid var(--line);border-left:5px solid var(--blue);padding:10px;background:#f8fafc}.node h3{font-size:12px;margin:0 0 7px;color:#34445e}.node code{white-space:pre-wrap;overflow-wrap:anywhere;font-family:Consolas,monospace;font-size:11px}.arrow{text-align:center;color:#73829a;font-weight:700}.kv{display:grid;grid-template-columns:105px 1fr;gap:5px 9px;font-size:12px}.kv b{color:#526178}.warn{border-left-color:var(--orange);background:#fff7ee}.ok{border-left-color:var(--green);background:#f1fbf6}.empty{padding:28px;background:#fff;border:1px solid var(--line);color:var(--gray)}.hide{display:none}.legend{padding:8px 18px;font-size:11px;color:#5e6a7c;background:#fff;border-bottom:1px solid var(--line)}
@media(max-width:950px){.cards{grid-template-columns:repeat(2,1fr)}.toolbar{grid-template-columns:1fr 1fr}.layout{grid-template-columns:1fr}.detail{border-left:0;border-top:1px solid var(--line)}.tabs{overflow:auto}.tab{white-space:nowrap}}
</style></head><body>
<header><h1>TripLens 로직·태그 추적기</h1><div class="sub">활성 로직 기준 · 물리출력 → Tag Master → 입력 → 로직 → 출력/알람 → 도면</div></header>
<section class="cards" id="cards"></section>
<nav class="tabs"><button class="tab on" data-tab="logic">활성 로직</button><button class="tab" data-tab="runtime">실행 알람</button><button class="tab" data-tab="ports">ECMS 포트</button><button class="tab" data-tab="drawing">P&amp;ID/SLD</button></nav>
<div class="legend">초록=태그까지 연결 · 주황=실제 입력/도면 연결 대기 · 이 화면은 연결 상태를 숨기지 않고 그대로 표시합니다.</div>
<section class="toolbar" id="toolbar"><input id="q" placeholder="로직 ID, 태그, 설비, 알람 검색"><select id="platform"><option value="">전체 플랫폼</option></select><select id="system"><option value="">전체 계통</option></select><select id="type"><option value="">전체 유형</option></select><select id="status"><option value="">전체 연결상태</option><option>MODEL_TAG_LINKED</option><option>SOURCE_REQUIRED</option><option>NO_SOURCE_DECLARED</option></select></section>
<main class="layout"><div class="gridwrap" id="grid"></div><aside class="detail" id="detail"><h2>항목을 선택하세요</h2><p class="muted">행을 누르면 단계별 연결과 단위 변환, 검증 상태를 볼 수 있습니다.</p></aside></main>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
const D=JSON.parse(document.getElementById('payload').textContent);let tab='logic';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const badge=(v,c='b-gray')=>`<span class="badge ${c}">${esc(v||'-')}</span>`;
const sev=v=>['TRIP'].includes(v)?'b-red':['HH','LL'].includes(v)?'b-orange':['H','L'].includes(v)?'b-yellow':['OPERATION'].includes(v)?'b-blue':'b-gray';
const st=v=>v==='MODEL_TAG_LINKED'?'b-green':v==='MIGRATED_V1'?'b-green':v==='CONNECTED_TO_CORE'?'b-green':'b-orange';
document.getElementById('cards').innerHTML=[['활성 로직',D.summary.active_logic],['태그 연결 로직',D.summary.source_linked_logic],['입력 확인 필요',D.summary.source_required_logic],['실행 알람',D.summary.runtime_rules],['ECMS 포트',D.summary.ecms_ports],['도면 연결',D.summary.drawing_links]].map(x=>`<div class="card"><b>${x[1]}</b><span>${x[0]}</span></div>`).join('');
function options(id,vals,label){document.getElementById(id).innerHTML=`<option value="">${label}</option>`+[...new Set(vals.filter(Boolean))].sort().map(x=>`<option>${esc(x)}</option>`).join('')}
options('platform',D.rules.map(x=>x.platform),'전체 플랫폼');options('system',D.rules.map(x=>x.system),'전체 계통');options('type',D.rules.map(x=>x.alarm_type),'전체 유형');
for(const e of document.querySelectorAll('.tab'))e.onclick=()=>{document.querySelector('.tab.on').classList.remove('on');e.classList.add('on');tab=e.dataset.tab;render()};
for(const id of ['q','platform','system','type','status'])document.getElementById(id).oninput=render;
function filtered(){const q=document.getElementById('q').value.toLowerCase(),p=platform.value,s=system.value,t=type.value,z=status.value;return D.rules.filter(r=>{const hay=JSON.stringify(r).toLowerCase();return(!q||hay.includes(q))&&(!p||r.platform===p)&&(!s||r.system===s)&&(!t||r.alarm_type===t)&&(!z||r.trace_status===z)})}
function render(){toolbar.classList.toggle('hide',tab!=='logic');if(tab==='logic')return renderLogic();if(tab==='runtime')return renderRuntime();if(tab==='ports')return renderPorts();renderDrawing()}
function renderLogic(){const rows=filtered();grid.innerHTML=`<table><thead><tr><th>ID</th><th>플랫폼/계통</th><th>설비</th><th>유형</th><th>알람</th><th>입력→태그</th></tr></thead><tbody>${rows.map(r=>`<tr onclick="showRule('${r.logic_id}')"><td class="id">${r.logic_id}</td><td>${esc(r.platform)}<br><small>${esc(r.system)}</small></td><td>${esc(r.equipment)}</td><td>${badge(r.alarm_type,sev(r.alarm_type))}</td><td>${esc(r.alarm_text_ko)}</td><td>${badge(r.trace_status,st(r.trace_status))}</td></tr>`).join('')}</tbody></table><p>${rows.length}개 표시</p>`}
window.showRule=id=>{const r=D.rules.find(x=>x.logic_id===id),models=r.source_links.filter(x=>x.source_kind==='MODEL_VARIABLE'),tags=r.source_links.filter(x=>x.source_kind==='TAG'),draw=D.drawings.filter(x=>tags.some(t=>t.tag_id===x.tag_id));const noSrc=r.trace_status!=='MODEL_TAG_LINKED';detail.innerHTML=`<h2>${esc(r.logic_id)} · ${esc(r.alarm_text_ko)}</h2><div class="kv"><b>실행 영역</b><span>${esc(r.execution_layer)}</span><b>검증</b><span>${esc(r.validation_status)}</span><b>구현 준비</b><span>${esc(r.implementation_readiness)}</span></div><hr><div class="chain"><div class="node ${noSrc?'warn':'ok'}"><h3>1. 물리/사건 입력</h3>${models.length?models.map(x=>`<code>${esc(x.source_name)} [${esc(x.source_unit)}]</code>`).join('<br>'):`<b>입력 연결 필요</b><br><small>${esc(r.implementation_readiness)}</small>`}</div><div class="arrow">↓</div><div class="node ${tags.length?'ok':'warn'}"><h3>2. Tag Master</h3>${tags.length?tags.map(x=>`<code>${esc(x.tag_id)} [${esc(x.target_unit)}]</code><br><small>${esc(x.unit_transform)} · ${esc(x.verification_status)}</small>`).join('<br>'):'<b>연결 태그 없음</b>'}</div><div class="arrow">↓</div><div class="node"><h3>3. 활성 로직</h3><code>${esc(r.condition_expression)}</code><div class="kv"><b>설정값</b><span>${esc(r.threshold_value??'-')} ${esc(r.threshold_unit||'')}</span><b>지연</b><span>${esc(r.delay_s)} s</span><b>Hysteresis</b><span>${esc(r.hysteresis_raw||'-')}</span></div></div><div class="arrow">↓</div><div class="node"><h3>4. 출력/알람</h3>${badge(r.alarm_type,sev(r.alarm_type))} ${esc(r.alarm_text_ko)}<br><small>${esc(r.trip_action||'표시/기록')}</small></div><div class="arrow">↓</div><div class="node ${draw.length?'ok':'warn'}"><h3>5. P&amp;ID/SLD</h3>${draw.length?draw.map(x=>`<code>${esc(x.drawing_id)} / ${esc(x.drawing_tag_id)}</code>`).join('<br>'):'도면 태그 매칭 대기'}</div></div>`}
function renderRuntime(){grid.innerHTML=`<table><thead><tr><th>Rule</th><th>시스템</th><th>물리/명령 태그</th><th>조건</th><th>출력 알람 태그</th></tr></thead><tbody>${D.runtime.map(r=>`<tr><td class="id">${r.rule_id}</td><td>${r.system}</td><td><code>${esc(r.source_tag_id)}</code></td><td>${esc(r.direction)} ${esc(r.threshold_value)} ${esc(r.unit)} / ${esc(r.delay_s)}s</td><td><code>${esc(r.alarm_output_tag_id)}</code></td></tr>`).join('')}</tbody></table>`;detail.innerHTML=`<h2>실행 알람 ${D.summary.runtime_rules}개</h2><p>Program A가 실제 CSV 생성 시 사용하는 배포 규칙입니다. Logic Master의 전체 후보 수와 구분합니다.</p>`}
function renderPorts(){grid.innerHTML=`<table><thead><tr><th>방향</th><th>포트</th><th>출처 계층</th><th>역할</th><th>태그 바인딩</th><th>상태</th></tr></thead><tbody>${D.ports.map(r=>`<tr><td>${badge(r.direction,r.direction==='IN'?'b-blue':'b-red')}</td><td class="id">${esc(r.signal_name)}</td><td>${esc(r.source_layer)}</td><td>${esc(r.role)}</td><td><code>${esc(r.bound_tag||'실제 외부 태그 연결 대기')}</code></td><td>${badge(r.status,st(r.status))}</td></tr>`).join('')}</tbody></table>`;detail.innerHTML=`<h2>ECMS Simulink 포트</h2><p>포트가 모델 내부 A Logic Core에 연결된 것과, 외부 전기·열물리 태그가 포트에 배선된 것은 별도 상태입니다.</p><div class="kv"><b>총 포트</b><span>${D.summary.ecms_ports}</span><b>외부 태그 지정</b><span>${D.summary.ecms_bound_ports}</span><b>미지정</b><span>${D.summary.ecms_ports-D.summary.ecms_bound_ports}</span></div>`}
function renderDrawing(){if(!D.drawings.length){grid.innerHTML='<div class="empty"><b>등록된 P&amp;ID/SLD 연결이 아직 없습니다.</b><br><br>도면 확보 후 Tag Master의 tag_id와 drawing_tag_id를 매칭하면 여기에 자동 표시됩니다.</div>'}else{grid.innerHTML=`<table><thead><tr><th>도면</th><th>도면 태그</th><th>Tag Master</th><th>설비</th><th>상태</th></tr></thead><tbody>${D.drawings.map(r=>`<tr><td>${esc(r.drawing_id)}</td><td>${esc(r.drawing_tag_id)}</td><td class="id">${esc(r.tag_id)}</td><td>${esc(r.equipment_reference)}</td><td>${esc(r.verification_status)}</td></tr>`).join('')}</tbody></table>`}detail.innerHTML='<h2>P&amp;ID/SLD 매칭</h2><p>도면 연결이 0개일 때도 완료된 것처럼 표시하지 않습니다.</p>'}
render();
</script></body></html>'''


def write_csv(path: Path, payload):
    fields = [
        "logic_id", "platform", "system", "subsystem", "equipment", "alarm_type",
        "alarm_text_ko", "trace_status", "execution_layer", "source_kind",
        "source_name", "tag_id", "source_unit", "target_unit", "unit_transform",
        "verification_status", "condition_expression", "threshold_value",
        "threshold_unit", "delay_s", "validation_status", "implementation_readiness",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rule in payload["rules"]:
            links = rule["source_links"] or [{}]
            for link in links:
                writer.writerow({key: link.get(key, rule.get(key, "")) for key in fields})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path, nargs="?", default=Path("outputs/triplens_logic_master_v2.sqlite"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(args.database)
    db.row_factory = sqlite3.Row
    try:
        payload = build_payload(db)
    finally:
        db.close()
    if payload["summary"]["active_logic"] <= 0:
        raise ValueError("Trace viewer requires a non-empty active Logic Core")
    if payload["summary"]["validation_passed"] != payload["summary"]["validation_total"]:
        raise ValueError("Trace viewer refuses a Logic DB with failed validations")
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (args.output_dir / "active_logic_trace.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(args.output_dir / "active_logic_trace.csv", payload)
    (args.output_dir / "logic_traceability.html").write_text(
        HTML.replace("__PAYLOAD__", compact), encoding="utf-8"
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
