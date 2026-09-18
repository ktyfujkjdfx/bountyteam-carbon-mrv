import { expect, test, type Page } from '@playwright/test';

const shots = process.env.E2E_SCREENSHOT_DIR;

async function shot(page: Page, name: string) {
  if (!shots) return;
  // A sticky top bar floats over the middle of a full-page capture; pin it for the frame only.
  await page.addStyleTag({ content: '.topbar { position: static !important; }' });
  await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
}

async function openLens(page: Page) {
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
  await page.goto('/lens');
  await expect(page.getByTestId('lens-request-panel')).toBeVisible();
  await expect(page.getByTestId('lens-area')).toContainText('га');
  return { pageErrors, external };
}

async function runScenario(page: Page, scenario: string) {
  await page.getByTestId('lens-scenario-select').selectOption(scenario);
  await page.getByTestId('lens-run').click();
  await expect(page.getByTestId('lens-q-value')).toBeVisible({ timeout: 20_000 });
}

test('lens workspace runs the doc example end to end and keeps every value labelled', async ({ page }) => {
  const { pageErrors, external } = await openLens(page);

  await expect(page.getByTestId('lens-mode')).toContainText('ПОМЕЧЕННЫЙ НАБОР');
  await expect(page.getByTestId('lens-source-bar')).toContainText('G0 ещё не опубликован');
  await expect(page.getByTestId('lens-aoi-select')).toHaveValue('RU_TVER_01');
  await expect(page.getByTestId('lens-map')).toBeVisible();
  await expect(page.locator('.leaflet-overlay-pane path').first()).toBeAttached();
  await expect(page.getByTestId('lens-summary')).toHaveCount(0);

  await runScenario(page, 'DOC_EXAMPLE_Q395');
  await expect(page.getByTestId('lens-q-value')).toContainText('395');
  await expect(page.getByTestId('lens-scenario-value')).toContainText('592 500');
  await page.getByTestId('lens-price-price_high').click();
  await expect(page.getByTestId('lens-scenario-value')).toContainText('1 580 000');
  await expect(page.getByTestId('lens-status-calculation')).toContainText('РАСЧЁТ ДОСТУПЕН');
  await expect(page.getByTestId('lens-fixture-note')).toContainText('Условный пример');
  await expect(page.getByTestId('lens-timeline-table')).toContainText('сценарий');
  await shot(page, 'lens-01-doc-example');

  await expect(page.getByTestId('lens-step-r')).toContainText('517');
  await expect(page.getByTestId('lens-step-q')).toContainText('395');

  await page.getByTestId('lens-tab-coverage').click();
  await expect(page.getByTestId('lens-coverage-BIOMASS_CCI')).toContainText('100 %');
  await expect(page.getByTestId('lens-coverage-OPTICAL_PAIRED_VALID')).toContainText('82 %');

  await page.getByTestId('lens-tab-zones').click();
  await expect(page.getByTestId('lens-zone-card')).toBeVisible();

  await page.getByTestId('lens-tab-passport').click();
  await page.getByTestId('lens-passport-verify').click();
  await expect(page.getByTestId('lens-passport-result')).toContainText('совпадает');
  await expect(page.getByTestId('lens-sources')).toContainText('Copernicus');

  expect(external, 'no external hosts').toEqual([]);
  expect(pageErrors).toEqual([]);
});

