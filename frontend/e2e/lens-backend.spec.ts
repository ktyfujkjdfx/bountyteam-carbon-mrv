import { expect, test, type Page } from '@playwright/test';

// Opt-in browser check against a running Carbon Lens service. It is skipped unless both variables are
// set, so the normal suite never depends on a backend being up:
//   $env:E2E_LENS_BACKEND_URL='http://127.0.0.1:8031/api/v2'
//   $env:E2E_LENS_SESSION='<session token the service accepts>'
//   npx playwright test e2e/lens-backend.spec.ts
const BASE = process.env.E2E_LENS_BACKEND_URL;
const SESSION = process.env.E2E_LENS_SESSION;

test.skip(!BASE || !SESSION, 'set E2E_LENS_BACKEND_URL and E2E_LENS_SESSION to run the live check');

// The service reviewed in PR #15 does not list Authorization in Access-Control-Allow-Headers, so the
// live check runs with the session-header scheme until Backend allows the bearer header.
const AUTH = process.env.E2E_LENS_AUTH ?? 'demo';

async function signIn(page: Page, email: string) {
  await page.goto(`/lens?demo=1&auth=${AUTH}`);
  await page.getByTestId('lens-login-username').fill(email);
  await page.getByTestId('lens-login-password').fill(SESSION as string);
  await page.getByTestId('lens-login-submit').click();
  await expect(page.getByTestId('lens-role')).toBeVisible({ timeout: 20_000 });
}

test('live service: the three roles run one analysis end to end', async ({ page }) => {
  const external: string[] = [];
  const pageErrors: string[] = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));
  page.on('request', (req) => {
    const url = new URL(req.url());
    if (!['127.0.0.1', 'localhost'].includes(url.hostname) && !['data:', 'blob:'].includes(url.protocol)) external.push(req.url());
  });

  await signIn(page, 'owner@demo.local');
  await expect(page.getByTestId('lens-mode')).toContainText('СЕРВИС');
  await expect(page.getByTestId('lens-catalog-error')).toHaveCount(0);

  // The catalog and the area both come from the service, including for the supplied contour.
  await page.getByTestId('lens-area-select').selectOption('RU_TVER_01');
  await expect(page.getByTestId('lens-area')).toContainText('га');
  // The service of PR #15 has no /areas/measure yet, so the label must say the number is preliminary
  // rather than claim it came from the service.
  await expect(page.getByTestId('lens-area-source')).toContainText(/Площадь сервиса|Предварительная оценка/);
  await page.getByTestId('lens-year-start').selectOption('2019');
  await page.getByTestId('lens-year-end').selectOption('2024');
  await page.getByTestId('lens-claim-input').fill('1000');
  await page.getByTestId('lens-submit').click();
  await expect(page.getByTestId('lens-my-requests')).toContainText('RU_TVER_01');

  await page.getByTestId('lens-logout').click();
  await signIn(page, 'verifier@demo.local');
  await page.getByTestId('lens-queue-list').locator('button').first().click();
  await page.getByTestId('lens-run-analysis').click();
  await expect(page.getByTestId('lens-q')).toBeVisible({ timeout: 180_000 });

  // Whatever the service computed is what the screen shows; the test asserts the shape, not the number.
  const verdict = await page.getByTestId('lens-verdict').textContent();
  expect(verdict).toMatch(/подтверждён|не подтверждён|Недостаточно данных/);
  await expect(page.getByTestId('lens-status-calculation')).toBeVisible();
  await expect(page.getByTestId('lens-claim-status')).toBeVisible();

  await page.getByTestId('lens-tab-quality').click();
  await expect(page.getByTestId('lens-coverage-biomass_fraction')).toContainText('%');
  await expect(page.getByTestId('lens-areas')).toContainText('га');

  await page.getByTestId('lens-show-cells').click();
  await expect(page.getByTestId('lens-cells-integrity')).toHaveCount(0);

  await page.getByTestId('lens-passport-verify').click();
  await expect(page.getByTestId('lens-passport-result')).toContainText('совпадает');
  await page.getByTestId('lens-finalize').click();
  await expect(page.getByTestId('lens-passport-status')).toContainText('ФИНАЛИЗИРОВАН');

  await page.getByTestId('lens-logout').click();
  await signIn(page, 'investor@demo.local');
  await page.getByTestId('lens-portfolio-list').locator('button').first().click();
  await expect(page.getByTestId('lens-q')).toBeVisible();

  expect(external, 'no external hosts').toEqual([]);
  expect(pageErrors).toEqual([]);
});

test('live service: a wrong token is rejected and nothing is invented', async ({ page }) => {
  await page.goto(`/lens?demo=1&auth=${AUTH}`);
  await page.getByTestId('lens-login-username').fill('verifier@demo.local');
  await page.getByTestId('lens-login-password').fill('not-the-session-token');
  await page.getByTestId('lens-login-submit').click();
  await expect(page.getByTestId('lens-catalog-error')).toContainText(/UNAUTHORIZED|401|session|сесси/i, { timeout: 20_000 });
  await expect(page.getByTestId('lens-q')).toHaveCount(0);
});
