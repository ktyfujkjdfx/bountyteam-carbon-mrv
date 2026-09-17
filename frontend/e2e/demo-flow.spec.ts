import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';

const shots = process.env.E2E_SCREENSHOT_DIR;

async function shot(page: Page, name: string) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
}

test('fixture demo flow: baseline → issue → buy → post_fire → FREEZE_REQUESTED → FROZEN → transfer rejected', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('pageerror', (err) => consoleErrors.push(err.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  const external: string[] = [];
  page.on('request', (req) => {
    const url = new URL(req.url());
    if (!['127.0.0.1', 'localhost'].includes(url.hostname) && !['data:', 'blob:'].includes(url.protocol)) external.push(req.url());
  });

  await page.goto('/?api=fixture');
  await expect(page.getByTestId('fixture-banner')).toBeVisible();
  await expect(page.getByTestId('adapter-mode')).toHaveText(/FIXTURE/);
  await expect(page.getByTestId('health-mode')).toHaveText('CONTRACT_FIXTURE');
  await expect(page.getByTestId('dataset-kind')).toHaveText('SYNTHETIC');
  await expect(page.getByTestId('computation-mode')).toHaveText('CACHED_REPLAY');

  // 1–2. Plot and baseline evidence.
  await expect(page.getByTestId('value-outcome')).toHaveText('NO_CHANGE');
  await expect(page.getByTestId('value-quality')).toHaveText('SUFFICIENT');
  await expect(page.getByTestId('value-decision')).toHaveText('NO_RESTRICTION');
  await expect(page.getByTestId('value-credit-none')).toBeVisible();
  await expect(page.getByTestId('before-after').locator('img')).toHaveCount(2);
  await expect(page.locator('.leaflet-overlay-pane path').first()).toBeAttached();
  await shot(page, '01-baseline');

  // Issue as issuer.
  await page.getByTestId('tab-credits').click();
  const issue = page.getByTestId('issue-submit');
  await expect(issue).toBeEnabled();
  await issue.dblclick();
  await expect(page.getByTestId('op-state-issue')).toHaveText(/QUEUED|SUBMITTED/);
  await expect(page.getByTestId('op-state-issue')).toHaveText('CONFIRMED', { timeout: 20_000 });
  await expect(page.getByTestId('batch-1')).toBeVisible();
  await expect(page.getByTestId('value-credit')).toHaveText('ACTIVE');
  await expect(page.getByTestId('seller-balance')).toHaveText('100');

  // Buy as buyer.
  await page.getByTestId('actor-select').selectOption('buyer');
  await expect(page.getByTestId('buy-submit')).toBeEnabled();
  await page.getByTestId('buy-submit').click();
  await expect(page.getByTestId('buy-submit')).toBeDisabled();
  await expect(page.getByTestId('op-state-buy')).toHaveText('CONFIRMED', { timeout: 20_000 });
  await expect(page.getByTestId('actor-balance')).toHaveText('10');
  await expect(page.getByTestId('seller-balance')).toHaveText('90');
  await shot(page, '02-active-after-buy');

  // 3–5. Post-fire verification as issuer.
  await page.getByTestId('actor-select').selectOption('issuer');
  await page.getByTestId('verify-post_fire').click();
  await expect(page.getByTestId('job-state')).toHaveText(/QUEUED|RUNNING/);
  await expect(page.getByTestId('job-state')).toHaveText('SUCCEEDED', { timeout: 20_000 });
  await expect(page.getByTestId('value-outcome')).toHaveText('DISTURBANCE_DETECTED');
  await expect(page.getByTestId('value-decision')).toHaveText('FREEZE_REQUESTED');
  await expect(page.getByTestId('value-reason')).toHaveText('FIRE_REVERSAL');
  await expect(page.getByTestId('value-credit')).toHaveText('ACTIVE');
  await expect(page.getByTestId('freeze-requested-banner')).toBeVisible();
  await shot(page, '03-freeze-requested-not-frozen');

  // 6. Confirmed FROZEN only after TX_CONFIRMED.
  await expect(page.getByTestId('value-credit')).toHaveText('FROZEN', { timeout: 30_000 });
  await expect(page.locator('[data-testid="journal-event"][data-kind="TX_CONFIRMED"]').first()).toBeVisible();
  await expect(page.getByTestId('freeze-requested-banner')).toHaveCount(0);

  // 7. Transfer disabled, attempt rejected by Backend, proof anchor.
  await page.getByTestId('tab-credits').click();
  await page.getByTestId('actor-select').selectOption('buyer');
  await expect(page.getByTestId('frozen-explainer')).toBeVisible();
  await expect(page.getByTestId('transfer-submit')).toBeDisabled();
  await expect(page.getByTestId('transfer-disabled-reason')).toContainText('смарт-контракт');
  await expect(page.getByTestId('buy-submit')).toBeDisabled();
  await page.getByTestId('transfer-attempt-frozen').click();
  await expect(page.getByTestId('error-notice').filter({ hasText: 'BATCH_NOT_ACTIVE' })).toBeVisible();
  await expect(page.getByTestId('client-log-entry').first()).toContainText('409');
  await expect(page.getByTestId('actor-balance')).toHaveText('10');
  await shot(page, '04-frozen-transfer-rejected');

  await page.getByTestId('tab-proof').click();
  await expect(page.getByTestId('anchors')).toContainText('Frozen');
  await shot(page, '05-proof-frozen-anchor');

  // Older baseline evidence shows its own Issued anchor, never the Frozen one.
  await page.getByTestId('history').getByRole('button').last().click();
  await expect(page.getByTestId('anchors')).toContainText('Issued');
  await expect(page.getByTestId('anchors')).not.toContainText('Frozen');

  // Insufficient evidence: no freeze, no anchors, status stays FROZEN (no automatic unfreeze).
  await page.getByTestId('actor-select').selectOption('issuer');
  await page.getByTestId('verify-insufficient').click();
  await expect(page.getByTestId('job-state')).toHaveText('SUCCEEDED', { timeout: 20_000 });
  await expect(page.getByTestId('value-outcome')).toHaveText('INSUFFICIENT_DATA');
  await expect(page.getByTestId('value-decision')).toHaveText('REVIEW_REQUIRED');
  await expect(page.getByTestId('value-credit')).toHaveText('FROZEN');
  await expect(page.getByTestId('no-anchors')).toBeVisible();

  expect(external, 'no external network requests').toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes('409'))).toEqual([]);
});

