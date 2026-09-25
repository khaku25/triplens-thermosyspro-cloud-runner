import test from 'node:test';
import assert from 'node:assert/strict';
import {
  WORKSPACE_SESSION_VERSION,
  buildWorkspaceSession,
  canRestoreWorkspaceSession,
} from './workspaceSession.mjs';

const eventFile = {name: 'EVENT.csv', size: 42};
const rawFile = {name: 'RAW.csv', size: 84};
const eventData = {fields: ['tag'], records: [{tag: 'TRIP'}]};
const rawData = {fields: ['vpp52STClosed'], records: [{vpp52STClosed: '1'}]};
const result = {run_id: 'RUN-1', analysis: {verification_gate: 'HOLD'}};
const reportRows = [{row_id: 'ROW-1', section: '개요'}];
const recovery = {status: 'NOT_STARTED'};

test('builds a restorable workspace payload without dropping analysis state', () => {
  const payload = buildWorkspaceSession({
    mode: 'blind', eventFile, rawFile, eventData, rawData, result,
    reportRows, recovery, activeTab: 'cause',
  });

  assert.equal(payload.schema_version, WORKSPACE_SESSION_VERSION);
  assert.equal(payload.mode, 'blind');
  assert.equal(payload.eventFile, eventFile);
  assert.equal(payload.rawFile, rawFile);
  assert.deepEqual(payload.eventData, eventData);
  assert.deepEqual(payload.rawData, rawData);
  assert.deepEqual(payload.result, result);
  assert.deepEqual(payload.reportRows, reportRows);
  assert.deepEqual(payload.recovery, recovery);
  assert.equal(payload.activeTab, 'cause');
  assert.equal(canRestoreWorkspaceSession(payload, 'blind'), true);
});

test('rejects sessions from another mode or schema version', () => {
  const payload = buildWorkspaceSession({mode: 'blind'});

  assert.equal(canRestoreWorkspaceSession({...payload, mode: 'demo'}, 'blind'), false);
  assert.equal(canRestoreWorkspaceSession({...payload, schema_version: 999}, 'blind'), false);
  assert.equal(canRestoreWorkspaceSession(null, 'blind'), false);
});
