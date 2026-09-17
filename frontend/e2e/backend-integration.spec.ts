import { expect, test, type Page } from '@playwright/test';

// Runs only against a live Backend: build with VITE_API_MODE=http and set E2E_BACKEND_URL + E2E_DEMO_SESSION.
const backend = process.env.E2E_BACKEND_URL ?? '';
const session = process.env.E2E_DEMO_SESSION ?? '';
const shots = process.env.E2E_SCREENSHOT_DIR;

test.skip(!backend || !session, 'set E2E_BACKEND_URL and E2E_DEMO_SESSION to run the Backend browser integration');
test.describe.configure({ mode: 'serial' });

async function shot(page: Page, name: string) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
}

async function openSyntheticPlot(page: Page) {
  await expect(page.getByTestId('plot-name')).toBeVisible();
  const select = page.getByTestId('plot-select');
  if ((await select.count()) > 0) {
    await select.selectOption('SYNTHETIC-PLOT-001');
    await expect(page.getByTestId('plot-select')).toHaveValue('SYNTHETIC-PLOT-001');
  }
}

async function browserFetch(page: Page, path: string, init: { method?: string; headers?: Record<string, string>; body?: string } = {}) {
  return page.evaluate(
    async ({ url, init: requestInit }) => {
      try {
        const response = await fetch(url, { ...requestInit, credentials: 'omit' });
        const text = await response.text();
        return { ok: true, status: response.status, body: text };
      } catch (error) {
        return { ok: false, status: 0, body: String(error) };
      }
    },
    { url: `${backend}${path}`, init },
  );
}

test('CORS: allowed browser origin passes preflight for custom headers and receives envelopes', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('adapter-mode')).toHaveText('BACKEND HTTP');

  // A readable cross-origin response is itself proof of an ACAO match (the header is not exposed to JS).
  const health = await browserFetch(page, '/health');
  expect(health).toMatchObject({ ok: true, status: 200 });
  expect(JSON.parse(health.body).mode).toBe('CONTRACT_FIXTURE');

  const authed = await browserFetch(page, '/plots', { headers: { 'X-Demo-Session': session } });
  expect(authed.status).toBe(200);

  const noSession = await browserFetch(page, '/plots');
  expect(noSession.status).toBe(401);
  expect(JSON.parse(noSession.body).error.code).toBe('UNAUTHORIZED');

  const notFound = await browserFetch(page, '/plots/UNKNOWN-PLOT', { headers: { 'X-Demo-Session': session, 'X-Demo-Actor': 'issuer' } });
  expect(notFound.status).toBe(404);
  expect(JSON.parse(notFound.body)).toMatchObject({ error: { code: 'NOT_FOUND' } });

  const invalid = await browserFetch(page, '/plots/SYNTHETIC-PLOT-001/verify', {
    method: 'POST',
    headers: { 'X-Demo-Session': session, 'X-Demo-Actor': 'issuer', 'Idempotency-Key': 'browser-invalid-1', 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario_id: 'simulate_fire' }),
  });
  expect(invalid.status).toBe(422);
  expect(JSON.parse(invalid.body).error.code).toBe('INVALID_EVIDENCE');

  const forbidden = await browserFetch(page, '/plots/SYNTHETIC-PLOT-001/issue', {
    method: 'POST',
    headers: { 'X-Demo-Session': session, 'X-Demo-Actor': 'buyer', 'Idempotency-Key': 'browser-forbidden-1', 'Content-Type': 'application/json' },
    body: JSON.stringify({ demo_authorization_id: 'SYNTHETIC-AUTH-001' }),
  });
  expect(forbidden.status).toBe(403);
});

test('CORS: an origin outside BACKEND_CORS_ORIGINS is blocked by the browser', async ({ page }) => {
  await page.goto('http://localhost:4173/');
  const blocked = await browserFetch(page, '/health');
  expect(blocked.ok).toBe(false);
  await expect(page.getByTestId('error-notice').first()).toContainText('Backend недоступен');
});