test('HTTP mode without Backend shows explicit error and manual offline fallback, not silent fixtures', async ({ page }) => {
  await page.goto('/?api=http');
  await expect(page.getByTestId('adapter-mode')).toHaveText('BACKEND HTTP');
  await expect(page.getByTestId('error-notice').first()).toBeVisible();
  await expect(page.getByTestId('fixture-banner')).toHaveCount(0);
  const fallback = page.getByTestId('offline-fallback-link');
  await expect(fallback).toBeVisible();
  await fallback.click();
  await expect(page.getByTestId('fixture-banner')).toBeVisible();
  await expect(page.getByTestId('value-decision')).toHaveText('NO_RESTRICTION');
});

test('keyboard: methodology dialog and on-map before/after divider are operable without a mouse', async ({ page }) => {
  await page.goto('/?api=fixture');
  await expect(page.getByTestId('value-decision')).toHaveText('NO_RESTRICTION');

  const methodology = page.getByTestId('open-methodology');
  await methodology.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('methodology')).toBeVisible();
  await expect(page.getByTestId('methodology')).toContainText('Вне контракта v1');
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('methodology')).toBeHidden();

  await page.getByTestId('map-compare').focus();
  await page.keyboard.press('Enter');
  const handle = page.getByTestId('map-compare-handle');
  await page.keyboard.press('Tab');
  await expect(handle).toBeFocused();
  const focusRing = await handle.evaluate((el) => getComputedStyle(el).boxShadow);
  expect(focusRing).not.toBe('none');
  await expect(handle).toHaveAttribute('aria-valuenow', '50');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Shift+ArrowRight');
  await expect(handle).toHaveAttribute('aria-valuenow', '62');
  await page.keyboard.press('Home');
  await expect(handle).toHaveAttribute('aria-valuenow', '0');
  await expect(page.locator('.leaflet-overlay-pane img')).toHaveCount(2);
});

