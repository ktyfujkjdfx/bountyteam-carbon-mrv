import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { LensApp } from '../src/lens/LensApp';
import { Headline, headlineSentence } from '../src/lens/components/Headline';
import { ClaimStressTest } from '../src/lens/components/ClaimStressTest';
import { QualityRisks, riskCards } from '../src/lens/components/QualityRisks';
import { ValueCalculator } from '../src/lens/components/ValueCalculator';
import { ProjectionChart } from '../src/lens/components/ProjectionChart';
import { CellCard } from '../src/lens/components/CellCard';
import { createFixtureLensClient } from '../src/lens/fixtureClient';
import { resetSessionStore } from '../src/lens/sessionStore';
import { demoLogin } from '../src/lens/auth';
import { parsedAreas } from '../src/lens/data';
import { newSubmission, saveSubmissions } from '../src/lens/workspace';
import type { AnalysisResult } from '../src/lens/types';

const offline = { mode: 'fixture' as const, baseUrl: '/api/v2', source: 'url' as const, demoAccounts: true, authScheme: 'bearer' as const };

async function resultOf(scenario: string, body: Record<string, unknown> = {}): Promise<AnalysisResult> {
  const client = createFixtureLensClient({ queuedMs: 0, runningMs: 0 });
  const accepted = await client.createAnalysis({ aoi_id: 'RU_TVER_01', year_start: 2019, year_end: 2024, ...body }, { idempotencyKey: `k-${Math.random()}`, scenario });
  const analysis = await client.getAnalysis(accepted.analysis_id);
  if (!analysis.result) throw new Error('no result');
  return analysis.result;
}

