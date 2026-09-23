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

test('Plant direct jump highlights exact pumps, bypass valves, condenser and EVENT label',async()=>{
  const browser=await playwright.chromium.launch({headless:true,executablePath,args:['--no-sandbox']});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:950}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    for(const [name,label] of [['LP BFP','LP BFP'],['HP BFP','HP BFP'],['IP BFP','IP BFP'],
      ['HP-BYPASS-VLV','HP Bypass'],['LP Bypass','LP Bypass'],['Condenser','Condenser']]){
      await page.goto(`${base}/drawing?equipment=${encodeURIComponent(name)}&view=plant&event=TRIP`);
      await page.locator('.drawing-hotspot.is-active').waitFor();
      assert.equal(await page.locator('.drawing-hotspot.is-active').count(),1);
      assert.match(await page.locator('.drawing-callout').innerText(),new RegExp(label,'i'));
      assert.match(await page.locator('.drawing-callout').innerText(),/EVENT/);
      assert.equal(await page.locator('.drawing-canvas img').evaluate(image=>image.naturalWidth),2044);
    }
    assert.equal(await page.locator('.drawing-hotspot').count(),21);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:'/workspace/scratch/dcbbc7676ae2/plant-preview.png'});
  }finally{await browser.close();}
});

test('existing MATLAB ECMS bus and breaker navigation and Plant mobile focus',async()=>{
  const browser=await playwright.chromium.launch({headless:true,executablePath,args:['--no-sandbox']});
  try{
    const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    await page.goto(`${base}/drawing`);
    await page.locator('.dm-inline-svg .triplens-hotspot-layer').waitFor();
    await page.locator('.triplens-hotspot-layer [data-view="BUS-A"]').click();
    await page.getByRole('heading',{name:'6.9 kV SWGR Detail'}).waitFor();
    await page.goto(`${base}/drawing?equipment=VCB-A01`);
    await page.locator('.triplens-highlight-layer').waitFor();
    await page.goto(`${base}/drawing?equipment=FWP-LP&view=plant`);
    await page.locator('.drawing-hotspot.is-active').waitFor();
    const centered=await page.evaluate(()=>{
      const spot=document.querySelector('.drawing-hotspot.is-active').getBoundingClientRect();
      const frame=document.querySelector('.drawing-scroll').getBoundingClientRect();
      return spot.left>=frame.left&&spot.right<=frame.right&&spot.top>=0&&spot.bottom<=window.innerHeight;
    });
    assert.equal(centered,true,'direct jump must bring LP BFP into mobile viewport');
    await page.screenshot({path:'/workspace/scratch/dcbbc7676ae2/plant-mobile-preview.png'});
  }finally{await browser.close();}
});

test('mobile Logic Master opens a distinct Plant Process View instead of a second logic screen',async()=>{
  const browser=await playwright.chromium.launch({headless:true,executablePath,args:['--no-sandbox']});
  try{
    const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    await page.goto(base);
    await page.locator('.side-links button').click();
    const dialog=page.getByRole('dialog',{name:'Logic / TAG Master · 로직 도면'});
    await dialog.waitFor();
    assert.equal(await page.frameLocator('dialog iframe').locator('#equipment-view').innerText(),'설비별 로직');
    await dialog.getByRole('link',{name:'Plant Process View 열기'}).click();
    await page.getByRole('heading',{name:'Plant Process View'}).waitFor();
    assert.match(page.url(),/\/drawing\?view=plant$/);
    assert.equal(await page.locator('.drawing-hotspot').count(),21);
  }finally{await browser.close();}
});

test('registered valves missing from v36 overview open their exact SVG and EVENT focus',async()=>{
  const browser=await playwright.chromium.launch({headless:true,executablePath,args:['--no-sandbox']});
  try{
    const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    for(const [equipment,asset] of [['HP FWCV','hp-fwcv.svg'],['COND EXTRACTION VALVE','cond-extraction-vlv.svg']]){
      await page.goto(`${base}/drawing?equipment=${encodeURIComponent(equipment)}&view=plant&event=TRIP`);
      await page.getByRole('heading',{name:'Equipment Detail'}).waitFor();
      assert.match(await page.locator('.valve-event-focus').innerText(),new RegExp(equipment));
      assert.match(await page.locator('object[type="image/svg+xml"]').getAttribute('data'),new RegExp(asset+'$'));
      assert.equal((await page.request.get(`${base}/topology/valves/${asset}`)).status(),200);
    }
    await page.goto(`${base}/drawing?equipment=HP%20TURB%20ADM%20VALVE&view=plant&event=TRIP`);
    await page.locator('.drawing-hotspot.is-active').waitFor();
    assert.equal(await page.locator('.drawing-hotspot.is-active').getAttribute('title'),'HP Turbine Admission Valve');
  }finally{await browser.close();}
});
