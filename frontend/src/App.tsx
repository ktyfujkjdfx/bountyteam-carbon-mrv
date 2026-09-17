import { useMemo, useState } from 'react';
import type { MrvApiClient } from './api/client';
import { switchAdapterHref, type AppConfig } from './api/config';
import { DEMO_ACTORS, type DemoActor } from './api/types';
import { HEALTH_MODE_META } from './domain/status';
import { useResource } from './hooks/useResource';
import { Dashboard } from './components/Dashboard';
import { Badge, Empty, ErrorNotice, Loading, StatusBadge } from './components/common';

interface Props {
  client: MrvApiClient;
  config: AppConfig;
}

export function App({ client, config }: Props) {
  const [actor, setActor] = useState<DemoActor>('issuer');
  const [selectedPlot, setSelectedPlot] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const health = useResource((signal) => client.getHealth({ signal }), [client, reloadKey]);
  const plots = useResource((signal) => client.listPlots({ signal }), [client, reloadKey]);

  const scope = useMemo(() => (config.adapter === 'http' ? `http:${config.baseUrl}` : 'fixture'), [config.adapter, config.baseUrl]);
  const plotId = selectedPlot ?? plots.data?.items[0]?.plot_id ?? null;
  const plotSummary = plots.data?.items.find((p) => p.plot_id === plotId) ?? null;
  const backendDown = health.error?.kind === 'network' || health.error?.kind === 'timeout' || plots.error?.kind === 'network';

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>BountyTeam MRV</h1>
          <span className="muted small">Прототип: наблюдение → решение → транзакция. Не сертификация и не расчёт углерода.</span>
        </div>
        <div className="topbar-badges" data-testid="mode-badges">
          <Badge tone={config.adapter === 'fixture' ? 'review' : 'info'} title="Источник данных UI">
            <span data-testid="adapter-mode">{config.adapter === 'fixture' ? 'FIXTURE ADAPTER (offline)' : 'BACKEND HTTP'}</span>
          </Badge>
          {health.data && <StatusBadge meta={HEALTH_MODE_META[health.data.mode]} testId="health-mode" />}
          {health.data && (
            <span className="health small" data-testid="health">
              api {health.data.api} · db {health.data.db} · worker {health.data.worker} · chain {health.data.chain}
            </span>
          )}
          <label className="actor-select">
            Demo-актор
            <select value={actor} onChange={(e) => setActor(e.target.value as DemoActor)} data-testid="actor-select">
              {DEMO_ACTORS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {config.adapter === 'fixture' ? (
        <div className="banner banner-fixture" role="note" data-testid="fixture-banner">
          <strong>Режим FIXTURE.</strong> Данные — SYNTHETIC golden fixtures (contracts-v1.0.0); Backend, RS и блокчейн эмулируются adapter-ом
          в браузере. Tx hashes, receipts и балансы не on-chain. <a href={switchAdapterHref('http', window.location)}>Переключить на Backend API</a>
        </div>
      ) : (
        <div className="banner banner-http" role="note">
          Backend API: <span className="mono">{config.baseUrl}</span>
          {!config.demoSession && <strong className="warn"> · VITE_DEMO_SESSION не задан — Backend вернёт 401</strong>}
        </div>
      )}
      {config.adapter === 'http' && health.data?.mode === 'CONTRACT_FIXTURE' && (
        <div className="banner banner-fixture" role="note" data-testid="mock-ledger-banner">
          <strong>Backend в режиме CONTRACT_FIXTURE.</strong> Chain = mock ledger Backend (chain {health.data.chain} относится к mock, не к
          блокчейну). Receipts, tx hashes и anchors — не on-chain доказательство.
        </div>
      )}

      {health.error && (
        <div className="banner-error">
          <ErrorNotice error={health.error} onRetry={() => setReloadKey((k) => k + 1)} title="Health недоступен" />
          {config.adapter === 'http' && (
            <p className="small">
              {backendDown ? 'Backend не отвечает.' : 'Backend отвечает не по контракту.'} Автоматического перехода на fixtures нет.{' '}
              <a href={switchAdapterHref('fixture', window.location)} data-testid="offline-fallback-link">
                Открыть offline fallback (FIXTURE, synthetic)
              </a>
            </p>
          )}
        </div>
      )}

      <main>
        <div className="plot-heading">
          {plots.loading && !plots.data && <Loading label="Загрузка участков…" />}
          {plots.error && !plots.data && <ErrorNotice error={plots.error} onRetry={() => setReloadKey((k) => k + 1)} />}
          {plots.data && plots.data.items.length === 0 && <Empty>Backend не вернул ни одного участка.</Empty>}
          {plots.data && plots.data.items.length > 0 && (
            <>
              <label>
                Участок{' '}
                <select value={plotId ?? ''} onChange={(e) => setSelectedPlot(e.target.value)} data-testid="plot-select">
                  {plots.data.items.map((p) => (
                    <option key={p.plot_id} value={p.plot_id}>
                      {p.name} ({p.plot_id})
                    </option>
                  ))}
                </select>
              </label>
              {plotSummary && <h2 data-testid="plot-name">{plotSummary.name}</h2>}
            </>
          )}
        </div>
        {plotId && (
          <Dashboard
            key={`${scope}|${plotId}`}
            client={client}
            scope={scope}
            plotId={plotId}
            actor={actor}
            demoAuthorizationId={config.demoAuthorizationId}
            ledger={client.kind === 'fixture' ? 'fixture' : health.data?.mode === 'CONTRACT_FIXTURE' ? 'mock' : health.data ? 'chain' : 'unknown'}
          />
        )}
      </main>
    </div>
  );
}
