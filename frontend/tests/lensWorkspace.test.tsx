import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { areaGeometryFromData, buildLayers, coverageGapGeometry, createFixtureLensClient, schematicZoneGeometry } from '../src/lens/adapter';
import { ComparisonPanel } from '../src/lens/components/ComparisonPanel';
import { LayersPanel } from '../src/lens/components/LayersPanel';
import { ObservationsPanel } from '../src/lens/components/ObservationsPanel';
import { PassportPanel, passportHtml, passportPayload, verifyPassportFile } from '../src/lens/components/PassportPanel';
import { HistoryPanel } from '../src/lens/components/HistoryPanel';
import { SummaryPanel } from '../src/lens/components/SummaryPanel';
import { ZonesPanel } from '../src/lens/components/ZonesPanel';
import { LensApp } from '../src/lens/LensApp';
import { DEMO_STEPS } from '../src/lens/demo';
import type { FixtureScenarioId } from '../src/lens/fixtures';
import { makeRun } from '../src/lens/session';
import type { LensRequest, LensResult } from '../src/lens/types';

function requestFor(aoiId: string, years: [number, number], claimed: number | null = null): LensRequest {
  return {
    aoi_id: aoiId,
    parent_aoi_id: null,
    geometry: areaGeometryFromData(aoiId) as never,
    year_start: years[0],
    year_end: years[1],
    claimed_units: claimed,
  };
}

async function resultOf(scenario: FixtureScenarioId, request: LensRequest): Promise<LensResult> {
  const client = createFixtureLensClient({ queuedMs: 0, runningMs: 0 });
  const job = await client.submitAnalysis(request, { scenario, idempotencyKey: `key-${Math.random()}` });
  const settled = await client.getJob(job.job_id);
  return client.getResult(settled.result_id ?? '');
}

describe('observations come from the official archive', () => {
  it('lists the real scenes of the period with cloud share and validity', async () => {
    const result = await resultOf('FIRE_SUPPORTED_LOSS', requestFor('RU_MORDOVIA_03', [2020, 2022]));
    render(<ObservationsPanel result={result} />);
    const table = screen.getByTestId('lens-scenes-table');
    expect(within(table).getAllByRole('row').length).toBeGreaterThan(1);
    expect(table).toHaveTextContent('2021');
  });

  it('shows the MODIS event row with its own limitations, not a measured burn area', async () => {
    const result = await resultOf('FIRE_SUPPORTED_LOSS', requestFor('RU_MORDOVIA_03', [2020, 2022]));
    render(<ObservationsPanel result={result} />);
    const event = screen.getByTestId('lens-event-RU_MORDOVIA_03_MODIS_FIRE_202108');
    expect(event).toHaveTextContent('2021-08-05');
    expect(event).toHaveTextContent('60');
    expect(event).toHaveTextContent(/Точный контур пожара/);
    expect(screen.getByTestId('lens-event-link-note')).toHaveTextContent(/не равен измеренной площади гари/i);
  });

  it('says plainly that an area has no event records instead of implying calm', async () => {
    const result = await resultOf('CAUSE_UNKNOWN_LOSS', requestFor('RU_VOLOGDA_02', [2019, 2024]));
    render(<ObservationsPanel result={result} />);
    expect(screen.getByTestId('lens-events-empty')).toHaveTextContent(/не означает отсутствие изменений/i);
    expect(screen.getByTestId('lens-baseline-table')).toHaveTextContent('2019');
  });
});

