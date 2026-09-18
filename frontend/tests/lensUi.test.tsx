import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { LensApp } from '../src/lens/LensApp';
import { RootErrorBoundary } from '../src/components/RootErrorBoundary';
import { CoveragePanel } from '../src/lens/components/CoveragePanel';
import { PassportPanel, passportContent } from '../src/lens/components/PassportPanel';
import { SummaryPanel } from '../src/lens/components/SummaryPanel';
import { TimelinePanel } from '../src/lens/components/TimelinePanel';
import { WaterfallPanel } from '../src/lens/components/WaterfallPanel';
import { ZonesPanel } from '../src/lens/components/ZonesPanel';
import { areaGeometryFromData, createFixtureLensClient } from '../src/lens/adapter';
import { buildFixtureResult, type FixtureScenarioId } from '../src/lens/fixtures';
import type { LensRequest, LensResult } from '../src/lens/types';

function requestFor(years: [number, number] = [2019, 2020], claimed: number | null = null): LensRequest {
  return {
    aoi_id: 'RU_TVER_01',
    parent_aoi_id: null,
    geometry: areaGeometryFromData('RU_TVER_01') as never,
    year_start: years[0],
    year_end: years[1],
    claimed_units: claimed,
  };
}

function resultOf(scenario: FixtureScenarioId, claimed: number | null = null): LensResult {
  return buildFixtureResult(scenario, requestFor([2019, 2020], claimed), 100);
}

const fastClient = () => createFixtureLensClient({ queuedMs: 0, runningMs: 0 });

describe('SummaryPanel separates q = null from q = 0', () => {
  it('shows a computed Q with scenario value and price switching', async () => {
    const result = resultOf('DOC_EXAMPLE_Q395');
    function Harness() {
      return <SummaryPanel result={result} priceId="price_base" onPrice={vi.fn()} />;
    }
    render(<Harness />);
    expect(screen.getByTestId('lens-q-value')).toHaveTextContent('395');
    expect(screen.getByTestId('lens-scenario-value')).toHaveTextContent('592 500');
    expect(screen.getByTestId('lens-status-calculation')).toHaveTextContent('РАСЧЁТ ДОСТУПЕН');
  });

  it('shows 0 with its reason, never as unavailable', () => {
    render(<SummaryPanel result={resultOf('ZERO_UNCERTAINTY')} priceId="price_base" onPrice={vi.fn()} />);
    expect(screen.getByTestId('lens-q-value')).toHaveTextContent('0');
    expect(screen.getByTestId('lens-q-value')).not.toHaveTextContent('Недоступно');
    expect(screen.getByTestId('lens-q-reason')).toHaveTextContent('неопределённость слишком велика');
  });

  it('shows unavailable with its reason, never as 0', () => {
    render(<SummaryPanel result={resultOf('UNAVAILABLE_COVERAGE')} priceId="price_base" onPrice={vi.fn()} />);
    const value = screen.getByTestId('lens-q-value');
    expect(value).toHaveTextContent('Недоступно');
    expect(value).not.toHaveTextContent('0');
    expect(screen.getByTestId('lens-q-reason')).toHaveTextContent('покрытие');
    expect(screen.getByTestId('lens-scenario-value')).toHaveTextContent('—');
  });

  it('renders unknown statuses from a drifted contract as neutral UNKNOWN', () => {
    render(<SummaryPanel result={resultOf('UNKNOWN_DRIFT')} priceId="price_base" onPrice={vi.fn()} />);
    const evidence = screen.getByTestId('lens-status-evidence');
    expect(evidence).toHaveTextContent('UNKNOWN: PARTIALLY_OBSERVED');
    expect(evidence).toHaveAttribute('data-tone', 'neutral');
    expect(screen.getByTestId('lens-status-claim')).toHaveTextContent('UNKNOWN: ESCALATED_TO_REGISTRY');
    expect(screen.getAllByTestId('unknown-value-note').length).toBeGreaterThan(0);
  });
});