test('lens shows the official observations behind a run and the layers it cannot draw', async ({ page }) => {
  const { pageErrors, external } = await openLens(page);

  await page.getByTestId('lens-demo-step-fire').click();
  await expect(page.getByTestId('lens-q-value')).toBeVisible({ timeout: 20_000 });

  await page.getByTestId('lens-tab-observations').click();
  await expect(page.getByTestId('lens-scenes-table')).toContainText('2021');
  await expect(page.getByTestId('lens-event-RU_MORDOVIA_03_MODIS_FIRE_202108')).toContainText('2021-08-05');
  await expect(page.getByTestId('lens-event-RU_MORDOVIA_03_MODIS_FIRE_202108')).toContainText('Точный контур пожара');
  await expect(page.getByTestId('lens-baseline-table')).toContainText('2021');

  await expect(page.getByTestId('lens-layer-availability-OPTICAL_QUALITY')).toContainText('нет данных');
  await expect(page.getByTestId('lens-layer-STOCK_PREVIEW')).toHaveAttribute('data-availability', 'NOT_IN_THIS_MODE');
  await expect(page.getByTestId('lens-map-missing-layers')).toContainText('Пустая карта не означает');

  await page.getByTestId('lens-tab-zones').click();
  await expect(page.getByTestId('lens-zone-cause')).toContainText('ПРИЧИНА ПОДТВЕРЖДЕНА');
  await expect(page.getByTestId('lens-zone-event')).toContainText('RU_MORDOVIA_03_MODIS_FIRE_202108');
  await shot(page, 'lens-06-fire-evidence');

  const zonePaths = page.locator('.leaflet-overlay-pane path');
  const before = await zonePaths.count();
  await page.getByTestId('lens-layer-toggle-CHANGE_ZONES').click();
  await expect(zonePaths).toHaveCount(before - 2);

  expect(external, 'no external hosts').toEqual([]);
  expect(pageErrors).toEqual([]);
});

test('lens keeps the session across a reload and compares runs without ranking them', async ({ page }) => {
  const { pageErrors } = await openLens(page);

  await runScenario(page, 'DOC_EXAMPLE_Q395');
  await page.getByTestId('lens-demo-step-control').click();
  await expect(page.getByTestId('lens-q-value')).toContainText('0', { timeout: 20_000 });
  await expect(page.getByTestId('lens-notice')).toBeVisible();

  await page.getByTestId('lens-tab-comparison').click();
  const table = page.getByTestId('lens-comparison-table');
  await expect(table).toContainText('395');
  await expect(table).toContainText('RU_TVER_01');
  await expect(page.getByTestId('lens-comparison-limits')).toContainText('не является рейтингом');
  await shot(page, 'lens-07-comparison');

  await page.reload();
  await expect(page.getByTestId('lens-restored-note')).toContainText('сохранённый расчёт');
  await expect(page.getByTestId('lens-q-value')).toBeVisible();
  await expect(page.getByTestId('lens-history')).toContainText('НОВОЕ НАБЛЮДЕНИЕ');

  expect(pageErrors).toEqual([]);
});

test('lens detects a modified copy of the downloaded passport', async ({ page }) => {
  const { pageErrors } = await openLens(page);

  await runScenario(page, 'DOC_EXAMPLE_Q395');
  await page.getByTestId('lens-tab-passport').click();

  const download = await Promise.all([page.waitForEvent('download'), page.getByTestId('lens-passport-download').click()]).then(([d]) => d);
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  const original = Buffer.concat(chunks).toString('utf8');

  await page.getByTestId('lens-passport-upload').setInputFiles({ name: 'passport.json', mimeType: 'application/json', buffer: Buffer.from(original) });
  await expect(page.getByTestId('lens-passport-file-result')).toContainText('не изменялся');

  const tampered = original.replace('"q": 395', '"q": 9999');
  expect(tampered).not.toBe(original);
  await page.getByTestId('lens-passport-upload').setInputFiles({ name: 'passport-tampered.json', mimeType: 'application/json', buffer: Buffer.from(tampered) });
  await expect(page.getByTestId('lens-passport-file-result')).toContainText('изменён после выдачи');
  await expect(page.getByTestId('lens-passport-file-result')).toContainText('не намерение автора');
  await shot(page, 'lens-08-passport-tampered');

  expect(pageErrors).toEqual([]);
});

test('lens separates q = 0 from q = null and explains both', async ({ page }) => {
  const { pageErrors } = await openLens(page);

  await runScenario(page, 'ZERO_NON_POSITIVE');
  await expect(page.getByTestId('lens-q-value')).toHaveText('0ед.');
  await expect(page.getByTestId('lens-q-reason')).toContainText('нет положительного результата');
  await shot(page, 'lens-02-zero');

  await runScenario(page, 'UNAVAILABLE_COVERAGE');
  await expect(page.getByTestId('lens-q-value')).toContainText('Недоступно');
  await expect(page.getByTestId('lens-q-value')).not.toContainText('0');
  await expect(page.getByTestId('lens-q-reason')).toContainText('покрытие');
  await page.getByTestId('lens-tab-coverage').click();
  await expect(page.getByTestId('lens-coverage-BIOMASS_CCI')).toContainText('69 %');
  await expect(page.getByTestId('lens-coverage-OPTICAL_PAIRED_VALID')).toContainText('94 %');
  await shot(page, 'lens-03-unavailable');

  expect(pageErrors).toEqual([]);
});

