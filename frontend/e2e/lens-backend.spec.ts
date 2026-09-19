import { expect, test, type Page, type Route } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

// What a juror does, in a real browser, against a running Carbon Lens service.
//
// The suite is skipped unless a service URL and all three role passwords are present, so the
// ordinary run never depends on a backend being up. Credentials come from the environment and
// from nowhere else — no default, no fallback, nothing committed:
//
//   $env:E2E_LENS_BACKEND_URL='http://127.0.0.1:8031/api/v2'
//   $env:E2E_LENS_PASSWORD_OWNER=...; $env:E2E_LENS_PASSWORD_VERIFIER=...; $env:E2E_LENS_PASSWORD_INVESTOR=...
//   $env:E2E_BASE_URL='http://127.0.0.1:4173'   # a build made with VITE_LENS_API_BASE_URL=<the service>
//   npx playwright test e2e/lens-backend.spec.ts
//
// Playwright is a check, not the demonstration: on the day, a person clicks this themselves.

const BASE = process.env.E2E_LENS_BACKEND_URL;
const PASSWORDS: Record<Role, string | undefined> = {
  owner: process.env.E2E_LENS_PASSWORD_OWNER,
  verifier: process.env.E2E_LENS_PASSWORD_VERIFIER,
  investor: process.env.E2E_LENS_PASSWORD_INVESTOR,
};

type Role = 'owner' | 'verifier' | 'investor';

test.skip(
  !BASE || !PASSWORDS.owner || !PASSWORDS.verifier || !PASSWORDS.investor,
  'set E2E_LENS_BACKEND_URL and E2E_LENS_PASSWORD_OWNER/VERIFIER/INVESTOR to run the live check',
);

const AOI = 'RU_TVER_01';
const RUN_TIMEOUT = 240_000;

/** Nothing may leave the machine, and nothing may throw in the page. Armed on every test. */
function watchPage(page: Page) {
  const external: string[] = [];
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['127.0.0.1', 'localhost'].includes(url.hostname) && !['data:', 'blob:'].includes(url.protocol)) {
      external.push(request.url());
    }
  });
  return {
    assertClean() {
      expect(external, 'no request left the machine').toEqual([]);
      expect(pageErrors, 'no uncaught error in the page').toEqual([]);
    },
  };
}

async function signIn(page: Page, role: Role) {
  await page.getByTestId('lens-login-username').fill(role);
  await page.getByTestId('lens-login-password').fill(PASSWORDS[role] as string);
  await page.getByTestId('lens-login-submit').click();
  await expect(page.getByTestId('lens-role')).toBeVisible({ timeout: 30_000 });
  // The service authenticated it. A screen that reached the offline set instead would say so here.
  await expect(page.getByTestId('lens-mode')).toContainText('СЕРВИС');
}

async function signOut(page: Page) {
  await page.getByTestId('lens-logout').click();
  await expect(page.getByTestId('lens-login-submit')).toBeVisible({ timeout: 30_000 });
}

/** The session token this tab holds, so a test can ask the service directly what it allows. */
async function sessionToken(page: Page): Promise<string> {
  const raw = await page.evaluate(() => globalThis.sessionStorage.getItem('carbon-lens.session'));
  const token = raw ? (JSON.parse(raw) as { token?: string }).token : null;
  expect(token, 'the tab holds a service session').toBeTruthy();
  return token as string;
}

