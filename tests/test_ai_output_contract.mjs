import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const contract = require('../webapp/triplens_ai_output_contract.js');

test('primary cause remains candidate unless engineering confirmation gates all pass', () => {
  const normalized = contract.normalizeAnalysis({
    verification_gate: 'HOLD',
    primary_cause: {
      status: 'CONFIRMED', claim: 'LP BFP speed degradation',
      evidence_ids: ['RAW-017'], recorded_time: '30.120',
      logic_master_status: 'VERIFIED', counter_evidence: [], ai_confidence: 0.99,
    },
  });
  assert.equal(normalized.primary_cause.status, 'CANDIDATE');
  assert.equal(normalized.primary_cause.ai_confidence, 0.99);
});

test('unsupported cause claim fails closed to unknown', () => {
  const normalized = contract.normalizeAnalysis({ primary_cause: { claim: 'Pump cavitation' } });
  assert.equal(normalized.primary_cause.status, 'UNKNOWN');
  assert.deepEqual(normalized.primary_cause.evidence_ids, []);
});

test('chronological critical events are not truncated at five items', () => {
  const events = Array.from({ length: 12 }, (_, i) => ({
    claim: `Event ${i + 1}`, status: 'OBSERVED', evidence_ids: [`EV-${i + 1}`], recorded_time: String(i),
  }));
  const normalized = contract.normalizeAnalysis({ critical_events: events });
  assert.equal(normalized.critical_events.length, 12);
});

test('hold verification blocks final-confirmed wording', () => {
  const normalized = contract.normalizeAnalysis({ verification_gate: 'HOLD' });
  assert.equal(normalized.finality.can_mark_final_confirmed, false);
  assert.equal(normalized.finality.output_label, '고장보고서 초안');
});


test('post-trigger secondary cause cannot be confirmed as primary cause', () => {
  const normalized = contract.normalizeAnalysis({
    verification_gate: 'PASS',
    direct_trigger: {
      status: 'CONFIRMED', claim: 'GT trip latch',
      evidence_ids: ['EV-TRIP'], recorded_time: '48.440',
      logic_master_status: 'VERIFIED',
    },
    primary_cause: {
      status: 'CONFIRMED', claim: 'IP drum HH',
      evidence_ids: ['EV-IP-HH'], recorded_time: '131.925',
      logic_master_status: 'VERIFIED', time_order_valid: true, counter_evidence: [],
    },
  });
  assert.equal(normalized.primary_cause.status, 'CANDIDATE');
  assert.equal(normalized.primary_cause.time_order_valid, false);
});

test('preceding verified cause may remain confirmed when gate passes', () => {
  const normalized = contract.normalizeAnalysis({
    verification_gate: 'PASS',
    direct_trigger: {
      status: 'CONFIRMED', claim: 'GT trip latch',
      evidence_ids: ['EV-TRIP'], recorded_time: '48.440',
      logic_master_status: 'VERIFIED',
    },
    primary_cause: {
      status: 'CONFIRMED', claim: 'Direct GT command',
      evidence_ids: ['RAW-CMD'], recorded_time: '48.400',
      logic_master_status: 'VERIFIED', time_order_valid: true, counter_evidence: [],
    },
  });
  assert.equal(normalized.primary_cause.status, 'CONFIRMED');
  assert.equal(normalized.primary_cause.time_order_valid, true);
});