describe('headline speaks plainly', () => {
  it('states the outcome for a positive, a zero and an unavailable result', async () => {
    expect(headlineSentence(await resultOf('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020 }))).toMatchObject({ tone: 'ok' });
    expect(headlineSentence(await resultOf('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020 })).text).toMatch(/подтверждено 395/);
    expect(headlineSentence(await resultOf('ZERO_UNCERTAINTY')).text).toMatch(/H\/R ≥ 1/);
    expect(headlineSentence(await resultOf('UNAVAILABLE_COVERAGE')).title).toMatch(/Недостаточно данных/);
  });

  it('shows four numbers and switches the scenario price', async () => {
    const user = userEvent.setup();
    const result = await resultOf('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020 });
    const onPrice = vi.fn();
    render(<Headline result={result} priceKey="base" onPriceKey={onPrice} customPrice={null} />);
    expect(screen.getByTestId('lens-q')).toHaveTextContent('395');
    expect(screen.getByTestId('lens-eproj')).toHaveTextContent('-689,3');
    expect(screen.getByTestId('lens-r')).toHaveTextContent('517');
    expect(screen.getByTestId('lens-value')).toHaveTextContent('592 500');
    await user.click(screen.getByTestId('lens-price-high'));
    expect(onPrice).toHaveBeenCalledWith('high');
  });
});

describe('claim stress test', () => {
  it('calls a zero claim absent, never supported', async () => {
    const result = await resultOf('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020, claimed_units: 0 });
    render(<ClaimStressTest result={result} priceKey="base" />);
    expect(screen.getByTestId('lens-claim-status')).toHaveTextContent('ПОЛОЖИТЕЛЬНОГО ЗАЯВЛЕНИЯ НЕТ');
    expect(screen.getByTestId('lens-claim-sentence')).toHaveTextContent('Положительное заявление отсутствует');
    expect(screen.queryByTestId('lens-claim-zero-warning')).toBeNull();
  });

  it('warns when a service still reports a zero claim as supported', async () => {
    const base = await resultOf('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020, claimed_units: 0 });
    const drifted: AnalysisResult = { ...base, claim: { ...base.claim, status: 'SUPPORTED_BY_CASE' } };
    render(<ClaimStressTest result={drifted} priceKey="base" />);
    expect(screen.getByTestId('lens-claim-zero-warning')).toHaveTextContent('не является подтверждённым');
  });

  it('shows the gap, its scenario value and the scope of the comparison', async () => {
    const result = await resultOf('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020, claimed_units: 1000 });
    render(<ClaimStressTest result={result} priceKey="base" />);
    expect(screen.getByTestId('lens-claim-status')).toHaveTextContent('ПОДТВЕРЖДЕНО ЧАСТИЧНО');
    expect(screen.getByTestId('lens-claim-gap')).toHaveTextContent('605');
    expect(screen.getByTestId('lens-claim-gap')).toHaveTextContent('907 500');
    expect(screen.getByTestId('lens-claim-share')).toHaveTextContent('40 %');
    expect(screen.getByTestId('lens-claim-scope')).toHaveTextContent('2019–2020');
    expect(screen.queryByText(/мошенничеств|greenwashing/i)).toBeNull();
  });

  it('explains an incomparable period instead of showing a gap', async () => {
    const result = await resultOf('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2024, claimed_units: 500 });
    render(<ClaimStressTest result={result} priceKey="base" />);
    expect(screen.getByTestId('lens-claim-status')).toHaveTextContent('СРАВНЕНИЕ НЕВОЗМОЖНО');
    expect(screen.getByTestId('lens-claim-reasons')).toHaveTextContent('другому периоду');
    expect(screen.getByTestId('lens-claim-gap')).toHaveTextContent('—');
  });
});

describe('quality and risks', () => {
  it('shows four coverage axes and keeps them apart', async () => {
    const result = await resultOf('WEAK_OPTICS_VALID_CCI', { year_start: 2021, year_end: 2022 });
    render(<QualityRisks result={result} />);
    expect(screen.getByTestId('lens-coverage-biomass_fraction')).toHaveTextContent('100 %');
    expect(screen.getByTestId('lens-coverage-optical_paired_valid_fraction')).toHaveTextContent('18 %');
    expect(screen.getByTestId('lens-coverage-uncertainty_fraction')).toBeVisible();
    expect(screen.getByTestId('lens-coverage-baseline_fraction')).toBeVisible();
    expect(screen.getByTestId('lens-warning-LOW_OPTICAL_PAIRED_VALID')).toHaveTextContent('ПРЕДУПРЕЖДЕНИЕ');
  });

  it('builds three independent risk cards from measured facts and no overall rating', async () => {
    const result = await resultOf('FIRE_SUPPORTED_LOSS', { aoi_id: 'RU_MORDOVIA_03', year_start: 2020, year_end: 2022 });
    const cards = riskCards(result);
    expect(cards.map((card) => card.id)).toEqual(['fire', 'forest-loss', 'data-quality']);
    render(<QualityRisks result={result} />);
    expect(screen.getByTestId('lens-risk-fire')).toHaveTextContent('признаком горения');
    expect(screen.getByTestId('lens-risk-forest-loss')).toHaveTextContent('га');
    expect(screen.getByText(/не сводятся в один рейтинг/)).toBeVisible();
    expect(screen.queryByText(/рейтинг A|инвестиционный рейтинг|INVESTABLE/i)).toBeNull();
  });

  it('names the interval a scenario range, not a confidence interval', async () => {
    const result = await resultOf('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020 });
    render(<QualityRisks result={result} />);
    expect(screen.getByTestId('lens-uncertainty')).toHaveTextContent('Сценарный диапазон');
    expect(screen.getByTestId('lens-uncertainty')).toHaveTextContent('не вероятностный доверительный интервал');
    expect(within(screen.getByTestId('lens-sensitivity')).getAllByRole('row').length).toBeGreaterThan(1);
  });
});

describe('value scenarios', () => {
  it('labels a custom price as the reader’s own scenario', async () => {
    const user = userEvent.setup();
    const result = await resultOf('DOC_EXAMPLE_Q395', { year_start: 2019, year_end: 2020 });
    const onCustom = vi.fn();
    render(<ValueCalculator result={result} priceKey="base" onPriceKey={vi.fn()} customPrice={null} onCustomPrice={onCustom} />);
    await user.type(screen.getByTestId('lens-custom-price'), '2000');
    expect(onCustom).toHaveBeenLastCalledWith(2000);
    expect(screen.getByTestId('lens-calculator-table')).toHaveTextContent('592 500');
  });

  it('shows zero roubles for q = 0 and no sum at all for q = null', async () => {
    const zero = await resultOf('ZERO_NON_POSITIVE');
    const { unmount } = render(<ValueCalculator result={zero} priceKey="base" onPriceKey={vi.fn()} customPrice={null} onCustomPrice={vi.fn()} />);
    expect(screen.getByTestId('lens-calculator-zero')).toBeVisible();
    unmount();

    const none = await resultOf('UNAVAILABLE_COVERAGE');
    render(<ValueCalculator result={none} priceKey="base" onPriceKey={vi.fn()} customPrice={null} onCustomPrice={vi.fn()} />);
    expect(screen.getByTestId('lens-calculator-unavailable')).toBeVisible();
    expect(screen.queryByTestId('lens-calculator-table')).toBeNull();
  });
});

describe('projection and cells', () => {
  it('separates observed years from the scenario baseline after them', async () => {
    const result = await resultOf('RECOVERY_AFTER_LOSS', { aoi_id: 'RU_MORDOVIA_04' });
    render(<ProjectionChart result={result} showProjection />);
    const table = screen.getByTestId('lens-timeline-table');
    expect(table).toHaveTextContent('наблюдение');
    expect(table).toHaveTextContent('сценарий');
    expect(screen.getByTestId('lens-projection-boundary')).toBeInTheDocument();
    expect(screen.getByTestId('lens-timeline')).toHaveTextContent('не прогноз фактического запаса');
  });

  it('hides the projection when the reader did not ask for it', async () => {
    const result = await resultOf('RECOVERY_AFTER_LOSS', { aoi_id: 'RU_MORDOVIA_04' });
    render(<ProjectionChart result={result} showProjection={false} />);
    expect(screen.queryByTestId('lens-projection-boundary')).toBeNull();
  });

  it('shows one cell with both dates and the modelling caveat', async () => {
    const result = await resultOf('FIRE_SUPPORTED_LOSS', { aoi_id: 'RU_MORDOVIA_03', year_start: 2020, year_end: 2022 });
    render(
      <CellCard
        result={result}
        cell={{ cell_id: 'RU_MORDOVIA_03:r0c0', zone_id: 'UNIT-ZONE-FIRE', valid: true, weight_ha: 12.5, carbon: { '2020': 47, '2022': 41.2 }, sd: { '2020': 3, '2022': 3 }, geometry: result.request.geometry }}
      />,
    );
    expect(screen.getByTestId('lens-cell-series')).toHaveTextContent('2020: 47');
    expect(screen.getByTestId('lens-cell-series')).toHaveTextContent('2022: 41,2');
    expect(screen.getByTestId('lens-cell-card')).toHaveTextContent('модельное допущение');
  });
});

describe('workspaces and guards', () => {
  it('signs in a demo owner and opens the owner workspace only', async () => {
    resetSessionStore(null);
    const user = userEvent.setup();
    render(<LensApp client={createFixtureLensClient({ queuedMs: 0, runningMs: 0 })} config={offline} />);
    await user.click(screen.getByTestId('lens-demo-account-owner'));
    await waitFor(() => expect(screen.getByTestId('lens-role')).toHaveTextContent('Владелец'));
    expect(screen.getByTestId('lens-request-form')).toBeVisible();
    expect(screen.queryByTestId('lens-queue-list')).toBeNull();
    expect(screen.queryByTestId('lens-run-analysis')).toBeNull();
    resetSessionStore(null);
  }, 20_000);

  it('keeps an investor out of the verifier screen with an explanation', async () => {
    resetSessionStore(demoLogin('investor@demo.local', 'demo'));
    window.location.hash = '#/verifier';
    render(<LensApp client={createFixtureLensClient({ queuedMs: 0, runningMs: 0 })} config={offline} />);
    await waitFor(() => expect(screen.getByTestId('lens-forbidden')).toBeVisible());
    expect(screen.getByTestId('lens-forbidden')).toHaveTextContent('решение принимает сервис');
    expect(screen.queryByTestId('lens-queue-list')).toBeNull();
    window.location.hash = '';
    resetSessionStore(null);
  }, 20_000);

  it('a verifier runs the analysis of a submitted request and finalises the passport', async () => {
    // The queue is filled by an owner; a verifier never creates a request of their own.
    const geometry = parsedAreas()[0]?.geometry;
    if (!geometry) throw new Error('no supplied areas');
    saveSubmissions([
      newSubmission({ owner_email: 'owner@demo.local', title: 'RU_TVER_01', aoi_id: 'RU_TVER_01', geometry, year_start: 2019, year_end: 2024, claimed_units: 3000 }),
    ]);
    resetSessionStore(demoLogin('verifier@demo.local', 'demo'));
    const user = userEvent.setup();
    render(<LensApp client={createFixtureLensClient({ queuedMs: 0, runningMs: 0 })} config={offline} />);
    await waitFor(() => expect(screen.getByTestId('lens-queue-list')).toBeVisible(), { timeout: 10_000 });
    expect(screen.queryByTestId('lens-claim-input')).toBeNull();
    await user.click(within(screen.getByTestId('lens-queue-list')).getAllByRole('button')[0] as HTMLElement);
    await user.click(screen.getByTestId('lens-run-analysis'));
    await waitFor(() => expect(screen.getByTestId('lens-q')).toBeVisible(), { timeout: 15_000 });
    await user.click(screen.getByTestId('lens-finalize'));
    expect(screen.getAllByTestId('lens-passport-status')[0]).toHaveTextContent('ФИНАЛИЗИРОВАН');
    resetSessionStore(null);
    sessionStorage.clear();
  }, 30_000);
});
