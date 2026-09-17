import { chromium } from '@playwright/test';

const [url = 'http://127.0.0.1:4173/', out = 'screenshot.png', waitFor = 'plot-name'] = process.argv.slice(2);
const browser = await chromium.launch({ channel: process.env.E2E_BROWSER_CHANNEL ?? 'msedge' });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('console', (msg) => {
  if (msg.type() === 'error') console.log(`[console.error] ${msg.text()}`);
});
page.on('pageerror', (err) => console.log(`[pageerror] ${err.message}`));
await page.goto(url);
await page.getByTestId(waitFor).first().waitFor({ timeout: 20000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: out, fullPage: true });
await browser.close();
console.log(`saved ${out}`);
