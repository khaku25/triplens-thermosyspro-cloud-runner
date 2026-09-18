import fs from 'node:fs';
import {buildDraftRows} from '../apps/web/lib/analysisClient.mjs';

const [,,inputPath,outputPath] = process.argv;
if (!inputPath || !outputPath) {
  console.error('usage: node tests/build_report_rows.mjs envelope.json report_rows.json');
  process.exit(2);
}
const envelope = JSON.parse(fs.readFileSync(inputPath,'utf8'));
const rows = buildDraftRows(envelope);
fs.writeFileSync(outputPath, JSON.stringify(rows,null,2), 'utf8');
console.log(JSON.stringify({rows:rows.length,sections:[...new Set(rows.map(r=>r.section))]},null,2));
