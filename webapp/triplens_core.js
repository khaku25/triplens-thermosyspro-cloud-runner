(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.TripLensCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const FORBIDDEN_KEY = /(scenario|root.?cause.?answer|expected.?root.?cause|answer.?key|ground.?truth|fault.?injection)/i;

  function parseCsv(text) {
    const input = String(text || '').replace(/^\uFEFF/, '');
    const rows = [];
    let row = [], field = '', quoted = false;
    for (let i = 0; i < input.length; i++) {
      const ch = input[i];
      if (quoted) {
        if (ch === '"' && input[i + 1] === '"') { field += '"'; i++; }
        else if (ch === '"') quoted = false;
        else field += ch;
      } else {
        if (ch === '"') quoted = true;
        else if (ch === ',') { row.push(field); field = ''; }
        else if (ch === '\n') { row.push(field.replace(/\r$/, '')); rows.push(row); row = []; field = ''; }
        else field += ch;
      }
    }
    if (field.length || row.length) { row.push(field.replace(/\r$/, '')); rows.push(row); }
    if (!rows.length) return [];
    const headers = rows.shift().map(h => h.trim());
    return rows.filter(r => r.some(v => String(v).trim() !== '')).map(r => {
      const obj = {};
      headers.forEach((h, idx) => { obj[h] = r[idx] == null ? '' : r[idx]; });
      return obj;
    });
  }

  function norm(value) { return String(value ?? '').trim(); }
  function upper(value) { return norm(value).toUpperCase(); }
  function keyPart(value) { return upper(value).replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, ''); }
  function pick(row, names) {
    for (const n of names) if (row && row[n] != null && norm(row[n]) !== '') return row[n];
    return '';
  }
  function numTime(row) {
    const raw = pick(row, ['aligned_time','original_time','model_time','time','timestamp','Time','TIME']);
    const n = Number(raw);
    if (Number.isFinite(n)) return n;
    const d = Date.parse(raw);
    return Number.isFinite(d) ? d / 1000 : NaN;
  }

  function canonicalForRegistry(row) {
    const rule = upper(row.rule_id);
    const equipment = upper(row.equipment);
    const tag = upper(row.tag || row.event_tag);
    if (rule === 'GT_TRIP_LATCH' || (equipment === 'GT' && tag === 'TRIP_LATCH')) return 'GT.TRIP.LATCH';
    if (rule === 'ST_TRIP_LATCH' || (equipment === 'ST' && tag === 'TRIP_LATCH')) return 'ST.TRIP.LATCH';
    const m = equipment.match(/^(HP|IP|LP) TURBINE$/);
    if (m && tag === 'FLOW_LOW') return `HRSG.${m[1]}.STEAM.FLOW.L`;
    if (m && tag === 'FLOW_LOW_LOW') return `HRSG.${m[1]}.STEAM.FLOW.LL`;
    return `EVENT.${keyPart(equipment || 'UNKNOWN').replace(/_/g,'.')}.${keyPart(tag || rule || 'UNKNOWN').replace(/_/g,'.')}`;
  }

  function buildEventMap(registryRows) {
    const rows = (registryRows || []).filter(r => norm(r.enabled || '1') !== '0').map(r => ({
      rule_id: norm(r.rule_id),
      equipment: norm(r.equipment),
      event_tag: norm(r.tag || r.event_tag),
      source_node: norm(r.source_node),
      priority: norm(r.priority),
      event_class: norm(r.event_class),
      canonical_tag: canonicalForRegistry(r),
      unit: norm(r.unit),
      active_message: norm(r.active_message),
      return_message: norm(r.return_message),
    }));
    const byRule = new Map(), byPair = new Map(), bySource = new Map();
    for (const r of rows) {
      if (r.rule_id) byRule.set(upper(r.rule_id), r);
      byPair.set(`${upper(r.equipment)}::${upper(r.event_tag)}`, r);
      if (r.source_node) {
        const k = upper(r.source_node);
        if (!bySource.has(k)) bySource.set(k, []);
        bySource.get(k).push(r);
      }
    }
    return { rows, byRule, byPair, bySource };
  }

  function resolveEventTag(event, map) {
    const canonical = norm(pick(event, ['canonical_tag','canonical_tag_id','tag_id']));
    if (canonical) return { canonical_tag: canonical, mapping_status: 'CANONICAL_TAG', matched_by: 'canonical_tag', mapping: null };
    const rule = upper(pick(event, ['rule_id','rule']));
    if (rule && map?.byRule?.has(rule)) {
      const r = map.byRule.get(rule); return { canonical_tag: r.canonical_tag, mapping_status: 'MAPPED', matched_by: 'rule_id', mapping: r };
    }
    const source = upper(pick(event, ['source_node','source_tag','raw_tag']));
    if (source && map?.bySource?.has(source)) {
      const candidates = map.bySource.get(source);
      if (candidates.length === 1) return { canonical_tag: candidates[0].canonical_tag, mapping_status: 'MAPPED', matched_by: 'source_node', mapping: candidates[0] };
      const eq = upper(pick(event, ['equipment','asset']));
      const tag = upper(pick(event, ['tag','event_tag','alarm_tag']));
      const exact = candidates.find(r => upper(r.equipment) === eq && upper(r.event_tag) === tag);
      if (exact) return { canonical_tag: exact.canonical_tag, mapping_status: 'MAPPED', matched_by: 'source_node+equipment+tag', mapping: exact };
    }
    const pair = `${upper(pick(event, ['equipment','asset']))}::${upper(pick(event, ['tag','event_tag','alarm_tag']))}`;
    if (map?.byPair?.has(pair)) {
      const r = map.byPair.get(pair); return { canonical_tag: r.canonical_tag, mapping_status: 'MAPPED', matched_by: 'equipment+tag', mapping: r };
    }
    return { canonical_tag: '', mapping_status: 'UNMAPPED_EVENT_TAG', matched_by: '', mapping: null };
  }

  function stateOf(row) { return upper(pick(row, ['state','status','event_state','alarm_state','active'])); }
  function isReturn(row) { return /RETURN|RESET|CLEAR|INACTIVE|NORMAL/.test(stateOf(row)); }
  function isCritical(ev) {
    const p = upper(ev.priority || ev.mapping?.priority);
    const tag = upper(ev.event_tag || ev.tag);
    return p === 'CRITICAL' || p === 'HIGH' || /(TRIP|BREAKER_OPEN|LOW_LOW|HIGH_HIGH|_LL$|_HH$|LOST)/.test(tag);
  }

  function sanitize(value) {
    if (Array.isArray(value)) return value.map(sanitize);
    if (value && typeof value === 'object') {
      const out = {};
      for (const [k,v] of Object.entries(value)) if (!FORBIDDEN_KEY.test(k)) out[k] = sanitize(v);
      return out;
    }
    return value;
  }

  function analyzeDualLog(eventRows, rawRows, eventMap, metadata) {
    const events = (eventRows || []).map((row, i) => {
      const resolved = resolveEventTag(row, eventMap);
      const mapping = resolved.mapping || {};
      const time = numTime(row);
      return {
        event_id: norm(pick(row, ['event_id','id'])) || `E${String(i + 1).padStart(4,'0')}`,
        original_time: Number.isFinite(time) ? time : norm(pick(row, ['time','model_time','timestamp'])),
        aligned_time: Number.isFinite(time) ? time : norm(pick(row, ['aligned_time'])),
        equipment: norm(pick(row, ['equipment','asset'])) || mapping.equipment || '',
        event_tag: norm(pick(row, ['tag','event_tag','alarm_tag'])) || mapping.event_tag || '',
        canonical_tag: resolved.canonical_tag,
        mapping_status: resolved.mapping_status,
        mapping_method: resolved.matched_by,
        rule_id: norm(pick(row, ['rule_id','rule'])) || mapping.rule_id || '',
        source_node: norm(pick(row, ['source_node','source_tag'])) || mapping.source_node || '',
        priority: norm(pick(row, ['priority'])) || mapping.priority || '',
        source_system: norm(pick(row, ['source','source_system'])) || 'EVENT',
        state: norm(pick(row, ['state','status','event_state'])) || '',
        value: norm(pick(row, ['value','event_value'])) || '',
        unit: norm(pick(row, ['unit'])) || mapping.unit || '',
        message: norm(pick(row, ['message','description','alarm_message'])) || mapping.active_message || '',
      };
    }).sort((a,b) => (Number(a.aligned_time) || 0) - (Number(b.aligned_time) || 0));

    const active = events.filter(e => !isReturn(e));
    const critical = active.filter(isCritical);
    const primary = critical[0] || active[0] || {};
    const trigger = critical.find(e => /(TRIP_LATCH|TRIP_CMD|BREAKER_OPEN|FLOW_LOW_LOW|LEVEL_LOW_LOW|PRESS_LOW_LOW|_LL$|_HH$)/.test(upper(e.event_tag))) || primary;
    const propagation = critical.filter(e => e.event_id !== trigger.event_id && Number(e.aligned_time) >= Number(trigger.aligned_time || -Infinity));
    const chain = [];
    for (let i = 0; i < critical.length - 1; i++) chain.push({ from_event_id: critical[i].event_id, to_event_id: critical[i+1].event_id, relation: 'TEMPORAL_PROPAGATION' });
    const recoveries = events.filter(isReturn);
    const rawTimes = (rawRows || []).map(numTime).filter(Number.isFinite);
    const eventTimes = events.map(e => Number(e.aligned_time)).filter(Number.isFinite);
    const rawMax = rawTimes.length ? Math.max(...rawTimes) : NaN;
    const eventMax = eventTimes.length ? Math.max(...eventTimes) : NaN;
    const rawCoverage = !rawTimes.length ? {status:'NO_RAW_DATA'} : (Number.isFinite(eventMax) && rawMax < eventMax ? {status:'INSUFFICIENT_POST_EVENT_WINDOW', raw_end:rawMax, event_end:eventMax} : {status:'COVERED', raw_end:rawMax, event_end:eventMax});
    const unmapped = events.filter(e => e.mapping_status === 'UNMAPPED_EVENT_TAG').length;
    const runId = norm(metadata?.run_id) || `RUN-${Date.now()}`;
    return {
      run_id: runId,
      generated_at: new Date().toISOString(),
      metadata: {
        event_filename: norm(metadata?.event_filename), raw_filename: norm(metadata?.raw_filename),
        event_count: events.length, raw_row_count: (rawRows || []).length, mapped_event_count: events.length - unmapped, unmapped_event_count: unmapped,
      },
      incident_summary: {
        status: 'DETERMINISTIC_BASELINE',
        first_event_time: events[0]?.aligned_time ?? '', last_event_time: events.at(-1)?.aligned_time ?? '',
        critical_event_count: critical.length, unmapped_event_count: unmapped, raw_coverage: rawCoverage.status,
        statement: primary.event_id ? `Earliest critical evidence: ${primary.canonical_tag || primary.event_tag}` : 'No critical EVENT evidence identified.'
      },
      critical_events: critical,
      primary_cause: primary,
      direct_trigger: trigger,
      propagation,
      causal_chain: chain,
      key_evidence: critical.slice(0, 12),
      recovery_check: { status: recoveries.length ? 'RECOVERY_EVIDENCE_PRESENT' : 'NOT_CONFIRMED', events: recoveries },
      raw_coverage: rawCoverage,
      event_evidence: events,
      raw_evidence: (rawRows || []).slice(0, 500).map(sanitize),
      logic_context: [],
      gemini_analysis: null,
    };
  }

  function buildGeminiPayload(report) {
    return sanitize({
      run_id: report?.run_id || '',
      event_evidence: report?.event_evidence || [],
      raw_evidence: report?.raw_evidence || [],
      logic_context: report?.logic_context || [],
      deterministic_summary: report?.incident_summary || {},
    });
  }

  return { parseCsv, buildEventMap, resolveEventTag, analyzeDualLog, buildGeminiPayload, sanitize };
});
