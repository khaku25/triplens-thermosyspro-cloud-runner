import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(new URL('..', import.meta.url).pathname);

test('independent app entry exposes Dual Log intake and exports', () => {
  const html = fs.readFileSync(path.join(root, 'webapp/index.html'), 'utf8');
  for (const token of ['id="eventFile"','id="rawFile"','id="analyzeBtn"','id="geminiBtn"','id="pdfBtn"','id="pinpointBtn"','id="analysisCsvBtn"']) {
    assert.match(html, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
  for (const src of ['/webapp/event_tag_resolver.js','/webapp/triplens_report_export.js','/webapp/triplens_core.js','/webapp/app.js']) {
    assert.ok(html.includes(src), `missing script ${src}`);
  }
  for (const section of ['Incident Summary','Critical Events','Primary Cause','Direct Trigger','Propagation','Causal Chain','Key Evidence','Recovery Check','Gemini Analysis']) {
    assert.ok(html.includes(section), `missing section ${section}`);
  }
});

test('release contract files define a Vercel root rewrite and npm test command', () => {
  const vercel = JSON.parse(fs.readFileSync(path.join(root, 'vercel.json'), 'utf8'));
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  assert.ok(vercel.rewrites.some(r => r.source === '/' && r.destination === '/webapp/index.html'));
  assert.ok(pkg.scripts?.test?.includes('node --test'));
});
