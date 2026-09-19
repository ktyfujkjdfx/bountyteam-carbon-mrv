import { expect, test, type Page } from '@playwright/test';

const shots = process.env.E2E_SCREENSHOT_DIR;
const OFFLINE = '/lens?lens=fixture&demo=1';

async function shot(page: Page, name: string) {
  if (!shots) return;
  await page.addStyleTag({ content: '.topbar { position: static !important; }' });
  await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
}

function watch(page: Page) {
  const pageErrors: string[] = [];
  const external: string[] = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') pageErrors.push(`console: ${msg.text()}`);
  });
  page.on('request', (req) => {
    const url = new URL(req.url());
    if (!['127.0.0.1', 'localhost'].includes(url.hostname) && !['data:', 'blob:'].includes(url.protocol)) external.push(req.url());
  });
  return { pageErrors, external };
}

async function signIn(page: Page, role: 'owner' | 'verifier' | 'investor') {
  await page.goto(OFFLINE);
  await expect(page.getByTestId('lens-demo-accounts')).toBeVisible();
  await page.getByTestId(`lens-demo-account-${role}`).click();
  await expect(page.getByTestId('lens-role')).toBeVisible();
}

async function submitAsOwner(page: Page, options: { aoi: string; yearStart: string; yearEnd: string; claim?: string }) {
  await signIn(page, 'owner');
  await page.getByTestId('lens-area-select').selectOption(options.aoi);
  await expect(page.getByTestId('lens-area')).toContainText('га');
  await page.getByTestId('lens-year-start').selectOption(options.yearStart);
  await page.getByTestId('lens-year-end').selectOption(options.yearEnd);
  if (options.claim !== undefined) await page.getByTestId('lens-claim-input').fill(options.claim);
  await page.getByTestId('lens-submit').click();
  await expect(page.getByTestId('lens-my-requests')).toContainText(options.aoi);
}

async function runAsVerifier(page: Page, scenario: string) {
  await page.getByTestId('lens-logout').click();
  await signIn(page, 'verifier');
  await page.getByTestId('lens-queue-list').locator('button').first().click();
  await page.getByTestId('lens-scenario-select').selectOption(scenario);
  await page.getByTestId('lens-run-analysis').click();
  await expect(page.getByTestId('lens-q')).toBeVisible({ timeout: 30_000 });
}

test('roles: owner submits, verifier calculates and finalises, investor reads the passport', async ({ page }) => {
  const { pageErrors, external } = watch(page);

  await submitAsOwner(page, { aoi: 'RU_TVER_01', yearStart: '2019', yearEnd: '2024', claim: '3000' });
  await expect(page.getByTestId('lens-owner-status')).toContainText('ждёт верификатора');
  await expect(page.getByTestId('lens-run-analysis')).toHaveCount(0);
  await shot(page, 'lens-01-owner');

  await runAsVerifier(page, 'ZERO_NON_POSITIVE');
  await expect(page.getByTestId('lens-verdict')).toContainText('дополнительный эффект не подтверждён');
  await expect(page.getByTestId('lens-q')).toContainText('0');
  await expect(page.getByTestId('lens-claim-status')).toContainText('НЕ ПОДТВЕРЖДЕНО');
  await page.getByTestId('lens-note-input').fill('Проверьте границы участка: контур включает просеку.');
  await page.getByTestId('lens-note-add').click();
  await page.getByTestId('lens-finalize').click();
  await expect(page.getByTestId('lens-passport-status')).toContainText('ФИНАЛИЗИРОВАН');
  await expect(page.getByTestId('lens-passport-finalizer')).toContainText('verifier@demo.local');
  await shot(page, 'lens-02-verifier');

  await page.getByTestId('lens-logout').click();
  await signIn(page, 'investor');
  await page.getByTestId('lens-portfolio-list').locator('button').first().click();
  await expect(page.getByTestId('lens-q')).toContainText('0');
  await expect(page.getByTestId('lens-calculator-zero')).toBeVisible();
  await expect(page.getByTestId('lens-lifecycle-reason-DEMO_ISSUE')).toContainText('0 единиц');
  await shot(page, 'lens-03-investor');

  expect(external, 'no external hosts').toEqual([]);
  expect(pageErrors).toEqual([]);
});

test('roles: forbidden screen explains itself and a reload keeps the session', async ({ page }) => {
  const { pageErrors } = watch(page);
  await signIn(page, 'investor');
  await expect(page.getByTestId('lens-investor-empty')).toBeVisible();

  await page.goto('/lens?lens=fixture&demo=1#/verifier');
  await expect(page.getByTestId('lens-forbidden')).toContainText('другой роли');
  await expect(page.getByTestId('lens-queue-list')).toHaveCount(0);

  await page.reload();
  await expect(page.getByTestId('lens-session-email')).toContainText('investor@demo.local');
  await page.getByTestId('lens-logout').click();
  await expect(page.getByTestId('lens-login-submit')).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('lens-login-submit')).toBeVisible();

  expect(pageErrors).toEqual([]);
});