describe('map layers state what is missing', () => {
  it('reports layers without data and the mode that has no raster previews', async () => {
    const result = await resultOf('WEAK_OPTICS_VALID_CCI', requestFor('RU_MORDOVIA_03', [2021, 2022]));
    render(<LayersPanel layers={result.layers} visible={new Set(['CHANGE_ZONES'])} onToggle={vi.fn()} />);
    expect(screen.getByTestId('lens-layer-availability-OPTICAL_QUALITY')).toHaveTextContent('нет данных');
    expect(screen.getByTestId('lens-layer-STOCK_PREVIEW')).toHaveAttribute('data-availability', 'NOT_IN_THIS_MODE');
    expect(screen.getByTestId('lens-layer-FIRE_EVIDENCE')).toHaveTextContent('RU_MORDOVIA_03_MODIS_FIRE_202108');
  });

  it('lets an available layer be switched off without hiding its explanation', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    const result = await resultOf('UNAVAILABLE_COVERAGE', requestFor('RU_TVER_01', [2019, 2020]));
    render(<LayersPanel layers={result.layers} visible={new Set(['COVERAGE_GAP'])} onToggle={onToggle} />);
    expect(screen.getByTestId('lens-layer-availability-COVERAGE_GAP')).toHaveTextContent('есть данные');
    await user.click(screen.getByTestId('lens-layer-toggle-COVERAGE_GAP'));
    expect(onToggle).toHaveBeenCalledWith('COVERAGE_GAP');
  });

  it('derives the gap layer only when numeric coverage is incomplete', async () => {
    const full = await resultOf('DOC_EXAMPLE_Q395', requestFor('RU_TVER_01', [2019, 2020]));
    const partial = await resultOf('UNAVAILABLE_COVERAGE', requestFor('RU_TVER_01', [2019, 2020]));
    const gapOf = (result: LensResult) => result.layers.find((layer) => layer.layer_id === 'COVERAGE_GAP');
    expect(gapOf(full)?.availability).toBe('NO_DATA');
    expect(gapOf(partial)?.availability).toBe('AVAILABLE');
    expect(gapOf(partial)?.geometry).not.toBeNull();
    expect(buildLayers(full, 'http').find((layer) => layer.layer_id === 'STOCK_PREVIEW')?.availability).toBe('NO_DATA');
  });

  it('keeps schematic geometry inside the request contour and labels it as schematic', async () => {
    const request = requestFor('RU_TVER_01', [2019, 2020]);
    const zone = schematicZoneGeometry(request.geometry, 0, 2);
    const ring = (zone?.coordinates as number[][][])[0] ?? [];
    for (const [lon, lat] of ring) {
      expect(lon).toBeGreaterThanOrEqual(32.91);
      expect(lon).toBeLessThanOrEqual(32.974);
      expect(lat).toBeGreaterThanOrEqual(56.59);
      expect(lat).toBeLessThanOrEqual(56.63);
    }
    expect(coverageGapGeometry(request.geometry, 0)).toBeNull();
    const result = await resultOf('FIRE_SUPPORTED_LOSS', request);
    expect(result.zones[0]?.geometry_note).toMatch(/схематич/i);
  });
});

describe('comparison of runs in the session', () => {
  it('asks for a second run instead of comparing one result with itself', async () => {
    const run = makeRun(requestFor('RU_TVER_01', [2019, 2020]), await resultOf('DOC_EXAMPLE_Q395', requestFor('RU_TVER_01', [2019, 2020])), 'fixture');
    render(<ComparisonPanel runs={[run]} priceId="price_base" />);
    expect(screen.getByTestId('lens-comparison-empty')).toBeVisible();
  });

  it('compares normalised values and names the limits instead of ranking', async () => {
    const a = requestFor('RU_TVER_01', [2019, 2020]);
    const b = requestFor('RU_MORDOVIA_03', [2020, 2022]);
    const runs = [makeRun(a, await resultOf('DOC_EXAMPLE_Q395', a), 'fixture'), makeRun(b, await resultOf('FIRE_SUPPORTED_LOSS', b), 'fixture')];
    render(<ComparisonPanel runs={runs} priceId="price_base" />);
    const table = screen.getByTestId('lens-comparison-table');
    expect(table).toHaveTextContent('395');
    expect(table).toHaveTextContent('RU_MORDOVIA_03');
    expect(table).toHaveTextContent('т CO₂-экв./га·год');
    const limits = screen.getByTestId('lens-comparison-limits');
    expect(limits).toHaveTextContent(/Периоды различаются/);
    expect(limits).toHaveTextContent(/не является рейтингом/);
    expect(screen.queryByText(/лучше купить|рекомендуем|инвестировать стоит/i)).toBeNull();
  });
});

