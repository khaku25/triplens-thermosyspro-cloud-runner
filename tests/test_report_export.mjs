import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const exporter = require('../webapp/triplens_report_export.js');

const report = {
  title: 'TripLens Incident Analysis Report',
  run_id: 'RUN-TEST-001',
  metadata: {
    run_id: 'RUN-TEST-001',
    event_file: 'EVENT.csv',
    raw_file: 'RAW.csv',
  },
  incident_summary: 'Dual Log evidence preserved',
  critical_events: [
    {
      claim: 'ST Trip latch active',
      disposition: 'CONFIRMED',
      evidence: [{
        source_system: 'DCS1', event_id: 'EV-1', original_time: '48.440', aligned_time: '48.440',
        equipment: 'ST', event_tag: 'TRIP_LATCH', canonical_tag: 'ST.TRIP.LATCH', value: 1,
        unit: 'BOOL', state: 'ACTIVE', evidence_role: 'TRIGGER', mapping_status: 'EVENT_RULE',
      }],
    },
  ],
  primary_cause: { claim: 'Cause candidate', disposition: 'CANDIDATE', review_required: true },
  direct_trigger: 'ST Trip latch',
  propagation: '52ST open -> secondary alarms',
  causal_chain: ['ST Trip latch', '52ST breaker open'],
  key_evidence: [{ source: 'EVENT.csv', tag: 'TRIP_LATCH' }],
  recovery_check: 'Not fully recovered',
  gemini_analysis: 'Additional engineering review text',
};

test('PDF report HTML expands every analysis section into the isolated report document', () => {
  const html = exporter.buildReportHtml(report);
  for (const text of [
    'Incident Summary', 'Critical Events', 'Primary Cause', 'Direct Trigger', 'Propagation',
    'Causal Chain', 'Key Evidence', 'Recovery Check', 'Gemini Analysis',
    'Additional engineering review text', 'EVENT.csv', 'RAW.csv',
  ]) assert.match(html, new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.match(html, /overflow:visible!important/);
  assert.match(html, /max-height:none!important/);
  assert.doesNotMatch(html, /window\.print\(\).*dashboard/i);
});

test('PINPOINT CSV keeps canonical evidence and review state', () => {
  const csv = exporter.buildPinpointCsv(report);
  assert.match(csv, /^run_id,pinpoint_rank,causal_stage,claim,disposition,/);
  assert.match(csv, /RUN-TEST-001/);
  assert.match(csv, /ST\.TRIP\.LATCH/);
  assert.match(csv, /TRIP_LATCH/);
  assert.match(csv, /CONFIRMED/);
  assert.match(csv, /CANDIDATE/);
});
