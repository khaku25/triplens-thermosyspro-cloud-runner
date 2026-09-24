import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const readJson = relativePath => JSON.parse(readFileSync(new URL(relativePath, import.meta.url), 'utf8'));

const logicIndex = readJson('../apps/web/public/logic-assets/logic_diagram_index.json');
const drawingIndex = readJson('../apps/web/public/logic-assets/drawing_master_index.json');
const manifest = readJson('../apps/web/public/logic-assets/asset_manifest.json');

test('published Logic/TAG assets expose the verified ST grid power signal', () => {
  assert.deepEqual(manifest.counts, {
    source_tags: 604,
    rules: 54,
    input_groups: 36,
    native_inputs: 45,
    native_outputs: 29,
    derived_outputs: 28,
    equipment_pages: 9,
    pages: 100,
  });

  const tag = logicIndex.tags.vppSTGridPowerMW;
  assert.equal(tag.raw_tag_id, 'vppSTGridPowerMW');
  assert.equal(tag.equipment_id, 'STG');
  assert.equal(tag.unit, 'MW');
  assert.equal(tag.writable, 'N');
  assert.deepEqual(tag.rule_ids, ['RESP-ST-GRID-POWER']);
});

test('published Drawing Master links ST grid power to its exact rule diagrams', () => {
  const rule = logicIndex.rules['RESP-ST-GRID-POWER'];
  assert.equal(rule.input_group_id, 'IG-036');
  assert.equal(rule.screen, 'ST Protection');
  assert.deepEqual(rule.outputs, ['vppSTGridPowerMW']);

  const pages = drawingIndex.entries
    .filter(entry => entry.tag_id === 'vppSTGridPowerMW' && entry.object_type === 'source')
    .map(entry => entry.page_name)
    .sort();

  assert.deepEqual(pages, [
    'IG-036 · ST Protection',
    'RESP-ST-GRID-POWER',
    'ST Protection',
  ]);
  assert.deepEqual(drawingIndex.counts, {
    drawings: 1,
    pages: 100,
    cells: 1583,
    linked_tags: 87,
    linked_logic: 54,
  });
});