test('positive result: the doc example shows Q = 395 and its formulas', async ({ page }) => {
  const { pageErrors } = watch(page);
  await submitAsOwner(page, { aoi: 'RU_TVER_01', yearStart: '2019', yearEnd: '2020' });
  await runAsVerifier(page, 'DOC_EXAMPLE_Q395');

  await expect(page.getByTestId('lens-q')).toContainText('395');
  await expect(page.getByTestId('lens-verdict')).toContainText('Дополнительный эффект подтверждён');
  await expect(page.getByTestId('lens-fixture-note')).toContainText('Условный пример');
  await expect(page.getByTestId('lens-value')).toContainText('592 500');
  await page.getByTestId('lens-price-high').click();
  await expect(page.getByTestId('lens-value')).toContainText('1 580 000');

  await page.getByTestId('lens-tab-how').click();
  await expect(page.getByTestId('lens-step-q')).toContainText('395');
  await page.getByTestId('lens-step-radj').getByText('Вычет за неопределённость').click();
  await expect(page.getByTestId('lens-step-radj')).toContainText('H/R');
  await shot(page, 'lens-04-doc-example');

  expect(pageErrors).toEqual([]);
});

test('q = null is not zero and the map keeps working without a cells layer', async ({ page }) => {
  const { pageErrors } = watch(page);
  await submitAsOwner(page, { aoi: 'RU_VOLOGDA_02', yearStart: '2019', yearEnd: '2020' });
  await runAsVerifier(page, 'UNAVAILABLE_COVERAGE');

  await expect(page.getByTestId('lens-q')).toContainText('Не рассчитано');
  await expect(page.getByTestId('lens-verdict')).toContainText('Недостаточно данных');
  await expect(page.getByTestId('lens-value')).toContainText('—');
  await page.getByTestId('lens-tab-quality').click();
  await expect(page.getByTestId('lens-coverage-biomass_fraction')).toContainText('69 %');
  await expect(page.getByTestId('lens-coverage-optical_paired_valid_fraction')).toContainText('94 %');
  await expect(page.getByTestId('lens-warning-INCOMPLETE_BIOMASS_COVERAGE')).toBeVisible();
  await expect(page.getByTestId('lens-map')).toBeVisible();
  await shot(page, 'lens-05-unavailable');

  expect(pageErrors).toEqual([]);
});

test('fire evidence: zones, cells to the pixel and the official event record', async ({ page }) => {
  const { pageErrors } = watch(page);
  await submitAsOwner(page, { aoi: 'RU_MORDOVIA_03', yearStart: '2020', yearEnd: '2022' });
  await runAsVerifier(page, 'FIRE_SUPPORTED_LOSS');

  await expect(page.getByTestId('lens-zone-cause')).toContainText('ПОЖАР ПО ПРОДУКТУ');
  await expect(page.getByTestId('lens-event-RU_MORDOVIA_03_MODIS_FIRE_202108')).toContainText('2021-08-05');
  await expect(page.getByTestId('lens-event-RU_MORDOVIA_03_MODIS_FIRE_202108')).toContainText('Точный контур пожара');

  await page.getByTestId('lens-show-cells').click();
  const cells = page.locator('.leaflet-overlay-pane path');
  await expect.poll(async () => cells.count()).toBeGreaterThan(5);
  await cells.nth(3).click();
  await expect(page.getByTestId('lens-cell-card')).toBeVisible();
  await expect(page.getByTestId('lens-cell-series')).toContainText('т C/га');
  await shot(page, 'lens-06-fire-cells');

  expect(pageErrors).toEqual([]);
});

test('arbitrary polygon: the server area is shown and an oversized contour is refused', async ({ page }) => {
  const { pageErrors } = watch(page);
  await signIn(page, 'owner');
  await page.getByText('Импорт GeoJSON').click();

  await page.getByTestId('lens-geojson-input').fill(
    JSON.stringify({ type: 'Polygon', coordinates: [[[32.91, 56.59], [32.93, 56.59], [32.93, 56.6], [32.91, 56.6], [32.91, 56.59]]] }),
  );
  await page.getByTestId('lens-geojson-apply').click();
  await expect(page.getByTestId('lens-geometry-source')).toContainText('импортированный GeoJSON');
  await expect(page.getByTestId('lens-area')).toContainText('га');
  await expect(page.getByTestId('lens-area-source')).toContainText('оценка');

  await page.getByTestId('lens-geojson-input').fill(JSON.stringify({ type: 'Polygon', coordinates: [[[32, 56], [33, 56], [33, 57], [32, 57], [32, 56]]] }));
  await page.getByTestId('lens-geojson-apply').click();
  await expect(page.getByTestId('lens-area-over-limit')).toContainText('превышает предел');
  await expect(page.getByTestId('lens-submit')).toBeDisabled();

  await page.getByTestId('lens-geojson-input').fill(JSON.stringify({ type: 'Polygon', coordinates: [[[32.91, 56.59], [32.93, 56.6], [32.93, 56.59], [32.91, 56.6], [32.91, 56.59]]] }));
  await page.getByTestId('lens-geojson-apply').click();
  await expect(page.getByTestId('lens-measure-error')).toContainText('пересекает сам себя');

  await page.getByTestId('lens-geojson-input').fill(JSON.stringify({ type: 'Polygon', coordinates: [[[3300000, 6200000], [3300100, 6200000], [3300100, 6200100], [3300000, 6200100], [3300000, 6200000]]] }));
  await page.getByTestId('lens-geojson-apply').click();
  await expect(page.getByTestId('lens-measure-error')).toContainText('WGS84');

  await page.getByTestId('lens-geojson-input').fill('{ not json');
  await page.getByTestId('lens-geojson-apply').click();
  await expect(page.getByTestId('lens-geojson-error')).toContainText('Это не JSON');

  expect(pageErrors).toEqual([]);
});

