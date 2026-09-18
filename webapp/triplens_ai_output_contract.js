/* TripLens AI output contract.
 *
 * Normalizes provider-specific/free-form analysis into an evidence-linked,
 * fail-closed incident-analysis object. This module does not mutate source
 * EVENT/RAW evidence and does not perform equipment control.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.TripLensAIOutputContract = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const VALID_STATUSES = new Set(['CONFIRMED', 'CANDIDATE', 'OBSERVED', 'UNKNOWN']);
  const STATUS_LABELS = Object.freeze({
    CONFIRMED: '■ 확인 (CONFIRMED)',
    CANDIDATE: '△ 후보 (CANDIDATE)',
    OBSERVED: '○ 관측 (OBSERVED)',
    UNKNOWN: '— 미확인 (UNKNOWN)',
  });

  function upper(value, fallback = '') {
    const text = String(value ?? '').trim().toUpperCase();
    return text || fallback;
  }

  function unique(values) {
    return [...new Set(values.filter((value) => value !== undefined && value !== null && String(value).trim() !== '').map(String))];
  }

  function array(value) {
    if (value == null || value === '') return [];
    return Array.isArray(value) ? value.slice() : [value];
  }

  function statusLabel(status) {
    return STATUS_LABELS[upper(status, 'UNKNOWN')] || STATUS_LABELS.UNKNOWN;
  }

  function evidenceIds(src) {
    const direct = array(src.evidence_ids || src.evidenceIds);
    const evidence = array(src.evidence).map((item) => {
      if (item && typeof item === 'object') return item.evidence_id || item.event_id || item.id || '';
      return item;
    });
    return unique([...direct, ...evidence]);
  }

  function relatedTags(src) {
    const direct = array(src.related_tags || src.relatedTags || src.tags);
    const evidence = array(src.evidence).flatMap((item) => {
      if (!item || typeof item !== 'object') return [];
      return [item.canonical_tag, item.event_tag, item.tag].filter(Boolean);
    });
    return unique([...direct, ...evidence]);
  }

  function claimText(src) {
    return String(src.claim ?? src.description ?? src.summary ?? src.title ?? src.text ?? '').trim();
  }

  function normalizeClaim(value, stage, context = {}) {
    const src = value && typeof value === 'object' && !Array.isArray(value)
      ? { ...value }
      : { claim: value == null ? '' : String(value) };
    const normalizedStage = upper(stage, 'UNKNOWN');
    const ids = evidenceIds(src);
    const tags = relatedTags(src);
    const claim = claimText(src);
    const rawStatus = upper(src.status || src.disposition, '');
    let status = VALID_STATUSES.has(rawStatus) ? rawStatus : 'UNKNOWN';

    if (claim && ids.length && !rawStatus) {
      if (normalizedStage === 'PRIMARY_CAUSE') status = 'CANDIDATE';
      else if (normalizedStage === 'PROPAGATION' || normalizedStage === 'CRITICAL_EVENT') status = 'OBSERVED';
    }

    if (claim && !ids.length) status = 'UNKNOWN';

    const logicMasterStatus = upper(src.logic_master_status || src.logic_master || src.logic_status, 'NOT_VERIFIED');
    const counterEvidence = array(src.counter_evidence).map((item) => (typeof item === 'object' ? { ...item } : item));
    const verificationGate = upper(context.verificationGate || context.verification_gate, 'HOLD');
    const recordedTime = String(src.recorded_time ?? src.aligned_time ?? src.aligned_time_s ?? src.time ?? src.timestamp ?? '');
    const recordedSeconds = Number(recordedTime);
    const cutoffSeconds = Number(context.initiatingCutoffTime);
    const hasCutoff = Number.isFinite(cutoffSeconds);
    const beforeOrAtCutoff = !hasCutoff || (Number.isFinite(recordedSeconds) && recordedSeconds <= cutoffSeconds + 1e-9);
    const deterministicTimeOrderValid = src.time_order_valid === true && beforeOrAtCutoff;

    if (normalizedStage === 'PRIMARY_CAUSE' && status !== 'UNKNOWN') {
      const canConfirm = verificationGate === 'PASS' && ids.length > 0 && deterministicTimeOrderValid &&
        logicMasterStatus === 'VERIFIED' && counterEvidence.length === 0;
      if (status === 'CONFIRMED' && !canConfirm) status = 'CANDIDATE';
      if (status === 'OBSERVED') status = 'CANDIDATE';
    }

    const aiConfidenceRaw = src.ai_confidence ?? src.confidence;
    const aiConfidence = aiConfidenceRaw === '' || aiConfidenceRaw == null || Number.isNaN(Number(aiConfidenceRaw))
      ? null
      : Number(aiConfidenceRaw);

    return {
      stage: normalizedStage,
      status,
      status_label: statusLabel(status),
      claim,
      description: claim,
      evidence_ids: ids,
      related_tags: tags,
      recorded_time: recordedTime,
      ai_confidence: aiConfidence,
      logic_master_status: logicMasterStatus,
      time_order_valid: normalizedStage === 'PRIMARY_CAUSE'
        ? (src.time_order_valid === true ? deterministicTimeOrderValid : src.time_order_valid === false ? false : null)
        : (src.time_order_valid === true ? true : src.time_order_valid === false ? false : null),
      counter_evidence: counterEvidence,
      review_required: src.review_required === true || status === 'CANDIDATE' || status === 'UNKNOWN',
      source: src.source || src.source_system || '',
      note: src.note || src.notes || '',
    };
  }

  function normalizeRecommendation(value) {
    const src = value && typeof value === 'object' && !Array.isArray(value) ? { ...value } : { claim: String(value ?? '') };
    return {
      claim: claimText(src),
      status: 'CANDIDATE',
      status_label: STATUS_LABELS.CANDIDATE,
      evidence_ids: evidenceIds(src),
      related_tags: relatedTags(src),
      note: src.note || src.notes || '담당자 승인 필요',
      requires_human_approval: true,
    };
  }

  function normalizeAnalysis(raw, options = {}) {
    const source = raw && typeof raw === 'object' ? raw : {};
    const verificationGate = upper(options.verification_gate || options.verificationGate || source.verification_gate || source.verificationGate, 'HOLD');
    const context = { verificationGate };

    const criticalEvents = array(source.critical_events).map((item) => normalizeClaim(item, 'CRITICAL_EVENT', context));
    const directTrigger = normalizeClaim(source.direct_trigger, 'DIRECT_TRIGGER', context);
    const triggerSeconds = Number(directTrigger.recorded_time);
    const primaryContext = Number.isFinite(triggerSeconds)
      ? { ...context, initiatingCutoffTime: triggerSeconds }
      : context;
    const primaryCause = normalizeClaim(source.primary_cause, 'PRIMARY_CAUSE', primaryContext);
    const propagation = array(source.propagation).map((item) => normalizeClaim(item, 'PROPAGATION', context));
    const causalChain = array(source.causal_chain).map((item) => {
      if (item && typeof item === 'object') return { ...item };
      return String(item ?? '');
    });
    const counterEvidence = array(source.counter_evidence).map((item) => (item && typeof item === 'object' ? { ...item } : item));
    const additionalEvidenceRequired = array(source.additional_evidence_required || source.additional_evidence || source.unknown_items)
      .map((item) => (item && typeof item === 'object' ? { ...item } : String(item ?? '')));
    const recommendations = array(source.review_recommendations || source.recommendations || source.recurrence_prevention)
      .map(normalizeRecommendation)
      .filter((item) => item.claim);

    return {
      critical_events: criticalEvents,
      primary_cause: primaryCause,
      direct_trigger: directTrigger,
      propagation,
      causal_chain: causalChain,
      counter_evidence: counterEvidence,
      additional_evidence_required: additionalEvidenceRequired,
      review_recommendations: recommendations,
      verification_gate: verificationGate,
      finality: {
        can_mark_final_confirmed: verificationGate === 'PASS',
        output_label: verificationGate === 'PASS' ? '고장보고서 검토본' : '고장보고서 초안',
        verification_label: verificationGate === 'PASS' ? '검증 통과' : '검증 미완료',
      },
    };
  }

  return {
    VALID_STATUSES,
    STATUS_LABELS,
    statusLabel,
    normalizeClaim,
    normalizeAnalysis,
  };
});