test.describe('the live service', () => {
  test('three roles carry one request from a contour to a finalized passport', async ({ page }) => {
    test.setTimeout(RUN_TIMEOUT);
    const watch = watchPage(page);
    await page.goto('/lens');

    // -- owner: a contour, a period, a stated volume ---------------------------------------
    await signIn(page, 'owner');
    await expect(page.getByTestId('lens-catalog-error')).toHaveCount(0);

    await page.getByTestId('lens-area-select').selectOption(AOI);
    await expect(page.getByTestId('lens-area')).toContainText('га');
    // The authoritative area is the geodesic one the service computed. A browser estimate is
    // labelled as preliminary, and submitting on one is refused, so this label is the whole claim.
    await expect(page.getByTestId('lens-area-source')).toContainText('Площадь сервиса', { timeout: 30_000 });

    await page.getByTestId('lens-year-start').selectOption('2019');
    await page.getByTestId('lens-year-end').selectOption('2024');
    await page.getByTestId('lens-claim-input').fill('1000');
    await page.getByTestId('lens-submit').click();

    await expect(page.getByTestId('lens-my-requests')).toContainText(AOI, { timeout: 60_000 });
    await expect(page.getByTestId('lens-request-error')).toHaveCount(0);
    await expect(page.getByTestId('lens-owner-status')).toContainText('ждёт верификатора');

    const ownerToken = await sessionToken(page);
    await signOut(page);
    // Signing out revokes the session on the service, not only in this tab.
    const afterLogout = await page.request.get(`${BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
    });
    expect(afterLogout.status(), 'the revoked token is refused by the service').toBe(401);

    // -- verifier: the analysis, and everything the result must carry ----------------------
    await signIn(page, 'verifier');
    await page.getByTestId('lens-queue-list').locator('button').first().click();
    await page.getByTestId('lens-run-analysis').click();
    await expect(page.getByTestId('lens-q')).toBeVisible({ timeout: 180_000 });
    await expect(page.getByTestId('lens-timeout')).toHaveCount(0);

    // Whatever the service computed is what the screen shows. The shape is asserted, never the
    // number: a test that expected a particular Q would be a reason to adjust the method.
    const verdict = await page.getByTestId('lens-verdict').textContent();
    expect(verdict).toMatch(/подтверждён|не подтверждён|Недостаточно данных/);
    await expect(page.getByTestId('lens-eproj')).toBeVisible();
    await expect(page.getByTestId('lens-r')).toBeVisible();
    // The stated volume beside the computed one, which is the comparison the case asks for.
    await expect(page.getByTestId('lens-claim')).toBeVisible();
    await expect(page.getByTestId('lens-claim-claimed')).toContainText('1');
    await expect(page.getByTestId('lens-claim-sentence')).not.toBeEmpty();

    // Four coverages, each answering its own question and none of them merged into the others.
    await page.getByTestId('lens-tab-quality').click();
    for (const axis of ['biomass_fraction', 'baseline_fraction', 'uncertainty_fraction', 'optical_paired_valid_fraction']) {
      await expect(page.getByTestId(`lens-coverage-${axis}`), `coverage axis ${axis}`).toContainText('%');
    }
    // The interval belongs beside the coverages, on the same tab: a number without it reads as
    // more certain than it is.
    await expect(page.getByTestId('lens-uncertainty')).toBeVisible();
    await expect(page.getByTestId('lens-risks')).toBeVisible();
    // Risks are evidence beside the number, never a second deduction from it.
    await expect(page.getByTestId('lens-quality-risks')).not.toContainText('вычет');

    // Change zones and the gaps between observations are separate layers: a map that showed only
    // what was seen invites reading the rest as unchanged.
    await page.getByTestId('lens-tab-what').click();
    const zones = page.getByTestId('lens-zone-list').locator('li');
    const zoneCount = await zones.count();
    const zonesAbsent = await page.getByTestId('lens-zones-empty').count();
    expect(zoneCount > 0 || zonesAbsent === 1, 'zones are listed or their absence is stated').toBe(true);

    await page.getByTestId('lens-show-cells').click();
    await expect(page.getByTestId('lens-cells-integrity')).toHaveCount(0);

    // The rendered report is offered as a file too, and it has to arrive.
    const htmlReport = await Promise.all([
      page.waitForEvent('download'),
      page.getByTestId('lens-download-report').click(),
    ]).then(([event]) => event);
    expect(await htmlReport.path(), 'the HTML report reached the disk').toBeTruthy();

    // -- the passport, downloaded and checked ----------------------------------------------
    // "совпадает" alone is satisfied by "не совпадает", so the phrase has to carry the word before
    // it. The looser form is how a broken integrity check went unnoticed.
    await page.getByTestId('lens-passport-verify').click();
    await expect(page.getByTestId('lens-passport-result')).toContainText('содержания совпадает');
    await expect(page.getByTestId('lens-passport-result')).not.toContainText('не совпадает');
    await page.getByTestId('lens-report-verify').click();
    await expect(page.getByTestId('lens-report-result')).toContainText('отчёта совпадает');

    const download = await Promise.all([
      page.waitForEvent('download'),
      page.getByTestId('lens-passport-download').click(),
    ]).then(([event]) => event);
    const downloadedPath = await download.path();
    expect(downloadedPath, 'the passport reached the disk').toBeTruthy();
    const passport = readFileSync(downloadedPath as string, 'utf8');
    expect(passport, 'no session token travels inside the passport').not.toContain(await sessionToken(page));

    const untouched = join(tmpdir(), `carbon-lens-passport-${Date.now()}.json`);
    writeFileSync(untouched, passport, 'utf8');
    await page.getByTestId('lens-passport-upload').setInputFiles(untouched);
    await expect(page.getByTestId('lens-passport-file-result')).toContainText('не изменялся');

    // The same file with one number moved must be refused. This is the check a reader repeats.
    const parsed = JSON.parse(passport) as { content: { units?: Record<string, unknown> } };
    parsed.content.units = { ...(parsed.content.units ?? {}), q: 999_999 };
    const tampered = join(tmpdir(), `carbon-lens-passport-tampered-${Date.now()}.json`);
    writeFileSync(tampered, JSON.stringify(parsed, null, 2), 'utf8');
    await page.getByTestId('lens-passport-upload').setInputFiles(tampered);
    await expect(page.getByTestId('lens-passport-file-result')).toContainText('изменён после выдачи');

    await page.getByTestId('lens-finalize').click();
    await expect(page.getByTestId('lens-passport-status')).toContainText('ФИНАЛИЗИРОВАН', { timeout: 60_000 });
    await expect(page.getByTestId('lens-passport-finalizer')).toContainText('верификатор');
    await signOut(page);

    // -- investor: a finalized passport, its stress test and its scenarios -----------------
    await signIn(page, 'investor');
    await page.getByTestId('lens-portfolio-list').locator('button').first().click();
    await expect(page.getByTestId('lens-q')).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('lens-claim')).toBeVisible();
    await expect(page.getByTestId('lens-claim-sentence')).not.toBeEmpty();
    // The projection runs to 2029, and the line marking where measurement ends and assumption
    // begins is drawn. `toBeVisible` cannot be used on it: an SVG line is one pixel wide and has a
    // zero-area box, so the assertion is that it is attached inside a chart that is on screen.
    await expect(page.getByTestId('lens-timeline')).toBeVisible();
    await expect(page.getByTestId('lens-projection-boundary')).toBeAttached();
    await expect(page.getByTestId('lens-timeline-table')).toContainText('2029');
    await expect(page.getByTestId('lens-calculator')).toBeVisible();
    // An investor never gets the verifier's actions, and the service is what enforces that.
    await expect(page.getByTestId('lens-run-analysis')).toHaveCount(0);
    await expect(page.getByTestId('lens-finalize')).toHaveCount(0);

    expect(page.url(), 'no token in the address bar').not.toMatch(/token=/);
    watch.assertClean();
  });

  test('a wrong password is refused and nothing is invented in its place', async ({ page }) => {
    const watch = watchPage(page);
    await page.goto('/lens');
    await page.getByTestId('lens-login-username').fill('verifier');
    await page.getByTestId('lens-login-password').fill('not-the-password');
    await page.getByTestId('lens-login-submit').click();
    await expect(page.getByTestId('lens-login-error')).toContainText(/не подошл|UNAUTHORIZED|401/i, { timeout: 30_000 });
    // The failure must not open a workspace, and must not quietly serve the offline set instead.
    await expect(page.getByTestId('lens-q')).toHaveCount(0);
    await expect(page.getByTestId('lens-role')).toHaveCount(0);
    watch.assertClean();
  });

  test('the service, not the screen, decides what each role may do', async ({ page }) => {
    // Hiding a button is a courtesy. These are the checks that matter: the calls are made with a
    // real session, past the screen, and every one of them has to come back refused.
    const watch = watchPage(page);
    await page.goto('/lens');

    // A verifier sees every request, so this is where a real identifier comes from.
    await signIn(page, 'verifier');
    const verifierToken = await sessionToken(page);
    const queue = await page.request.get(`${BASE}/requests`, {
      headers: { Authorization: `Bearer ${verifierToken}` },
    });
    expect(queue.status()).toBe(200);
    const requests = ((await queue.json()) as { requests: Array<{ request_id: string }> }).requests;
    expect(requests.length, 'the earlier test left a request behind').toBeGreaterThan(0);
    const requestId = requests[0]?.request_id as string;

    // A verifier reviews a claim; changing it would make the comparison their own work.
    const edited = await page.request.patch(`${BASE}/requests/${requestId}`, {
      headers: { Authorization: `Bearer ${verifierToken}` },
      data: { claimed_units: 1 },
    });
    expect([403, 409], 'a verifier does not restate the owner claim').toContain(edited.status());
    await signOut(page);

    await signIn(page, 'owner');
    const ownerToken = await sessionToken(page);
    const selfFinalized = await page.request.post(`${BASE}/requests/${requestId}/finalize`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
    });
    expect([403, 404], 'nobody finalizes their own verification').toContain(selfFinalized.status());
    await signOut(page);

    await signIn(page, 'investor');
    const investorToken = await sessionToken(page);
    const started = await page.request.post(`${BASE}/requests/${requestId}/analysis`, {
      headers: { Authorization: `Bearer ${investorToken}`, 'Idempotency-Key': 'e2e-investor-probe' },
    });
    expect([403, 404], 'refused, never accepted').toContain(started.status());

    const measured = await page.request.post(`${BASE}/areas/measure`, {
      headers: { Authorization: `Bearer ${investorToken}` },
      data: { geometry: { type: 'Polygon', coordinates: [[[32.9, 56.5], [32.95, 56.5], [32.95, 56.55], [32.9, 56.55], [32.9, 56.5]]] } },
    });
    expect(measured.status(), 'measuring an area is not an investor action').toBe(403);

    const anonymous = await page.request.get(`${BASE}/requests`);
    expect(anonymous.status(), 'no session, no answer').toBe(401);
    watch.assertClean();
  });

  test('an unavailable service is reported, never replaced by the offline set', async ({ page }) => {
    const watch = watchPage(page);
    await page.goto('/lens');
    await signIn(page, 'verifier');
    await page.route('**/api/v2/**', (route: Route) => route.abort('failed'));
    await page.reload();

    await expect(page.getByTestId('lens-catalog-error')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('lens-catalog-error')).toContainText('не подставляется автоматически');
    // The decisive part: no number appears from anywhere while the service is unreachable.
    await expect(page.getByTestId('lens-q')).toHaveCount(0);
    await expect(page.getByTestId('lens-mode')).not.toContainText('ОФЛАЙН');
    watch.assertClean();
  });

  test('a request state this client does not know neither blanks the screen nor is guessed', async ({ page }) => {
    const watch = watchPage(page);
    await page.goto('/lens');
    await signIn(page, 'verifier');

    // A newer service inventing a state must not take the screen down with it.
    await page.route('**/api/v2/requests', async (route: Route) => {
      const response = await route.fetch();
      const body = (await response.json()) as { requests: Array<Record<string, unknown>> };
      for (const item of body.requests) item.status = 'WITHDRAWN_BY_OWNER';
      await route.fulfill({ response, json: body });
    });
    await page.reload();

    await expect(page.getByTestId('lens-queue-list')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('lens-queue-list')).toContainText('СОСТОЯНИЕ НЕИЗВЕСТНО');
    await page.getByTestId('lens-queue-list').locator('button').first().click();
    // Unknown is not "ready to run": the action stays closed rather than being offered and refused.
    await expect(page.getByTestId('lens-run-analysis')).toBeDisabled();
    watch.assertClean();
  });

  test('a result with no units says so instead of showing a zero', async ({ page }) => {
    // A client-side check, and only that: the service computed a real result, and this test rewrites
    // it on the way in to see what the screen does with an unavailable Q. The distinction it guards
    // is the one that matters most here — "not calculable" and "calculated as zero" are different
    // findings, and a screen that renders both as 0 destroys the difference.
    const watch = watchPage(page);
    await page.route('**/api/v2/analyses/*', async (route: Route) => {
      const response = await route.fetch();
      const body = (await response.json()) as { result?: { units?: Record<string, unknown> } };
      if (body.result?.units) {
        body.result.units = { ...body.result.units, q: null, status: 'UNAVAILABLE' };
      }
      await route.fulfill({ response, json: body });
    });

    await page.goto('/lens');
    await signIn(page, 'verifier');
    await page.getByTestId('lens-queue-list').locator('button').first().click();
    await expect(page.getByTestId('lens-q')).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('lens-q')).toContainText('Не рассчитано');
    await expect(page.getByTestId('lens-q')).not.toContainText(/(^|\s)0(\s|$)/);
    watch.assertClean();
  });

  test('the workspace is usable at 390 px and from the keyboard alone', async ({ page }) => {
    const watch = watchPage(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/lens');

    // Signing in without touching the mouse: the form has to be reachable in tab order.
    await page.getByTestId('lens-login-username').focus();
    await page.keyboard.type('owner');
    await page.keyboard.press('Tab');
    await page.keyboard.type(PASSWORDS.owner as string);
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('lens-role')).toBeVisible({ timeout: 30_000 });

    // Nothing may scroll the page sideways at this width.
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, 'no horizontal scroll at 390 px').toBeLessThanOrEqual(1);

    await expect(page.getByTestId('lens-request-form')).toBeVisible();
    const focused = await page.evaluate(() => document.activeElement?.tagName ?? '');
    expect(focused, 'focus stayed inside the document').not.toBe('');
    watch.assertClean();
  });
});