describe('history panel', () => {
  it('labels a different period of the same contour as a new observation', async () => {
    const first = requestFor('RU_TVER_01', [2019, 2020]);
    const second = requestFor('RU_TVER_01', [2019, 2024]);
    const runs = [
      makeRun(second, await resultOf('ZERO_NON_POSITIVE', second), 'fixture', new Date('2026-09-19T10:05:00Z')),
      makeRun(first, await resultOf('DOC_EXAMPLE_Q395', first), 'fixture', new Date('2026-09-19T10:00:00Z')),
    ];
    const onOpen = vi.fn();
    render(<HistoryPanel runs={runs} activeRunId={runs[0]?.run_id ?? null} onOpen={onOpen} onClear={vi.fn()} />);
    expect(screen.getByTestId(`lens-history-relation-${runs[0]?.run_id}`)).toHaveTextContent('НОВОЕ НАБЛЮДЕНИЕ');
    await userEvent.click(screen.getByTestId(`lens-history-item-${runs[1]?.run_id}`));
    expect(onOpen).toHaveBeenCalledWith(runs[1]?.run_id);
  });
});

describe('passport integrity for an outside reader', () => {
  it('is stamped by the adapter so a clean file verifies', async () => {
    const request = requestFor('RU_TVER_01', [2019, 2020]);
    const result = await resultOf('DOC_EXAMPLE_Q395', request);
    expect(result.passport.content_sha256).toMatch(/^0x[0-9a-f]{64}$/);
    expect(await verifyPassportFile(passportPayload(result))).toMatchObject({ kind: 'match' });
  });

  it('detects a modified copy of a downloaded report', async () => {
    const request = requestFor('RU_TVER_01', [2019, 2020]);
    const result = await resultOf('DOC_EXAMPLE_Q395', request);
    const payload = JSON.parse(passportPayload(result)) as { content: { units: { q: number } }; integrity: { content_sha256: string } };
    const honest = JSON.stringify({ ...payload, integrity: { content_sha256: '0x00' } });

    // A real file carries the hash of its own content: build one, then tamper with the numbers.
    const original = JSON.parse(passportPayload(result)) as typeof payload;
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(original.content, null, 2)));
    const hash = `0x${[...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')}`;
    const signed = JSON.stringify({ content: original.content, integrity: { content_sha256: hash } }, null, 2);

    const clean = await verifyPassportFile(signed);
    expect(clean.kind).toBe('match');

    const tamperedContent = JSON.parse(JSON.stringify(original.content)) as { units: { q: number } };
    tamperedContent.units.q = 9999;
    const tampered = JSON.stringify({ content: tamperedContent, integrity: { content_sha256: hash } }, null, 2);
    const verdict = await verifyPassportFile(tampered);
    expect(verdict.kind).toBe('mismatch');

    expect((await verifyPassportFile(honest)).kind).toBe('mismatch');
    expect((await verifyPassportFile('{"nope":1}')).kind).toBe('invalid');
    expect((await verifyPassportFile('not json')).kind).toBe('invalid');
  });

  it('checks an uploaded file through the panel and explains the verdict', async () => {
    const user = userEvent.setup();
    const request = requestFor('RU_TVER_01', [2019, 2020]);
    const result = await resultOf('DOC_EXAMPLE_Q395', request);
    render(<PassportPanel result={result} />);
    const file = new File([passportPayload(result)], 'passport.json', { type: 'application/json' });
    await user.upload(screen.getByTestId('lens-passport-upload'), file);
    const verdict = await screen.findByTestId('lens-passport-file-result');
    expect(verdict).toHaveTextContent(/изменён|не изменялся/);
    expect(screen.getByTestId('lens-passport-origin')).toHaveTextContent(/Помеченный набор/);
  });

  it('writes an HTML report with the same values and escapes user text', async () => {
    const request = requestFor('RU_TVER_01', [2019, 2020]);
    const result = await resultOf('DOC_EXAMPLE_Q395', request);
    const html = passportHtml({ ...result, limitations: ['<script>alert(1)</script>'] });
    expect(html).toContain('395');
    expect(html).toContain('2019–2020');
    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).toContain('&lt;script&gt;');
  });
});

