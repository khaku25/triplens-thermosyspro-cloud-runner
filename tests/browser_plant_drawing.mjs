// Run against a built app with: DRAWING_BASE_URL=http://127.0.0.1:3151 node --test tests/browser_plant_drawing.mjs
import test, {before,after} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const require = createRequire(import.meta.url);
const playwright = require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
  ? `${process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES}/playwright`
  : 'playwright');
const base = process.env.DRAWING_BASE_URL || 'http://127.0.0.1:3151';
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || playwright.chromium.executablePath();
let server;
before(async () => {
  if (process.env.DRAWING_BASE_URL) return;
  const cwd = fileURLToPath(new URL('../apps/web/',import.meta.url));
  const env = {...process.env};
  if (process.env.DRAWING_OS_SHIM) env.NODE_OPTIONS = `--require=${process.env.DRAWING_OS_SHIM}`;
  server = spawn(process.execPath,['node_modules/next/dist/bin/next','start','--port','3151','--hostname','127.0.0.1'],{cwd,env,stdio:'ignore'});
  for (let i=0;i<80;i++) {
    try { if ((await fetch(base)).ok) return; } catch {}
    if (server.exitCode !== null) throw Error(`Next server exited with code ${server.exitCode}`);
    await new Promise(resolve => setTimeout(resolve,150));
  }
  throw Error('Next server not ready');
});
after(() => server?.kill());

test('Plant direct jump highlights exact pump, valves, condenser, and exposes hotspots', async () => {
  const browser = await playwright.chromium.launch({headless:true,executablePath,args:['--no-sandbox']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:950}});
    const errors = [];
    page.on('pageerror',error => errors.push(error.message));
    for (const [name,id] of [['LP BFP','LP_BFP'],['HP BFP','HP_BFP'],['IP BFP','IP_BFP'],
      ['HP-BYPASS-VLV','HP_BYPASS_VLV'],['LP Bypass','LP_BYPASS_VLV'],['Condenser','CONDENSER']]) {
      await page.goto(`${base}/drawing?equipment=${encodeURIComponent(name)}&view=plant`);
      const hotspot = page.getByRole('button',{name:new RegExp(`${id.replaceAll('_',' ')} 도면 위치`,'i')});
      if (id === 'HP_BYPASS_VLV' || id === 'LP_BYPASS_VLV') {
        await assert.doesNotReject(() => page.locator('.drawing-hotspot.is-active').waitFor());
      } else await assert.doesNotReject(() => hotspot.waitFor());
      assert.equal(await page.locator('.drawing-hotspot.is-active').count(),1);
      assert.match(await page.locator('[role=status]').innerText(),/위치 표시 중/);
      assert.equal(await page.locator('.drawing-canvas img').evaluate(image => image.naturalWidth),2044);
    }
    assert.equal(await page.locator('.drawing-hotspot').count(),19);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:'/workspace/scratch/dcbbc7676ae2/plant-preview.png'});
  } finally { await browser.close(); }
});

test('ECMS bus drill down and exact breaker direct jump remain usable on mobile', async () => {
  const browser = await playwright.chromium.launch({headless:true,executablePath,args:['--no-sandbox']});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    await page.goto(`${base}/drawing?view=ecms`);
    assert.equal(await page.locator('.drawing-canvas img').evaluate(image => image.naturalWidth),1400);
    await page.getByRole('button',{name:'6.9 kV BUS-A 도면 위치'}).click();
    await page.waitForURL(/page=detail/);
    assert.equal(await page.locator('.drawing-canvas img').evaluate(image => image.naturalWidth),1500);
    assert.match(await page.locator('[role=status]').innerText(),/BUS-A/);
    await page.goto(`${base}/drawing?equipment=VCB-A01`);
    assert.equal(await page.locator('.drawing-hotspot.is-active').getAttribute('title'),'VCB-A01 · HP BFP');
    await page.getByRole('button',{name:'02 Plant Process View'}).click();
    await page.getByLabel('설비 위치').selectOption('FWP-LP');
    assert.match(await page.locator('[role=status]').innerText(),/LP BFP/);
    const centered = await page.evaluate(() => {
      const spot = document.querySelector('.drawing-hotspot.is-active').getBoundingClientRect();
      const frame = document.querySelector('.drawing-scroll').getBoundingClientRect();
      return spot.left >= frame.left && spot.right <= frame.right;
    });
    assert.equal(centered,true,'direct jump must bring the pump into the mobile viewport');
    await page.screenshot({path:'/workspace/scratch/dcbbc7676ae2/plant-mobile-preview.png'});
  } finally { await browser.close(); }
});
