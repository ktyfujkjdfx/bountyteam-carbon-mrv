import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import httpExamples from '../../fixtures/http_examples.json';
import type { MrvApiClient } from '../src/api/client';
import { resolveConfig } from '../src/api/config';
import { createFixtureBackend } from '../src/api/fixtureAdapter';
import type { CreditBatch, History, Plot, Verification } from '../src/api/types';
import { App } from '../src/App';
import { CreditsPanel } from '../src/components/CreditsPanel';
import { EvidencePanel } from '../src/components/EvidencePanel';
import { ObservationsPanel } from '../src/components/ObservationsPanel';
import { RootErrorBoundary } from '../src/components/RootErrorBoundary';
import { StatusStrip } from '../src/components/StatusStrip';
import { StatusBadge } from '../src/components/common';
import {
  CREDIT_META,
  DECISION_META,
  OUTCOME_META,
  REASON_LABELS,
  UNKNOWN_VALUE_HINT,
  labelFor,
  metaFor,
  toneFor,
  type Tone,
} from '../src/domain/status';

// Mirrors the journal event tone table shape used by JournalPanel.
const KIND_TONE_FALLBACK_PROBE: Record<'VERIFICATION' | 'TX_CONFIRMED', Tone> = { VERIFICATION: 'neutral', TX_CONFIRMED: 'ok' };

// Wire data from a drifted Backend is not type-safe by definition; tests build it through JSON on purpose.
function drift<T>(value: T, patch: (raw: Record<string, unknown>) => void): T {
  const raw = JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
  patch(raw);
  return raw as unknown as T;
}

const example = <T,>(name: string): T => JSON.parse(JSON.stringify(httpExamples.cases.find((c) => c.name === name)?.body)) as T;
const fire = example<Verification>('verification_fire');
const plot = example<Plot>('plot');

const unknownFire = drift(fire, (raw) => {
  (raw.evidence as Record<string, unknown>).outcome = 'WILDFIRE_V2';
  raw.decision = 'ESCALATE_TO_AUDITOR';
  raw.reason = 'NEW_REASON_CODE';
  raw.evidence_quality = 'PARTIAL';
  ((raw.evidence as Record<string, unknown>).firms as Record<string, unknown>).support = 'PENDING_ARCHIVE';
  (raw.evidence as Record<string, unknown>).dataset_kind = 'SIMULATED';
  raw.computation_mode = 'STREAMED';
});

const batch: CreditBatch = {
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
  can_buy: false,
  can_transfer_backend: false,
};
const unknownBatch = drift(batch, (raw) => {
  raw.credit_status = 'SUSPENDED_PENDING_REVIEW';
});

function expectUnknownBadge(element: HTMLElement, received: string) {
  expect(element).toHaveAttribute('data-tone', 'neutral');
  expect(element).toHaveAttribute('data-unknown', 'true');
  expect(element).toHaveTextContent(`Неизвестное значение: ${received}`);
  expect(element).toHaveAttribute('title', UNKNOWN_VALUE_HINT);
}