describe('hostile and extreme input', () => {
  it('treats a claim written as HTML as text and refuses it as a number', async () => {
    const user = userEvent.setup();
    render(<LensApp client={createFixtureLensClient({ queuedMs: 0, runningMs: 0 })} />);
    await waitFor(() => expect(screen.getByTestId('lens-area')).toHaveTextContent('га'));
    await user.type(screen.getByTestId('lens-claim-input'), '<img src=x onerror=alert(1)>');
    await user.click(screen.getByTestId('lens-run'));
    expect(screen.getByTestId('lens-validation-error')).toHaveTextContent('должны быть числом');
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByTestId('lens-claim-input')).toHaveValue('<imgsrc=xonerror=alert(1)>');
  }, 20_000);

  it('rejects a negative claim and carries a very large one through without breaking', async () => {
    const negative = requestFor('RU_TVER_01', [2019, 2020], -5);
    await expect(resultOf('DOC_EXAMPLE_Q395', negative)).rejects.toMatchObject({ code: 'INVALID_CLAIM' });

    const huge = requestFor('RU_TVER_01', [2019, 2020], 1e12);
    const result = await resultOf('DOC_EXAMPLE_Q395', huge);
    expect(result.units.q).toBe(395);
    expect(result.claim.gap_units).toBe(1e12 - 395);
    render(<SummaryPanel result={result} priceId="price_base" onPrice={vi.fn()} />);
    expect(screen.getByTestId('lens-q-value')).toHaveTextContent('395');
  });

  it('renders a zone with a very long identifier without losing the card', async () => {
    const base = await resultOf('FIRE_SUPPORTED_LOSS', requestFor('RU_MORDOVIA_03', [2020, 2022]));
    const longId = `ZONE-${'0123456789'.repeat(12)}`;
    const zone = base.zones[0];
    if (!zone) throw new Error('fixture has no zone');
    const result: LensResult = { ...base, zones: [{ ...zone, zone_id: longId, label: longId }] };
    render(<ZonesPanel result={result} selectedZoneId={longId} onSelectZone={vi.fn()} />);
    expect(screen.getByTestId('lens-zone-card')).toHaveTextContent(longId.slice(0, 40));
  });
});

describe('guided walkthrough drives the real controls', () => {
  it('runs a step and shows its acceptance scenario on screen', async () => {
    const user = userEvent.setup();
    render(<LensApp client={createFixtureLensClient({ queuedMs: 0, runningMs: 0 })} />);
    await waitFor(() => expect(screen.getByTestId('lens-area')).toHaveTextContent('га'));
    await user.click(screen.getByTestId('lens-demo-step-fire'));
    expect(await screen.findByTestId('lens-q-value', {}, { timeout: 10_000 })).toHaveTextContent('0');
    expect(screen.getByTestId('lens-fixture-note')).toHaveTextContent('S2');
    await waitFor(() => expect(screen.getByTestId('lens-zone-cause')).toHaveTextContent('ПРИЧИНА ПОДТВЕРЖДЕНА'));
  }, 30_000);

  it('covers every acceptance scenario of the roadmap in the script', () => {
    const covered = new Set(DEMO_STEPS.map((step) => step.acceptance).filter((id): id is string => id !== null));
    for (const id of ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9']) {
      expect(covered.has(id)).toBe(true);
    }
  });
});
