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
  await expect(page.getByTestId('plot-name')).toBeVisible();

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
  await shot(page, 'backend-01-baseline');

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
  await shot(page, 'backend-02-frozen-transfer-rejected');

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
  await shot(page, 'backend-03-insufficient-still-frozen');

  // Refresh keeps confirmed state from Backend (no local invention).
  await page.reload();
  await expect(page.getByTestId('value-credit')).toHaveText('FROZEN');
  await expect(page.getByTestId('value-decision')).toHaveText('REVIEW_REQUIRED');

  expect(backendRequests.some((r) => r.includes('/freeze'))).toBe(false);
  expect(apiErrors).toEqual([]);
});
