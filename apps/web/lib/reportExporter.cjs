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

  const STATUS_LABELS = contract?.STATUS_LABELS || {
    CONFIRMED: '■ 확인 (CONFIRMED)',
    CANDIDATE: '△ 후보 (CANDIDATE)',
    OBSERVED: '○ 관측 (OBSERVED)',
    UNKNOWN: '— 미확인 (UNKNOWN)',
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
    return contract?.statusLabel ? contract.statusLabel(key) : (STATUS_LABELS[key] || STATUS_LABELS.UNKNOWN);
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
    return `<tr><th>${esc(label)}<br><span class="en">${esc(english)}</span></th><td>${esc(claimField(claim, 'claim', ''))}</td><td>${esc(statusLabel(claimField(claim, 'status', 'UNKNOWN')))}</td><td>${esc(joinList(claimField(claim, 'evidence_ids', [])))}</td><td>${esc(joinList(claimField(claim, 'related_tags', [])))}</td><td>${esc(claimField(claim, 'recorded_time', ''))}</td><td>${esc(claimField(claim, 'logic_master_status', ''))}</td><td>${claimField(claim, 'ai_confidence', null) == null ? '' : esc(claimField(claim, 'ai_confidence'))}</td></tr>`;
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

  function buildReportHtml(report) {
    const analysis = normalizedAnalysis(report);
    const metadata = report.metadata || {};
    const title = analysis.verification_gate === 'PASS' ? '설비 고장 분석보고서 (검토본)' : '설비 고장 분석보고서 (초안)';
    const metaRows = [
      ['Run ID', report.run_id || metadata.run_id || ''],
      ['EVENT', metadata.event_file || report.event_file || 'EVENT.csv'],
      ['RAW', metadata.raw_file || report.raw_file || 'RAW.csv'],
      ['Data Digest', metadata.data_digest || report.data_digest || ''],
      ['Verification Gate', `${analysis.verification_gate} · ${analysis.finality.verification_label}`],
      ['Analysis Engine', metadata.analysis_engine || report.analysis_engine || 'Gemini'],
    ].map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('');

    const operating = report.operating_status && typeof report.operating_status === 'object'
      ? Object.entries(report.operating_status).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(asText(v))}</td></tr>`).join('')
      : '<tr><th>운전 상태</th><td>자료 없음</td></tr>';

    const firstCritical = analysis.critical_events[0];
    const incidentRows = [
      ['발생 시각', report.incident_time || metadata.incident_time || claimField(firstCritical, 'recorded_time', '')],
      ['대상 설비', report.equipment || metadata.equipment || ''],
      ['장애 요약', report.incident_summary || ''],
      ['분석 상태', analysis.finality.output_label],
    ].map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(asText(v))}</td></tr>`).join('');

    const criticalRows = analysis.critical_events.map((item) => `<tr><td>${esc(item.recorded_time)}</td><td>${esc(item.claim)}</td><td>${esc(statusLabel(item.status))}</td><td>${esc(joinList(item.evidence_ids))}</td></tr>`).join('');
    const propagationRows = analysis.propagation.map((item) => causeRow('파급 과정', 'Propagation', item)).join('');
    const causalSummary = analysis.causal_chain.map((item) => typeof item === 'object' ? (item.claim || item.description || asText(item)) : asText(item)).filter(Boolean).join(' → ');
    const counterEvidence = analysis.counter_evidence.length ? analysis.counter_evidence.map((item) => `<li>${esc(asText(item))}</li>`).join('') : '<li>없음 / 추가 확인 필요</li>';
    const additional = analysis.additional_evidence_required.length ? analysis.additional_evidence_required.map((item) => `<li>${esc(asText(item))}</li>`).join('') : '<li>추가 확인 항목 없음</li>';
    const recommendationRows = analysis.review_recommendations.length ? analysis.review_recommendations.map((item, index) => `<tr><td>${index + 1}</td><td>${esc(item.claim || asText(item))}</td><td>${esc(statusLabel(item.status || 'CANDIDATE'))}</td><td>${esc(joinList(item.evidence_ids || []))}</td><td>${esc(item.note || '담당자 승인 필요')}</td></tr>`).join('') : '<tr><td colspan="5">검토 권고사항 없음</td></tr>';
    const evidenceRows = pinpointRows(report).map((row) => `<tr><td>${esc(row.event_id || '')}</td><td>${esc(row.source_system || '')}</td><td>${esc(row.event_tag || '')}</td><td>${esc(row.canonical_tag || '')}</td><td>${esc(row.aligned_time || row.original_time || '')}</td><td>${esc(row.disposition || row.state || '')}</td></tr>`).join('');

    const editedRows = Array.isArray(report.report_rows) ? report.report_rows : [];
    const editedBody = editedRows.length ? FAILURE_REPORT_SECTIONS.map((section, index) => {
      const rows = editedRows.filter((row) => String(row.section ?? row['구분'] ?? '') === section);
      const body = rows.length ? rows.map((row) => `<tr><td>${esc(row.item ?? row['항목'] ?? '')}</td><td>${esc(row.content ?? row['내용'] ?? '')}</td><td>${esc(row.status ?? row['상태'] ?? '')}</td><td>${esc(row.evidence_ids ?? row['근거 ID'] ?? '')}</td><td>${esc(row.tags ?? row['관련 태그'] ?? '')}</td><td>${esc(row.time ?? row['기록 시각'] ?? '')}</td><td>${esc(row.note ?? row['비고'] ?? '')}</td></tr>`).join('') : '<tr><td colspan="7">자료 없음</td></tr>';
      return `<section class="section"><h2>${index + 1}. ${esc(section)}</h2><table><thead><tr><th>항목</th><th>내용</th><th>상태</th><th>근거 ID</th><th>관련 태그</th><th>기록 시각</th><th>비고</th></tr></thead><tbody>${body}</tbody></table></section>`;
    }).join('') : '';

    const generatedBody = `
<section class="section"><h2>1. 개요</h2><table><tbody>${incidentRows}</tbody></table></section>
<section class="section"><h2>2. 사고 발생 전 운전 현황</h2><table><tbody>${operating}</tbody></table></section>
<section class="section"><h2>3. 장애 현상</h2><table><thead><tr><th>기록 시각</th><th>주요 사건 (Critical Events)</th><th>상태</th><th>근거 ID</th></tr></thead><tbody>${criticalRows || '<tr><td colspan="4">자료 없음</td></tr>'}</tbody></table></section>
<section class="section"><h2>4. 시간대별 조치사항</h2><table><thead><tr><th>순번</th><th>시각</th><th>구분</th><th>현상/동작</th><th>상태</th><th>근거 ID</th><th>관련 태그</th></tr></thead><tbody>${chronologyRows(report) || '<tr><td colspan="7">자료 없음</td></tr>'}</tbody></table><div class="note">※ 시간순 EVENT/RAW는 임의 5개 제한 없이 전체 배열을 유지합니다. 출력 시 페이지가 넘치면 “시간대별 조치사항 (계속)”으로 이어집니다.</div></section>
<section class="section"><h2>5. 발생 원인</h2><table><thead><tr><th>항목</th><th>내용</th><th>상태</th><th>근거 ID</th><th>관련 태그</th><th>기록 시각</th><th>Logic Master</th><th>AI Confidence</th></tr></thead><tbody>${causeRow('선행 원인','Primary Cause',analysis.primary_cause)}${causeRow('직접 Trip 원인','Direct Trigger',analysis.direct_trigger)}${propagationRows}</tbody></table>${causalSummary ? `<p><strong>인과관계 요약:</strong> ${esc(causalSummary)}</p>` : ''}<div class="note">※ AI Confidence는 공학적 원인 확정과 별도입니다.</div></section>
<section class="section"><h2>6. 조치 결과</h2><table><tbody><tr><th>복구 상태</th><td>${esc(asText(report.recovery_check || 'UNKNOWN'))}</td></tr><tr><th>Verification Gate</th><td>${esc(analysis.verification_gate)} · ${esc(analysis.finality.verification_label)}</td></tr><tr><th>문서 상태</th><td>${esc(analysis.finality.output_label)}</td></tr></tbody></table></section>
<section class="section"><h2>7. 추정 원인 및 미확인 사항</h2><table><tbody><tr><th>반대 근거</th><td><ul>${counterEvidence}</ul></td></tr><tr><th>추가 확인 필요</th><td><ul>${additional}</ul></td></tr></tbody></table></section>
<section class="section"><h2>8. 재발방지 대책 — 검토 권고사항</h2><table><thead><tr><th>순번</th><th>권고사항</th><th>상태</th><th>근거 ID</th><th>비고</th></tr></thead><tbody>${recommendationRows}</tbody></table><div class="note">※ 자동 분석 단계의 권고사항은 CANDIDATE이며 담당자 승인 후 재발방지 대책으로 확정합니다.</div></section>
<section class="section"><h2>9. 증거자료</h2><table><thead><tr><th>근거 ID</th><th>원천</th><th>원본 태그</th><th>정규 태그</th><th>기록 시각</th><th>상태</th></tr></thead><tbody>${evidenceRows || '<tr><td colspan="6">자료 없음</td></tr>'}</tbody></table></section>`;

    return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<style>