describe('calculation, coverage, zones and passport panels', () => {
  it('waterfall exposes formulas and the stop-rule note without recomputing', async () => {
    render(<WaterfallPanel result={resultOf('ZERO_NON_POSITIVE')} />);
    expect(screen.getByTestId('lens-step-r')).toHaveTextContent('-245,666');
    expect(screen.getByTestId('lens-step-q')).toHaveTextContent('0');
    expect(screen.getByText(/Расчёт остановлен на нуле/)).toBeVisible();
    await userEvent.click(within(screen.getByTestId('lens-step-unc')).getByText(/Вычет за неопределённость/));
    expect(screen.getByTestId('lens-step-unc')).toHaveTextContent('H/R не вычисляется при R ≤ 0');
  });

  it('coverage keeps biomass and optics apart', () => {
    render(<CoveragePanel result={resultOf('WEAK_OPTICS_VALID_CCI')} />);
    expect(screen.getByTestId('lens-coverage-BIOMASS_CCI')).toHaveTextContent('100 %');
    expect(screen.getByTestId('lens-coverage-OPTICAL_PAIRED_VALID')).toHaveTextContent('18 %');
    expect(screen.getByTestId('lens-coverage')).toHaveTextContent('не восполняет отсутствующие числовые данные');
  });

  it('timeline marks gaps and scenario years instead of drawing a continuous line', () => {
    render(<TimelinePanel result={resultOf('DOC_EXAMPLE_Q395')} />);
    const table = screen.getByTestId('lens-timeline-table');
    expect(table).toHaveTextContent('нет данных');
    expect(table).toHaveTextContent('сценарий');
    // 2015 and 2019 are not consecutive observations, so the observed series must not bridge them.
    const series = screen.getByTestId('lens-timeline').querySelectorAll('path.chart-series');
    expect(series.length).toBe(1);
    expect(series[0]?.getAttribute('d')).not.toMatch(/M[\d.,]+ L[\d.,]+ L/);
  });

  it('zone card shows contribution in E and refuses to attribute Q to a zone', async () => {
    const result = resultOf('WEAK_OPTICS_VALID_CCI');
    render(<ZonesPanel result={result} selectedZoneId={null} onSelectZone={vi.fn()} />);
    const card = screen.getByTestId('lens-zone-card');
    expect(card).toHaveTextContent('24,5 га');
    expect(card).toHaveTextContent('1 136,7 т CO₂-экв.');
    expect(screen.getByTestId('lens-zone-cause')).toHaveTextContent('ПРИЧИНА НЕ УСТАНОВЛЕНА');
    expect(screen.getByTestId('lens-zones')).toHaveTextContent('неаддитивны');
  });

  it('passport verifies the downloaded content and explains a mismatch', async () => {
    const result = resultOf('DOC_EXAMPLE_Q395');
    const payload = passportContent(result);
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(payload));
    const hash = `0x${[...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')}`;

    const matching: LensResult = { ...result, passport: { ...result.passport, content_sha256: hash } };
    const { unmount } = render(<PassportPanel result={matching} />);
    await userEvent.click(screen.getByTestId('lens-passport-verify'));
    expect(await screen.findByTestId('lens-passport-result')).toHaveTextContent('совпадает');
    unmount();

    render(<PassportPanel result={result} />);
    await userEvent.click(screen.getByTestId('lens-passport-verify'));
    const mismatch = await screen.findByTestId('lens-passport-result');
    expect(mismatch).toHaveTextContent('отличается');
    expect(mismatch).toHaveTextContent('не диагноз');
    expect(screen.getByTestId('lens-sources')).toHaveTextContent('Copernicus');
  });
});