test('real Frontend against Backend: baseline → issue → buy → post_fire → FROZEN → transfer rejected', async ({ page }) => {
  const apiErrors: string[] = [];
  page.on('pageerror', (err) => apiErrors.push(err.message));
  // Expected rejections (403 wrong actor, 409 frozen transfer) are logged by the browser as failed resources.
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !/status of (403|409) /.test(msg.text())) apiErrors.push(`console: ${msg.text()}`);
  });
  const backendRequests: string[] = [];
  page.on('request', (req) => {
    const url = new URL(req.url());
    if (url.port === new URL(backend).port) backendRequests.push(`${req.method()} ${url.pathname}`);
    if (!['127.0.0.1', 'localhost'].includes(url.hostname) && !['data:', 'blob:'].includes(url.protocol)) apiErrors.push(`external ${req.url()}`);
  });

  await page.goto('/');
  await expect(page.getByTestId('health-mode')).toHaveText('CONTRACT_FIXTURE');
  await expect(page.getByTestId('mock-ledger-banner')).toBeVisible();
  await expect(page.getByTestId('fixture-banner')).toHaveCount(0);
  await openSyntheticPlot(page);

  // 403 surfaced in UI for a non-issuer verification.
  await page.getByTestId('actor-select').selectOption('buyer');
  await page.getByTestId('verify-baseline').click();
  await expect(page.getByTestId('job-status').getByTestId('error-notice')).toContainText('HTTP 403');
  await page.getByTestId('actor-select').selectOption('issuer');

  await page.getByTestId('verify-baseline').dblclick();
  await expect(page.getByTestId('job-state')).toHaveText('SUCCEEDED', { timeout: 30_000 });
  await expect(page.getByTestId('value-outcome')).toHaveText('NO_CHANGE');
  await expect(page.getByTestId('value-quality')).toHaveText('SUFFICIENT');
  await expect(page.getByTestId('value-decision')).toHaveText('NO_RESTRICTION');
  await expect(page.getByTestId('dataset-kind')).toHaveText('SYNTHETIC');
  await expect(page.getByTestId('computation-mode')).toHaveText('CACHED_REPLAY');
  const images = page.getByTestId('before-after').locator('img');
  await expect(images).toHaveCount(2);
  await expect.poll(async () => images.first().evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await expect(images.first()).toHaveAttribute('src', /^blob:/);
  expect(backendRequests.filter((r) => r === 'POST /api/v1/plots/SYNTHETIC-PLOT-001/verify')).toHaveLength(2);
  await shot(page, 'backend-01-no-change');

  await page.getByTestId('tab-credits').click();
  await page.getByTestId('issue-submit').dblclick();
  await expect(page.getByTestId('op-state-issue')).toHaveText('CONFIRMED', { timeout: 30_000 });
  await expect(page.getByTestId('op-status-issue')).toContainText('readback ok');
  await expect(page.getByTestId('value-credit')).toHaveText('ACTIVE');
  await expect(page.getByTestId('ledger-note')).toHaveAttribute('data-ledger', 'mock');
  expect(backendRequests.filter((r) => r === 'POST /api/v1/plots/SYNTHETIC-PLOT-001/issue')).toHaveLength(1);

  await page.getByTestId('actor-select').selectOption('buyer');
  await page.getByTestId('buy-submit').click();
  await expect(page.getByTestId('op-state-buy')).toHaveText('CONFIRMED', { timeout: 30_000 });
  await expect(page.getByTestId('actor-balance')).toHaveText('10');
  await expect(page.getByTestId('seller-balance')).toHaveText('90');

  await page.getByTestId('actor-select').selectOption('issuer');
  await page.getByTestId('verify-post_fire').click();
  await expect(page.getByTestId('job-state')).toHaveText('SUCCEEDED', { timeout: 30_000 });
  await expect(page.getByTestId('value-decision')).toHaveText('FREEZE_REQUESTED');
  await expect(page.getByTestId('value-reason')).toHaveText('FIRE_REVERSAL');
  await shot(page, 'backend-02-disturbance-freeze-requested');
  await expect(page.getByTestId('value-credit')).toHaveText(/ACTIVE|FROZEN/);
  await expect(page.getByTestId('value-credit')).toHaveText('FROZEN', { timeout: 30_000 });
  await expect(page.locator('[data-testid="journal-event"][data-kind="TX_CONFIRMED"]').first()).toBeVisible();
  await expect(page.locator('.leaflet-overlay-pane path').nth(1)).toBeAttached();
  await expect(page.locator('.leaflet-overlay-pane img')).toHaveCount(1);

  await page.getByTestId('actor-select').selectOption('buyer');
  await page.getByTestId('tab-credits').click();
  await expect(page.getByTestId('transfer-submit')).toBeDisabled();
  await page.getByTestId('transfer-attempt-frozen').click();
  await expect(page.getByTestId('error-notice').filter({ hasText: 'BATCH_NOT_ACTIVE' })).toBeVisible();
  await expect(page.getByTestId('client-log-entry').first()).toContainText('409');
  await expect(page.getByTestId('actor-balance')).toHaveText('10');
  await shot(page, 'backend-03-frozen-transfer-rejected');

  await page.getByTestId('tab-proof').click();
  await expect(page.getByTestId('anchors')).toContainText('Frozen');
  await expect(page.getByTestId('ledger-note')).toContainText('mock ledger');
  await page.getByRole('button', { name: 'Загрузить canonical evidence' }).click();
  await expect(page.getByTestId('canonical-loaded')).toContainText('DISTURBANCE_DETECTED');
  await page.getByTestId('history').getByRole('button').last().click();
  await expect(page.getByTestId('anchors')).not.toContainText('Frozen');

  await page.getByTestId('actor-select').selectOption('issuer');
  await page.getByTestId('verify-insufficient').click();
  await expect(page.getByTestId('job-state')).toHaveText('SUCCEEDED', { timeout: 30_000 });
  await expect(page.getByTestId('value-outcome')).toHaveText('INSUFFICIENT_DATA');
  await expect(page.getByTestId('value-decision')).toHaveText('REVIEW_REQUIRED');
  await expect(page.getByTestId('value-credit')).toHaveText('FROZEN');
  await shot(page, 'backend-04-insufficient-review-still-frozen');

  // Refresh keeps confirmed state from Backend (no local invention).
  await page.reload();
  await openSyntheticPlot(page);
  await expect(page.getByTestId('value-credit')).toHaveText('FROZEN');
  await expect(page.getByTestId('value-decision')).toHaveText('REVIEW_REQUIRED');

  expect(backendRequests.some((r) => r.includes('/freeze'))).toBe(false);
  expect(apiErrors).toEqual([]);
});