@page{size:A4;margin:12mm 11mm 14mm}
*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#111;font-family:Arial,"Noto Sans KR",sans-serif;font-size:10pt;line-height:1.45}
.report{width:100%;max-width:190mm;margin:0 auto}.doc-head{border:1px solid #333;margin-bottom:5mm}.doc-title{font-size:18pt;font-weight:700;text-align:center;padding:5mm 3mm;border-bottom:1px solid #333}.doc-meta table{border:0}.section{margin:0 0 5mm;break-inside:auto;page-break-inside:auto;overflow:visible!important;max-height:none!important;height:auto!important}.section h2{font-size:11.5pt;margin:0 0 2mm;padding-bottom:1.5mm;border-bottom:1.5px solid #222;color:#111}.note{font-size:8.5pt;color:#444}.en{font-size:7.5pt;color:#555;font-weight:400}
table{width:100%;border-collapse:collapse;table-layout:auto;break-inside:auto}thead{display:table-header-group}tr{break-inside:avoid-page;page-break-inside:avoid}th,td{border:1px solid #bbb;padding:1.8mm;vertical-align:top;overflow-wrap:anywhere}th{background:#f5f5f5;text-align:left;font-weight:700}ul{margin:1mm 0 0 5mm;padding-left:3mm}.footer{margin-top:7mm;padding-top:2mm;border-top:1px solid #bbb;font-size:8pt;color:#555}
@media print{html,body{width:auto!important;height:auto!important;overflow:visible!important}.report{max-width:none}.section,table,tr{overflow:visible!important;max-height:none!important;height:auto!important}}
</style></head><body><main class="report">
<header class="doc-head"><div class="doc-title">${esc(title)}</div><div class="doc-meta"><table><tbody>${metaRows}</tbody></table></div></header>
${editedBody || generatedBody}
<footer class="footer">TripLens는 설비를 제어하지 않는 READ-ONLY 사고분석 계층입니다. 본 문서는 EVENT + RAW 근거에서 생성된 초안/검토본이며 최종 확정은 담당자가 수행합니다.</footer>
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
    return [FAILURE_REPORT_COLUMNS.join(','), ...rows.map((row) => FAILURE_REPORT_COLUMNS.map((column) => csvCell(row[column])).join(','))].join('\r\n') + '\r\n';
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
    downloadText(filename || 'PINPOINT.csv', '\ufeff' + buildPinpointCsv(report), 'text/csv;charset=utf-8');
  }

  function downloadFailureReportCsv(report, filename) {
    downloadText(filename || '고장보고서_초안.csv', '\ufeff' + buildFailureReportCsv(report), 'text/csv;charset=utf-8');
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
