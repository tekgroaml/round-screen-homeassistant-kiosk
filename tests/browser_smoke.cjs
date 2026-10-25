// Optional UI acceptance: a local demo server + Playwright/Chromium are required.
// ORBIT_TEST_URL defaults to a local fixture; never point this at a live HA backend.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {})
  });
  try {
    for (const size of [360, 480, 720, 800]) {
      const context = await browser.newContext({ viewport: { width: size, height: size }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const base = process.env.ORBIT_TEST_URL || 'http://127.0.0.1:18765';
      const api = await context.request.get(base + '/api/state');
      assert.equal((await api.json()).mode, 'demo', 'This test must never write to a live backend');
      await context.request.post(base + '/api/setpoint', { data: { target: 22 } });
      await page.goto(base);
      await page.waitForFunction(() => document.querySelector('#status').textContent.includes('DEMO'));
      const writes = [];
      page.on('request', request => { if (request.method() === 'POST') writes.push(request.postDataJSON()); });
      await page.locator('#increase').tap();
      await page.waitForFunction(() => document.querySelector('#status').textContent === 'DEMO TARGET SAVED');
      assert.equal(await page.locator('#setpoint').textContent(), '22.5');
      assert.deepEqual(writes, [{ target: 22.5 }]);
      // Touching the central label must not accidentally adjust a thermostat.
      await page.touchscreen.tap(size / 2, size / 2);
      await page.waitForTimeout(350);
      assert.equal(writes.length, 1);
      const box = await page.locator('.dial').boundingBox();
      const point = (dx, dy, id) => ({ x: box.x + box.width * dx, y: box.y + box.height * dy, id });
      const cdp = await context.newCDPSession(page);
      const top = point(.5, .117, 1), left = point(.117, .5, 2), right = point(.883, .5, 1);
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [top] });
      const primaryValue = await page.locator('#setpoint').textContent();
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [top, left] });
      assert.equal(await page.locator('#setpoint').textContent(), primaryValue, 'Second finger must not take over');
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [right, left] });
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
      await page.waitForFunction(() => document.querySelector('#status').textContent === 'DEMO TARGET SAVED');
      assert.equal(writes.length, 2, 'One ring gesture produces one write');
      const saved = await page.locator('#setpoint').textContent();
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [top] });
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchCancel', touchPoints: [] });
      await page.waitForTimeout(350);
      assert.equal(writes.length, 2, 'Cancelled gestures do not write');
      assert.equal(await page.locator('#setpoint').textContent(), saved);
      const problems = await page.evaluate(() => {
        const b = document.querySelector('.dial').getBoundingClientRect();
        return [...document.querySelectorAll('.adjustments button, header, .weather, #control, .humidity, #clock, #status')]
          .filter(node => { const r = node.getBoundingClientRect(); return r.left < b.left || r.right > b.right || r.top < b.top || r.bottom > b.bottom; })
          .map(node => node.id || node.className || node.tagName);
      });
      assert.deepEqual(problems, []);
      assert.deepEqual(errors, []);
      const output = path.join(__dirname, '../docs/previews');
      fs.mkdirSync(output, { recursive: true });
      await context.request.post(base + '/api/setpoint', { data: { target: 22 } });
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#status').textContent.includes('DEMO'));
      await page.screenshot({ path: path.join(output, 'round-' + size + '.png') });
      console.log('PASS: ' + size + 'x' + size + ' touch buttons, ring, second finger, cancel and bounds');
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
