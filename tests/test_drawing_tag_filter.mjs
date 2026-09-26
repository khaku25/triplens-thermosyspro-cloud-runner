import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const viewer = await readFile(new URL('../scripts/logic_assets/viewer.html', import.meta.url), 'utf8');

function loadProductionFunction(name) {
  const start = viewer.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `production function ${name} must exist`);
  const open = viewer.indexOf('{', start);
  let depth = 0;
  for (let cursor = open; cursor < viewer.length; cursor += 1) {
    if (viewer[cursor] === '{') depth += 1;
    if (viewer[cursor] === '}') depth -= 1;
    if (depth === 0) return vm.runInNewContext(`(${viewer.slice(start, cursor + 1)})`);
  }
  assert.fail(`production function ${name} has an incomplete body`);
}

test('tag selection contains only exact tag-linked drawing rows and picks the first location', () => {
  const select = loadProductionFunction('tagDrawingSelection');
  const rows = [
    { tag_id: 'tag-a', page_id: 'page-a', cell_id: 'page-location' },
    { tag_id: 'tag-b', page_id: 'page-b', cell_id: 'other-tag' },
    { tag_id: 'tag-a', page_id: 'page-a-rule', cell_id: 'rule-location' },
    { canonical_tag: 'tag-a', page_id: 'page-canonical', cell_id: 'canonical-only' },
  ];

  const result = JSON.parse(JSON.stringify(select(rows, 'tag-a')));
  assert.deepEqual(result.rows.map(row => row.cell_id), ['page-location', 'rule-location']);
  assert.equal(result.selected.cell_id, 'page-location');
  assert.equal(result.pageId, 'page-a');
});

test('tag selection reports no selected drawing when there are no exact locations', () => {
  const select = loadProductionFunction('tagDrawingSelection');
  const result = JSON.parse(JSON.stringify(select([{ tag_id: 'tag-b', page_id: 'page-b', cell_id: 'other-tag' }], 'tag-a')));
  assert.deepEqual(result, { rows: [], selected: null, pageId: 'overview' });
});
