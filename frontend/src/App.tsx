import { useMemo, useRef, useState } from 'react';
import type { MrvApiClient } from './api/client';
import { switchAdapterHref, type AppConfig } from './api/config';
import { DEMO_ACTORS, type DemoActor, type Health } from './api/types';
import { HEALTH_MODE_META, metaFor } from './domain/status';
import { useResource } from './hooks/useResource';
import { Dashboard, type LedgerKind } from './components/Dashboard';
import { MethodologyDialog } from './components/MethodologyDialog';
import { Empty, ErrorNotice, Skeleton, StatusBadge } from './components/common';

interface Props {
  client: MrvApiClient;
  config: AppConfig;
}

function ledgerKind(client: MrvApiClient, health: Health | null): LedgerKind {
  if (client.kind === 'fixture') return 'fixture';
  if (!health) return 'unknown';
  return health.mode === 'CONTRACT_FIXTURE' ? 'mock' : 'chain';
}

function SystemHealth({ health, ledger }: { health: Health; ledger: LedgerKind }) {
  const items: Array<[string, Health['api']]> = [
    ['API', health.api],
    ['DB', health.db],
    ['WORKER', health.worker],
    [ledger === 'mock' ? 'LEDGER·MOCK' : ledger === 'fixture' ? 'LEDGER·EMU' : 'CHAIN', health.chain],
  ];
  return (
    <div className="system-health" data-testid="health" aria-label="Состояние сервисов Backend">
      {items.map(([name, state]) => (
        <span key={name} data-state={state}>
          {name} <b>{state}</b>
        </span>
      ))}
    </div>
  );
}

export function App({ client, config }: Props) {
  const [actor, setActor] = useState<DemoActor>('issuer');
  const [selectedPlot, setSelectedPlot] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const methodologyRef = useRef<HTMLDialogElement | null>(null);

  const health = useResource((signal) => client.getHealth({ signal }), [client, reloadKey]);
  const plots = useResource((signal) => client.listPlots({ signal }), [client, reloadKey]);

  const scope = useMemo(() => (config.adapter === 'http' ? `http:${config.baseUrl}` : 'fixture'), [config.adapter, config.baseUrl]);
  const plotId = selectedPlot ?? plots.data?.items[0]?.plot_id ?? null;
  const backendDown = health.error?.kind === 'network' || health.error?.kind === 'timeout' || plots.error?.kind === 'network';
  const ledger = ledgerKind(client, health.data);
  const reload = () => setReloadKey((k) => k + 1);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">BOUNTYTEAM</span>
          <span className="brand-descriptor">Forest carbon MRV</span>
        </div>
        <nav className="topnav" aria-label="Разделы">
          <button type="button" className="topnav-item" aria-current="page">
            Мониторинг
          </button>
          <button type="button" className="topnav-item" onClick={() => methodologyRef.current?.showModal()} data-testid="open-methodology">
            Методология
          </button>
          <a className="topnav-item" href="/lens" data-testid="open-lens">
            Открыть Carbon Lens
          </a>
        </nav>
        <div className="topbar-right" data-testid="mode-badges">
          {health.data && <SystemHealth health={health.data} ledger={ledger} />}
          {health.data && <StatusBadge meta={metaFor(HEALTH_MODE_META, health.data.mode)} testId="health-mode" />}
          <label className="field-inline">
            Demo-актор
            <select className="select" value={actor} onChange={(e) => setActor(e.target.value as DemoActor)} data-testid="actor-select">
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
        <div className="source-bar tone-review-bar" role="note" data-testid="fixture-banner">
          <span className="dot" aria-hidden="true" />
          <strong data-testid="adapter-mode">Демонстрация без сервиса</strong>
          <span>
            Все числа на этом экране — заранее заготовленные синтетические примеры (SYNTHETIC): сервис, спутниковый расчёт и журнал
            операций изображаются в браузере. Это не блокчейн и не реальные операции.
          </span>
          <a href={switchAdapterHref('http', window.location)}>Подключиться к сервису</a>
        </div>
      ) : (
        <div className={`source-bar${health.data?.mode === 'CONTRACT_FIXTURE' ? ' tone-review-bar' : ''}`} role="note">
          <strong data-testid="adapter-mode">Работает сервис</strong>
          {!config.demoSession && <span className="warn">Не задан ключ сеанса: сервис ответит «нужен вход» (401).</span>}
          {health.data?.mode === 'CONTRACT_FIXTURE' && (
            <span data-testid="mock-ledger-banner">
              Блокчейн не подключён: операции записываются во внутренний журнал сервиса, а не в сеть. Номера транзакций и подтверждения на
              этом экране — демонстрационные, доказательством в блокчейне они не являются.
            </span>
          )}
          <details className="lens-tech">
            <summary>Технические подробности</summary>
            <div className="lens-tech-body mono small">
              {config.baseUrl}
              {health.data?.mode ? ` · режим ${health.data.mode}` : ''}
            </div>
          </details>
        </div>
      )}

      {health.error && (
        <div className="banner-error">
          <ErrorNotice error={health.error} onRetry={reload} title={backendDown ? 'Сервис недоступен' : 'Сервис не сообщил о своём состоянии'} />
          {config.adapter === 'http' && (
            <p className="small muted">
              {backendDown ? 'Сервис не отвечает.' : 'Сервис ответил не так, как описано в контракте.'} Сами собой примеры вместо ответа
              сервиса не подставляются.{' '}
              <a href={switchAdapterHref('fixture', window.location)} data-testid="offline-fallback-link">
                Открыть демонстрацию без сервиса
              </a>
            </p>
          )}
        </div>
      )}

      <main id="main">
        {plots.loading && !plots.data && <Skeleton label="Загрузка участков мониторинга…" height={120} />}
        {plots.error && !plots.data && (
          <ErrorNotice error={plots.error} onRetry={reload} title={backendDown ? 'Сервис недоступен' : 'Список участков недоступен'} />
        )}
        {plots.data && plots.data.items.length === 0 && (
          <Empty>
            <strong>Нет участков мониторинга</strong>
            <span>Backend не вернул ни одного участка.</span>
          </Empty>
        )}
        {plotId && plots.data && (
          <Dashboard
            key={`${scope}|${plotId}`}
            client={client}
            scope={scope}
            plotId={plotId}
            plots={plots.data.items}
            onSelectPlot={setSelectedPlot}
            actor={actor}
            demoAuthorizationId={config.demoAuthorizationId}
            ledger={ledger}
          />
        )}
      </main>
      <MethodologyDialog ref={methodologyRef} />
    </div>
  );
}