test('passport: a modified copy of the downloaded report is detected', async ({ page }) => {
  const { pageErrors } = watch(page);
  await submitAsOwner(page, { aoi: 'RU_TVER_01', yearStart: '2019', yearEnd: '2020' });
  await runAsVerifier(page, 'DOC_EXAMPLE_Q395');

  await page.getByTestId('lens-passport-verify').click();
  await expect(page.getByTestId('lens-passport-result')).toContainText('совпадает');

  const download = await Promise.all([page.waitForEvent('download'), page.getByTestId('lens-passport-download').click()]).then(([d]) => d);
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  const original = Buffer.concat(chunks).toString('utf8');

  await page.getByTestId('lens-passport-upload').setInputFiles({ name: 'passport.json', mimeType: 'application/json', buffer: Buffer.from(original) });
  await expect(page.getByTestId('lens-passport-file-result')).toContainText('не изменялся');

  const tampered = original.replace('"q": 395', '"q": 9999');
  expect(tampered).not.toBe(original);
  await page.getByTestId('lens-passport-upload').setInputFiles({ name: 'tampered.json', mimeType: 'application/json', buffer: Buffer.from(tampered) });
  await expect(page.getByTestId('lens-passport-file-result')).toContainText('изменён после выдачи');
  await shot(page, 'lens-07-passport');

  expect(pageErrors).toEqual([]);
});

test('unknown values from the service degrade to neutral labels without a white screen', async ({ page }) => {
  const { pageErrors } = watch(page);
  await submitAsOwner(page, { aoi: 'RU_TVER_01', yearStart: '2019', yearEnd: '2020' });
  await runAsVerifier(page, 'UNKNOWN_DRIFT');

  await expect(page.getByTestId('lens-status-evidence')).toContainText('UNKNOWN: PARTIALLY_OBSERVED');
  await expect(page.getByTestId('lens-status-evidence')).toHaveAttribute('data-tone', 'neutral');
  await page.getByTestId('lens-tab-quality').click();
  await expect(page.getByTestId('lens-warning-ESCALATED_TO_REGISTRY')).toContainText('UNKNOWN: ESCALATION');
  await expect(page.getByTestId('root-error-boundary')).toHaveCount(0);
  expect(await page.locator('#root').innerHTML()).not.toBe('');

  expect(pageErrors).toEqual([]);
});

test('live mode without a service reports the failure and never substitutes the offline set', async ({ page }) => {
  const { pageErrors } = watch(page);
  await page.goto('/lens?demo=1');
  await page.getByTestId('lens-login-username').fill('verifier@demo.local');
  await page.getByTestId('lens-login-password').fill('demo');
  await page.getByTestId('lens-login-submit').click();
  // Either the login fails against the missing service, or the labelled demo account is used and the
  // catalog request then fails. In both cases the screen says so and shows no calculated numbers.
  await expect(page.getByTestId('lens-login-error').or(page.getByTestId('lens-catalog-error'))).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId('lens-q')).toHaveCount(0);
  // A missing service legitimately produces network console noise; anything else would be a defect.
  const unexpected = pageErrors.filter((error) => !/Failed to fetch|Failed to load resource|404|ERR_/.test(error));
  expect(unexpected).toEqual([]);
});

test('mobile and keyboard: single column at 390 px, dialog and tabs without a mouse', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 2 });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(err.message));

  await submitAsOwner(page, { aoi: 'RU_TVER_01', yearStart: '2019', yearEnd: '2020' });
  await runAsVerifier(page, 'DOC_EXAMPLE_Q395');

  await page.getByTestId('lens-open-methodology').focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('methodology')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('methodology')).toBeHidden();

  await page.getByTestId('lens-tab-quality').focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('lens-quality-risks')).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await shot(page, 'lens-08-mobile');

  expect(errors).toEqual([]);
  await context.close();
});
