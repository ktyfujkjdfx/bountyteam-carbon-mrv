import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import httpExamples from '../../fixtures/http_examples.json';
import type { MrvApiClient } from '../src/api/client';
import { ApiError } from '../src/api/errors';
import { createFixtureBackend } from '../src/api/fixtureAdapter';
import type { CreditBatch, Operation, Plot, Verification } from '../src/api/types';
import { ErrorNotice } from '../src/components/common';
import { CreditsPanel } from '../src/components/CreditsPanel';
import { EvidenceMap } from '../src/components/EvidenceMap';
import { EvidencePanel } from '../src/components/EvidencePanel';
import { ProofPanel } from '../src/components/ProofPanel';
import { StatusStrip } from '../src/components/StatusStrip';
import { App } from '../src/App';
import { resolveConfig } from '../src/api/config';

const example = <T,>(name: string): T => structuredClone(httpExamples.cases.find((c) => c.name === name)?.body) as T;
const fire = example<Verification>('verification_fire');
const insufficient = example<Verification>('verification_insufficient');
const plot = example<Plot>('plot');

const batch = (overrides: Partial<CreditBatch> = {}): CreditBatch => ({
  batch_id: '1',
  plot_id: 'SYNTHETIC-PLOT-001',
  seller: '0x00000000000000000000000000000000000000a1',
  actor: 'buyer',
  total_supply: '100',
  seller_balance: '90',
  actor_balance: '10',
  unit_price_wei: '1000000000000000',
  credit_status: 'ACTIVE',
  evidence_hash: fire.evidence_hash,
  decision_hash: fire.decision_hash,
  issued_at: '2026-09-17T10:00:00Z',
  frozen_at: null,
  last_observed_at: '2024-08-01T05:00:00Z',
  chain_state_checked_at: '2026-09-17T10:05:00Z',
  can_buy: true,
  can_transfer_backend: true,
  ...overrides,
});

const operation = (state: Operation['transaction_state']): Operation => ({
  operation_id: '40000000-0000-4000-8000-000000000009',
  kind: 'FREEZE',
  transaction_state: state,
  tx_hash: state === 'QUEUED' ? null : `0x${'1'.repeat(64)}`,
  batch_id: '1',
  error: null,
  receipt: null,
});

describe('StatusStrip', () => {
  it('shows outcome, quality, decision, operation and credit as distinct labelled layers', () => {
    render(<StatusStrip verification={fire} batch={batch()} operation={operation('SUBMITTED')} operationSource="Backend oracle" />);
    expect(within(screen.getByTestId('layer-outcome')).getByTestId('value-outcome')).toHaveTextContent('DISTURBANCE_DETECTED');
    expect(within(screen.getByTestId('layer-quality')).getByTestId('value-quality')).toHaveTextContent('SUFFICIENT');
    expect(within(screen.getByTestId('layer-decision')).getByTestId('value-decision')).toHaveTextContent('FREEZE_REQUESTED');
    expect(within(screen.getByTestId('layer-operation')).getByTestId('value-operation')).toHaveTextContent('SUBMITTED');
    expect(within(screen.getByTestId('layer-credit')).getByTestId('value-credit')).toHaveTextContent('ACTIVE');
    expect(screen.getByTestId('freeze-pending-note')).toBeVisible();
    expect(screen.getByTestId('layer-credit')).not.toHaveTextContent('FROZEN');
    expect(screen.getByTestId('layer-quality')).toHaveTextContent('не вероятность');
  });

  it('shows FROZEN only from the credit batch, never from decision', () => {
    const { rerender } = render(<StatusStrip verification={fire} batch={null} operation={null} operationSource={null} />);
    expect(screen.queryByText('FROZEN')).toBeNull();
    expect(screen.getByTestId('value-credit-none')).toBeVisible();
    rerender(<StatusStrip verification={fire} batch={batch({ credit_status: 'FROZEN' })} operation={operation('CONFIRMED')} operationSource={null} />);
    expect(screen.getByTestId('value-credit')).toHaveTextContent('FROZEN');
    expect(screen.getByTestId('value-credit')).toHaveAttribute('data-tone', 'blocked');
    expect(screen.getByTestId('value-decision')).toHaveAttribute('data-tone', 'alert');
  });

  it('insufficient evidence does not look like a violation', () => {
    render(<StatusStrip verification={insufficient} batch={null} operation={null} operationSource={null} />);
    expect(screen.getByTestId('value-outcome')).toHaveAttribute('data-tone', 'neutral');
    expect(screen.getByTestId('value-quality')).toHaveAttribute('data-tone', 'neutral');
    expect(screen.getByTestId('value-decision')).toHaveAttribute('data-tone', 'review');
  });
});