test('unknown enum values from Backend degrade to neutral UNKNOWN badges without a white screen', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  const cases = JSON.parse(readFileSync(new URL('../../fixtures/http_examples.json', import.meta.url), 'utf8')) as {
    cases: Array<{ name: string; body: unknown }>;
  };
  const body = (name: string) => JSON.parse(JSON.stringify(cases.cases.find((c) => c.name === name)?.body));

  const verification = body('verification_fire');
  verification.evidence.outcome = 'WILDFIRE_V2';
  verification.evidence_quality = 'PARTIAL';
  verification.decision = 'ESCALATE_TO_AUDITOR';
  verification.reason = 'NEW_REASON_CODE';
  const verificationId = verification.verification_id;

  const plot = body('plot');
  plot.latest_verification_id = verificationId;
  const history = body('history');
  history.items[0].verification_id = verificationId;
  history.items[0].outcome = 'WILDFIRE_V2';
  history.items[0].decision = 'ESCALATE_TO_AUDITOR';
  const credits = {
    items: [
      {
        batch_id: '1',
        plot_id: 'SYNTHETIC-PLOT-001',
        seller: '0x00000000000000000000000000000000000000a1',
        actor: 'issuer',
        total_supply: '100',
        seller_balance: '90',
        actor_balance: '90',
        unit_price_wei: '1000000000000000',
        credit_status: 'SUSPENDED_PENDING_REVIEW',
        evidence_hash: verification.evidence_hash,
        decision_hash: verification.decision_hash,
        issued_at: '2026-09-17T10:00:00Z',
        frozen_at: null,
        last_observed_at: '2024-08-01T05:00:00Z',
        chain_state_checked_at: '2026-09-17T10:05:00Z',
        can_buy: false,
        can_transfer_backend: false,
      },
    ],
  };
  const health = { ...body('health'), mode: 'STAGING_V2' };
  const proof = { ...body('proof'), canonical_url: `/api/v1/verifications/${verificationId}/canonical`, anchors: [] };

  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '');
    const json = (data: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
    if (path === '/health') return json(health);
    if (path === '/plots') return json(body('plots'));
    if (path === '/plots/SYNTHETIC-PLOT-001') return json(plot);
    if (path.endsWith('/history')) return json(history);
    if (path.endsWith('/credits')) return json(credits);
    if (path === '/events') return json(body('events'));
    if (path.endsWith('/proof')) return json(proof);
    if (path.startsWith('/verifications/')) return json(verification);
    if (path.startsWith('/artifacts/')) {
      const file = path.includes('firms') ? 'verification_fire/firms_points.geojson' : path.includes('affected') ? 'verification_fire/affected_area.geojson' : null;
      if (file) {
        return route.fulfill({ status: 200, contentType: 'application/geo+json', body: readFileSync(new URL(`../../fixtures/assets/${file}`, import.meta.url), 'utf8') });
      }
      const png = path.includes('before') ? 'before.png' : 'after.png';
      return route.fulfill({ status: 200, contentType: 'image/png', body: readFileSync(new URL(`../../fixtures/assets/verification_fire/${png}`, import.meta.url)) });
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: { code: 'NOT_FOUND', message: 'not mocked', details: {} }, request_id: '30000000-0000-4000-8000-000000000001' }) });
  });

  await page.goto('/?api=http');

  const unknown = (testId: string, received: string) => expect(page.getByTestId(testId)).toContainText(`UNKNOWN: ${received}`);
  await unknown('value-outcome', 'WILDFIRE_V2');
  await unknown('value-quality', 'PARTIAL');
  await unknown('value-decision', 'ESCALATE_TO_AUDITOR');
  await unknown('value-credit', 'SUSPENDED_PENDING_REVIEW');
  await unknown('health-mode', 'STAGING_V2');
  await expect(page.getByTestId('value-credit')).toHaveAttribute('data-tone', 'neutral');
  await expect(page.getByTestId('layer-decision')).toContainText('Неизвестное значение: NEW_REASON_CODE');
  await expect(page.getByTestId('unknown-value-note').first()).toContainText('отсутствует в текущем API-контракте');

  // The rest of the dashboard keeps working.
  await expect(page.getByTestId('evidence-map')).toBeVisible();
  await expect(page.locator('.leaflet-overlay-pane img')).toHaveCount(1);
  await expect(page.getByTestId('journal')).toBeVisible();
  await expect(page.getByTestId('history')).toContainText('UNKNOWN: ESCALATE_TO_AUDITOR');
  await expect(page.getByTestId('before-after').locator('img')).toHaveCount(2);
  await page.getByTestId('tab-credits').click();
  await expect(page.getByTestId('actor-balance')).toHaveText('90');
  await expect(page.getByTestId('transfer-submit')).toBeDisabled();
  await page.getByTestId('tab-proof').click();
  await expect(page.getByTestId('proof-panel')).toBeVisible();

  await expect(page.getByTestId('root-error-boundary')).toHaveCount(0);
  expect(await page.locator('#root').innerHTML()).not.toBe('');
  const bodyText = (await page.locator('#root').innerText()).toLowerCase();
  expect(bodyText).not.toContain('cannot read properties');
  expect(pageErrors).toEqual([]);
  await shot(page, '06-unknown-enum-contract-drift');
});