describe('LensApp workspace', () => {
  it('runs the full request → job → result path and keeps the fixture label visible', async () => {
    render(<LensApp client={fastClient()} />);
    expect(await screen.findByTestId('lens-request-panel')).toBeVisible();
    await waitFor(() => expect(screen.getByTestId('lens-geometry-source')).toHaveTextContent('RU_TVER_01'));
    await waitFor(() => expect(screen.getByTestId('lens-area')).toHaveTextContent('га'));
    expect(screen.queryByTestId('lens-summary')).toBeNull();
  }, 20_000);

  it('shows Q, badges, tabs and the claim comparison after a run', async () => {
    const user = userEvent.setup();
    render(<LensApp client={fastClient()} />);
    await waitFor(() => expect(screen.getByTestId('lens-area')).toHaveTextContent('га'));
    await user.click(screen.getByTestId('lens-run'));
    expect(await screen.findByTestId('lens-q-value', {}, { timeout: 10_000 })).toHaveTextContent('395');
    expect(screen.getByTestId('lens-fixture-note')).toHaveTextContent('Условный пример');

    await user.click(screen.getByTestId('lens-tab-coverage'));
    expect(screen.getByTestId('lens-coverage-BIOMASS_CCI')).toBeVisible();
    await user.click(screen.getByTestId('lens-tab-zones'));
    expect(screen.getByTestId('lens-zone-card')).toBeVisible();
    await user.click(screen.getByTestId('lens-tab-passport'));
    expect(screen.getByTestId('lens-passport')).toBeVisible();
  }, 20_000);

  it('explains NOT_COMPARABLE for a claim from another period and keeps Q unchanged', async () => {
    const user = userEvent.setup();
    render(<LensApp client={fastClient()} />);
    await waitFor(() => expect(screen.getByTestId('lens-area')).toHaveTextContent('га'));
    await user.type(screen.getByTestId('lens-claim-input'), '500');
    await user.selectOptions(screen.getByTestId('lens-year-end'), '2024');
    await user.click(screen.getByTestId('lens-run'));
    expect(await screen.findByTestId('lens-status-claim', {}, { timeout: 10_000 })).toHaveTextContent('НЕСОПОСТАВИМО');
    expect(screen.getByTestId('lens-claim-reasons')).toHaveTextContent('период');
    expect(screen.getByTestId('lens-q-value')).toHaveTextContent('395');
    expect(screen.getByTestId('lens-gap-value')).toHaveTextContent('—');
  }, 20_000);

  it('blocks an invalid period before sending the request', async () => {
    const user = userEvent.setup();
    render(<LensApp client={fastClient()} />);
    await waitFor(() => expect(screen.getByTestId('lens-area')).toHaveTextContent('га'));
    await user.selectOptions(screen.getByTestId('lens-year-start'), '2022');
    await user.selectOptions(screen.getByTestId('lens-year-end'), '2020');
    await user.click(screen.getByTestId('lens-run'));
    expect(screen.getByTestId('lens-validation-error')).toHaveTextContent('Конечный год должен быть больше начального');
    expect(screen.queryByTestId('lens-q-value')).toBeNull();
  }, 20_000);

  it('surfaces an adapter failure as an error state inside the workspace', async () => {
    const user = userEvent.setup();
    const client = fastClient();
    const failing = {
      ...client,
      submitAnalysis: async () => {
        throw new (await import('../src/lens/adapter')).LensError('SERVICE_UNAVAILABLE', 'Сервис расчёта недоступен');
      },
    };
    render(
      <RootErrorBoundary>
        <LensApp client={failing as never} />
      </RootErrorBoundary>,
    );
    await waitFor(() => expect(screen.getByTestId('lens-area')).toHaveTextContent('га'));
    await user.click(screen.getByTestId('lens-run'));
    const error = await screen.findByTestId('lens-error');
    expect(error).toHaveTextContent('SERVICE_UNAVAILABLE');
    expect(screen.queryByTestId('root-error-boundary')).toBeNull();
    expect(screen.getByTestId('lens-map')).toBeInTheDocument();
  }, 20_000);
});