test('mobile viewport keeps status, map and critical state readable', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, hasTouch: true });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(err.message));
  await page.goto('/');
  await openSyntheticPlot(page);
  await expect(page.getByTestId('value-credit')).toHaveText('FROZEN');
  await expect(page.getByTestId('evidence-map')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await shot(page, 'backend-05-mobile');
  expect(errors).toEqual([]);
  await context.close();
});

test('unknown enum values injected into live Backend responses never blank the dashboard', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  // Rewrite real Backend payloads on the wire: the SPA must degrade, not crash.
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!/\/credits$|\/history$|\/verifications\/[0-9a-f-]+$/.test(path)) return route.fallback();
    const response = await route.fetch();
    if (!String(response.headers()['content-type'] ?? '').includes('json')) return route.fulfill({ response });
    const data = await response.json();
    if (path.endsWith('/credits')) {
      for (const item of data.items ?? []) item.credit_status = 'SUSPENDED_PENDING_REVIEW';
    } else if (path.endsWith('/history')) {
      for (const item of data.items ?? []) {
        item.outcome = 'WILDFIRE_V2';
        item.decision = 'ESCALATE_TO_AUDITOR';
      }
    } else {
      data.evidence.outcome = 'WILDFIRE_V2';
      data.decision = 'ESCALATE_TO_AUDITOR';
      data.reason = 'NEW_REASON_CODE';
    }
    return route.fulfill({ response, json: data });
  });

  await page.goto('/');
  await openSyntheticPlot(page);

  await expect(page.getByTestId('value-outcome')).toContainText('UNKNOWN: WILDFIRE_V2');
  await expect(page.getByTestId('value-decision')).toContainText('UNKNOWN: ESCALATE_TO_AUDITOR');
  await expect(page.getByTestId('value-decision')).toHaveAttribute('data-tone', 'neutral');
  await expect(page.getByTestId('value-credit')).toContainText('UNKNOWN: SUSPENDED_PENDING_REVIEW');
  await expect(page.getByTestId('unknown-value-note').first()).toContainText('отсутствует в текущем API-контракте');
  await expect(page.getByTestId('history')).toContainText('UNKNOWN: WILDFIRE_V2');

  // Map, balances, proof and journal survive the drift.
  await expect(page.getByTestId('evidence-map')).toBeVisible();
  await expect(page.getByTestId('journal')).toBeVisible();
  await expect(page.locator('.leaflet-overlay-pane img')).toHaveCount(1);
  await page.getByTestId('tab-credits').click();
  await expect(page.getByTestId('actor-balance')).toBeVisible();
  await expect(page.getByTestId('transfer-submit')).toBeDisabled();
  await page.getByTestId('tab-proof').click();
  await expect(page.getByTestId('proof-panel')).toBeVisible();

  await expect(page.getByTestId('root-error-boundary')).toHaveCount(0);
  expect(await page.locator('#root').innerHTML()).not.toBe('');
  expect(pageErrors).toEqual([]);
  await shot(page, 'backend-06-unknown-enum-drift');
});