describe('safe status accessor', () => {
  it('returns known metadata unchanged', () => {
    expect(metaFor(CREDIT_META, 'FROZEN')).toBe(CREDIT_META.FROZEN);
    expect(metaFor(OUTCOME_META, 'NO_CHANGE')).toBe(OUTCOME_META.NO_CHANGE);
  });

  it.each([
    ['unknown string', 'SUSPENDED', 'Неизвестное значение: SUSPENDED'],
    ['null', null, 'Неизвестное значение: —'],
    ['undefined', undefined, 'Неизвестное значение: —'],
    ['empty string', '', 'Неизвестное значение: —'],
    ['number', 42, 'Неизвестное значение: 42'],
    ['object', { state: 'FROZEN' }, 'Неизвестное значение: UNKNOWN'],
    ['prototype key', 'toString', 'Неизвестное значение: toString'],
    ['__proto__', '__proto__', 'Неизвестное значение: __proto__'],
  ])('%s → neutral fallback, never undefined', (_name, value, label) => {
    const meta = metaFor(CREDIT_META, value);
    expect(meta).toEqual({ label, tone: 'neutral', hint: UNKNOWN_VALUE_HINT, unknown: true });
    expect(meta.label).not.toMatch(/undefined|null|\[object/);
  });

  it('does not present an unknown value as ACTIVE, FROZEN, FAILED or VERIFIED', () => {
    for (const value of ['ACTIVE ', 'frozen', 'FAILED_V2', 'VERIFIED']) {
      const meta = metaFor(CREDIT_META, value);
      expect(meta.tone).toBe('neutral');
      expect(meta.label.startsWith('Неизвестное значение: ')).toBe(true);
    }
  });

  it('truncates very long received values', () => {
    expect(metaFor(DECISION_META, 'X'.repeat(500)).label.length).toBeLessThan(80);
  });

  it('labels and tones fall back safely', () => {
    expect(labelFor(REASON_LABELS, 'FIRE_REVERSAL')).toBe(REASON_LABELS.FIRE_REVERSAL);
    expect(labelFor(REASON_LABELS, 'NEW_CODE')).toBe('Неизвестное значение: NEW_CODE');
    expect(labelFor(REASON_LABELS, undefined)).toBe('Неизвестное значение: —');
    expect(toneFor(KIND_TONE_FALLBACK_PROBE, 'TX_REPLACED')).toBe('neutral');
    expect(toneFor(KIND_TONE_FALLBACK_PROBE, 'TX_CONFIRMED')).toBe('ok');
  });

  it('StatusBadge renders a neutral UNKNOWN badge even for missing metadata', () => {
    render(<StatusBadge meta={undefined} testId="badge" />);
    expectUnknownBadge(screen.getByTestId('badge'), '—');
  });
});

describe('components with contract drift', () => {
  it('StatusStrip shows unknown outcome, quality, decision and credit as neutral with the drift explanation', () => {
    render(<StatusStrip verification={unknownFire} batch={unknownBatch} operation={null} operationSource={null} />);
    expectUnknownBadge(screen.getByTestId('value-outcome'), 'WILDFIRE_V2');
    expectUnknownBadge(screen.getByTestId('value-quality'), 'PARTIAL');
    expectUnknownBadge(screen.getByTestId('value-decision'), 'ESCALATE_TO_AUDITOR');
    expectUnknownBadge(screen.getByTestId('value-credit'), 'SUSPENDED_PENDING_REVIEW');
    expect(screen.getByTestId('layer-decision')).toHaveTextContent('Неизвестное значение: NEW_REASON_CODE');
    expect(screen.getAllByTestId('unknown-value-note').length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText('FROZEN')).toBeNull();
  });

  it('EvidencePanel renders with unknown outcome, decision, reason, FIRMS support and modes', () => {
    render(<EvidencePanel verification={unknownFire} />);
    const panel = screen.getByTestId('evidence-panel');
    expect(panel).toHaveTextContent('Неизвестное значение: WILDFIRE_V2');
    expect(panel).toHaveTextContent('Неизвестное значение: ESCALATE_TO_AUDITOR');
    expect(panel).toHaveTextContent('Неизвестное значение: NEW_REASON_CODE');
    expectUnknownBadge(screen.getByTestId('firms-support'), 'PENDING_ARCHIVE');
    expectUnknownBadge(screen.getByTestId('evidence-dataset-kind'), 'SIMULATED');
    expectUnknownBadge(screen.getByTestId('evidence-computation-mode'), 'STREAMED');
    expect(screen.getByTestId('limitations').children.length).toBe(fire.evidence.limitations.length);
  });

  it('CreditsPanel keeps balances and actions visible for an unknown credit_status and never treats it as FROZEN', () => {
    const { client } = createFixtureBackend();
    render(
      <CreditsPanel
        client={client}
        scope="t"
        plot={{ ...plot, can_issue: false }}
        actor="buyer"
        credits={{ items: [unknownBatch] }}
        creditsError={null}
        creditsLoading={false}
        onReloadCredits={vi.fn()}
        demoAuthorizationId="SYNTHETIC-AUTH-001"
        onChanged={vi.fn()}
        onOperation={vi.fn()}
        onRejected={vi.fn()}
        ledger="mock"
      />,
    );
    expectUnknownBadge(screen.getByTestId('batch-credit-status'), 'SUSPENDED_PENDING_REVIEW');
    expect(screen.getByTestId('actor-balance')).toHaveTextContent('10');
    expect(screen.getByTestId('seller-balance')).toHaveTextContent('90');
    expect(screen.getByTestId('unknown-value-note')).toHaveTextContent(UNKNOWN_VALUE_HINT);
    expect(screen.queryByTestId('frozen-explainer')).toBeNull();
    expect(screen.getByTestId('transfer-submit')).toBeDisabled();
  });

  it('ObservationsPanel history renders unknown outcome, quality and decision', () => {
    const { client } = createFixtureBackend();
    const history = drift<History>(example<History>('history'), (raw) => {
      const item = (raw.items as Array<Record<string, unknown>>)[0];
      if (item) {
        item.outcome = 'WILDFIRE_V2';
        item.evidence_quality = null;
        item.decision = undefined;
      }
    });
    render(
      <ObservationsPanel
        client={client}
        scope="t"
        plotId="SYNTHETIC-PLOT-001"
        actor="issuer"
        history={history}
        historyError={null}
        historyLoading={false}
        onReloadHistory={vi.fn()}
        selectedId={null}
        onSelect={vi.fn()}
        onJobSucceeded={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    const list = screen.getByTestId('history');
    expect(list).toHaveTextContent('Неизвестное значение: WILDFIRE_V2');
    expect(within(list).getAllByText('Неизвестное значение: —')).toHaveLength(2);
    expect(list.textContent).not.toMatch(/undefined|null/);
  });
});

describe('App with a drifted Backend', () => {
  it('keeps map, balances, proof and journal rendered when credits, verification and history carry unknown enums', async () => {
    const { client } = createFixtureBackend({ timings: { jobQueuedMs: 0, jobRunningMs: 0, opQueuedMs: 0, opSubmittedMs: 0 } });
    const drifted: MrvApiClient = {
      ...client,
      kind: 'http',
      getHealth: async () => drift(await client.getHealth(), (raw) => {
        raw.mode = 'STAGING_V2';
      }),
      getCredits: async () => ({ items: [unknownBatch] }),
      getVerification: async (id, opts) =>
        drift(await client.getVerification(id, opts), (raw) => {
          (raw.evidence as Record<string, unknown>).outcome = 'WILDFIRE_V2';
          raw.decision = 'ESCALATE_TO_AUDITOR';
        }),
      getHistory: async (plotId, opts) =>
        drift(await client.getHistory(plotId, opts), (raw) => {
          for (const item of raw.items as Array<Record<string, unknown>>) item.decision = 'ESCALATE_TO_AUDITOR';
        }),
    };
    const onError = vi.fn();
    window.addEventListener('error', onError);
    const { container } = render(
      <RootErrorBoundary>
        <App client={drifted} config={resolveConfig({ VITE_API_MODE: 'http', VITE_DEMO_SESSION: 'x' }, '')} />
      </RootErrorBoundary>,
    );

    expectUnknownBadge(await screen.findByTestId('value-credit'), 'SUSPENDED_PENDING_REVIEW');
    await waitFor(() => expectUnknownBadge(screen.getByTestId('value-outcome'), 'WILDFIRE_V2'));
    expectUnknownBadge(screen.getByTestId('value-decision'), 'ESCALATE_TO_AUDITOR');
    expectUnknownBadge(screen.getByTestId('health-mode'), 'STAGING_V2');
    expect(screen.getByTestId('evidence-map')).toBeInTheDocument();
    expect(screen.getByTestId('journal')).toBeInTheDocument();
    expect(screen.getByTestId('history')).toHaveTextContent('Неизвестное значение: ESCALATE_TO_AUDITOR');

    await userEvent.click(screen.getByTestId('tab-credits'));
    expect(await screen.findByTestId('actor-balance')).toHaveTextContent('10');
    await userEvent.click(screen.getByTestId('tab-proof'));
    expect(await screen.findByTestId('proof-panel')).toBeInTheDocument();

    expect(screen.queryByTestId('root-error-boundary')).toBeNull();
    expect(container.textContent?.length ?? 0).toBeGreaterThan(0);
    expect(onError).not.toHaveBeenCalled();
    window.removeEventListener('error', onError);
  });
});

describe('RootErrorBoundary', () => {
  function Bomb({ explode }: { explode: boolean }) {
    if (explode) throw new Error('Synthetic render failure\n    at stack line that must stay hidden');
    return <p data-testid="recovered">Интерфейс восстановлен</p>;
  }

  it('shows recovery UI with reload and recover instead of an empty root', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const onReload = vi.fn();
    let setExplode: (value: boolean) => void = () => undefined;
    function Harness() {
      const [explode, set] = useState(true);
      setExplode = set;
      return (
        <RootErrorBoundary onReload={onReload}>
          <Bomb explode={explode} />
        </RootErrorBoundary>
      );
    }
    const { container } = render(<Harness />);

    const fallback = screen.getByTestId('root-error-boundary');
    expect(fallback).toHaveAttribute('role', 'alert');
    expect(fallback).toHaveTextContent('Интерфейс не смог отобразить данные');
    expect(screen.getByTestId('root-error-message')).toHaveTextContent('Synthetic render failure');
    expect(fallback).not.toHaveTextContent('stack line');
    expect(container.innerHTML).not.toBe('');

    await userEvent.click(screen.getByTestId('root-error-reload'));
    expect(onReload).toHaveBeenCalledOnce();

    setExplode(false);
    await userEvent.click(screen.getByTestId('root-error-recover'));
    expect(await screen.findByTestId('recovered')).toBeInTheDocument();
  });
});
