import test from 'node:test';
import assert from 'node:assert/strict';

import {analysisApiUrl} from '../apps/web/lib/analysisApi.mjs';

test('browser analysis calls always use the same-origin proxy',()=>{
  process.env.NEXT_PUBLIC_TRIPLENS_API_BASE='https://legacy-api.example.com';
  assert.equal(analysisApiUrl('/bootstrap'),'/api/triplens/bootstrap');
  assert.equal(analysisApiUrl('analyze'),'/api/triplens/analyze');
});
