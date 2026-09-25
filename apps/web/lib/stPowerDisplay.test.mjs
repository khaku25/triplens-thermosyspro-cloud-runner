import test from 'node:test';
import assert from 'node:assert/strict';
import {ST_POWER_DISPLAY} from './stPowerDisplay.mjs';

test('defines the exact ST power display identity', () => {
  assert.deepEqual(ST_POWER_DISPLAY, {
    label: 'ST POWER',
    tag: 'vppSTGridPowerMW',
    unit: 'MW',
    href: '/logic?tag=vppSTGridPowerMW',
  });
});
