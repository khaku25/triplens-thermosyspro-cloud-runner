/* TripLens report export helper.
 *
 * Builds isolated, evidence-linked incident report output from the current
 * analysis state. Source EVENT/RAW data are never mutated and export never
 * reruns the analysis.
 */
(function (root, factory) {
  let contract = root && root.TripLensAIOutputContract;
  if (typeof module === 'object' && module.exports) {
    try { contract = require('./triplens_ai_output_contract.js'); } catch (_) { contract = null; }
  }
  const api = factory(contract);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.TripLensReportExport = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (contract) {
  'use strict';

  const PINPOINT_COLUMNS = [
    'run_id', 'pinpoint_rank', 'causal_stage', 'claim', 'disposition',
    'source_system', 'event_id', 'original_time', 'aligned_time', 'equipment',
    'event_tag', 'canonical_tag', 'value', 'unit', 'state', 'evidence_role',
    'logic_id', 'mapping_status', 'counter_evidence', 'recovery_status',
    'review_required',
  ];

  const FAILURE_REPORT_COLUMNS = ['구분', '항목', '내용', '상태', '근거 ID', '관련 태그', '기록 시각', '비고'];

  const FAILURE_REPORT_SECTIONS = [
    '개요',
    '사고 발생 전 운전 현황',
    '장애 현상',
    '시간대별 조치사항',
    '발생 원인',
    '조치 결과',
    '추정 원인 및 미확인 사항',
    '재발방지 대책 — 검토 권고사항',
    '증거자료',
  ];

  const WORKSPACE_REPORT_SECTIONS = [
    '개요',
    '사고 발생 전 운전 현황',
    '장애 현상',
    '시간대별 사건·자동동작(SOE)',
    '발생 원인',
    '운전원·정비 조치사항',
    '조치 결과 및 복구 판정',
    '추정 원인 및 미확인 사항',
    '재발방지 대책 — 검토 권고사항',
    '증거자료',
  ];

  const KNOWN_SECTIONS = [
    ['incident_summary', 'Incident Summary'],
    ['critical_events', 'Critical Events'],
    ['primary_cause', 'Primary Cause'],
    ['direct_trigger', 'Direct Trigger'],
    ['propagation', 'Propagation'],
    ['causal_chain', 'Causal Chain'],
    ['key_evidence', 'Key Evidence'],
    ['recovery_check', 'Recovery Check'],
    ['gemini_analysis', 'Gemini Analysis'],
  ];

  const STATUS_LABELS = {
    CONFIRMED: '확인',
    CANDIDATE: '분석 항목',
    OBSERVED: '관측',
    UNKNOWN: '확인 필요',
  };

  function esc(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function csvCell(value) {
    const text = String(value ?? '');
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function formulaSafeCsvCell(value) {
    let text = String(value ?? '');
    if (/^[\s]*[=+@-]/.test(text)) text = "'" + text;
    return csvCell(text);
  }

  function asText(value) {
    if (value == null) return '';
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (Array.isArray(value)) return value.map(asText).filter(Boolean).join('\n');
    return Object.entries(value).map(([k, v]) => `${k}: ${asText(v)}`).join('\n');
  }

  function list(value) {
    if (value == null || value === '') return [];
    return Array.isArray(value) ? value.slice() : [value];
  }

  function joinList(value, separator = ', ') {
    return list(value).map(asText).filter(Boolean).join(separator);
  }

  function statusLabel(status) {
    const key = String(status || 'UNKNOWN').toUpperCase();
    return STATUS_LABELS[key] || STATUS_LABELS.UNKNOWN;
  }

  function normalizeSections(report) {
    if (Array.isArray(report.sections)) {
      return report.sections.map((section, index) => ({
        id: section.id || `section-${index + 1}`,
        title: section.title || section.id || `Section ${index + 1}`,
        value: section.value ?? section.content ?? section.data ?? '',
      }));
    }
    return KNOWN_SECTIONS
      .filter(([key]) => report[key] !== undefined)
      .map(([key, title]) => ({ id: key, title, value: report[key] }));
  }

  function normalizedAnalysis(report) {
    if (contract?.normalizeAnalysis) return contract.normalizeAnalysis(report || {});
    return {
      critical_events: list(report?.critical_events),
      primary_cause: report?.primary_cause || {},
      direct_trigger: report?.direct_trigger || {},
      propagation: list(report?.propagation),
      causal_chain: list(report?.causal_chain),
      counter_evidence: list(report?.counter_evidence),
      additional_evidence_required: list(report?.additional_evidence_required || report?.additional_evidence),
      review_recommendations: list(report?.review_recommendations || report?.recommendations),
      verification_gate: String(report?.verification_gate || 'HOLD').toUpperCase(),
      finality: {
        can_mark_final_confirmed: String(report?.verification_gate || '').toUpperCase() === 'PASS',
        output_label: String(report?.verification_gate || '').toUpperCase() === 'PASS' ? '고장보고서 검토본' : '고장보고서 초안',
        verification_label: String(report?.verification_gate || '').toUpperCase() === 'PASS' ? '검증 통과' : '검증 미완료',
      },
    };
  }

  function claimField(claim, key, fallback = '') {
    if (!claim || typeof claim !== 'object') return fallback;
    return claim[key] ?? fallback;
  }

  function causeRow(label, english, claim) {
    return `<tr><th>${esc(label)}<br><span class="en">${esc(english)}</span></th><td>${esc(claimField(claim, 'claim', ''))}</td><td>${esc(statusLabel(claimField(claim, 'status', 'UNKNOWN')))}</td><td>${esc(joinList(claimField(claim, 'evidence_ids', [])))}</td><td>${esc(joinList(claimField(claim, 'related_tags', [])))}</td><td>${esc(claimField(claim, 'recorded_time', ''))}</td><td>${esc(claimField(claim, 'logic_master_status', ''))}</td></tr>`;
  }

  function chronology(report) {
    return list(report.chronological_events || report.soe || report.timeline || report.actions);
  }

  function chronologyRows(report) {
    return chronology(report).map((item, index) => {
      const obj = item && typeof item === 'object' ? item : { claim: asText(item) };
      const ids = obj.evidence_ids || obj.evidenceIds || list(obj.evidence).map((e) => e?.event_id || e?.evidence_id).filter(Boolean);
      const tags = obj.related_tags || obj.relatedTags || obj.tags || [];
      return `<tr><td>${index + 1}</td><td>${esc(obj.recorded_time ?? obj.aligned_time ?? obj.time ?? '')}</td><td>${esc(obj.category || obj.stage || obj.source || '')}</td><td>${esc(obj.claim || obj.description || obj.summary || '')}</td><td>${esc(statusLabel(obj.status || obj.disposition || 'UNKNOWN'))}</td><td>${esc(joinList(ids))}</td><td>${esc(joinList(tags))}</td></tr>`;
    }).join('');
  }

  function pinpointRows(report) {
    if (Array.isArray(report.pinpoints)) return report.pinpoints;
    const runId = report.run_id || report.metadata?.run_id || '';
    const sections = normalizeSections(report);
    const rows = [];
    let rank = 1;
    for (const section of sections) {
      const values = Array.isArray(section.value) ? section.value : [section.value];
      for (const value of values) {
        if (value == null || value === '') continue;
        const obj = typeof value === 'object' && !Array.isArray(value) ? value : { claim: asText(value) };
        const evidence = Array.isArray(obj.evidence) && obj.evidence.length ? obj.evidence : [{}];
        for (const ev of evidence) {
          rows.push({
            run_id: runId,
            pinpoint_rank: rank,
            causal_stage: String(obj.causal_stage || section.id || '').toUpperCase(),
            claim: obj.claim || obj.title || obj.summary || asText(value),
            disposition: obj.disposition || obj.status || '',
            source_system: ev.source_system || ev.source || obj.source_system || '',
            event_id: ev.event_id || ev.evidence_id || '',
            original_time: ev.original_time || ev.original_time_s || '',
            aligned_time: ev.aligned_time || ev.aligned_time_s || '',
            equipment: ev.equipment || obj.equipment || '',
            event_tag: ev.event_tag || ev.tag || '',
            canonical_tag: ev.canonical_tag || '',
            value: ev.value ?? '',
            unit: ev.unit || '',
            state: ev.state || '',
            evidence_role: ev.evidence_role || ev.role || '',
            logic_id: ev.logic_id || obj.logic_id || '',
            mapping_status: ev.mapping_status || '',
            counter_evidence: obj.counter_evidence || '',
            recovery_status: obj.recovery_status || '',
            review_required: obj.review_required ?? (String(obj.disposition || '').toUpperCase() === 'REVIEW_REQUIRED'),
          });
        }
        rank += 1;
      }
    }
    return rows;
  }

  function displayTime(item) {
    const wall = String(item?.wall_time_utc || item?.recorded_wall_time || '').trim();
    const clock = wall.match(/T(\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?)/)?.[1] || '';
    const raw = item?.model_time_s ?? item?.recorded_time ?? item?.aligned_time ?? item?.time;
    const seconds = raw === null || raw === undefined || String(raw).trim() === '' ? null : Number(raw);
    const model = seconds !== null && Number.isFinite(seconds) ? `T+${seconds.toFixed(3)} s` : '';
    return { primary: clock || model || '시각 미확인', secondary: clock ? model : '' };
  }

  function shortText(value, limit = 160) {
    const text = String(value || '').trim();
    return text.length > limit ? `${text.slice(0, limit).trimEnd()}…` : text;
  }

  function operatorPhrase(value, limit = 180) {
    let text = String(value || '').trim();
    if (!text) return '';
    const gtStLatch = /((가스\s*터빈|GT).*트립\s*래치.*(증기\s*터빈|ST).*트립\s*래치|(증기\s*터빈|ST).*트립\s*래치.*(가스\s*터빈|GT).*트립\s*래치)/i.test(text);
    if (gtStLatch && /(활성|동작|작동|ACTIVE|LATCH)/i.test(text)) return 'GT·ST Trip Latch 동시 동작';
    if (/외부\s*(?:GT\s*)?(?:Trip|트립)\s*(?:Command|명령).*(?:입력|인가|관측)/i.test(text)) return '외부 Trip Command 입력';
    text = text
      .replace(/model_time_s\s*=?\s*\d+(?:\.\d+)?\s*초에\s*/gi, '')
      .replace(/^\s*\d+(?:\.\d+)?\s*초에\s*/, '')
      .replace(/RAW\s*변화\s*시간구간이\s*Direct Trigger\s*시각과\s*겹칩니다\.?/gi, 'RAW 변화구간 · Direct Trigger 시각 중첩')
      .replace(/선후관계는\s*표본만으로\s*확정할\s*수\s*없습니다\.?/g, '선후관계 미확정')
      .replace(/선후관계를\s*확정할\s*수\s*없습니다\.?/g, '선후관계 미확정')
      .replace(/확인(?:이)?\s*필요합니다\.?/g, '확인 필요')
      .replace(/확인해야\s*합니다\.?/g, '확인 필요')
      .replace(/검토해야\s*합니다\.?/g, '검토 필요')
      .replace(/확정할\s*수\s*없습니다\.?/g, '미확정')
      .replace(/판단할\s*수\s*없습니다\.?/g, '판단 불가')
      .replace(/알\s*수\s*없습니다\.?/g, '미확인')
      .replace(/활성화되었습니다\.?/g, '활성')
      .replace(/동작되었습니다\.?/g, '동작')
      .replace(/작동(?:하였|했)습니다\.?/g, '동작')
      .replace(/관측되었습니다\.?/g, '관측')
      .replace(/기록되었습니다\.?/g, '기록')
      .replace(/입력되었습니다\.?/g, '입력')
      .replace(/인가되었습니다\.?/g, '인가')
      .replace(/없습니다\.?/g, '없음')
      .replace(/있습니다\.?/g, '있음')
      .replace(/입니다\.?$/g, '')
      .replace(/합니다\.?$/g, '')
      .replace(/\.\s+/g, ' · ')
      .replace(/[.]$/, '')
      .replace(/\s+/g, ' ')
      .replace(/\s+([,])/g, '$1')
      .trim();
    return text.length > limit ? `${text.slice(0, limit).trimEnd()}…` : text;
  }

  function operatorClaim(item, stage = '') {
    const tags = new Set(list(item?.related_tags || item?.relatedTags || item?.tags).map(String));
    const source = String(item?.claim || item?.message || item?.description || item?.summary || asText(item));
    const state = String(item?.state || '').toUpperCase();
    const rawValue = item?.value;
    const numericValue = rawValue === null || rawValue === undefined || String(rawValue).trim() === '' ? null : Number(rawValue);
    const active = /ACTIVE|TRIPPED|LATCHED/.test(state) || rawValue === true || numericValue === 1 || /ACTIVE|동작|작동|인가/.test(source);
    const opened = /OPEN|TRIPPED/.test(state) || numericValue === 0 || /\bOPEN\b|개방|개로/.test(source);
    const low = /LOW|ALARM/.test(state) || /\bLOW(?:_LOW)?\b|저하|저유량|저온|하한|\bLL\b/i.test(source);
    if (stage === 'primary' && tags.has('vppExternalTripCommandNative')) return '외부 Trip Command 입력';
    if (stage === 'direct' && active && tags.has('vppGTTripLatch') && tags.has('vppSTTripLatchPublished')) return 'GT·ST Trip Latch 동시 동작';
    if (stage === 'direct' && active && tags.has('vppGTTripLatch')) return 'GT Trip Latch 동작';
    if (stage === 'direct' && active && tags.has('vppSTTripLatchPublished')) return 'ST Trip Latch 동작';
    const mapped = [
      ['vpp52GTClosed', '52GT 차단기 OPEN', opened],
      ['vpp52STClosed', '52ST 차단기 OPEN', opened],
      ['vppGTExhaustMassFlowTH', 'GT 배기유량 LOW', low],
      ['vppGTExhaustTemperatureK', 'GT 배기온도 LOW', low],
      ['vppHPTurbineSteamFlowTH', 'HP 터빈 증기유량 LOW', low],
      ['vppIPTurbineSteamFlowTH', 'IP 터빈 증기유량 LOW', low],
      ['vppLPTurbineSteamFlowTH', 'LP 터빈 증기유량 LOW', low],
    ].find(([tag,,confirmed]) => confirmed && tags.has(tag));
    if (mapped) return mapped[1];
    return operatorPhrase(source
      .replace(/model_time_s\s*=?\s*\d+(?:\.\d+)?\s*초에\s*/gi, '')
      .replace(/\((?:vpp[A-Za-z0-9_.-]+)\)/g, '')
      .replace(/\b(?:태그\s+)?vpp[A-Za-z0-9_.-]+(?:가|이|는|은)?\b/g, '')
      .replace(/1(?:\.0)?\s*\(ACTIVE\)(?:으로)?/gi, 'ACTIVE')
      .replace(/개로\s*\(0(?:\.0)?\)\s*됨/g, '개방')
      .replace(/\s+/g, ' ')
      .replace(/\s+([,.])/g, '$1')
      .trim());
  }

  function editedContent(report, section, item, fallback = '') {
    const row = editedRow(report, section, item);
    return row ? String(row.content ?? row['내용'] ?? fallback) : fallback;
  }

  function editedRow(report, section, item) {
    return list(report?.report_rows).find(value => String(value?.section ?? value?.['구분'] ?? '') === section && String(value?.item ?? value?.['항목'] ?? '') === item);
  }

  function evidenceIds(value) {
    return list(value).flatMap(item => String(item || '').split(';')).map(item => item.trim()).filter(Boolean);
  }

  function equipmentLabel(item) {
    if (item?.equipment) return String(item.equipment);
    const text = `${operatorClaim(item)} ${joinList(item?.related_tags || item?.tags)}`.toUpperCase();
    if (text.includes('52GT')) return '52GT';
    if (text.includes('52ST')) return '52ST';
    if (text.includes('GT')) return 'GT';
    if (text.includes('ST')) return 'ST';
    if (text.includes('DRUM')) return 'HRSG';
    return String(item?.category || item?.stage || 'PLANT');
  }

  function briefTimeline(report, limit = 7) {
    const events = chronology(report).slice();
    const sourceRows = list(report?.report_rows).filter(row => String(row?.section ?? row?.['구분'] ?? '') === '시간대별 사건·자동동작(SOE)');
    const rows = sourceRows.length ? sourceRows.map((row,index) => {
      const wanted = new Set(evidenceIds(row.evidence_ids ?? row['근거 ID']));
      const event = events.find(item => evidenceIds(item.evidence_ids).some(id => wanted.has(id))) || events[index] || {};
      const content = String(row.content ?? row['내용'] ?? '').trim();
      const original = String(event.claim || event.message || '').trim();
      const contentEdited = row.edited === true || (content && content !== original);
      return {...event,claim:content || original,__reportContent:contentEdited,__timeOverride:row.edited === true ? String(row.time || '') : ''};
    }) : events;
    rows.sort((left, right) => {
      const a = Number(left?.model_time_s ?? left?.recorded_time ?? left?.aligned_time ?? left?.time);
      const b = Number(right?.model_time_s ?? right?.recorded_time ?? right?.aligned_time ?? right?.time);
      return (Number.isFinite(a) ? a : Infinity) - (Number.isFinite(b) ? b : Infinity);
    });
    return { visible: rows.slice(0, limit), hiddenCount: Math.max(0, rows.length - limit) };
  }

  function buildReportHtml(report) {
    const analysis = normalizedAnalysis(report);
    const metadata = report.metadata || {};
    const title = '설비 고장 분석보고서';
    const firstCritical = analysis.critical_events[0];
    const incidentTime = displayTime({
      wall_time_utc: report.incident_wall_time || firstCritical?.wall_time_utc,
      model_time_s: report.incident_time || metadata.incident_time || firstCritical?.model_time_s || firstCritical?.recorded_time,
    });
    const primaryOriginal = claimField(analysis.primary_cause, 'claim', '');
    const directOriginal = claimField(analysis.direct_trigger, 'claim', '');
    const primaryRow = editedRow(report, '발생 원인', '선행 원인');
    const directRow = editedRow(report, '발생 원인', '직접 Trip 원인');
    const primarySource = String(primaryRow?.content ?? primaryRow?.['내용'] ?? primaryOriginal);
    const directSource = String(directRow?.content ?? directRow?.['내용'] ?? directOriginal);
    const primaryEdited = Boolean(primaryRow && (primaryRow.edited === true || primarySource !== String(primaryOriginal)));
    const directEdited = Boolean(directRow && (directRow.edited === true || directSource !== String(directOriginal)));
    const primary = (primaryEdited ? shortText(primarySource) : operatorPhrase(operatorClaim(analysis.primary_cause, 'primary'))) || '발생 원인 기록 없음';
    const direct = (directEdited ? shortText(directSource) : operatorPhrase(operatorClaim(analysis.direct_trigger, 'direct'))) || '직접 보호동작 기록 없음';
    const summaryOriginal = report.incident_summary || direct;
    const summaryRow = editedRow(report, '개요', '장애 요약');
    const summarySource = String(summaryRow?.content ?? summaryRow?.['내용'] ?? summaryOriginal);
    const summaryEdited = Boolean(summaryRow && (summaryRow.edited === true || summarySource !== String(summaryOriginal)));
    const summary = summaryEdited ? shortText(summarySource, 180) : operatorPhrase(summarySource, 180);
    const equipment = report.equipment || metadata.equipment || [...new Set(analysis.critical_events.map(equipmentLabel).filter(Boolean))].slice(0,3).join(' · ') || 'PLANT';
    const timeline = briefTimeline(report, 7);
    const timelineRows = timeline.visible.map(item => {
      const when = item.__timeOverride ? {primary:item.__timeOverride,secondary:''} : displayTime(item);
      const claim = item.__reportContent ? shortText(item.claim) : operatorPhrase(operatorClaim(item));
      return `<tr class="timeline-row"><td><b>${esc(when.primary)}</b>${when.secondary?`<small>${esc(when.secondary)}</small>`:''}</td><td>${esc(equipmentLabel(item))}</td><td>${esc(claim)}</td></tr>`;
    }).join('');
    const recoveryRows = list(report.report_rows).filter(row => ['운전원·정비 조치사항','조치 결과 및 복구 판정'].includes(String(row?.section || '')));
    const recoveryBody = recoveryRows.length
      ? recoveryRows.map(row => `<tr><th>${esc(row.item || '')}</th><td>${esc(row.content || '기록 없음')}${row.time?`<small>${esc(row.time)}</small>`:''}${row.note?`<small>${esc(row.note)}</small>`:''}</td></tr>`).join('')
      : `<tr><th>복구 상태</th><td>${esc(asText(report.recovery_check || '기록 없음'))}</td></tr>`;

    return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<style>
@page{size:A4;margin:0}
*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#172f3f;font-family:"Noto Sans KR","Malgun Gothic",Arial,sans-serif;font-size:10.5pt;line-height:1.42}
.report{width:210mm;min-height:297mm;margin:0 auto;padding:11mm 12mm 12mm}.doc-head{border-top:4px solid #173e55;border-bottom:1px solid #8ea0ab;padding:0 0 4mm;margin-bottom:5mm}.doc-title{font-size:20pt;font-weight:800;color:#102f43;margin-bottom:3mm}.doc-meta{display:grid;grid-template-columns:repeat(3,1fr);gap:2mm}.doc-meta div{background:#eef3f5;border-left:3px solid #2a657f;padding:2.5mm}.doc-meta span{display:block;font-size:8pt;color:#5e7380;margin-bottom:.7mm}.doc-meta b{font-size:10pt}.section{margin:0 0 4.5mm;break-inside:avoid;page-break-inside:avoid}.section h2{font-size:12pt;margin:0 0 2mm;padding-bottom:1.5mm;border-bottom:1.5px solid #234b62;color:#15384d}.cause-grid{display:grid;grid-template-columns:1fr 1fr;gap:3mm}.cause-box{border:1px solid #aebcc4;padding:3mm;min-height:23mm}.cause-box span{display:block;color:#5d7280;font-size:8.5pt;margin-bottom:1.2mm}.cause-box strong{font-size:13pt;color:#12364b}.cause-box small{display:block;margin-top:1.5mm;color:#607582}.summary-line{padding:3mm;border:1px solid #aebcc4;background:#f7f9fa;font-size:11pt;font-weight:700}
table{width:100%;border-collapse:collapse;table-layout:fixed}thead{display:table-header-group}tr{break-inside:avoid-page;page-break-inside:avoid}th,td{border:1px solid #b8c3c9;padding:2.1mm;vertical-align:top;overflow-wrap:anywhere}th{background:#edf2f4;text-align:left;font-weight:700}td small{display:block;color:#6a7e89;font-size:8pt;margin-top:.5mm}.timeline th:nth-child(1){width:31%}.timeline th:nth-child(2){width:18%}.timeline td:nth-child(3){font-weight:650}.note{font-size:8.5pt;color:#586d79;margin-top:1.5mm}.footer{margin-top:5mm;padding-top:2mm;border-top:1px solid #aebbc3;font-size:8pt;color:#607480}
@media print{html,body{width:210mm;height:auto;overflow:visible}.report{margin:0}.section,table,tr{overflow:visible!important;max-height:none!important;height:auto!important}}
</style></head><body><main class="report">
<header class="doc-head"><div class="doc-title">${esc(title)}</div><div class="doc-meta"><div><span>발생 시각</span><b>${esc(incidentTime.primary)}</b>${incidentTime.secondary?`<small>${esc(incidentTime.secondary)}</small>`:''}</div><div><span>대상 설비</span><b>${esc(equipment)}</b></div><div><span>입력 자료</span><b>${esc(metadata.event_file || 'EVENT.csv')} + ${esc(metadata.raw_file || 'RAW.csv')}</b></div></div></header>
<section class="section"><h2>1. 사고 개요</h2><div class="summary-line">${esc(operatorClaim({claim:summary}) || direct)}</div></section>
<section class="section"><h2>2. 발생 원인</h2><div class="cause-grid"><div class="cause-box"><span>발생 원인</span><strong>${esc(primary)}</strong><small>${esc(displayTime(analysis.primary_cause).primary)}</small></div><div class="cause-box"><span>직접 보호동작</span><strong>${esc(direct)}</strong><small>${esc(displayTime(analysis.direct_trigger).primary)}</small></div></div></section>
<section class="section"><h2>3. 시간순 사고 경위</h2><table class="timeline"><thead><tr><th>시간</th><th>설비 / 구분</th><th>발생 내용</th></tr></thead><tbody>${timelineRows || '<tr><td colspan="3">사고 기록 없음</td></tr>'}</tbody></table>${timeline.hiddenCount?`<div class="note">후속 기록 ${timeline.hiddenCount}건 · 상세 분석 데이터 참조</div>`:''}</section>
<section class="section"><h2>4. 복구조치 및 확인사항</h2><table><tbody>${recoveryBody}</tbody></table></section>
<footer class="footer">TripLens READ-ONLY 사고분석 · 상세 근거는 CSV 내보내기에서 확인</footer>
</main></body></html>`;
  }

  function printReport(report) {
    if (typeof window === 'undefined' || !window.open) throw new Error('printReport requires a browser window');
    const popup = window.open('', '_blank');
    if (!popup) throw new Error('Report window was blocked by the browser');
    try { popup.opener = null; } catch (_) { /* cross-origin hardening is best effort */ }
    popup.document.open();
    popup.document.write(buildReportHtml(report));
    popup.document.close();
    const printWhenReady = () => {
      const fonts = popup.document.fonts && popup.document.fonts.ready ? popup.document.fonts.ready : Promise.resolve();
      fonts.finally(() => { popup.focus(); popup.print(); });
    };
    if (popup.document.readyState === 'complete') printWhenReady();
    else popup.addEventListener('load', printWhenReady, { once: true });
    return popup;
  }

  function buildPinpointCsv(report) {
    const rows = pinpointRows(report);
    return [PINPOINT_COLUMNS.join(','), ...rows.map((row) => PINPOINT_COLUMNS.map((column) => csvCell(row[column])).join(','))].join('\r\n') + '\r\n';
  }

  function reportRow(section, item, content, status, evidenceIds, relatedTags, recordedTime, note) {
    return {
      '구분': section, '항목': item, '내용': asText(content), '상태': status ? statusLabel(status) : '',
      '근거 ID': joinList(evidenceIds), '관련 태그': joinList(relatedTags), '기록 시각': recordedTime || '', '비고': note || '',
    };
  }

  function failureReportRows(report) {
    const analysis = normalizedAnalysis(report);
    const rows = [];
    const metadata = report.metadata || {};
    rows.push(reportRow('개요', '발생 시각', report.incident_time || metadata.incident_time || claimField(analysis.critical_events[0], 'recorded_time', ''), '', [], [], '', ''));
    rows.push(reportRow('개요', '장애 요약', report.incident_summary || '', '', [], [], '', ''));
    if (report.operating_status && typeof report.operating_status === 'object') {
      for (const [key, value] of Object.entries(report.operating_status)) rows.push(reportRow('운전 현황', key, value, 'OBSERVED', [], [], '', ''));
    }
    if (analysis.critical_events[0]) {
      const item = analysis.critical_events[0];
      rows.push(reportRow('장애 현상', '최초 Event', item.claim, item.status, item.evidence_ids, item.related_tags, item.recorded_time, ''));
    }
    chronology(report).forEach((item, index) => {
      const obj = item && typeof item === 'object' ? item : { claim: asText(item) };
      rows.push(reportRow('시간대별 조치사항', `SOE ${index + 1}`, obj.claim || obj.description || obj.summary || '', obj.status || obj.disposition || 'UNKNOWN', obj.evidence_ids || [], obj.related_tags || obj.tags || [], obj.recorded_time || obj.aligned_time || obj.time || '', obj.category || obj.stage || ''));
    });
    analysis.critical_events.forEach((item, index) => rows.push(reportRow('Critical Events', `Critical Event ${index + 1}`, item.claim, item.status, item.evidence_ids, item.related_tags, item.recorded_time, item.logic_master_status)));
    rows.push(reportRow('Primary Cause', '선행 원인', analysis.primary_cause.claim, analysis.primary_cause.status, analysis.primary_cause.evidence_ids, analysis.primary_cause.related_tags, analysis.primary_cause.recorded_time, `Logic Master: ${analysis.primary_cause.logic_master_status}; AI confidence: ${analysis.primary_cause.ai_confidence ?? ''}`));
    rows.push(reportRow('Direct Trigger', '직접 Trip 원인', analysis.direct_trigger.claim, analysis.direct_trigger.status, analysis.direct_trigger.evidence_ids, analysis.direct_trigger.related_tags, analysis.direct_trigger.recorded_time, `Logic Master: ${analysis.direct_trigger.logic_master_status}; AI confidence: ${analysis.direct_trigger.ai_confidence ?? ''}`));
    analysis.propagation.forEach((item, index) => rows.push(reportRow('Propagation', `파급 결과 ${index + 1}`, item.claim, item.status, item.evidence_ids, item.related_tags, item.recorded_time, item.logic_master_status)));
    analysis.causal_chain.forEach((item, index) => rows.push(reportRow('Causal Chain', `인과 단계 ${index + 1}`, typeof item === 'object' ? (item.claim || item.description || asText(item)) : item, '', [], [], '', '')));
    rows.push(reportRow('조치 결과', '복구 상태', report.recovery_check || 'UNKNOWN', 'UNKNOWN', [], [], '', analysis.verification_gate === 'HOLD' ? '검증 미완료' : ''));
    analysis.counter_evidence.forEach((item, index) => rows.push(reportRow('반대 근거', `반대 근거 ${index + 1}`, item, 'OBSERVED', [], [], '', '')));
    analysis.additional_evidence_required.forEach((item, index) => rows.push(reportRow('추가 확인 필요', `확인 항목 ${index + 1}`, item, 'UNKNOWN', [], [], '', '추가 확인 필요')));
    analysis.review_recommendations.forEach((item, index) => rows.push(reportRow('재발방지 대책', `검토 권고사항 ${index + 1}`, item.claim || asText(item), item.status || 'CANDIDATE', item.evidence_ids || [], item.related_tags || [], '', item.note || '담당자 승인 필요')));
    return rows;
  }

  function buildFailureReportCsv(report) {
    const rows = failureReportRows(report);
    return [FAILURE_REPORT_COLUMNS.join(','), ...rows.map((row) => FAILURE_REPORT_COLUMNS.map((column) => formulaSafeCsvCell(row[column])).join(','))].join('\r\n') + '\r\n';
  }

  function downloadText(filename, text, mimeType) {
    if (typeof document === 'undefined') throw new Error('downloadText requires a browser document');
    const blob = new Blob([text], { type: mimeType || 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = filename; link.style.display = 'none';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function downloadPinpointCsv(report, filename) {
    downloadText(filename || '상세분석데이터.csv', '\ufeff' + buildPinpointCsv(report), 'text/csv;charset=utf-8');
  }

  function downloadFailureReportCsv(report, filename) {
    downloadText(filename || '고장분석보고서.csv', '\ufeff' + buildFailureReportCsv(report), 'text/csv;charset=utf-8');
  }

  return {
    PINPOINT_COLUMNS,
    FAILURE_REPORT_COLUMNS,
    normalizeSections,
    buildReportHtml,
    printReport,
    pinpointRows,
    buildPinpointCsv,
    downloadPinpointCsv,
    failureReportRows,
    buildFailureReportCsv,
    downloadFailureReportCsv,
  };
});