describe('ErrorNotice', () => {
  it.each([401, 403, 404, 409, 422, 503])('renders HTTP %i with code, request id and retry', async (status) => {
    const onRetry = vi.fn();
    render(<ErrorNotice error={new ApiError({ kind: 'http', status, code: 'X', message: 'm', requestId: 'req-1' })} onRetry={onRetry} />);
    const notice = screen.getByTestId('error-notice');
    expect(notice).toHaveTextContent(`HTTP ${status}`);
    expect(notice).toHaveTextContent('req-1');
    await userEvent.click(within(notice).getByRole('button', { name: 'Повторить' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('renders offline state for network errors', () => {
    render(<ErrorNotice error={new ApiError({ kind: 'network', message: 'Failed to fetch' })} />);
    expect(screen.getByTestId('error-notice')).toHaveTextContent('Backend недоступен');
  });
});

describe('EvidencePanel', () => {
  it('shows scene IDs, dates, units, EQS limits, FIRMS caveat and limitations', () => {
    render(<EvidencePanel verification={fire} />);
    expect(screen.getByText('SYNTHETIC_T1_fire')).toBeVisible();
    expect(screen.getByText('SYNTHETIC_T2_fire')).toBeVisible();
    expect(screen.getByTestId('affected-area')).toHaveTextContent('16 га');
    expect(screen.getByTestId('eqs-value')).toHaveTextContent('100 / 100');
    expect(screen.getByTestId('evidence-panel')).toHaveTextContent('Не вероятность');
    expect(screen.getByTestId('evidence-panel')).toHaveTextContent('не периметр');
    expect(screen.getByTestId('evidence-dataset-kind')).toHaveTextContent('SYNTHETIC');
    expect(screen.getByTestId('evidence-computation-mode')).toHaveTextContent('CACHED_REPLAY');
    expect(screen.getByTestId('limitations').children.length).toBe(fire.evidence.limitations.length);
  });

  it('insufficient evidence shows missing metrics as unknown, not zero', () => {
    render(<EvidencePanel verification={insufficient} />);
    expect(screen.getByTestId('affected-area')).toHaveTextContent('нет данных');
  });
});

describe('ProofPanel', () => {
  it('evidence without anchors shows no attributed anchor', async () => {
    const { client } = createFixtureBackend();
    const baseline = await client.getVerification('20000000-0000-4000-8000-000000000001');
    render(<ProofPanel client={client} verification={baseline} refreshKey={0} ledger="fixture" />);
    expect(await screen.findByTestId('no-anchors')).toHaveTextContent('не приписываются');
    expect(screen.getByTestId('proof-panel')).toHaveTextContent(baseline.evidence_hash);
  });

  it('shows a loading then error state with retry', async () => {
    const { client, controls } = createFixtureBackend();
    controls.failNext('getProof', { status: 503, code: 'DB', message: 'down' });
    const baseline = await client.getVerification('20000000-0000-4000-8000-000000000001');
    render(<ProofPanel client={client} verification={baseline} refreshKey={0} ledger="fixture" />);
    expect(screen.getByRole('status')).toHaveTextContent('Загрузка');
    const notice = await screen.findByTestId('error-notice');
    expect(notice).toHaveTextContent('HTTP 503');
    await userEvent.click(within(notice).getByRole('button', { name: 'Повторить' }));
    expect(await screen.findByTestId('no-anchors')).toBeVisible();
  });
});

function creditsProps(client: MrvApiClient, overrides: Partial<Parameters<typeof CreditsPanel>[0]> = {}) {
  return {
    client,
    scope: 'test',
    plot: { ...plot, can_issue: false, action_block_reason: null },
    actor: 'buyer' as const,
    credits: { items: [batch()] },
    creditsError: null,
    creditsLoading: false,
    onReloadCredits: vi.fn(),
    demoAuthorizationId: 'SYNTHETIC-AUTH-001',
    onChanged: vi.fn(),
    onOperation: vi.fn(),
    onRejected: vi.fn(),
    ledger: 'fixture' as const,
    ...overrides,
  };
}

describe('CreditsPanel', () => {
  it('FROZEN disables transfer and buy with an explanation that the contract enforces it', () => {
    const { client } = createFixtureBackend();
    render(
      <CreditsPanel
        {...creditsProps(client, {
          credits: { items: [batch({ credit_status: 'FROZEN', frozen_at: '2026-09-17T10:10:00Z', can_buy: false, can_transfer_backend: false })] },
        })}
      />,
    );
    expect(screen.getByTestId('transfer-submit')).toBeDisabled();
    expect(screen.getByTestId('buy-submit')).toBeDisabled();
    expect(screen.getByTestId('transfer-disabled-reason')).toHaveTextContent('смарт-контракт');
    expect(screen.getByTestId('frozen-explainer')).toHaveTextContent('не юридическое аннулирование');
  });

  it('even if Backend flags were inconsistent, FROZEN still disables the transfer button', () => {
    const { client } = createFixtureBackend();
    render(<CreditsPanel {...creditsProps(client, { credits: { items: [batch({ credit_status: 'FROZEN', can_transfer_backend: true })] } })} />);
    expect(screen.getByTestId('transfer-submit')).toBeDisabled();
  });

  it('prevents duplicate submission: rapid clicks send one request with one idempotency key', async () => {
    const buyCredits = vi.fn(
      () =>
        new Promise<{ operation_id: string; transaction_state: 'QUEUED'; status_url: string }>((resolve) =>
          setTimeout(() => resolve({ operation_id: 'op', transaction_state: 'QUEUED', status_url: '/api/v1/operations/op' }), 50),
        ),
    );
    const getOperation = vi.fn(async () => ({ ...operation('CONFIRMED'), kind: 'BUY' as const, receipt: {
      transaction_hash: `0x${'2'.repeat(64)}`, block_number: '5', status: 1 as const, event_names: ['Purchased'], state_readback_ok: true as const } }));
    const { client: base } = createFixtureBackend();
    const client = { ...base, buyCredits, getOperation } as MrvApiClient;
    const onChanged = vi.fn();
    render(<CreditsPanel {...creditsProps(client, { onChanged })} />);
    const button = screen.getByTestId('buy-submit');
    await act(async () => {
      button.click();
      button.click();
      button.click();
    });
    expect(button).toBeDisabled();
    await waitFor(() => expect(screen.getByTestId('op-state-buy')).toHaveTextContent('CONFIRMED'), { timeout: 5000 });
    expect(buyCredits).toHaveBeenCalledTimes(1);
    expect(onChanged).toHaveBeenCalled();
  });

  it('reuses the same idempotency key when retrying after a transient failure', async () => {
    const keys: string[] = [];
    let attempt = 0;
    const { client: base } = createFixtureBackend();
    const client = {
      ...base,
      buyCredits: vi.fn(async (_b: string, _a: string, _body: unknown, opts: { idempotencyKey: string }) => {
        keys.push(opts.idempotencyKey);
        attempt += 1;
        if (attempt === 1) throw new ApiError({ kind: 'network', message: 'offline' });
        return { operation_id: 'op', transaction_state: 'QUEUED' as const, status_url: '/api/v1/operations/op' };
      }),
      getOperation: vi.fn(async () => ({ ...operation('SUBMITTED'), kind: 'BUY' as const })),
    } as unknown as MrvApiClient;
    render(<CreditsPanel {...creditsProps(client)} />);
    await userEvent.click(screen.getByTestId('buy-submit'));
    expect(await screen.findByTestId('error-notice')).toHaveTextContent('Backend недоступен');
    await userEvent.click(screen.getByTestId('buy-submit'));
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[1]).toBe(keys[0]);
  });

  it('SUBMITTED is shown as pending, not as a final failure or success', async () => {
    const { client: base } = createFixtureBackend();
    const client = {
      ...base,
      buyCredits: vi.fn(async () => ({ operation_id: 'op', transaction_state: 'QUEUED' as const, status_url: '/api/v1/operations/op' })),
      getOperation: vi.fn(async () => ({ ...operation('SUBMITTED'), kind: 'BUY' as const })),
    } as unknown as MrvApiClient;
    render(<CreditsPanel {...creditsProps(client)} />);
    await userEvent.click(screen.getByTestId('buy-submit'));
    const state = await screen.findByTestId('op-state-buy');
    expect(state).toHaveTextContent('SUBMITTED');
    expect(screen.getByTestId('op-status-buy')).toHaveTextContent('не финальный результат');
    expect(screen.queryByTestId('error-notice')).toBeNull();
  });

  it('SUBMITTED with a Backend diagnostic error (RECEIPT_PENDING) stays pending, not failed', async () => {
    const { client: base } = createFixtureBackend();
    const client = {
      ...base,
      buyCredits: vi.fn(async () => ({ operation_id: 'op', transaction_state: 'QUEUED' as const, status_url: '/api/v1/operations/op' })),
      getOperation: vi.fn(async () => ({
        ...operation('SUBMITTED'),
        kind: 'BUY' as const,
        error: { code: 'RECEIPT_PENDING', message: 'receipt not yet available', details: {} },
      })),
    } as unknown as MrvApiClient;
    render(<CreditsPanel {...creditsProps(client)} />);
    await userEvent.click(screen.getByTestId('buy-submit'));
    expect(await screen.findByTestId('op-state-buy')).toHaveTextContent('SUBMITTED');
    expect(screen.getByTestId('op-state-buy')).toHaveAttribute('data-tone', 'info');
    expect(screen.getByTestId('op-status-buy')).toHaveTextContent('RECEIPT_PENDING');
    expect(screen.getByTestId('op-status-buy')).toHaveTextContent('не финальный результат');
    expect(screen.queryByTestId('error-notice')).toBeNull();
  });

  it('artifact integrity failure explains the hash mismatch instead of a generic 503', () => {
    render(<ErrorNotice error={new ApiError({ kind: 'http', status: 503, code: 'ARTIFACT_INTEGRITY_FAILED', message: 'Stored artifact failed its hash check' })} />);
    expect(screen.getByTestId('error-notice')).toHaveTextContent('SHA-256');
  });

  it('keeps last confirmed balances visible when a refresh fails', () => {
    const { client } = createFixtureBackend();
    render(<CreditsPanel {...creditsProps(client, { creditsError: new ApiError({ kind: 'network', message: 'offline' }) })} />);
    expect(screen.getByTestId('actor-balance')).toHaveTextContent('10');
    expect(screen.getByTestId('error-notice')).toHaveTextContent('показаны последние подтверждённые');
  });

  it('empty credits show an empty state', () => {
    const { client } = createFixtureBackend();
    render(<CreditsPanel {...creditsProps(client, { credits: { items: [] } })} />);
    expect(screen.getByTestId('credits-panel')).toHaveTextContent('Серий пока нет');
  });
});

describe('EvidenceMap', () => {
  it('renders plot boundary and independently toggleable layers only for present artifacts', async () => {
    const { client } = createFixtureBackend();
    const verification = await client.getVerification('20000000-0000-4000-8000-000000000001');
    render(<EvidenceMap client={client} plot={plot} verification={verification} />);
    expect(screen.getByTestId('evidence-map')).toBeInTheDocument();
    expect(within(screen.getByTestId('layer-toggle-boundary')).getByRole('checkbox')).toBeChecked();
    expect(within(screen.getByTestId('layer-toggle-firms')).getByRole('checkbox')).toBeDisabled();
    expect(within(screen.getByTestId('layer-toggle-dnbr')).getByRole('checkbox')).toBeDisabled();
    const affected = within(screen.getByTestId('layer-toggle-affected')).getByRole('checkbox');
    expect(affected).toBeEnabled();
    await userEvent.click(affected);
    expect(affected).not.toBeChecked();
    await waitFor(() => expect(document.querySelector('.leaflet-overlay-pane path')).not.toBeNull());
  });

  it('rejects swapped coordinates visibly', () => {
    const { client } = createFixtureBackend();
    const ring = (plot.geometry.coordinates[0] ?? []) as number[][];
    const swapped: Plot = {
      ...plot,
      geometry: { type: 'Polygon', coordinates: [ring.map(([lon, lat]) => [lat as number, lon as number])] },
    };
    render(<EvidenceMap client={client} plot={swapped} verification={null} />);
    expect(screen.getByTestId('geometry-error')).toHaveTextContent('перепутанный');
  });

  it('shows an artifact error state when a Backend artifact is missing', async () => {
    const { client } = createFixtureBackend();
    const verification = await client.getVerification('20000000-0000-4000-8000-000000000001');
    const broken: Verification = {
      ...verification,
      artifacts: verification.artifacts.map((a) => (a.role === 'AFFECTED_AREA' ? { ...a, url: '/api/v1/artifacts/does-not-exist' } : a)),
    };
    render(<EvidenceMap client={client} plot={plot} verification={broken} />);
    expect(await screen.findByText(/Артефакт недоступен/)).toBeVisible();
  });
});

describe('App on golden fixtures', () => {
  it('main flow: loading → baseline → issue CONFIRMED → post_fire FREEZE_REQUESTED (ACTIVE) → FROZEN', async () => {
    const { client } = createFixtureBackend({ timings: { jobQueuedMs: 20, jobRunningMs: 20, opQueuedMs: 20, opSubmittedMs: 150 } });
    const config = resolveConfig({}, '?api=fixture');
    render(<App client={client} config={config} />);
    expect(screen.getAllByRole('status')[0]).toHaveTextContent('Загрузка');
    expect(await screen.findByTestId('fixture-banner')).toHaveTextContent('SYNTHETIC');
    expect(await screen.findByTestId('value-decision')).toHaveTextContent('NO_RESTRICTION');
    expect(await screen.findByTestId('plot-area')).toHaveTextContent('100 га');

    await userEvent.click(screen.getByTestId('tab-credits'));
    await userEvent.click(await screen.findByTestId('issue-submit'));
    await waitFor(() => expect(screen.getByTestId('op-state-issue')).toHaveTextContent('CONFIRMED'), { timeout: 8000 });
    await waitFor(() => expect(screen.getByTestId('value-credit')).toHaveTextContent('ACTIVE'), { timeout: 8000 });

    await userEvent.click(screen.getByTestId('verify-post_fire'));
    await waitFor(() => expect(screen.getByTestId('value-decision')).toHaveTextContent('FREEZE_REQUESTED'), { timeout: 8000 });
    await waitFor(() => expect(screen.getByTestId('value-credit')).toHaveTextContent('FROZEN'), { timeout: 10_000 });
    await userEvent.selectOptions(screen.getByTestId('actor-select'), 'buyer');
    await waitFor(() => expect(screen.getByTestId('transfer-submit')).toBeDisabled());
  }, 30_000);

  it('offline Backend shows error + retry without fixture substitution', async () => {
    const { client, controls } = createFixtureBackend();
    controls.setOffline(true);
    const httpLike = { ...client, kind: 'http' } as MrvApiClient;
    render(<App client={httpLike} config={resolveConfig({ VITE_API_MODE: 'http' }, '')} />);
    const [firstNotice] = await screen.findAllByTestId('error-notice');
    if (!firstNotice) throw new Error('error notice expected');
    expect(firstNotice).toHaveTextContent('Backend недоступен');
    expect(screen.getByTestId('offline-fallback-link')).toHaveAttribute('href', expect.stringContaining('api=fixture'));
    expect(screen.queryByTestId('fixture-banner')).toBeNull();
    controls.setOffline(false);
    await userEvent.click(within(firstNotice).getByRole('button', { name: 'Повторить' }));
    expect(await screen.findByTestId('value-decision')).toHaveTextContent('NO_RESTRICTION');
  });

  it('HTTP Backend in CONTRACT_FIXTURE mode labels its mock ledger receipts as not on-chain', async () => {
    const { client } = createFixtureBackend({ timings: { jobQueuedMs: 0, jobRunningMs: 0, opQueuedMs: 0, opSubmittedMs: 0 } });
    const backend = { ...client, kind: 'http', getHealth: async () => ({ api: 'UP', db: 'UP', worker: 'UP', chain: 'UP', deployment_id: '09791e2a-c20a-436b-94f5-c1567da0eb23', mode: 'CONTRACT_FIXTURE' }) } as MrvApiClient;
    render(<App client={backend} config={resolveConfig({ VITE_API_MODE: 'http', VITE_DEMO_SESSION: 'x' }, '')} />);
    expect(await screen.findByTestId('mock-ledger-banner')).toHaveTextContent('не on-chain');
    expect(screen.queryByTestId('fixture-banner')).toBeNull();
    await userEvent.click(await screen.findByTestId('tab-credits'));
    expect(await screen.findByTestId('ledger-note')).toHaveAttribute('data-ledger', 'mock');
  });

  it('empty plot list shows empty state', async () => {
    const { client } = createFixtureBackend();
    const empty = { ...client, listPlots: async () => ({ items: [] }) } as MrvApiClient;
    render(<App client={empty} config={resolveConfig({}, '')} />);
    expect(await screen.findByText('Backend не вернул ни одного участка.')).toBeVisible();
  });
});
