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
      .replace(/model_time_s\s*=?\s*\d+(?:\.\d+)?\s*초에(?=\s)\s*/gi, '')
      .replace(/^\s*\d+(?:\.\d+)?\s*초에(?=\s)\s*/, '')
      .replace(/RAW\s*변화\s*시간구간이\s*Direct Trigger\s*시각과\s*겹칩니다\.?/gi, 'RAW 변화구간 · Direct Trigger 시각 중첩.')
      .replace(/선후관계는\s*표본만으로\s*확정할\s*수\s*없습니다\.?/g, '선후관계 미확정')
      .replace(/선후관계를\s*확정할\s*수\s*없습니다\.?/g, '선후관계 미확정')
      .replace(/확인되지\s*않았습니다\.?/g, '미확인.')
      .replace(/완료되지\s*않았습니다\.?/g, '미완료')
      .replace(/조회가\s*미확인/g, '조회 미확인')
      .replace(/확인(?:이)?\s*필요합니다\.?/g, '확인 필요')
      .replace(/확인해야\s*합니다\.?/g, '확인 필요.')
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
    const sourceValue = item && typeof item === 'object'
      ? (item.claim || item.message || item.description || item.summary || '')
      : asText(item);
    const source = String(sourceValue || '');
    const state = String(item?.state || '').toUpperCase();
    const rawValue = item?.value;
    const numericValue = rawValue === null || rawValue === undefined || String(rawValue).trim() === '' ? null : Number(rawValue);
    const active = /ACTIVE|TRIPPED|LATCHED/.test(state) || rawValue === true || numericValue === 1 || /ACTIVE|동작|작동|인가/.test(source);
    const opened = /OPEN|TRIPPED/.test(state) || numericValue === 0 || /\bOPEN\b|개방|개로/.test(source);
    const low = /LOW|ALARM/.test(state) || /\bLOW(?:_LOW)?\b|저하|저유량|저온|하한|\bLL\b/i.test(source);
    const joinedTags = [...tags].join(' ');
    if (stage === 'primary' && /vppExternal(?:ST)?TripCommandNative/.test(joinedTags)) return /ExternalSTTripCommandNative/.test(joinedTags) ? '외부 ST Trip Command 입력' : '외부 GT Trip Command 입력';
    if (stage === 'primary' && /vppCause(?:GT|ST)?BreakerOpenWhileRunning/.test(joinedTags)) {
      const unit = /vppCauseSTBreakerOpenWhileRunning/.test(joinedTags) ? 'ST' : /vppCauseGTBreakerOpenWhileRunning/.test(joinedTags) ? 'GT' : '';
      return unit ? unit + ' 운전 중 차단기 개로 원인 활성화됨' : '운전 중 차단기 개로 원인 활성화됨';
    }
    if (stage === 'primary' && /vppECMS52(?:GT|ST)ClosedCommandNative/.test(joinedTags)) return /vppECMS52STClosedCommandNative/.test(joinedTags) ? '52ST 차단기 투입 명령 해제' : '52GT 차단기 투입 명령 해제';
    if (stage === 'direct' && /vpp(?:GT|ST)TripLatch(?:Published)?/.test(joinedTags)) {
      const gt = /vppGTTripLatch/.test(joinedTags); const st = /vppSTTripLatch/.test(joinedTags);
      if (gt && st) return 'GT·ST Trip Latch 동시 동작';
      if (gt) return 'GT Trip Latch 동작';
      if (st) return 'ST Trip Latch 동작';
    }
    if (stage === 'primary' && tags.has('vppExternalTripCommandNative')) return '외부 Trip Command 입력';
    if (stage === 'primary' && tags.has('vppECMS52GTClosedCommandNative') && tags.has('vppCauseGTBreakerOpenWhileRunning')) return 'GT 운전 중 52GT 차단기 개로 원인 활성화됨';
    if (stage === 'primary' && tags.has('vppECMS52GTClosedCommandNative')) return '52GT 차단기 투입 명령 해제';
    if (stage === 'primary' && tags.has('vppECMS52STClosedCommandNative') && tags.has('vppCauseSTBreakerOpenWhileRunning')) return 'ST 운전 중 52ST 차단기 개로 원인 활성화됨';
    if (stage === 'primary' && tags.has('vppECMS52STClosedCommandNative')) return '52ST 차단기 투입 명령 해제';
    if (stage === 'direct' && active && tags.has('vppGTTripLatch') && tags.has('vppSTTripLatchPublished')) return 'GT·ST Trip Latch 동시 동작';
    if (stage === 'direct' && active && tags.has('vppGTTripLatch')) return 'GT Trip Latch 동작';
    if (stage === 'direct' && active && tags.has('vppSTTripLatchPublished')) return 'ST Trip Latch 동작';
    const lowSeverity = /LOW[\s_-]*LOW|\bLL\b|저[\s-]*저/i.test(`${source} ${item?.tag || ''} ${item?.original_tag || ''}`) ? 'LOW-LOW' : 'LOW';
    const mapped = [
      ['vpp52GTClosed', '52GT 차단기 OPEN', opened],
      ['vpp52STClosed', '52ST 차단기 OPEN', opened],
      ['vppGTExhaustMassFlowTH', `GT 배기유량 ${lowSeverity}`, low],
      ['vppGTExhaustTemperatureK', `GT 배기온도 ${lowSeverity}`, low],
      ['vppHPTurbineSteamFlowTH', `HP 터빈 증기유량 ${lowSeverity}`, low],
      ['vppIPTurbineSteamFlowTH', `IP 터빈 증기유량 ${lowSeverity}`, low],
      ['vppLPTurbineSteamFlowTH', `LP 터빈 증기유량 ${lowSeverity}`, low],
    ].find(([tag,,confirmed]) => confirmed && tags.has(tag));
    if (mapped) return mapped[1];
    let cleaned = source
      .replace(/model_time_s\s*=?\s*\d+(?:\.\d+)?\s*초에(?=\s)\s*/gi, '')
      .replace(/\((?:vpp[A-Za-z0-9_.-]+)\)/g, '')
      .replace(/\b(?:태그\s+)?vpp[A-Za-z0-9_.-]+(?:가|이|는|은)?\b/g, '')
      .replace(/1(?:\.0)?\s*\(ACTIVE\)(?:으로)?/gi, 'ACTIVE')
      .replace(/개로\s*\(0(?:\.0)?\)\s*됨/g, '개방')
      .replace(/\(\s*,+\s*/g, '(')
      .replace(/([,(])\s*=\s*/g, '$1')
      .replace(/,\s*=\s*/g, ', ')
      .replace(/\(\s*(급증|급감|상승|하락|증가|감소|활성|비활성|동작|정지)\s*\)/g, ' $1')
      .replace(/\(\s*\)/g, '')
      .replace(/\(\s+/g, '(')
      .replace(/\s+\)/g, ')')
      .replace(/\s*,\s*/g, ', ')
      .replace(/\s+/g, ' ')
      .replace(/\s+([,.])/g, '$1')
      .trim();
    if (/^서\s+-?\d+(?:\.\d+)?\s*초\s*(?:사이|구간)/.test(cleaned)) {
      const start = Array.isArray(item?.time_interval_s) && Number.isFinite(Number(item.time_interval_s[0])) ? Number(item.time_interval_s[0]) : null;
      cleaned = `${start === null ? '관측 시작 시각에' : `${start}초에`}${cleaned}`;
    }
    return operatorPhrase(cleaned);
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

  const NON_EQUIPMENT_LABELS = new Set([
    'PLANT', 'HRSG', 'EVENT', 'RAW', 'CRITICAL EVENT', 'PRIMARY CAUSE', 'DIRECT TRIGGER',
    'PROPAGATION', 'CAUSAL CHAIN', 'ALARM', 'PROTECTION', 'SYSTEM', 'OPERATOR ACTION',
  ]);

  function canonicalEquipment(value) {
    let text = String(value || '').trim().toUpperCase().replace(/_/g, ' ').replace(/\s+/g, ' ');
    if (!text || NON_EQUIPMENT_LABELS.has(text)) return '';
    let match = text.match(/^FWP[- ](HP|IP|LP)$/);
    if (match) return `${match[1]} BFP`;
    match = text.match(/^(HP|IP|LP) FWP$/);
    if (match) return `${match[1]} BFP`;
    text = text.replace(/FEED\s+WATER/g, 'FEEDWATER');
    return NON_EQUIPMENT_LABELS.has(text) ? '' : text;
  }

  function semanticEquipment(value) {
    const source = String(value || '');
    const upper = source.toUpperCase().replace(/_/g, ' ');
    const result = [];
    const add = value => {
      const equipment = canonicalEquipment(value);
      if (equipment && !result.includes(equipment)) result.push(equipment);
    };
    for (const match of source.matchAll(/vpp(HP|IP|LP)Drum[A-Za-z0-9_.-]*/g)) add(`${match[1]} DRUM`);
    for (const match of upper.matchAll(/\b(HP|IP|LP)\s+DRUM\b/g)) add(`${match[1]} DRUM`);
    if (/고압\s*드럼/.test(source)) add('HP DRUM');
    if (/중압\s*드럼/.test(source)) add('IP DRUM');
    if (/저압\s*드럼/.test(source)) add('LP DRUM');
    for (const match of source.matchAll(/vpp(HP|IP|LP)FWP(?:Trip|Reset|Speed|Running|Latch|Command|Pushbutton)[A-Za-z0-9_.-]*/g)) add(`${match[1]} BFP`);
    for (const match of upper.matchAll(/\b(HP|IP|LP)\s+(?:BFP|FWP)\b/g)) add(`${match[1]} BFP`);
    for (const match of upper.matchAll(/\b(HP|IP|LP)\s+(?:FEEDWATER|FW\s+FLOW)\b/g)) add(`${match[1]} FEEDWATER`);
    for (const match of source.matchAll(/\b(HP|IP|LP)\s*급수/g)) add(`${match[1]} FEEDWATER`);
    for (const match of upper.matchAll(/\bVCB[- ]?([A-Z]\d{2})\b/g)) add(`VCB-${match[1]}`);
    for (const match of source.matchAll(/vpp(?:ECMS)?VCB([A-Z]\d{2})[A-Za-z0-9_.-]*/g)) add(`VCB-${match[1]}`);
    for (const match of upper.matchAll(/\b(HP|IP|LP)\s+BFP\s+NRV\b/g)) add(`${match[1]} BFP NRV`);
    for (const match of upper.matchAll(/\b(HP|IP|LP)\s+TURBINE\b/g)) add(`${match[1]} TURBINE`);
    if (/\b52GT\b/.test(upper)) add('52GT');
    if (/\b52ST\b/.test(upper)) add('52ST');
    if (/\bGT\b.*(?:TRIP|LATCH)|(?:TRIP|LATCH).*\bGT\b/i.test(upper)) add('GT');
    if (/\bST\b.*(?:TRIP|LATCH)|(?:TRIP|LATCH).*\bST\b/i.test(upper)) add('ST');
    return result;
  }

  function equipmentSpecificity(value) {
    if (/\b(?:BFP|DRUM|VCB)-?|FEEDWATER/.test(value)) return 30;
    if (/\b(?:TURBINE|EXHAUST|NRV)\b/.test(value)) return 20;
    if (/^52(?:GT|ST)$/.test(value)) return 10;
    return 0;
  }

  function observedProtectionEvent(report) {
    const rows = chronology(report);
    return rows.find(item => /TRIP[ _-]*LATCH|트립\s*래치/i.test(`${item?.claim || item?.message || ''} ${joinList(item?.related_tags || item?.tags)}`))
      || rows.find(item => /PROTECTION/i.test(String(item?.category || item?.event_class || item?.source || '')))
      || rows[0]
      || null;
  }

  function deriveReportEquipment(report, analysis, observedEvent) {
    const candidates = new Map();
    let order = 0;
    const add = (value, baseScore) => {
      const equipment = canonicalEquipment(value);
      if (!equipment) return;
      const score = baseScore + equipmentSpecificity(equipment);
      const previous = candidates.get(equipment);
      if (!previous || score > previous.score) candidates.set(equipment, {equipment, score, order:order++});
    };
    const inspect = (item, baseScore) => {
      if (!item || typeof item !== 'object') return;
      add(item.equipment, baseScore + 20);
      for (const evidence of list(item.evidence)) add(evidence?.equipment, baseScore + 20);
      const semantic = [item.claim, item.message, item.description, item.summary, joinList(item.related_tags || item.tags), item.tag, item.original_tag].filter(Boolean).join(' ');
      for (const equipment of semanticEquipment(semantic)) add(equipment, baseScore);
    };
    add(report?.equipment, 260);
    add(report?.metadata?.equipment, 250);
    inspect(report?.primary_cause || analysis?.primary_cause, 160);
    for (const item of list(report?.critical_events).length ? list(report.critical_events) : list(analysis?.critical_events)) inspect(item, 150);
    inspect(report?.direct_trigger || analysis?.direct_trigger, 135);
    for (const item of list(report?.propagation).length ? list(report.propagation) : list(analysis?.propagation)) inspect(item, 110);
    const directSource = report?.direct_trigger || analysis?.direct_trigger || {};
    const directNarrative = String(directSource?.claim || directSource?.description || '').trim();
    inspect(observedEvent, directNarrative && !/^(?:설명 미제공|분석 결과 없음|추가 확인 필요)$/.test(directNarrative) ? 90 : 170);
    chronology(report).forEach((item, index) => inspect(item, Math.max(45, 80 - index)));
    const ranked = [...candidates.values()].sort((left, right) => right.score - left.score || left.order - right.order);
    if (!ranked.length) return 'PLANT';
    const eligible = ranked.filter(item => item.score >= ranked[0].score - 55);
    const specific = eligible.filter(item => equipmentSpecificity(item.equipment) > 0);
    return (specific.length ? specific : eligible).slice(0, 3).map(item => item.equipment).join(' · ') || 'PLANT';
  }

  function equipmentLabel(item) {
    const explicit = canonicalEquipment(item?.equipment);
    if (explicit) return explicit;
    const text = `${operatorClaim(item)} ${joinList(item?.related_tags || item?.tags)} ${item?.tag || ''}`;
    return semanticEquipment(text)[0] || 'PLANT';
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
      const projected = {...event,claim:content || original,__reportContent:contentEdited};
      const field = (...keys) => keys.find(key => Object.prototype.hasOwnProperty.call(row, key));
      const statusKey = field('status', '상태');
      if (statusKey) {
        const status = String(row[statusKey] ?? '').trim() || 'UNKNOWN';
        projected.status = status;
        projected.disposition = status;
      }
      const evidenceKey = field('evidence_ids', '근거 ID');
      if (evidenceKey) projected.evidence_ids = evidenceIds(row[evidenceKey]);
      const tagsKey = field('tags', '관련 태그');
      if (tagsKey) projected.related_tags = list(row[tagsKey]).flatMap(value => String(value || '').split(/[;,]/)).map(value => value.trim()).filter(Boolean);
      const timeKey = field('time', '기록 시각');
      projected.__timeOverride = timeKey ? (String(row[timeKey] ?? '').trim() || '시각 미확인') : '';
      return projected;
    }) : events;
    rows.sort((left, right) => {
      const a = Number(left?.model_time_s ?? left?.recorded_time ?? left?.aligned_time ?? left?.time);
      const b = Number(right?.model_time_s ?? right?.recorded_time ?? right?.aligned_time ?? right?.time);
      return (Number.isFinite(a) ? a : Infinity) - (Number.isFinite(b) ? b : Infinity);
    });
    return { visible: rows.slice(0, limit), hiddenCount: Math.max(0, rows.length - limit) };
  }

  function reportEvidenceLine(item) {
    const ids = evidenceIds(item?.evidence_ids || item?.evidenceIds || []);
    const time = displayTime(item);
    const timeText = [time.primary, time.secondary].filter(value => value && value !== '시각 미확인').join(' · ');
    return [timeText, ids.length ? '근거 ' + ids.length + '건' : '근거 기록 없음'].filter(Boolean).join(' · ');
  }
  function buildReportHtml(report) {
    const analysis = normalizedAnalysis(report);
    const metadata = report.metadata || {};
    const title = '설비 장애·고장 보고서';
    const reportRows = list(report.report_rows);
    const valueOf = (row, ...keys) => {
      for (const key of keys) {
        const value = row?.[key];
        if (value !== undefined && value !== null && String(value).trim() !== '') return String(value).trim();
      }
      return '';
    };
    const sectionRows = (...names) => {
      const wanted = new Set(names);
      return reportRows.filter(row => wanted.has(valueOf(row, 'section', '구분')));
    };
    const placeholder = /^(?:기록 없음|복구·조치 기록 입력 대기|입력 대기|입력 필요|추가 확인 필요|설명 미제공|분석 결과 없음|미확인|미기록|—|-)$/;
    const fullText = value => String(value ?? '')
      .replace(/…/g, '')
      .replace(/\.{3,}/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    const useful = value => {
      const text = fullText(value);
      return text && !placeholder.test(text) ? text : '';
    };
    const printableStatus = value => {
      const status = String(value || '').toUpperCase();
      if (/CONFIRMED|PASS|APPROVED|ACTIVE|COMPLETE/.test(status)) return '■ 확인';
      if (/OBSERVED|RECOVERED|PARTIAL/.test(status)) return '○ 관측';
      if (/CANDIDATE|HOLD|UNKNOWN|REVIEW|PENDING/.test(status)) return '△ 후보';
      return useful(value) || '연결';
    };
    const fullOperator = (item, stage = '') => {
      const compact = fullText(operatorClaim(item, stage));
      if (compact && !String(operatorClaim(item, stage)).includes('…')) return compact;
      const source = item && typeof item === 'object'
        ? (item.claim || item.message || item.description || item.summary || '')
        : asText(item);
      return fullText(operatorPhrase(source, 4000));
    };
    const evidenceCount = item => evidenceIds(item?.evidence_ids || item?.evidenceIds || []).length;
    const evidenceMeta = item => {
      const when = displayTime(item);
      const time = when.primary === '시각 미확인' ? '' : [when.primary, when.secondary].filter(Boolean).join(' · ');
      const count = evidenceCount(item);
      return [time, count ? `근거 ${count}건` : ''].filter(Boolean).join(' · ') || 'EVENT·RAW 연결';
    };
    const observedDirect = observedProtectionEvent(report);
    const observedDirectText = useful(fullOperator(observedDirect, 'direct'));
    const firstCritical = analysis.critical_events.find(item => useful(fullOperator(item))) || observedDirect || analysis.critical_events[0];
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
    const primary = useful(primaryEdited ? primarySource : fullOperator(analysis.primary_cause, 'primary')) || '선행 원인 후보 없음';
    const directAnalysisText = useful(directEdited ? directSource : fullOperator(analysis.direct_trigger, 'direct'));
    const direct = directAnalysisText || observedDirectText || '직접 보호동작 근거 확인 필요';
    const criticalDisplay = firstCritical === observedDirect ? observedDirectText : useful(fullOperator(firstCritical));
    const projectClaimRow = (source, row, claim) => {
      const projected = {...(source || {}), claim};
      if (!row) return projected;
      const field = (...keys) => keys.find(key => Object.prototype.hasOwnProperty.call(row, key));
      const statusKey = field('status', '상태');
      if (statusKey) {
        const status = String(row[statusKey] ?? '').trim() || 'UNKNOWN';
        projected.status = status;
        projected.disposition = status;
      }
      const evidenceKey = field('evidence_ids', '근거 ID');
      if (evidenceKey) projected.evidence_ids = evidenceIds(row[evidenceKey]);
      const tagsKey = field('tags', '관련 태그');
      if (tagsKey) projected.related_tags = list(row[tagsKey]).flatMap(value => String(value || '').split(/[;,]/)).map(value => value.trim()).filter(Boolean);
      const timeKey = field('time', '기록 시각');
      if (timeKey) {
        delete projected.model_time_s;
        delete projected.aligned_time;
        const reportTime = String(row[timeKey] ?? '').trim();
        const modelTime = reportTime.match(/(?:T\+)?(-?\d+(?:\.\d+)?)\s*s?$/i);
        if (/^\d{4}-\d{2}-\d{2}T/.test(reportTime)) projected.wall_time_utc = reportTime;
        else projected.recorded_time = modelTime ? modelTime[1] : reportTime;
      }
      return projected;
    };
    const primaryItem = projectClaimRow(analysis.primary_cause, primaryRow, primary);
    const directItem = projectClaimRow(directAnalysisText ? analysis.direct_trigger : (observedDirect || analysis.direct_trigger), directRow, direct);
    const summaryOriginal = report.incident_summary || direct;
    const summaryRow = editedRow(report, '개요', '장애 요약');
    const summarySource = String(summaryRow?.content ?? summaryRow?.['내용'] ?? summaryOriginal);
    const summaryEdited = Boolean(summaryRow && (summaryRow.edited === true || summarySource !== String(summaryOriginal)));
    const summary = fullText(summarySource);
    const summaryDisplay = useful(summaryEdited ? summary : fullOperator({claim:summary})) || direct || criticalDisplay;
    const equipment = deriveReportEquipment(report, analysis, observedDirect);
    const timeline = briefTimeline(report, 12);
    const timelineItems = timeline.visible;
    const timelineTotal = timelineItems.length + timeline.hiddenCount;
    const timelineRow = (item, index, detailed = false) => {
      const when = item.__timeOverride ? {primary:item.__timeOverride,secondary:''} : displayTime(item);
      const claim = useful(item.__reportContent ? item.claim : fullOperator(item)) || '사고 구간 변화';
      const ids = evidenceIds(item?.evidence_ids || item?.evidenceIds || []);
      const source = useful(item?.source || item?.category || item?.stage) || 'EVENT';
      const state = printableStatus(item?.status || item?.disposition || 'OBSERVED');
      if (detailed) return `<tr><td>${index + 1}</td><td><b>${esc(when.primary === '시각 미확인' ? '사고 구간' : when.primary)}</b>${when.secondary?`<small>${esc(when.secondary)}</small>`:''}</td><td>${esc(source)}</td><td>${esc(equipmentLabel(item))}</td><td>${esc(claim)}</td><td>${esc(state)}</td><td>${esc(ids.join(' · ') || '연결')}</td></tr>`;
      return `<tr><td><b>${esc(when.primary === '시각 미확인' ? '사고 구간' : when.primary)}</b>${when.secondary?`<small>${esc(when.secondary)}</small>`:''}</td><td>${esc(source)}</td><td>${esc(claim)}</td><td>${esc(state)}</td><td>${esc(ids.join(' · ') || '연결')}</td></tr>`;
    };
    const firstTimelineRows = timelineItems.slice(0, 4).map((item, index) => timelineRow(item, index)).join('');
    const continuation = timelineItems.length > 4 ? timelineItems.slice(4) : timelineItems;
    const continuationRows = continuation.map((item, index) => timelineRow(item, timelineItems.length > 4 ? index + 4 : index, true)).join('');

    const operationRows = sectionRows('사고 발생 전 운전 현황').filter(row => useful(valueOf(row, 'content', '내용')));
    const operationCards = (operationRows.length ? operationRows.slice(0, 4).map(row => ({
      label:valueOf(row, 'item', '항목') || '운전 상태', value:useful(valueOf(row, 'content', '내용')),
    })) : [
      {label:'대상 설비',value:equipment},
      {label:'사고 구간',value:incidentTime.secondary || (incidentTime.primary === '시각 미확인' ? 'EVENT 기준' : incidentTime.primary)},
      {label:'보호 상태',value:direct},
      {label:'파급 항목',value:analysis.propagation.length ? `${analysis.propagation.length}건 관측` : 'EVENT·RAW 연결'},
    ]).map(item => `<div class="metric-card"><span>${esc(item.label)}</span><b>${esc(item.value)}</b></div>`).join('');

    const propagationText = analysis.propagation.map(item => fullOperator(item, 'propagation')).filter(Boolean).slice(0, 4).join(' → ') || '보호동작 이후 설비 변화 연결';
    const faultRows = [
      ['최초 Event', criticalDisplay || direct, printableStatus(firstCritical?.status || directItem?.status || 'OBSERVED')],
      ['주요 현상', [direct, propagationText].filter(Boolean).join(' → '), '시간순 확인'],
      ['상태 판정', `선행 원인 ${printableStatus(primaryItem?.status || primaryItem?.disposition || 'CANDIDATE')} · 직접 보호동작 ${printableStatus(directItem?.status || directItem?.disposition || 'CONFIRMED')} · 파급 ${analysis.propagation.length ? '○ 관측' : '연결'}`, '근거 연결'],
    ].map(row => `<tr><th>${esc(row[0])}</th><td>${esc(row[1])}</td><td>${esc(row[2])}</td></tr>`).join('');

    const causeRows = [
      ['선행 원인 (Primary Cause)', primary, printableStatus(primaryItem?.status || primaryItem?.disposition || 'CANDIDATE'), evidenceMeta(primaryItem)],
      ['직접 Trip 원인 (Direct Trigger)', direct, printableStatus(directItem?.status || directItem?.disposition || 'CONFIRMED'), evidenceMeta(directItem)],
      ['파급 결과 (Propagation)', propagationText, analysis.propagation.length ? '○ 관측' : '연결', analysis.propagation.length ? `${analysis.propagation.length}개 파급 항목` : 'EVENT·RAW 연결'],
    ].map(row => `<div class="cause-row"><b>${esc(row[0])}</b><div><strong>${esc(row[1])}</strong><small>${esc(row[3])}</small></div><span class="status">${esc(row[2])}</span></div>`).join('');
    const keyEvidenceRows = [
      ['선행 원인', evidenceMeta(primaryItem), printableStatus(primaryItem?.status || primaryItem?.disposition || 'CANDIDATE')],
      ['직접 보호동작', evidenceMeta(directItem), printableStatus(directItem?.status || directItem?.disposition || 'CONFIRMED')],
      ['파급 결과', analysis.propagation.length ? `${analysis.propagation.length}개 항목 · EVENT·RAW 연결` : 'EVENT·RAW 연결', analysis.propagation.length ? '○ 관측' : '연결'],
    ].map(row => `<tr><th>${esc(row[0])}</th><td>${esc(row[1])}</td><td>${esc(row[2])}</td></tr>`).join('');

    const causalCards = [
      ['선행 원인 (Primary Cause)', primary, primaryItem],
      ['주요 이벤트 (Critical Event)', criticalDisplay || direct, firstCritical || directItem],
      ['직접 Trip 원인 (Direct Trigger)', direct, directItem],
      ['파급 결과 (Propagation)', propagationText, analysis.propagation[0] || {}],
    ].map(([label,claim,item]) => {
      const when=displayTime(item); const ids=evidenceIds(item?.evidence_ids || []);
      return `<div class="chain-row"><div class="chain-time">${esc(when.primary === '시각 미확인' ? '사고 구간' : when.primary)}</div><div class="chain-card"><b>${esc(label)}</b><span class="status">${esc(printableStatus(item?.status || (label.includes('선행')?'CANDIDATE':'OBSERVED')))}</span><strong>${esc(claim)}</strong><small>${esc(ids.length ? `근거 ID ${ids.join(' · ')}` : evidenceMeta(item))}</small></div></div>`;
    }).join('');

    const recommendationRows = sectionRows('재발방지 대책 — 검토 권고사항').filter(row => useful(valueOf(row, 'content', '내용')));
    const recommendationSource = recommendationRows.length ? recommendationRows : analysis.review_recommendations.map((item,index)=>({item:`검토 항목 ${index+1}`,content:item?.claim || asText(item),status:item?.status || 'CANDIDATE'}));
    const recommendationBody = (recommendationSource.length ? recommendationSource : [
      {item:'근거 연결 유지',content:'EVENT·RAW와 Tag Master 연결 상태를 다음 분석에도 동일하게 유지',status:'CANDIDATE'},
    ]).slice(0,5).map(row => `<tr><th>${esc(valueOf(row,'item','항목') || '검토 항목')}</th><td>${esc(useful(valueOf(row,'content','내용') || row?.claim) || '근거 연결 유지')}</td><td>${esc(printableStatus(valueOf(row,'status','상태') || row?.status || 'CANDIDATE'))}</td></tr>`).join('');

    const recoveryDetailRows = sectionRows('운전원·정비 조치사항','조치 결과 및 복구 판정').filter(row => useful(valueOf(row,'content','내용')));
    const recoveryDetails = recoveryDetailRows.length ? `<table class="recovery-details"><tbody>${recoveryDetailRows.map(row => {
      const content=useful(valueOf(row,'content','내용'));
      const meta=[useful(valueOf(row,'time','기록 시각')),useful(valueOf(row,'note','비고'))].filter(Boolean).join(' · ');
      return `<tr><th>${esc(valueOf(row,'item','항목') || '조치 결과')}</th><td>${esc(content)}${meta?`<small>${esc(meta)}</small>`:''}</td></tr>`;
    }).join('')}</tbody></table>` : '';

    const evidenceSourceRows = sectionRows('증거자료').filter(row => evidenceIds(valueOf(row,'evidence_ids','근거 ID')).length || useful(valueOf(row,'tags','관련 태그')) || useful(valueOf(row,'content','내용')));
    const claimEvidence = [primaryItem,directItem,...analysis.critical_events,...analysis.propagation].flatMap((item,itemIndex) => {
      const ids=evidenceIds(item?.evidence_ids || []); const tags=list(item?.related_tags || item?.tags);
      return ids.map((id,index)=>({section:'증거자료',item:id,content:fullOperator(item),status:item?.status || 'OBSERVED',evidence_ids:id,tags:tags[index] || tags[0] || '',time:displayTime(item).primary,__order:itemIndex}));
    });
    const evidenceRows = (evidenceSourceRows.length ? evidenceSourceRows : claimEvidence).slice(0, 10).map((row,index) => {
      const ids=evidenceIds(valueOf(row,'evidence_ids','근거 ID'));
      const id=ids[0] || valueOf(row,'item','항목') || `근거-${index+1}`;
      const source=/^RAW/i.test(id)?'RAW':/^EV|EVENT/i.test(id)?'EVENT':'EVENT/RAW';
      const tag=useful(valueOf(row,'tags','관련 태그','source_node','canonical_tag')) || '연결 태그';
      const label=useful(valueOf(row,'content','내용','item','항목')) || fullOperator(row) || '근거 데이터';
      const time=useful(valueOf(row,'time','기록 시각','recorded_time')) || '사고 구간';
      const status=printableStatus(valueOf(row,'status','상태') || row?.status || 'OBSERVED');
      return {id,source,tag,label,time,status};
    });
    const evidenceBody = evidenceRows.map(row => `<tr><td>${esc(row.id)}</td><td>${esc(row.source)}</td><td><code>${esc(row.tag)}</code></td><td>${esc(row.label)}</td><td>${esc(row.time)}</td><td>${esc(row.status)}</td></tr>`).join('') || '<tr><td colspan="6">EVENT·RAW 핵심 근거 연결</td></tr>';
    const tagExample = evidenceRows[0] || {tag:'Tag Master 연결',label:'표시명',source:'EVENT/RAW',id:'연결 근거'};
    const documentDate = String(report.incident_wall_time || firstCritical?.wall_time_utc || '').slice(0,10) || '사고 분석일';
    const documentNumber = useful(report.document_number || metadata.document_number) || `TL-INC-${String(report.run_id || metadata.run_id || 'REPORT').replace(/[^A-Za-z0-9-]/g,'-')}`;
    const inputFiles = `${metadata.event_file || 'EVENT.csv'} + ${metadata.raw_file || 'RAW.csv'}`;
    const header = (page, continued = false) => `<header class="report-head"><div><h1>${esc(title)}${continued?' <span>(계속)</span>':''}</h1><p>사고분석 근거: ${esc(inputFiles)} / 분석제출: READ-ONLY</p><p>문서번호 ${esc(documentNumber)} · 설비 ${esc(equipment)} · 발생일시 ${esc(documentDate)}</p></div><div class="approval"><div><span>작성</span><b>자동</b></div><div><span>검토</span><b>자동</b></div><div><span>승인</span><b>READ-ONLY</b></div></div></header>`;
    const footer = page => `<footer class="page-footer"><span>TripLens READ-ONLY · 근거 확보 항목만 표시 · 원본 EVENT/RAW 별도 보관</span><b>${page} / 4</b></footer>`;
    const page = (number, body, continued = number > 1) => `<main class="report-page">${header(number,continued)}<div class="page-body"><div class="page-content">${body}</div></div>${footer(number)}</main>`;

    const pageOne = page(1, `
      <section><h2>1. 개요</h2><table class="overview"><tbody>
        <tr><th>발생 시각</th><td>${esc(incidentTime.primary === '시각 미확인' ? 'EVENT 기록 기준 사고 구간' : [incidentTime.primary,incidentTime.secondary].filter(Boolean).join(' · '))}</td></tr>
        <tr><th>대상 설비</th><td>${esc(equipment)}</td></tr>
        <tr><th>장애 요약</th><td>${esc(summaryDisplay)}</td></tr>
        <tr><th>분석 상태</th><td>EVENT·RAW 연결 · 핵심 사고경위 ${timelineItems.length}건${timeline.hiddenCount ? ` / 전체 ${timelineTotal}건` : ''}</td></tr>
      </tbody></table></section>
      <section><h2>2. 운전 현황</h2><div class="metric-grid">${operationCards}</div></section>
      <section><h2>3. 장애 현상</h2><table class="phenomena"><tbody>${faultRows}</tbody></table></section>
      <section><h2>5. 발생 원인</h2><div class="cause-list">${causeRows}</div></section>
      <section><h2>핵심 근거 요약</h2><table class="key-evidence"><tbody>${keyEvidenceRows}</tbody></table></section>
      <p class="policy-note">상태 표시는 보고서 편집 행의 확인·관측·후보 판정과 연결 근거를 그대로 따른다.</p>`);

    const pageTwo = page(2, `
      <div class="page-kicker">시간대별 조치사항 및 인과관계</div>
      <section><h2>4. 시간대별 조치사항</h2><table class="timeline"><thead><tr><th>기록 시각</th><th>구분</th><th>내용</th><th>상태</th><th>근거 ID</th></tr></thead><tbody>${firstTimelineRows || '<tr><td colspan="5">EVENT·RAW 사고 구간 연결</td></tr>'}</tbody></table></section>
      <section><h2>6. 조치 결과</h2><div class="metric-grid three"><div class="metric-card"><span>보호 동작</span><b>${esc(printableStatus(directItem?.status || directItem?.disposition || 'CONFIRMED'))}</b></div><div class="metric-card"><span>근거 연결</span><b>EVENT·RAW ${evidenceRows.length}건</b></div><div class="metric-card"><span>최종 판정</span><b>${esc(report.document_state==='REVIEWED'?'검토 완료':'분석 완료')}</b></div></div>${recoveryDetails}</section>
      <section><h2>5-1. 인과관계 요약</h2><div class="chain-list">${causalCards}</div></section>
      <section><h2>7. 판정 기준</h2><div class="rule-box"><b>선행 원인</b><span>RAW 변화구간과 원인 로직 연결</span><b>직접 보호동작</b><span>EVENT 기록과 RAW 상태 연결</span><b>표시 원칙</b><span>확인 · 관측 · 후보 상태로 구분</span></div></section>`);

    const pageThree = page(3, `
      <div class="page-kicker">재발방지 대책 및 증거자료</div>
      <section><h2>8. 재발방지 대책</h2><table class="recommendations"><thead><tr><th>검토 영역</th><th>내용</th><th>상태</th></tr></thead><tbody>${recommendationBody}</tbody></table></section>
      <section><h2>9. 증거자료</h2><table class="evidence"><thead><tr><th>근거 ID</th><th>원천</th><th>원본 태그</th><th>표시명</th><th>기록 시각</th><th>상태</th></tr></thead><tbody>${evidenceBody}</tbody></table></section>
      <section><h2>태그 표시 예시</h2><div class="tag-example"><b>원본 태그</b><code>${esc(tagExample.tag)}</code><b>표시명</b><span>${esc(tagExample.label)}</span><b>원천</b><span>${esc(tagExample.source)}</span><b>근거 ID</b><span>${esc(tagExample.id)}</span></div></section>
      <section><h2>보고서 적용 기준</h2><ul class="report-rules"><li>근거 ID와 원본 태그를 함께 표시</li><li>EVENT·RAW 원본은 별도 보관하고 PDF에는 핵심 행만 표시</li><li>빈 입력란과 미래 담당자 입력 항목은 출력하지 않음</li></ul></section>`);

    const pageFour = page(4, `
      <section><h2>4. 시간대별 조치사항 ${timelineItems.length > 4 ? '(계속)' : '(전체)'}</h2><div class="metric-grid four"><div class="metric-card"><span>총 이벤트</span><b>${timelineTotal}건</b></div><div class="metric-card"><span>PDF 표시</span><b>${timelineItems.length}건</b></div><div class="metric-card"><span>시간 유효성</span><b>EVENT·RAW 연결</b></div><div class="metric-card"><span>CSV 전체 유지</span><b>원본 보존</b></div></div>
      <table class="timeline detailed"><thead><tr><th>순번</th><th>기록 시각</th><th>원천</th><th>설비/태그</th><th>내용</th><th>상태</th><th>근거 ID</th></tr></thead><tbody>${continuationRows || '<tr><td colspan="7">EVENT·RAW 사고 구간 연결</td></tr>'}</tbody></table></section>
      <div class="source-note"><b>사건 EVENT/RAW는 고정된 원본 CSV와 함께 보존한다.</b><p>본 보고서는 핵심 근거 요약본이며, 전체 이벤트·태그·시간축은 CSV 원본과 상세 근거 화면에서 확인한다.${timeline.hiddenCount ? ` 나머지 ${timeline.hiddenCount}건은 보고서 CSV에서 확인한다.` : ''}</p></div>`);

    return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<style>
@page{size:A4;margin:0}
*{box-sizing:border-box}html,body{margin:0;padding:0;background:#eef1f3;color:#263845;font-family:"Noto Sans KR","Malgun Gothic",Arial,sans-serif;font-size:8pt;line-height:1.3}body{padding:8mm 0}.report-page{position:relative;width:210mm;height:297mm;margin:0 auto 8mm;background:#fff;padding:9mm 10mm 15mm;overflow:hidden;break-after:page;page-break-after:always}.report-page:last-child{break-after:auto;page-break-after:auto}.report-head{height:16mm;border:1px solid #b8c5ce;display:grid;grid-template-columns:1fr 54mm;grid-template-rows:minmax(0,1fr);margin-bottom:4mm}.report-head>div:first-child{padding:2.4mm 3mm}.report-head h1{font-size:11.5pt;line-height:1.15;margin:0 0 1.2mm}.report-head h1 span{font-size:8pt;color:#667785}.report-head p{font-size:6.2pt;color:#667785;margin:.4mm 0}.approval{display:grid;grid-template-columns:repeat(3,1fr)}.approval>div{border-left:1px solid #b8c5ce;padding:1.5mm;text-align:center}.approval span{display:block;color:#667785;font-size:6pt}.approval b{display:block;margin-top:2.2mm;font-size:6.3pt}.page-body{height:245mm;overflow:hidden;position:relative}.page-content{transform-origin:top left}.page-kicker{font-size:10pt;font-weight:800;margin:0 0 2.5mm}section{margin:0 0 3mm;break-inside:avoid;page-break-inside:avoid}section h2{font-size:8.7pt;margin:0 0 2mm;padding-bottom:1.2mm;border-bottom:1px solid #b8c5ce}table{width:100%;border-collapse:collapse;table-layout:fixed}thead{display:table-header-group}tr{break-inside:avoid-page;page-break-inside:avoid}th,td{border:1px solid #b8c5ce;padding:2mm 2.4mm;vertical-align:top;overflow-wrap:anywhere;word-break:break-word}th{background:#eef3f6;text-align:left;font-weight:700}thead th{background:#486477;color:#fff;text-align:center;font-size:6.4pt}.overview th{width:34mm}.phenomena th{width:34mm}.phenomena td:last-child{width:27mm;text-align:center}.key-evidence th{width:34mm}.key-evidence td:last-child{width:23mm;text-align:center}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1.5mm}.metric-grid.three{grid-template-columns:repeat(3,1fr)}.metric-grid.four{margin-bottom:2.2mm}.metric-card{min-height:13mm;border:1px solid #b8c5ce;padding:2mm;background:#fff}.metric-card span{display:block;color:#667785;font-size:6.2pt;margin-bottom:1mm}.metric-card b{font-size:7pt}.recovery-details{margin-top:1.5mm;font-size:6.7pt}.recovery-details th{width:34mm}.recovery-details th,.recovery-details td{padding:1.35mm 2mm}.recovery-details td small{display:block;margin-top:.45mm;color:#667785;font-size:5.7pt}.cause-list{display:grid;gap:1mm}.cause-row{display:grid;grid-template-columns:55mm 1fr 23mm;gap:3mm;align-items:start;border:1px solid #b8c5ce;padding:2.1mm 3mm;min-height:8.5mm}.cause-row strong,.cause-row small{display:block}.cause-row strong{font-size:7.2pt}.cause-row small{color:#667785;font-size:6.1pt;margin-top:.6mm}.status{text-align:center;color:#486477;font-weight:800;font-size:6.2pt}.policy-note{margin:1.5mm 0 0;color:#667785;font-size:6.1pt}.timeline th,.timeline td{padding:1.5mm 2mm}.timeline th:nth-child(1){width:27mm}.timeline th:nth-child(2){width:25mm}.timeline th:nth-child(4){width:20mm}.timeline th:nth-child(5){width:26mm}.timeline td small{display:block;color:#667785;font-size:5.7pt}.chain-list{display:grid;gap:.8mm}.chain-row{display:grid;grid-template-columns:20mm 1fr;gap:2mm;align-items:start}.chain-time{padding-top:2.5mm;text-align:center;color:#667785;font-size:5.9pt}.chain-card{position:relative;border:1px solid #b8c5ce;padding:1.7mm 27mm 1.7mm 3mm;min-height:12.5mm}.chain-card>b,.chain-card>strong,.chain-card>small{display:block}.chain-card>strong{margin-top:.55mm}.chain-card>small{margin-top:.5mm;color:#667785;font-size:5.8pt}.chain-card>.status{position:absolute;right:3mm;top:2mm}.rule-box{display:grid;grid-template-columns:27mm 1fr;border:1px solid #b8c5ce;background:#f7f9fa}.rule-box>*{padding:1.2mm 2.5mm;border-bottom:1px solid #d8e1e7}.rule-box>*:nth-last-child(-n+2){border-bottom:0}.recommendations th:first-child{width:45mm}.recommendations th:last-child{width:22mm}.evidence{font-size:6.2pt}.evidence th:nth-child(1){width:21mm}.evidence th:nth-child(2){width:18mm}.evidence th:nth-child(3){width:50mm}.evidence th:nth-child(5){width:31mm}.evidence th:nth-child(6){width:20mm}.evidence code,.tag-example code{font-family:"Noto Sans Mono","Malgun Gothic",monospace;white-space:normal;overflow-wrap:anywhere}.tag-example{display:grid;grid-template-columns:27mm 1fr;border:1px solid #b8c5ce;background:#f7f9fa}.tag-example>*{padding:1.7mm 3mm;border-bottom:1px solid #d8e1e7}.tag-example>*:nth-last-child(-n+2){border-bottom:0}.report-rules{margin:0;padding:3mm 7mm;border:1px solid #b8c5ce;background:#f7f9fa}.report-rules li{margin:1mm 0}.timeline.detailed{font-size:6.2pt}.timeline.detailed th:nth-child(1){width:12mm}.timeline.detailed th:nth-child(2){width:26mm}.timeline.detailed th:nth-child(3){width:19mm}.timeline.detailed th:nth-child(4){width:38mm}.timeline.detailed th:nth-child(6){width:19mm}.timeline.detailed th:nth-child(7){width:23mm}.source-note{margin-top:5mm;padding:4mm;border:1px solid #b8c5ce;background:#f7f9fa}.source-note p{color:#667785;margin:1.5mm 0 0}.page-footer{position:absolute;left:10mm;right:10mm;bottom:8mm;border-top:1px solid #d8e1e7;padding-top:2mm;display:flex;justify-content:space-between;color:#667785;font-size:6pt}
@media print{html,body{width:210mm;background:#fff;padding:0;height:auto}.report-page{margin:0;height:297mm!important;min-height:297mm!important;max-height:297mm!important;overflow:hidden!important}}
</style></head><body>${pageOne}${pageTwo}${pageThree}${pageFour}<script>
function fitReportPages(){document.querySelectorAll('.page-body').forEach(function(body){const content=body.querySelector('.page-content');if(!content)return;content.style.transform='none';content.style.width='100%';const available=Math.max(1,body.clientHeight);let scale=Math.min(1,available/Math.max(1,content.scrollHeight));for(let pass=0;pass<3;pass+=1){content.style.width=(100/scale)+'%';scale=Math.min(1,available/Math.max(1,content.scrollHeight));}content.style.width=(100/scale)+'%';content.style.transform='scale('+scale+')';const bodyRect=body.getBoundingClientRect();const contentRect=content.getBoundingClientRect();const safeHeight=Math.max(1,bodyRect.bottom-contentRect.top-.5);if(contentRect.height>safeHeight){scale*=safeHeight/Math.max(1,contentRect.height);content.style.transform='scale('+scale+')';}content.dataset.fitScale=scale.toFixed(4);});}
window.TripLensFitReport=fitReportPages;requestAnimationFrame(function(){fitReportPages();requestAnimationFrame(fitReportPages);});
</script></body></html>`;
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
      fonts.finally(() => { if (typeof popup.TripLensFitReport === 'function') popup.TripLensFitReport(); popup.focus(); popup.print(); });
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