test('lens compares a user claim and refuses an incomparable scope', async ({ page }) => {
  const { pageErrors } = await openLens(page);

  await page.getByTestId('lens-claim-input').fill('1000');
  await runScenario(page, 'DOC_EXAMPLE_Q395');
  await expect(page.getByTestId('lens-status-claim')).toContainText('ПОДДЕРЖАНО ЧАСТИЧНО');
  await expect(page.getByTestId('lens-gap-value')).toContainText('907 500');
  await expect(page.getByTestId('lens-q-value')).toContainText('395');

  await page.getByTestId('lens-year-end').selectOption('2024');
  await page.getByTestId('lens-run').click();
  await expect(page.getByTestId('lens-status-claim')).toContainText('НЕСОПОСТАВИМО', { timeout: 20_000 });
  await expect(page.getByTestId('lens-claim-reasons')).toContainText('период');
  await expect(page.getByTestId('lens-q-value')).toContainText('395');
  await shot(page, 'lens-04-claim-not-comparable');

  expect(pageErrors).toEqual([]);
});

test('lens degrades unknown contract values and survives an invalid request', async ({ page }) => {
  const { pageErrors } = await openLens(page);

  await runScenario(page, 'UNKNOWN_DRIFT');
  await expect(page.getByTestId('lens-status-evidence')).toContainText('UNKNOWN: PARTIALLY_OBSERVED');
  await expect(page.getByTestId('lens-status-evidence')).toHaveAttribute('data-tone', 'neutral');
  await expect(page.getByTestId('root-error-boundary')).toHaveCount(0);
  expect(await page.locator('#root').innerHTML()).not.toBe('');

  await page.getByTestId('lens-year-start').selectOption('2022');
  await page.getByTestId('lens-year-end').selectOption('2020');
  await page.getByTestId('lens-run').click();
  await expect(page.getByTestId('lens-validation-error')).toContainText('Конечный год должен быть больше начального');
  await expect(page.getByTestId('lens-map')).toBeVisible();

  expect(pageErrors).toEqual([]);
});

test('lens accepts a drawn contour and the official sub-request', async ({ page }) => {
  const { pageErrors } = await openLens(page);

  await page.getByTestId('lens-sample-request').click();
  await expect(page.getByTestId('lens-geometry-source')).toContainText('CHECK_TRANSFER_01');
  await expect(page.getByTestId('lens-area')).toContainText('806');
  await expect(page.getByTestId('lens-year-start')).toHaveValue('2020');
  await expect(page.getByTestId('lens-year-end')).toHaveValue('2024');

  await page.getByTestId('lens-draw-toggle').click();
  await expect(page.getByTestId('lens-draw-hint')).toBeVisible();
  const map = page.getByTestId('lens-map');
  const box = await map.boundingBox();
  if (!box) throw new Error('map has no box');
  await page.mouse.click(box.x + box.width * 0.4, box.y + box.height * 0.4);
  await page.mouse.click(box.x + box.width * 0.55, box.y + box.height * 0.55);
  await expect(page.getByTestId('lens-geometry-source')).toContainText('нарисованный контур');
  await expect(page.getByTestId('lens-area')).toContainText('га');

  expect(pageErrors).toEqual([]);
});

test('lens keyboard and mobile: methodology dialog, tabs and no horizontal overflow', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 2 });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(err.message));

  await page.goto('/lens');
  await expect(page.getByTestId('lens-request-panel')).toBeVisible();
  await page.getByTestId('lens-run').click();
  await expect(page.getByTestId('lens-q-value')).toBeVisible({ timeout: 20_000 });

  await page.getByTestId('lens-open-methodology').focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('methodology')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('methodology')).toBeHidden();

  await page.getByTestId('lens-tab-passport').focus();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('lens-passport')).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await shot(page, 'lens-05-mobile');

  expect(errors).toEqual([]);
  await context.close();
});
